"""Persistent orchestration for Seedream image-generation batches."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from contextlib import suppress
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from PIL import Image

from backend.image_layout import read_generation_layout
from backend.seedream.client import ArkAPIError, ArkClient, ArkResponseError, SubmissionUnknownError
from backend.seedream.downloader import ImageDownloader
from backend.seedream.models import ImageBatch, MODEL_CAPABILITIES, SeedreamRequest, platform_model_id
from backend.seedream.repository import BatchRepository, utc_now_iso
from backend.seedream.validation import _build_prompt_with_ratio, build_api_payload, validate_request
from backend.platform.client import PlatformError, PlatformUnauthorizedError, new_idem_key
from backend.platform.downloads import direct_link_candidates
from backend.platform.images import PlatformImageClient
from backend.platform.video import parse_error_json

EventSink = Callable[[str, dict[str, Any]], None]

from backend.platform.sources import PLATFORM_SOURCE  # noqa: F401  (re-export，保持既有导入路径可用)

_ACTIVE_STATUSES = {"queued", "generating", "downloading"}
_TERMINAL_STATUSES = {"succeeded", "failed", "unknown", "download_failed"}
# Active attempts whose response was never persisted: the remote outcome is
# undeterminable after a crash, so they become "unknown" (may already be billed).
_INTERRUPTED_TO_UNKNOWN_STATUSES = {"submitting", "queued", "generating"}
_URL_EXPIRY_SECONDS = 24 * 3600


class SeedreamBatchManager:
    """Create batches and run independent image attempts concurrently."""

    def __init__(
        self,
        client: ArkClient,
        repository: BatchRepository,
        downloader: ImageDownloader,
        *,
        now: Callable[[], datetime] | None = None,
        platform: PlatformImageClient | None = None,
    ) -> None:
        self._client = client
        self._repository = repository
        self._downloader = downloader
        self._platform = platform
        self._now = now or (lambda: datetime.now(UTC))
        self._event_sink: EventSink | None = None
        self._event_lock = threading.Lock()
        self._active_attempts: dict[str, set[int]] = {}
        self._active_lock = threading.Lock()

    def set_event_sink(self, sink: EventSink | None) -> None:
        with self._event_lock:
            self._event_sink = sink

    def create_batch(self, request: SeedreamRequest) -> dict[str, Any]:
        """Persist the batch with N attempt placeholders before any paid request."""
        validate_request(request)
        batch = self._repository.create_batch(request)
        for index in range(len(batch.attempts)):
            self._run_attempt_async(batch.local_id, index)
        return self.public_batch(batch)

    def get_batch(self, local_id: str) -> dict[str, Any]:
        return self.public_batch(self._repository.get(local_id))

    def list_batches(self) -> list[dict[str, Any]]:
        batches = self._repository.list()
        public = [self.public_batch(batch) for batch in batches]
        self._assign_sequences(public)
        return public

    def get_regeneration_draft(self, local_id: str) -> dict[str, Any]:
        """Return the original request as an editable draft without paid generation.

        Restoring a regeneration draft never calls ImageGenerations or any other
        paid endpoint. The user must explicitly confirm a new paid generation to
        create a fresh batch with the full requested count.
        """
        batch = self._repository.get(local_id)
        request = batch.request if isinstance(batch.request, dict) else {}
        reference_path, reference_url = self._reference_image_restore(local_id, request)
        return {
            "request": {
                "prompt": request.get("prompt", ""),
                "model": request.get("model", "pro"),
                "resolution": request.get("resolution", "1K"),
                "ratio": request.get("ratio", "16:9"),
                "count": request.get("count", 2),
                "reference_image": reference_path,
            },
            "reference_image_url": reference_url,
        }

    def _reference_image_restore(self, local_id: str, request: dict[str, Any]) -> tuple[str | None, str | None]:
        """Resolve the stored reference image for resubmission and preview.

        Returns (absolute path, media URL). A batch whose cached reference
        image has gone missing restores the draft without one rather than
        failing the whole draft.
        """
        stored = request.get("reference_image")
        if not isinstance(stored, str) or not stored:
            return None, None
        try:
            resolved = self._repository.resolve_asset(local_id, stored)
        except (FileNotFoundError, ValueError):
            return None, None
        if not resolved.is_file():
            return None, None
        return str(resolved), f"/seedream-media/{quote(local_id, safe='')}/reference"

    def delete_batch(self, local_id: str) -> None:
        with self._active_lock:
            if local_id in self._active_attempts:
                raise ValueError("Cannot delete a batch with active generation attempts")
        batch = self._repository.get(local_id)
        if any(attempt.status not in _TERMINAL_STATUSES for attempt in batch.attempts):
            raise ValueError("Cannot delete a batch with active generation attempts")
        self._repository.delete(local_id)

    def retry_download(self, local_id: str, attempt_index: int) -> dict[str, Any]:
        """Retry downloading the original URL without calling ImageGenerations."""
        batch = self._repository.get(local_id)
        if attempt_index < 0 or attempt_index >= len(batch.attempts):
            raise FileNotFoundError("Seedream attempt not found")
        attempt = batch.attempts[attempt_index]
        if attempt.status != "download_failed":
            raise ValueError("Can only retry download for download_failed attempts")
        if self._is_url_expired(attempt):
            raise ValueError("URL_EXPIRED")
        url = self._extract_image_url(attempt.response)
        self._run_download_retry(local_id, attempt_index, url)
        return self.public_batch(self._repository.get(local_id))

    def _download_platform_image(
        self, batch_id: str, attempt_index: int, response: dict[str, Any], fallback_url: str
    ) -> str:
        """平台图片取回：新鲜直链优先，失败自动回退平台伪地址（不算下载失败）。

        重试路径（retry_download）只走平台地址——直链只在生成当场用一次，
        不重复消耗上游 ~100 次的下载额度。
        """
        data = response.get("data")
        entry = data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else {}
        candidates = direct_link_candidates(entry, fallback_url)
        for index, url in enumerate(candidates):
            try:
                return self._downloader.download_image(batch_id, attempt_index, url)
            except Exception:  # noqa: BLE001 - 回退平台地址是设计行为
                if index == len(candidates) - 1:
                    raise
        raise ArkResponseError("Platform image download exhausted all candidates")

    def _run_download_retry(self, batch_id: str, attempt_index: int, url: str) -> None:
        with self._active_lock:
            self._active_attempts.setdefault(batch_id, set()).add(attempt_index)
        try:
            self._update_attempt(batch_id, attempt_index, lambda a: setattr(a, "status", "downloading"))
            self._emit(batch_id)

            local_path = self._downloader.download_image(batch_id, attempt_index, url)

            self._update_attempt(
                batch_id,
                attempt_index,
                lambda a: (
                    setattr(a, "local_path", local_path),
                    setattr(a, "status", "succeeded"),
                    setattr(a, "finished_at", utc_now_iso()),
                ),
            )
            self._emit(batch_id)
        except Exception as error:
            self._update_attempt(
                batch_id,
                attempt_index,
                lambda a, caught=error: (
                    setattr(a, "status", "download_failed"),
                    setattr(a, "error", self._error_dict(caught)),
                    setattr(a, "finished_at", utc_now_iso()),
                ),
            )
            self._emit(batch_id)
        finally:
            with self._active_lock:
                indices = self._active_attempts.get(batch_id)
                if indices is not None:
                    indices.discard(attempt_index)
                    if not indices:
                        self._active_attempts.pop(batch_id, None)

    def has_active_batches(self) -> bool:
        with self._active_lock:
            return bool(self._active_attempts)

    def active_attempt_count(self) -> int:
        """Count persisted attempts that are still in a non-terminal status.

        Reads the repository so the count stays accurate across restarts and
        counts individual attempts rather than batches.
        """
        return sum(
            1
            for batch in self._repository.list()
            for attempt in batch.attempts
            if attempt.status not in _TERMINAL_STATUSES
        )

    def reclassify_interrupted_attempts(self) -> dict[str, int]:
        """Mark leftover active attempts terminal after an unclean shutdown.

        ``submitting``/``queued``/``generating`` attempts never persisted a
        response, so they become ``unknown`` (the remote outcome is unknown and
        the request may already have been billed). ``downloading`` attempts
        already persisted a response, so they become ``download_failed`` and
        remain eligible for #5's download retry. This never calls
        ImageGenerations or any other paid endpoint.
        """
        reclassified = {"unknown": 0, "download_failed": 0}
        for batch in self._repository.list():
            for attempt in batch.attempts:
                if attempt.status in _INTERRUPTED_TO_UNKNOWN_STATUSES:
                    self._mark_recovered(batch.local_id, attempt.index, "unknown")
                    reclassified["unknown"] += 1
                elif attempt.status == "downloading":
                    self._mark_recovered(batch.local_id, attempt.index, "download_failed")
                    reclassified["download_failed"] += 1
        return reclassified

    def _mark_recovered(self, batch_id: str, attempt_index: int, status: str) -> None:
        error = self._recovery_error(status)
        self._update_attempt(
            batch_id,
            attempt_index,
            lambda a: (
                setattr(a, "status", status),
                setattr(a, "error", error),
                setattr(a, "finished_at", utc_now_iso()),
            ),
        )
        self._emit(batch_id)

    @staticmethod
    def _recovery_error(status: str) -> dict[str, Any]:
        if status == "unknown":
            return {
                "code": "SUBMISSION_UNKNOWN",
                "message": "Image generation outcome is unknown after application restart",
            }
        return {
            "code": "DOWNLOAD_INTERRUPTED",
            "message": "Image download was interrupted before completion",
        }

    def public_batch(self, batch: ImageBatch) -> dict[str, Any]:
        attempts = [self._public_attempt(batch.local_id, attempt) for attempt in batch.attempts]
        request = batch.request if isinstance(batch.request, dict) else {}
        stored_reference = request.get("reference_image")
        reference_image_url = (
            f"/seedream-media/{quote(batch.local_id, safe='')}/reference"
            if isinstance(stored_reference, str) and stored_reference
            else None
        )
        return deepcopy({
            "local_id": batch.local_id,
            "request": batch.request,
            "status": self._aggregate_status(batch),
            "sequence": "",
            "reference_image_url": reference_image_url,
            "attempts": attempts,
            "created_at": batch.created_at,
            "updated_at": batch.updated_at,
        })

    @staticmethod
    def _assign_sequences(public_batches: list[dict[str, Any]]) -> None:
        """Assign stable circle sequence numbers to batches with identical parameters.

        Only batches whose prompt+model+resolution+ratio+count all match are
        sequenced together. Within a group, batches are ordered by creation time
        then local_id, and assigned ①②③ etc. Batches with no duplicates keep "".
        """
        groups: dict[str, list[dict[str, Any]]] = {}
        for batch in public_batches:
            signature = SeedreamBatchManager._batch_signature(batch)
            groups.setdefault(signature, []).append(batch)
        circled = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
        for group in groups.values():
            if len(group) < 2:
                continue
            group.sort(key=lambda b: (b.get("created_at", ""), b.get("local_id", "")))
            for index, batch in enumerate(group, start=1):
                batch["sequence"] = circled[index - 1] if index <= len(circled) else f"({index})"

    @staticmethod
    def _batch_signature(batch: dict[str, Any]) -> str:
        request = batch.get("request", {})
        if not isinstance(request, dict):
            request = {}
        return json.dumps(
            {
                "prompt": request.get("prompt", ""),
                "model": request.get("model", ""),
                "resolution": request.get("resolution", ""),
                "ratio": request.get("ratio", ""),
                "count": request.get("count", 0),
                "reference_image": bool(request.get("reference_image")),
            },
            sort_keys=True,
            ensure_ascii=False,
        )

    def _public_attempt(self, batch_id: str, attempt) -> dict[str, Any]:
        response = attempt.response if isinstance(attempt.response, dict) else {}
        usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
        total_tokens = usage.get("total_tokens")
        image_url = ""
        if attempt.local_path:
            image_url = f"/seedream-media/{quote(batch_id, safe='')}/image/{attempt.index}"
        data_list = response.get("data") if isinstance(response.get("data"), list) else []
        first_data = data_list[0] if data_list and isinstance(data_list[0], dict) else {}
        image_width = first_data.get("image_width")
        image_height = first_data.get("image_height")
        generation_layout = None
        if attempt.local_path:
            local_path = self._repository.resolve_asset(batch_id, attempt.local_path)
            try:
                with Image.open(local_path) as image:
                    generation_layout = read_generation_layout(
                        local_path, width=image.width, height=image.height
                    )
            except (OSError, ValueError):
                generation_layout = None
        return deepcopy({
            "local_id": attempt.local_id,
            "index": attempt.index,
            "status": attempt.status,
            "request": attempt.request,
            "response": response,
            "usage": usage,
            "total_tokens": total_tokens if isinstance(total_tokens, (int, float)) else None,
            "image_url": image_url,
            "image_width": image_width if isinstance(image_width, int) else None,
            "image_height": image_height if isinstance(image_height, int) else None,
            "local_path": attempt.local_path,
            "generation_layout": generation_layout,
            "url_expired": attempt.status == "download_failed" and self._is_url_expired(attempt),
            "created_at": attempt.created_at,
            "updated_at": attempt.updated_at,
            "finished_at": attempt.finished_at,
            "elapsed_seconds": self._elapsed_seconds(attempt),
            "error": attempt.error,
        })

    def _run_attempt_async(self, batch_id: str, attempt_index: int) -> None:
        with self._active_lock:
            self._active_attempts.setdefault(batch_id, set()).add(attempt_index)
        thread = threading.Thread(
            target=self._run_attempt,
            args=(batch_id, attempt_index),
            name=f"seedream-attempt-{attempt_index}",
            daemon=True,
        )
        thread.start()

    def _run_attempt(self, batch_id: str, attempt_index: int) -> None:
        batch = self._repository.get(batch_id)
        request = SeedreamRequest.from_dict(batch.request)
        if request.source == PLATFORM_SOURCE:
            self._run_platform_attempt(batch_id, attempt_index, request)
            return
        self._run_ark_attempt(batch_id, attempt_index, request)

    def _run_platform_attempt(self, batch_id: str, attempt_index: int, request: SeedreamRequest) -> None:
        """One synchronous platform image job per attempt (sync endpoint held in this thread)."""
        try:
            if self._platform is None:
                raise ValueError("Platform generation is not configured; sign in first")
            if request.reference_image:
                # Same convention as the Ark path: resolve the batch-relative
                # reference path before building the platform request.
                reference = Path(request.reference_image)
                if not reference.is_absolute():
                    reference = self._repository.resolve_asset(batch_id, request.reference_image)
                request.reference_image = str(reference)
            self._update_attempt(batch_id, attempt_index, lambda a: setattr(a, "status", "generating"))
            self._emit(batch_id)

            payload = self._build_platform_payload(request)
            response = self._platform.generate_image(payload)
            platform_status = str(response.get("platform_status", ""))

            if platform_status == "SUCCEEDED":
                # Persist the response BEFORE downloading the image.
                self._update_attempt(
                    batch_id,
                    attempt_index,
                    lambda a: (
                        setattr(a, "response", response),
                        setattr(a, "status", "downloading"),
                    ),
                )
                self._emit(batch_id)
                image_url = self._extract_image_url(response)
                local_path = self._download_platform_image(batch_id, attempt_index, response, image_url)
                self._update_attempt(
                    batch_id,
                    attempt_index,
                    lambda a: (
                        setattr(a, "local_path", local_path),
                        setattr(a, "status", "succeeded"),
                        setattr(a, "finished_at", utc_now_iso()),
                    ),
                )
                self._emit(batch_id)
                return

            error = parse_error_json(response.get("error")) or {
                "code": "PLATFORM_ERROR",
                "message": "平台生成未成功",
            }
            if platform_status == "SUBMISSION_UNKNOWN":
                # 平台已计费但结果未确定（制品转存失败等），保持 unknown 待人工确认。
                error = {**error, "code": error.get("code") or "SUBMISSION_UNKNOWN"}
                self._finish_platform_attempt(batch_id, attempt_index, "unknown", error)
            else:
                self._finish_platform_attempt(batch_id, attempt_index, "failed", error)
        except PlatformUnauthorizedError as error:
            self._finish_platform_attempt(
                batch_id, attempt_index, "failed", {"code": "UNAUTHORIZED", "message": error.message}
            )
        except PlatformError as error:
            self._finish_platform_attempt(
                batch_id, attempt_index, "failed", {"code": error.code, "message": error.message, "status": error.status}
            )
        except (OSError, TimeoutError) as error:
            self._finish_platform_attempt(
                batch_id,
                attempt_index,
                "unknown",
                {"code": "SUBMISSION_UNKNOWN", "message": f"平台请求未收到确定结果：{error}"},
            )
        except Exception as error:
            self._fail_attempt(batch_id, attempt_index, error)
        finally:
            with self._active_lock:
                indices = self._active_attempts.get(batch_id)
                if indices is not None:
                    indices.discard(attempt_index)
                    if not indices:
                        self._active_attempts.pop(batch_id, None)

    def _finish_platform_attempt(
        self, batch_id: str, attempt_index: int, status: str, error: dict[str, Any]
    ) -> None:
        self._update_attempt(
            batch_id,
            attempt_index,
            lambda a: (
                setattr(a, "status", status),
                setattr(a, "error", error),
                setattr(a, "finished_at", utc_now_iso()),
            ),
        )
        self._emit(batch_id)

    def _build_platform_payload(self, request: SeedreamRequest) -> dict[str, Any]:
        assert self._platform is not None
        payload: dict[str, Any] = {
            "idemKey": new_idem_key(),
            "model": platform_model_id(request.model),
            "prompt": _build_prompt_with_ratio(request.prompt, request.ratio),
            # 尺寸档沿用客户端取值（1K/1.5K/2K），与 Ark 文档口径一致；平台侧大小写不敏感。
            "size": request.resolution,
        }
        if request.reference_image:
            asset = self._platform.upload_asset(Path(request.reference_image))
            payload["image"] = str(asset["assetId"])
        return payload

    def _fail_attempt(self, batch_id: str, attempt_index: int, error: Exception) -> None:
        self._update_attempt(
            batch_id,
            attempt_index,
            lambda a, caught=error: (
                setattr(a, "status", "failed"),
                setattr(a, "error", self._error_dict(caught)),
                setattr(a, "finished_at", utc_now_iso()),
            ),
        )
        self._emit(batch_id)

    def _run_ark_attempt(self, batch_id: str, attempt_index: int, request: SeedreamRequest) -> None:
        response_persisted = False
        try:
            batch = self._repository.get(batch_id)
            attempt = batch.attempts[attempt_index]
            if request.reference_image:
                # The persisted request stores the reference image as a path
                # relative to the batch directory; resolve it before building
                # the Ark payload.
                request.reference_image = str(self._repository.resolve_asset(batch_id, request.reference_image))

            self._update_attempt(batch_id, attempt_index, lambda a: setattr(a, "status", "generating"))
            self._emit(batch_id)

            payload = build_api_payload(request)
            response = self._client.generate_image(payload)

            # Persist response BEFORE downloading the image.
            self._update_attempt(
                batch_id,
                attempt_index,
                lambda a: (
                    setattr(a, "response", response),
                    setattr(a, "status", "downloading"),
                ),
            )
            response_persisted = True
            self._emit(batch_id)

            image_url = self._extract_image_url(response)
            local_path = self._downloader.download_image(batch_id, attempt_index, image_url)

            self._update_attempt(
                batch_id,
                attempt_index,
                lambda a: (
                    setattr(a, "local_path", local_path),
                    setattr(a, "status", "succeeded"),
                    setattr(a, "finished_at", utc_now_iso()),
                ),
            )
            self._emit(batch_id)

        except SubmissionUnknownError as error:
            self._update_attempt(
                batch_id,
                attempt_index,
                lambda a, caught=error: (
                    setattr(a, "status", "unknown"),
                    setattr(a, "error", self._error_dict(caught)),
                    setattr(a, "finished_at", utc_now_iso()),
                ),
            )
            self._emit(batch_id)
        except ArkAPIError as error:
            self._update_attempt(
                batch_id,
                attempt_index,
                lambda a, caught=error: (
                    setattr(a, "status", "failed"),
                    setattr(a, "error", self._error_dict(caught)),
                    setattr(a, "finished_at", utc_now_iso()),
                ),
            )
            self._emit(batch_id)
        except Exception as error:
            status = "download_failed" if response_persisted else "failed"
            self._update_attempt(
                batch_id,
                attempt_index,
                lambda a, caught=error, s=status: (
                    setattr(a, "status", s),
                    setattr(a, "error", self._error_dict(caught)),
                    setattr(a, "finished_at", utc_now_iso()),
                ),
            )
            self._emit(batch_id)
        finally:
            with self._active_lock:
                indices = self._active_attempts.get(batch_id)
                if indices is not None:
                    indices.discard(attempt_index)
                    if not indices:
                        self._active_attempts.pop(batch_id, None)

    def _update_attempt(self, batch_id: str, attempt_index: int, updater) -> None:
        def batch_updater(batch: ImageBatch) -> None:
            if 0 <= attempt_index < len(batch.attempts):
                updater(batch.attempts[attempt_index])

        self._repository.update(batch_id, batch_updater)

    @staticmethod
    def _aggregate_status(batch: ImageBatch) -> str:
        if not batch.attempts:
            return "generating"
        statuses = [attempt.status for attempt in batch.attempts]
        if any(s in _ACTIVE_STATUSES for s in statuses):
            return "generating"
        if all(s == "succeeded" for s in statuses):
            return "completed"
        has_success = any(s == "succeeded" for s in statuses)
        if has_success:
            return "partially_complete"
        # No successes - all terminal. Check for unknown outcomes.
        has_unknown = any(s == "unknown" for s in statuses)
        if has_unknown:
            return "unknown"
        return "failed"

    @staticmethod
    def _extract_image_url(response: dict[str, Any]) -> str:
        data = response.get("data")
        if not isinstance(data, list) or not data:
            raise ArkResponseError("Ark response has no image data")
        first = data[0]
        if not isinstance(first, dict):
            raise ArkResponseError("Ark response image entry is not an object")
        url = first.get("url")
        if not isinstance(url, str) or not url:
            raise ArkResponseError("Ark response image has no URL")
        return url

    @staticmethod
    def _error_dict(error: Exception) -> dict[str, Any]:
        if isinstance(error, ArkAPIError):
            result: dict[str, Any] = {"code": error.code, "message": error.message, "status": error.status}
            if error.request_id:
                result["request_id"] = error.request_id
            return result
        if isinstance(error, SubmissionUnknownError):
            return {"code": "SUBMISSION_UNKNOWN", "message": "Image generation outcome is unknown"}
        return {"code": type(error).__name__, "message": str(error)}

    def _elapsed_seconds(self, attempt) -> int:
        created = self._parse_time(attempt.created_at)
        if created is None:
            return 0
        finished = self._parse_time(attempt.finished_at) if attempt.finished_at else None
        end = finished or self._now()
        return max(0, int((end - created).total_seconds()))

    @staticmethod
    def _parse_time(value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)

    def _is_url_expired(self, attempt) -> bool:
        """Check if the image URL has expired (24 hours after generation).

        Platform artifact pseudo-URLs follow the platform's 30-day artifact
        retention instead of the upstream 24-hour rule; they expire only when
        the download itself fails with the platform's expiry error.
        """
        response = attempt.response if isinstance(attempt.response, dict) else {}
        data = response.get("data")
        if isinstance(data, list) and data and isinstance(data[0], dict):
            url = data[0].get("url")
            if isinstance(url, str) and url.startswith("platform://"):
                return False
        created = response.get("created")
        if isinstance(created, (int, float)) and created > 0:
            try:
                generated_at = datetime.fromtimestamp(created, tz=UTC)
            except (OSError, ValueError):
                generated_at = None
        else:
            generated_at = None
        if generated_at is None:
            generated_at = self._parse_time(attempt.updated_at)
        if generated_at is None:
            return False
        age = self._now() - generated_at
        return age.total_seconds() > _URL_EXPIRY_SECONDS

    def _emit(self, batch_id: str) -> None:
        with suppress(Exception):
            batch = self._repository.get(batch_id)
            payload = self.public_batch(batch)
            with self._event_lock:
                sink = self._event_sink
            if sink is not None:
                sink("seedream-batch-updated", payload)
