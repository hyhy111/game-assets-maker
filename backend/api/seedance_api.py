"""PyWebView-facing facade for persisted Seedance generation tasks."""

from __future__ import annotations

import base64
import binascii
import os
import shutil
from collections.abc import Callable
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import webview
from PIL import Image, ImageOps

from backend.image_layout import edit_source_path, read_generation_layout, write_generation_layout

from backend.seedance.cache import CacheManager
from backend.seedance.client import ArkAPIError, ArkClient, SubmissionUnknownError
from backend.seedance.downloader import ResultDownloader
from backend.seedance.manager import SeedanceTaskManager
from backend.seedance.media import SeedanceMediaResolver
from backend.seedance.models import SeedanceRequest
from backend.seedance.repository import TaskRepository
from backend.seedance.validation import ValidationError, build_api_payload, validate_request
from src.utils.ai_cache_paths import ai_cache_root, ai_video_cache_root
from src.utils.app_config import load_app_config, public_app_config, save_app_config
from src.utils.storage_locations import StorageLocations

_IMAGE_FILE_TYPES = (
    "Image files (*.jpg;*.jpeg;*.png;*.webp;*.bmp;*.tif;*.tiff;*.gif;*.heic;*.heif)",
)


class SeedanceAPI:
    """Convert PyWebView input/output to the Seedance domain's safe public contract."""

    def __init__(
        self,
        manager: SeedanceTaskManager | None = None,
        *,
        project_api: Any | None = None,
        window_getter: Callable[[], Any | None] | None = None,
        client_factory: Callable[[str], ArkClient] = ArkClient,
        media_base_url: str = "http://localhost:8080",
        media_resolver: SeedanceMediaResolver | None = None,
        storage_locations: StorageLocations | None = None,
    ) -> None:
        self._project_api = project_api
        self._window_getter = window_getter or self._active_window
        self._client_factory = client_factory
        self._media_base_url = media_base_url.rstrip("/")
        self._manager = manager
        self._external_manager = manager is not None
        self._media_resolver = media_resolver
        self._storage_locations = storage_locations
        self._window = None
        self._started = False

    def set_media_base_url(self, media_base_url: str) -> None:
        self._media_base_url = media_base_url.rstrip("/")

    @property
    def media_resolver(self) -> SeedanceMediaResolver:
        self._ensure_manager()
        assert self._media_resolver is not None
        return self._media_resolver

    def set_window(self, window: Any) -> None:
        """Attach the event sink before starting the single polling manager."""
        self._window = window
        manager = self._ensure_manager()
        manager.set_event_sink(self._dispatch_task_update)
        if not self._started:
            manager.start()
            self._started = True

    def shutdown(self) -> None:
        if self._manager is not None:
            self._manager.shutdown()
        self._started = False

    def select_image_file(self) -> str | None:
        window = self._window or self._window_getter()
        if window is None:
            return None
        result = window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=_IMAGE_FILE_TYPES,
        )
        return result[0] if result else None

    def get_editable_image(self, source_path: str) -> dict[str, Any]:
        """Return a full-resolution, browser-decodable PNG for the local image editor."""
        try:
            source = Path(source_path).expanduser()
            if not source.is_file():
                raise FileNotFoundError("Selected image is not available")
            with Image.open(source) as opened:
                image = ImageOps.exif_transpose(opened).convert("RGBA")
            source_sidecar = edit_source_path(source)
            with Image.open(source_sidecar if source_sidecar.is_file() else source) as opened:
                edit_source = ImageOps.exif_transpose(opened).convert("RGBA")
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
            edit_source_buffer = BytesIO()
            edit_source.save(edit_source_buffer, format="PNG")
            edit_source_encoded = base64.b64encode(edit_source_buffer.getvalue()).decode("ascii")
            return {
                "success": True,
                "data": {
                    "image_data_url": f"data:image/png;base64,{encoded}",
                    "edit_source_data_url": f"data:image/png;base64,{edit_source_encoded}",
                    "width": image.width,
                    "height": image.height,
                    "generation_layout": read_generation_layout(
                        source, width=image.width, height=image.height
                    ),
                },
            }
        except Exception as error:
            return self._error_response(error)

    def save_edited_image(
        self,
        source_path: str,
        image_data_url: str,
        edit_source_data_url: str,
        generation_layout: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Save an editor result as a new cached PNG without modifying the selected source."""
        try:
            source = Path(source_path).expanduser()
            if not source.is_file():
                raise FileNotFoundError("Selected image is not available")
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

            with Image.open(source) as opened:
                source_size = ImageOps.exif_transpose(opened).size
            with Image.open(BytesIO(payload)) as opened_edit:
                edited = opened_edit.convert("RGBA")
            with Image.open(BytesIO(edit_source_payload)) as opened_source:
                edit_source = opened_source.convert("RGBA")
            if edited.size != source_size:
                raise ValueError("Edited image dimensions must match the selected image")
            if edit_source.size != source_size:
                raise ValueError("Edit source dimensions must match the selected image")

            output_dir = self._video_cache_root() / "edited-inputs"
            output_dir.mkdir(parents=True, exist_ok=True)
            destination = output_dir / f"{uuid4().hex}.png"
            temporary = output_dir / f".{destination.name}.tmp"
            edited.save(temporary, format="PNG")
            os.replace(temporary, destination)
            source_sidecar = edit_source_path(destination)
            source_temporary = source_sidecar.with_name(f".{source_sidecar.name}.tmp")
            edit_source.save(source_temporary, format="PNG")
            os.replace(source_temporary, source_sidecar)
            saved_layout = None
            if generation_layout is not None:
                saved_layout = write_generation_layout(
                    destination,
                    generation_layout,
                    width=edited.width,
                    height=edited.height,
                )
            return {
                "success": True,
                "data": {
                    "path": str(destination.resolve()),
                    "width": edited.width,
                    "height": edited.height,
                    "generation_layout": saved_layout,
                },
            }
        except Exception as error:
            return self._error_response(error)

    def save_video(self, local_id: str) -> dict[str, Any]:
        try:
            source = self.media_resolver.resolve(local_id, "video")
            window = self._window or self._window_getter()
            if window is None:
                raise RuntimeError("The application window is not available")
            result = window.create_file_dialog(
                webview.FileDialog.SAVE,
                save_filename=f"seedance-{local_id[:8]}.mp4",
                file_types=("MP4 video (*.mp4)",),
            )
            if not result:
                return {"success": True, "data": {"saved": False}}
            destination = Path(result[0])
            shutil.copy2(source, destination)
            return {"success": True, "data": {"saved": True, "path": str(destination)}}
        except Exception as error:
            return self._error_response(error)

    def create_task(self, request_data: dict[str, Any]) -> dict[str, Any]:
        try:
            request = SeedanceRequest.from_dict(request_data)
            validate_request(request)
            self._require_api_key()
            task = self._ensure_manager().create(request)
            return {"success": True, "task": self._decorate_task(task)}
        except Exception as error:
            return self._error_response(error)

    def validate_request(self, request_data: dict[str, Any]) -> dict[str, Any]:
        """Validate the exact compact Base64 request without creating a local or remote task."""
        try:
            request = SeedanceRequest.from_dict(request_data)
            build_api_payload(request)
            return {"success": True, "data": {"valid": True}}
        except Exception as error:
            return self._error_response(error)

    def list_tasks(self) -> dict[str, Any]:
        try:
            tasks = [self._decorate_task(task) for task in self._ensure_manager().list_tasks()]
            return {"success": True, "tasks": tasks}
        except Exception as error:
            return self._error_response(error)

    def get_task(self, local_id: str) -> dict[str, Any]:
        try:
            return {"success": True, "task": self._decorate_task(self._ensure_manager().get_task(local_id))}
        except Exception as error:
            return self._error_response(error)

    def get_regeneration_draft(self, local_id: str) -> dict[str, Any]:
        """Return a reusable local request without creating a paid task."""
        try:
            manager = self._ensure_manager()
            task = manager.get_task(local_id)
            input_paths = manager.local_asset_paths(local_id).get("input_paths", {})
            first_frame = input_paths.get("first_frame")
            if not isinstance(first_frame, str):
                raise FileNotFoundError("Task first frame is unavailable")
            request = {
                **task.get("request", {}),
                "first_frame": first_frame,
                "last_frame": input_paths.get("last_frame"),
            }
            preview_urls = {
                key: self._media_url(local_id, key)
                for key in ("first_frame", "last_frame")
                if key in input_paths
            }
            return {"success": True, "data": {"request": request, "preview_urls": preview_urls}}
        except Exception as error:
            return self._error_response(error)

    def get_continuation_draft(self, local_id: str) -> dict[str, Any]:
        """Prepare a new request from a task's returned final frame without creating it."""
        try:
            manager = self._ensure_manager()
            task = manager.get_task(local_id)
            output_paths = manager.local_asset_paths(local_id).get("output_paths", {})
            returned_last_frame = output_paths.get("returned_last_frame")
            if not isinstance(returned_last_frame, str):
                raise FileNotFoundError("Task returned last frame is unavailable")
            request = {
                **task.get("request", {}),
                "first_frame": returned_last_frame,
                "last_frame": None,
                "prompt": "",
            }
            return {
                "success": True,
                "data": {
                    "request": request,
                    "preview_urls": {"first_frame": self._media_url(local_id, "returned_last_frame")},
                },
            }
        except Exception as error:
            return self._error_response(error)

    def cancel_task(self, local_id: str) -> dict[str, Any]:
        return self._task_action(lambda: self._ensure_manager().cancel(local_id))

    def retry_task(self, local_id: str) -> dict[str, Any]:
        try:
            self._require_api_key()
            return self._task_action(lambda: self._ensure_manager().retry_generation(local_id))
        except Exception as error:
            return self._error_response(error)

    def retry_download(self, local_id: str) -> dict[str, Any]:
        return self._task_action(lambda: self._ensure_manager().retry_download(local_id))

    def continue_task(self, local_id: str) -> dict[str, Any]:
        try:
            self._require_api_key()
            return self._task_action(lambda: self._ensure_manager().continue_generation(local_id))
        except Exception as error:
            return self._error_response(error)

    def delete_task(self, local_id: str, allow_protected: bool = False) -> dict[str, Any]:
        try:
            self._ensure_manager().delete_task(local_id, allow_protected)
            return {"success": True}
        except Exception as error:
            return self._error_response(error)

    def handoff(self, local_id: str, role: str, action: str) -> dict[str, Any]:
        try:
            result = self._ensure_manager().handoff(local_id, role, action)
            result = deepcopy(result)
            if isinstance(result.get("task"), dict):
                result["task"] = self._decorate_task(result["task"])
            return {"success": True, **result}
        except Exception as error:
            return self._error_response(error)

    def get_settings(self) -> dict[str, Any]:
        settings = public_app_config(load_app_config())["seedance"]
        if not settings["cache_dir"]:
            settings["cache_dir"] = str(ai_cache_root(None).resolve())
        return settings

    def save_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        try:
            if not isinstance(settings, dict):
                raise ValueError("Seedance settings must be an object")
            update = {key: value for key, value in settings.items() if key != "api_key_configured"}
            save_app_config({"seedance": update})
            if not self._external_manager and {"api_key", "cache_dir"}.intersection(update):
                self._replace_manager()
            return {"success": True, "settings": self.get_settings()}
        except Exception as error:
            return self._error_response(error)

    def test_connection(self, api_key: str | None = None) -> dict[str, Any]:
        draft_key = api_key.strip() if isinstance(api_key, str) else ""
        try:
            key_to_test = draft_key or self._require_api_key()
            self._client_factory(key_to_test).list_tasks(page_size=1)
            return {"success": True, "data": {"configured": True}}
        except Exception as error:
            return self._error_response(error, secret=draft_key)

    def cache_status(self) -> dict[str, Any]:
        try:
            return {"success": True, "data": self._ensure_manager().cache_status()}
        except Exception as error:
            return self._error_response(error)

    def clean_cache(self, older_than_days: int | None = None) -> dict[str, Any]:
        try:
            return {"success": True, "data": self._ensure_manager().clean_cache(older_than_days)}
        except Exception as error:
            return self._error_response(error)

    def _task_action(self, action: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        try:
            return {"success": True, "task": self._decorate_task(action())}
        except Exception as error:
            return self._error_response(error)

    def _ensure_manager(self) -> SeedanceTaskManager:
        if self._manager is None:
            config = load_app_config()["seedance"]
            # Injected locations win: the composition root freezes the cache
            # root for the process lifetime; standalone constructions (tests,
            # CLI) resolve from the current config instead.
            cache_root = self._video_cache_root(config)
            repository = TaskRepository(cache_root)
            self._manager = SeedanceTaskManager(
                self._client_factory(config["api_key"]),
                repository,
                ResultDownloader(repository),
                CacheManager(repository, self._project_api),
                config,
                config_saver=lambda seedance: save_app_config({"seedance": seedance}),
            )
        if self._media_resolver is None:
            self._media_resolver = SeedanceMediaResolver(self._manager._repository)
        return self._manager

    def _video_cache_root(self, config: dict[str, Any] | None = None) -> Path:
        if self._storage_locations is not None:
            return self._storage_locations.ai_video_cache_root
        return self._configured_cache_root(config)

    @staticmethod
    def _configured_cache_root(config: dict[str, Any] | None = None) -> Path:
        seedance = config or load_app_config()["seedance"]
        return ai_video_cache_root(seedance.get("cache_dir"))

    def _replace_manager(self) -> None:
        old_manager = self._manager
        if old_manager is not None:
            old_manager.shutdown()
        self._manager = None
        self._media_resolver = None
        self._started = False
        if self._window is not None:
            self.set_window(self._window)

    def _decorate_task(self, task: dict[str, Any]) -> dict[str, Any]:
        decorated = self._redact_task_value(deepcopy(task), self._configured_api_key())
        local_id = decorated.get("local_id")
        if not isinstance(local_id, str):
            return decorated
        input_urls: dict[str, str] = {}
        output_urls: dict[str, str] = {}
        for asset_key in ("first_frame", "last_frame"):
            if self._asset_available(local_id, asset_key):
                input_urls[asset_key] = self._media_url(local_id, asset_key)
        for asset_key in ("video", "returned_last_frame", "thumbnail"):
            if self._asset_available(local_id, asset_key):
                output_urls[asset_key] = self._media_url(local_id, asset_key)
        decorated["input_urls"] = input_urls
        decorated["output_urls"] = output_urls
        return decorated

    @classmethod
    def _redact_task_value(cls, value: Any, api_key: str) -> Any:
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
                redacted[redacted_key] = cls._redact_task_value(item, api_key)
            return redacted
        if isinstance(value, list):
            return [cls._redact_task_value(item, api_key) for item in value]
        if isinstance(value, tuple):
            return tuple(cls._redact_task_value(item, api_key) for item in value)
        return value

    def _asset_available(self, local_id: str, asset_key: str) -> bool:
        try:
            self.media_resolver.resolve(local_id, asset_key)
        except (FileNotFoundError, ValueError):
            return False
        return True

    def _media_url(self, local_id: str, asset_key: str) -> str:
        return f"{self._media_base_url}/seedance-media/{quote(local_id, safe='')}/{asset_key}"

    def _dispatch_task_update(self, _event_name: str, task: dict[str, Any]) -> None:
        if self._window is None:
            return
        import json

        public_task = self._decorate_task(task)
        self._window.evaluate_js(
            "window.dispatchEvent(new CustomEvent('seedance-task-updated', { detail: "
            + json.dumps(public_task, ensure_ascii=False)
            + " }));"
        )

    def _require_api_key(self) -> str:
        api_key = load_app_config()["seedance"].get("api_key")
        if not isinstance(api_key, str) or not api_key:
            raise ValidationError("api_key", "API_KEY_NOT_CONFIGURED", "Configure an API key before continuing")
        return api_key

    def _error_response(self, error: Exception, secret: str = "") -> dict[str, Any]:
        if isinstance(error, ValidationError):
            error_data = {"code": error.code, "message": self._safe_text(str(error), secret), "field": error.field}
        elif isinstance(error, ArkAPIError):
            error_data = {"code": error.code, "message": self._safe_text(error.message, secret), "field": None}
        elif isinstance(error, SubmissionUnknownError):
            error_data = {"code": "SUBMISSION_UNKNOWN", "message": "Task submission outcome is unknown", "field": None}
        elif isinstance(error, FileNotFoundError):
            error_data = {"code": "NOT_FOUND", "message": "Seedance task or asset was not found", "field": None}
        elif isinstance(error, ValueError):
            error_data = {"code": "INVALID_REQUEST", "message": self._safe_text(str(error), secret), "field": None}
        else:
            error_data = {"code": "INTERNAL_ERROR", "message": "Unable to complete Seedance request", "field": None}
        return {"success": False, "error": error_data}

    @staticmethod
    def _safe_text(message: str, secret: str = "") -> str:
        api_key = SeedanceAPI._configured_api_key()
        if (api_key and api_key in message) or (secret and secret in message):
            return "Unable to complete Seedance request"
        return message

    @staticmethod
    def _configured_api_key() -> str:
        api_key = load_app_config()["seedance"].get("api_key")
        return api_key if isinstance(api_key, str) else ""

    @staticmethod
    def _active_window() -> Any | None:
        return webview.windows[0] if webview.windows else None
