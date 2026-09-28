"""PyWebView-facing facade for persisted Seedream image-generation batches."""

from __future__ import annotations

import base64
import binascii
import json
import os
import shutil
from io import BytesIO
from statistics import median
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import quote

import webview
from PIL import Image, ImageOps

from backend.image_layout import (
    delete_edit_source,
    delete_generation_layout,
    edit_source_path,
    write_generation_layout,
)
from backend.platform.client import PlatformClient, PlatformError, PlatformUnauthorizedError
from backend.platform.config import PlatformConfig
from backend.platform.downloads import PlatformArtifactTransport
from backend.platform.images import PlatformImageClient
from backend.seedream.client import ArkAPIError, ArkClient, SubmissionUnknownError
from backend.seedream.downloader import ImageDownloader
from backend.seedream.manager import PLATFORM_SOURCE, SeedreamBatchManager
from backend.seedream.media import SeedreamMediaResolver
from backend.seedream.models import MODEL_CAPABILITIES, SeedreamRequest, platform_model_id
from backend.seedream.repository import BatchRepository
from src.utils.ai_cache_paths import ai_pic_cache_root
from backend.seedream.validation import ValidationError, _ALLOWED_RATIOS, validate_request
from src.utils.app_config import load_app_config, save_app_config

_DEFAULT_MODEL = "pro"
# 平台定价尺寸档（客户端用 1K/1.5K/2K 展示，下发前转小写）
_PLATFORM_SIZES = ("1K", "1.5K", "2K")
_DEFAULT_RESOLUTION = "1K"
_DEFAULT_RATIO = "16:9"
_DEFAULT_COUNT = 2

_IMAGE_FILE_TYPES = ("JPEG image (*.jpg;*.jpeg)",)
_REFERENCE_FILE_TYPES = (
    "Image files (*.jpg;*.jpeg;*.png;*.webp;*.bmp;*.tif;*.tiff;*.gif;*.heic;*.heif)",
)


class SeedreamAPI:
    """Convert PyWebView input/output to the Seedream domain's safe public contract."""

    def __init__(
        self,
        manager: SeedreamBatchManager | None = None,
        *,
        window_getter: Callable[[], Any | None] | None = None,
        client_factory: Callable[[str], ArkClient] = ArkClient,
        media_base_url: str = "http://localhost:8080",
        media_resolver: SeedreamMediaResolver | None = None,
        platform_config: PlatformConfig | None = None,
    ) -> None:
        self._window_getter = window_getter or self._active_window
        self._client_factory = client_factory
        self._media_base_url = media_base_url.rstrip("/")
        self._manager = manager
        self._external_manager = manager is not None
        self._media_resolver = media_resolver
        self._platform_config = platform_config
        self._platform_client: PlatformClient | None = None
        self._window = None
        self._started = False

    def update_platform(self, base_url: str, token: str | None) -> None:
        """Refresh platform base URL/token (see SeedanceAPI.update_platform)."""
        if self._platform_config is None:
            return
        old_base = self._platform_client.base_url if self._platform_client is not None else None
        self._platform_config.set(base_url, token)
        if self._platform_client is None:
            if self._platform_config.configured():
                self._platform_client = self._platform_config.client()
                self._refresh_manager_platform()
            return
        if (base_url or "").rstrip("/") != old_base:
            if self._platform_config.configured():
                self._platform_client = self._platform_config.client()
            self._refresh_manager_platform()
            return
        self._platform_client.set_token(token)

    def _refresh_manager_platform(self) -> None:
        """Attach platform support to an already-created manager (post-login)."""
        if self._manager is None or self._manager._platform is not None:
            return
        if self._platform_client is None:
            return
        self._manager = SeedreamBatchManager(
            self._manager._client,
            self._manager._repository,
            ImageDownloader(self._manager._repository, PlatformArtifactTransport(self._platform_client)),
            platform=PlatformImageClient(self._platform_client),
        )
        self._media_resolver = None
        if self._window is not None:
            self._manager.set_event_sink(self._dispatch_batch_update)

    def set_media_base_url(self, media_base_url: str) -> None:
        self._media_base_url = media_base_url.rstrip("/")

    @property
    def media_resolver(self) -> SeedreamMediaResolver:
        self._ensure_manager()
        assert self._media_resolver is not None
        return self._media_resolver

    def set_window(self, window: Any) -> None:
        """Attach the event sink before starting generation."""
        self._window = window
        manager = self._ensure_manager()
        if not self._started:
            # Recover leftover active attempts from an unclean shutdown before any
            # event sink is attached, so the frontend sees terminal states.
            manager.reclassify_interrupted_attempts()
            self._started = True
        manager.set_event_sink(self._dispatch_batch_update)

    def shutdown(self) -> None:
        if self._manager is not None:
            self._manager.set_event_sink(None)
        self._started = False

    def select_image_file(self) -> str | None:
        window = self._window or self._window_getter()
        if window is None:
            return None
        result = window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=_REFERENCE_FILE_TYPES,
        )
        return result[0] if result else None

    def create_batch(self, request_data: dict[str, Any], source: str = "api-key") -> dict[str, Any]:
        try:
            request = SeedreamRequest.from_dict({**request_data, "source": source})
            validate_request(request)
            if request.source == PLATFORM_SOURCE:
                self._require_platform()
            else:
                self._require_api_key()
            batch = self._ensure_manager().create_batch(request)
            return {"success": True, "batch": self._decorate_batch(batch)}
        except Exception as error:
            return self._error_response(error)

    def get_batch(self, local_id: str) -> dict[str, Any]:
        try:
            return {"success": True, "batch": self._decorate_batch(self._ensure_manager().get_batch(local_id))}
        except Exception as error:
            return self._error_response(error)

    def list_batches(self) -> dict[str, Any]:
        try:
            batches = [self._decorate_batch(batch) for batch in self._ensure_manager().list_batches()]
            return {"success": True, "batches": batches}
        except Exception as error:
            return self._error_response(error)

    def save_image(self, local_id: str, attempt_index: int = 0) -> dict[str, Any]:
        try:
            source = self.media_resolver.resolve(local_id, "image", attempt_index)
            window = self._window or self._window_getter()
            if window is None:
                raise RuntimeError("The application window is not available")
            result = window.create_file_dialog(
                webview.FileDialog.SAVE,
                save_filename=f"seedream-{local_id[:8]}-{attempt_index}.jpg",
                file_types=_IMAGE_FILE_TYPES,
            )
            if not result:
                return {"success": True, "data": {"saved": False}}
            destination = Path(result[0])
            shutil.copy2(source, destination)
            return {"success": True, "data": {"saved": True, "path": str(destination)}}
        except Exception as error:
            return self._error_response(error)

    def resize_character(
        self,
        local_id: str,
        attempt_index: int,
        top: int,
        bottom: int,
        target_height: int,
        bottom_distance: int | None = None,
    ) -> dict[str, Any]:
        """Scale a candidate image from a measured character height and pad it back to its canvas size."""
        try:
            source = self.media_resolver.resolve(local_id, "image", attempt_index)
            with Image.open(source) as opened:
                image_format = opened.format or "PNG"
                image = ImageOps.exif_transpose(opened).copy()

            width, height = image.size
            if not all(isinstance(value, int) and not isinstance(value, bool) for value in (top, bottom, target_height)):
                raise ValueError("Character bounds and target height must be integer pixels")
            if top < 0 or bottom > height or top >= bottom:
                raise ValueError("Character bounds must be inside the image")
            measured_height = bottom - top
            if target_height <= 0 or target_height >= measured_height:
                raise ValueError("Target height must be smaller than the measured character height")
            if bottom_distance is None:
                bottom_distance = height - bottom
            if not isinstance(bottom_distance, int) or isinstance(bottom_distance, bool):
                raise ValueError("Bottom distance must be an integer pixel value")
            if bottom_distance < 0 or bottom_distance + target_height > height:
                raise ValueError("Bottom distance places the character outside the image")

            scale = target_height / measured_height
            resized_size = (
                max(1, round(width * scale)),
                max(1, round(height * scale)),
            )
            background_color = self._corner_background_color(image)
            output_mode = "RGBA" if image.mode == "RGBA" else "RGB"
            working = image.convert(output_mode)
            resized = working.resize(resized_size, Image.Resampling.LANCZOS)
            fill = (*background_color, 255) if output_mode == "RGBA" else background_color
            canvas = Image.new(output_mode, (width, height), fill)
            target_bottom = height - bottom_distance
            offset = ((width - resized.width) // 2, round(target_bottom - bottom * scale))
            canvas.paste(resized, offset, resized if output_mode == "RGBA" else None)

            backup = source.with_name(f"{source.stem}.original{source.suffix}")
            if not backup.exists():
                shutil.copy2(source, backup)
            temporary = source.with_name(f".{source.name}.resize.tmp")
            save_options = {"quality": 95} if image_format.upper() in {"JPEG", "JPG"} else {}
            canvas.save(temporary, format=image_format, **save_options)
            os.replace(temporary, source)

            generation_layout = write_generation_layout(source, {
                "source_width": width,
                "source_height": height,
                "measured_top": top,
                "measured_bottom": bottom,
                "measured_height": measured_height,
                "target_height": target_height,
                "character_height_ratio": target_height / height,
                "bottom_distance": bottom_distance,
                "bottom_margin_ratio": bottom_distance / height,
                "scale": scale,
            }, width=width, height=height)

            return {
                "success": True,
                "data": {
                    "width": width,
                    "height": height,
                    "measured_height": measured_height,
                    "target_height": target_height,
                    "bottom_distance": bottom_distance,
                    "scale": scale,
                    "background_color": list(background_color),
                    "generation_layout": generation_layout,
                },
            }
        except Exception as error:
            return self._error_response(error)

    def restore_character(self, local_id: str, attempt_index: int) -> dict[str, Any]:
        """Restore the untouched candidate image saved before the first character resize."""
        try:
            source = self.media_resolver.resolve(local_id, "image", attempt_index)
            backup = source.with_name(f"{source.stem}.original{source.suffix}")
            if not backup.is_file():
                raise FileNotFoundError("Original candidate image backup is not available")
            temporary = source.with_name(f".{source.name}.restore.tmp")
            shutil.copy2(backup, temporary)
            os.replace(temporary, source)
            delete_generation_layout(source)
            delete_edit_source(source)
            with Image.open(source) as restored:
                width, height = restored.size
            return {"success": True, "data": {"restored": True, "width": width, "height": height}}
        except Exception as error:
            return self._error_response(error)

    def apply_eraser(
        self,
        local_id: str,
        attempt_index: int,
        image_data_url: str,
        edit_source_data_url: str,
        generation_layout: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist a same-size canvas edited by the background-color eraser."""
        try:
            prefix = "data:image/png;base64,"
            if not isinstance(image_data_url, str) or not image_data_url.startswith(prefix):
                raise ValueError("Edited image must be a PNG data URL")
            if not isinstance(edit_source_data_url, str) or not edit_source_data_url.startswith(prefix):
                raise ValueError("Edit source must be a PNG data URL")

            def decode_data_url(value: str, label: str) -> bytes:
                encoded = value[len(prefix):]
                if len(encoded) > 64 * 1024 * 1024:
                    raise ValueError(f"{label} is too large")
                try:
                    return base64.b64decode(encoded, validate=True)
                except (binascii.Error, ValueError, TypeError) as exc:
                    raise ValueError(f"{label} data is invalid") from exc

            payload = decode_data_url(image_data_url, "Edited image")
            edit_source_payload = decode_data_url(edit_source_data_url, "Edit source")

            source = self.media_resolver.resolve(local_id, "image", attempt_index)
            with Image.open(source) as opened:
                image_format = opened.format or "PNG"
                current = ImageOps.exif_transpose(opened).copy()
            with Image.open(BytesIO(payload)) as opened_edit:
                edited = opened_edit.copy()
            with Image.open(BytesIO(edit_source_payload)) as opened_source:
                edit_source = opened_source.convert("RGBA")
            if edited.size != current.size:
                raise ValueError("Edited image dimensions must match the candidate image")
            if edit_source.size != current.size:
                raise ValueError("Edit source dimensions must match the candidate image")

            backup = source.with_name(f"{source.stem}.original{source.suffix}")
            if not backup.exists():
                shutil.copy2(source, backup)
            temporary = source.with_name(f".{source.name}.eraser.tmp")
            output_mode = "RGBA" if current.mode == "RGBA" and image_format.upper() == "PNG" else "RGB"
            save_options = {"quality": 95} if image_format.upper() in {"JPEG", "JPG"} else {}
            edited.convert(output_mode).save(temporary, format=image_format, **save_options)
            os.replace(temporary, source)
            source_sidecar = edit_source_path(source)
            source_temporary = source_sidecar.with_name(f".{source_sidecar.name}.tmp")
            edit_source.save(source_temporary, format="PNG")
            os.replace(source_temporary, source_sidecar)
            saved_layout = None
            if generation_layout is not None:
                saved_layout = write_generation_layout(
                    source, generation_layout, width=edited.width, height=edited.height
                )
            return {
                "success": True,
                "data": {
                    "saved": True,
                    "width": edited.width,
                    "height": edited.height,
                    "generation_layout": saved_layout,
                },
            }
        except Exception as error:
            return self._error_response(error)

    @staticmethod
    def _corner_background_color(image: Image.Image) -> tuple[int, int, int]:
        rgb = image.convert("RGB")
        width, height = rgb.size
        patch_size = max(1, round(min(width, height) * 0.05))
        boxes = (
            (0, 0, patch_size, patch_size),
            (width - patch_size, 0, width, patch_size),
            (0, height - patch_size, patch_size, height),
            (width - patch_size, height - patch_size, width, height),
        )
        channels = [[], [], []]
        for box in boxes:
            for pixel in rgb.crop(box).get_flattened_data():
                for index, value in enumerate(pixel):
                    channels[index].append(value)
        return tuple(round(median(channel)) for channel in channels)

    def get_handoff_image(self, local_id: str, attempt_index: int = 0) -> dict[str, Any]:
        """Resolve a successful candidate image's local file path for Seedance handoff."""
        try:
            batch = self._ensure_manager().get_batch(local_id)
            attempt = next(
                (
                    candidate
                    for candidate in batch.get("attempts", [])
                    if isinstance(candidate, dict) and candidate.get("index") == attempt_index
                ),
                None,
            )
            if attempt is None or attempt.get("status") != "succeeded":
                raise FileNotFoundError("Seedream candidate image is not available for handoff")
            path = self.media_resolver.resolve(local_id, "image", attempt_index)
            return {"success": True, "data": {"local_path": str(path)}}
        except Exception as error:
            return self._error_response(error)

    def delete_batch(self, local_id: str) -> dict[str, Any]:
        try:
            self._ensure_manager().delete_batch(local_id)
            return {"success": True}
        except Exception as error:
            return self._error_response(error)

    def get_regeneration_draft(self, local_id: str) -> dict[str, Any]:
        """Return a reusable local request without creating a paid batch.

        The draft restores the original prompt/model/resolution/ratio/count so the
        user can edit and re-confirm via the normal paid confirmation flow. It
        never calls ImageGenerations or creates a new batch.
        """
        try:
            draft = self._ensure_manager().get_regeneration_draft(local_id)
            return {"success": True, "data": draft}
        except Exception as error:
            return self._error_response(error)

    def retry_download(self, local_id: str, attempt_index: int = 0) -> dict[str, Any]:
        try:
            batch = self._ensure_manager().retry_download(local_id, attempt_index)
            return {"success": True, "batch": self._decorate_batch(batch)}
        except Exception as error:
            return self._error_response(error)

    def get_active_attempt_count(self) -> dict[str, Any]:
        """Return the number of currently active image-generation attempts."""
        try:
            count = self._ensure_manager().active_attempt_count()
            return {"success": True, "data": {"active_count": count}}
        except Exception as error:
            return self._error_response(error)

    def reclassify_interrupted_attempts(self) -> dict[str, Any]:
        """Mark leftover active attempts terminal after an unclean shutdown."""
        try:
            result = self._ensure_manager().reclassify_interrupted_attempts()
            return {"success": True, "data": result}
        except Exception as error:
            return self._error_response(error)

    def get_settings(self) -> dict[str, Any]:
        try:
            config = load_app_config()
            seedream_config = config.get("seedream", {})
            if not isinstance(seedream_config, dict):
                seedream_config = {}
            default_count = seedream_config.get("default_count", _DEFAULT_COUNT)
            if not isinstance(default_count, int) or default_count < 1 or default_count > 4:
                default_count = _DEFAULT_COUNT
            default_model = seedream_config.get("default_model", _DEFAULT_MODEL)
            if default_model not in MODEL_CAPABILITIES:
                default_model = _DEFAULT_MODEL
            default_resolution = seedream_config.get("default_resolution", _DEFAULT_RESOLUTION)
            if default_resolution not in MODEL_CAPABILITIES[default_model]["resolutions"]:
                default_resolution = MODEL_CAPABILITIES[default_model]["resolutions"][0]
            default_ratio = seedream_config.get("default_ratio", _DEFAULT_RATIO)
            if default_ratio not in _ALLOWED_RATIOS:
                default_ratio = _DEFAULT_RATIO
            return {
                "success": True,
                "settings": {
                    "default_count": default_count,
                    "default_model": default_model,
                    "default_resolution": default_resolution,
                    "default_ratio": default_ratio,
                },
            }
        except Exception as error:
            return self._error_response(error)

    def save_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        try:
            if not isinstance(settings, dict):
                raise ValueError("Seedream settings must be an object")
            default_count = settings.get("default_count", _DEFAULT_COUNT)
            if not isinstance(default_count, int) or default_count < 1 or default_count > 4:
                raise ValidationError("default_count", "INVALID_COUNT", "Image count must be between 1 and 4")
            default_model = settings.get("default_model", _DEFAULT_MODEL)
            if default_model not in MODEL_CAPABILITIES:
                raise ValidationError("default_model", "UNSUPPORTED_MODEL", "Unsupported Seedream model")
            default_resolution = settings.get("default_resolution", _DEFAULT_RESOLUTION)
            if default_resolution not in MODEL_CAPABILITIES[default_model]["resolutions"]:
                raise ValidationError(
                    "default_resolution", "UNSUPPORTED_RESOLUTION", "Resolution is unsupported for this model"
                )
            default_ratio = settings.get("default_ratio", _DEFAULT_RATIO)
            if default_ratio not in _ALLOWED_RATIOS:
                raise ValidationError("default_ratio", "UNSUPPORTED_RATIO", "Unsupported aspect ratio")
            save_app_config({
                "seedream": {
                    "default_count": default_count,
                    "default_model": default_model,
                    "default_resolution": default_resolution,
                    "default_ratio": default_ratio,
                }
            })
            return {
                "success": True,
                "settings": {
                    "default_count": default_count,
                    "default_model": default_model,
                    "default_resolution": default_resolution,
                    "default_ratio": default_ratio,
                },
            }
        except Exception as error:
            return self._error_response(error)

    def _ensure_manager(self) -> SeedreamBatchManager:
        if self._manager is None:
            config = load_app_config()["seedance"]
            repository = BatchRepository(ai_pic_cache_root(config.get("cache_dir")))
            platform = self._build_platform_images()
            self._manager = SeedreamBatchManager(
                self._client_factory(config["api_key"]),
                repository,
                ImageDownloader(
                    repository,
                    PlatformArtifactTransport(self._platform_client) if platform is not None else None,
                ),
                platform=platform,
            )
        if self._media_resolver is None:
            self._media_resolver = SeedreamMediaResolver(self._manager._repository)
        return self._manager

    def _build_platform_images(self) -> PlatformImageClient | None:
        if self._platform_config is None or not self._platform_config.configured():
            return None
        if self._platform_client is None:
            self._platform_client = self._platform_config.client()
        return PlatformImageClient(self._platform_client)

    def quote_image(self, request_data: dict[str, Any]) -> dict[str, Any]:
        """Server-side quote preview for the platform source (read-only).

        Pricing dimensions are model + size, so the preview deliberately does NOT
        require prompt or a reference image — the create page quotes as soon as
        the model/size are chosen, before the user picks an image. Count is a
        client-side fan-out (N images = N jobs), so the caller multiplies.
        """
        try:
            config = self._require_platform()
            # 见 quote_video：平台源下 model 是上游 ID，本地表拦不得。
            model = platform_model_id(request_data.get("model") or "pro")
            # 与 Ark 文档口径一致（大写）；平台入参大小写不敏感，此处按客户端取值原样下发。
            resolution = str(request_data.get("resolution") or "1K").upper()
            if resolution not in _PLATFORM_SIZES:
                raise ValidationError("resolution", "UNSUPPORTED_RESOLUTION", "平台仅支持 1K/1.5K/2K")
            body = {"model": model, "size": resolution}
            data = config.client().quote_image(body)
            return {"success": True, "data": data}
        except Exception as error:
            return self._error_response(error)

    def _require_platform(self) -> PlatformConfig:
        if self._platform_config is None or not self._platform_config.configured():
            raise ValidationError("source", "PLATFORM_NOT_CONFIGURED", "请先登录 ForFuner 账户")
        return self._platform_config

    def _decorate_batch(self, batch: dict[str, Any]) -> dict[str, Any]:
        decorated = self._redact_value(deepcopy(batch), self._configured_api_key())
        local_id = decorated.get("local_id")
        if not isinstance(local_id, str):
            return decorated
        for attempt in decorated.get("attempts", []):
            if isinstance(attempt, dict) and attempt.get("image_url"):
                index = attempt.get("index", 0)
                attempt["image_url"] = self._media_url(local_id, index if isinstance(index, int) else 0)
                try:
                    source = self.media_resolver.resolve(local_id, "image", index if isinstance(index, int) else 0)
                    backup = source.with_name(f"{source.stem}.original{source.suffix}")
                    attempt["has_original_backup"] = backup.is_file()
                except (OSError, TypeError, ValueError):
                    attempt["has_original_backup"] = False
        return decorated

    @classmethod
    def _redact_value(cls, value: Any, api_key: str) -> Any:
        if not api_key:
            return value
        if isinstance(value, str):
            return value.replace(api_key, "[REDACTED]")
        if isinstance(value, dict):
            redacted: dict[Any, Any] = {}
            for key, item in value.items():
                redacted_key = key.replace(api_key, "[REDACTED]") if isinstance(key, str) else key
                if isinstance(redacted_key, str) and redacted_key in redacted:
                    suffix = 2
                    candidate = f"{redacted_key}#{suffix}"
                    while candidate in redacted:
                        suffix += 1
                        candidate = f"{redacted_key}#{suffix}"
                    redacted_key = candidate
                redacted[redacted_key] = cls._redact_value(item, api_key)
            return redacted
        if isinstance(value, list):
            return [cls._redact_value(item, api_key) for item in value]
        if isinstance(value, tuple):
            return tuple(cls._redact_value(item, api_key) for item in value)
        return value

    def _media_url(self, local_id: str, attempt_index: int = 0) -> str:
        return f"{self._media_base_url}/seedream-media/{quote(local_id, safe='')}/image/{attempt_index}"

    def _dispatch_batch_update(self, _event_name: str, batch: dict[str, Any]) -> None:
        if self._window is None:
            return
        public_batch = self._decorate_batch(batch)
        self._window.evaluate_js(
            "window.dispatchEvent(new CustomEvent('seedream-batch-updated', { detail: "
            + json.dumps(public_batch, ensure_ascii=False)
            + " }));"
        )

    def _require_api_key(self) -> str:
        api_key = load_app_config()["seedance"].get("api_key")
        if not isinstance(api_key, str) or not api_key:
            raise ValidationError("api_key", "API_KEY_NOT_CONFIGURED", "Configure an API key before continuing")
        return api_key

    def _error_response(self, error: Exception) -> dict[str, Any]:
        if isinstance(error, ValidationError):
            error_data = {"code": error.code, "message": self._safe_text(str(error)), "field": error.field}
        elif isinstance(error, ArkAPIError):
            error_data = {"code": error.code, "message": self._safe_text(error.message), "field": None}
        elif isinstance(error, PlatformUnauthorizedError):
            error_data = {"code": "UNAUTHORIZED", "message": error.message, "field": None}
        elif isinstance(error, PlatformError):
            # 平台业务异常原文透传（未定价/余额不足/超并发/素材无效）。
            error_data = {"code": error.code, "message": error.message, "field": None}
        elif isinstance(error, SubmissionUnknownError):
            error_data = {"code": "SUBMISSION_UNKNOWN", "message": "Image generation outcome is unknown", "field": None}
        elif isinstance(error, FileNotFoundError):
            error_data = {"code": "NOT_FOUND", "message": "Seedream batch or asset was not found", "field": None}
        elif isinstance(error, ValueError):
            error_data = {"code": "INVALID_REQUEST", "message": self._safe_text(str(error)), "field": None}
        else:
            error_data = {"code": "INTERNAL_ERROR", "message": "Unable to complete Seedream request", "field": None}
        return {"success": False, "error": error_data}

    @staticmethod
    def _safe_text(message: str) -> str:
        api_key = SeedreamAPI._configured_api_key()
        if api_key and api_key in message:
            return "Unable to complete Seedream request"
        return message

    @staticmethod
    def _configured_api_key() -> str:
        api_key = load_app_config()["seedance"].get("api_key")
        return api_key if isinstance(api_key, str) else ""

    @staticmethod
    def _active_window() -> Any | None:
        return webview.windows[0] if webview.windows else None
