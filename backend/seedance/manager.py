"""Persistent orchestration for Seedance generation tasks."""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from backend.seedance.cache import CacheManager
from backend.seedance.client import ArkAPIError, ArkClient, ArkResponseError, SubmissionUnknownError
from backend.seedance.downloader import ResultDownloader
from backend.seedance.models import SeedanceRequest, SeedanceTask, platform_model_id
from backend.seedance.repository import TaskRepository
from backend.seedance.validation import build_api_payload, validate_request
from backend.platform.client import PlatformError, PlatformUnauthorizedError, new_idem_key
from backend.platform.last_frame import extract_last_frame
from backend.platform.video import PlatformVideoClient

EventSink = Callable[[str, dict[str, Any]], None]
ConfigSaver = Callable[[dict[str, Any]], None]

from backend.platform.sources import PLATFORM_SOURCE  # noqa: F401  (re-export，保持既有导入路径可用)

# 平台入参合法域（单一来源：manager 校验、API 预校验、报价预览三处共用）。
PLATFORM_RESOLUTIONS = ("480p", "720p", "1080p")
PLATFORM_RATIOS = ("adaptive", "16:9", "1:1", "4:3")
PLATFORM_MIN_DURATION = 4
PLATFORM_MAX_DURATION = 15

_ACTIVE_STATUSES = {"queued", "running"}
_CANCELLING_STATUS = "cancelling"
_POLLABLE_STATUSES = _ACTIVE_STATUSES | {_CANCELLING_STATUS}
_TERMINAL_STATUSES = {"succeeded", "failed", "expired", "cancelled"}
_REMOTE_STATUSES = _ACTIVE_STATUSES | _TERMINAL_STATUSES
_REMOTE_FIELDS = {"created_at", "updated_at", "content", "usage", "output", "error"}
_OUTPUT_FIELDS = {"resolution", "ratio", "duration", "fps", "generate_audio", "return_last_frame"}
_RETRY_AGE = timedelta(days=7)
_SUCCESS_INTERVAL_SECONDS = 10
_MAX_FAILURE_INTERVAL_SECONDS = 300
_EVENT_QUEUE_SIZE = 64
_EVENT_SHUTDOWN_TIMEOUT_SECONDS = 1.0


class SeedanceTaskManager:
    """Submit, poll, and recover local tasks without duplicating a POST."""

    def __init__(
        self,
        client: ArkClient,
        repository: TaskRepository,
        downloader: ResultDownloader,
        cache_manager: CacheManager,
        config: dict[str, Any],
        *,
        now: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] | None = None,
        config_saver: ConfigSaver | None = None,
        platform: PlatformVideoClient | None = None,
        platform_downloader: ResultDownloader | None = None,
    ) -> None:
        self._client = client
        self._repository = repository
        self._downloader = downloader
        self._cache_manager = cache_manager
        self._platform = platform
        self._platform_downloader = platform_downloader
        self._config = config.get("seedance", config)
        self._now = now or (lambda: datetime.now(UTC))
        self._monotonic = monotonic or time.monotonic
        self._config_saver = config_saver
        self._event_sink: EventSink | None = None
        self._event_queue: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue(maxsize=_EVENT_QUEUE_SIZE)
        self._event_lock = threading.Lock()
        self._event_stop = threading.Event()
        self._event_worker: threading.Thread | None = None
        self._scheduled_at: dict[str, float] = {}
        self._failure_counts: dict[str, int] = {}
        self._cancelling_inflight: set[str] = set()
        self._scheduler_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None

    def set_event_sink(self, sink: EventSink | None) -> None:
        with self._event_lock:
            self._event_sink = sink
            if sink is not None:
                self._ensure_event_worker_locked()

    def start(self) -> None:
        """Start one recovery worker and schedule all locally active tasks now."""
        with self._scheduler_lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._run_due_cleanup()
            self._recover_tasks()
            self._stop_event.clear()
            self._worker = threading.Thread(target=self._worker_loop, name="seedance-task-poller", daemon=True)
            self._worker.start()

    def shutdown(self) -> None:
        """Stop and join the sole worker; no task is cancelled during shutdown."""
        with self._scheduler_lock:
            worker = self._worker
            self._stop_event.set()
        if worker is not None and worker is not threading.current_thread():
            worker.join()
        with self._scheduler_lock:
            if self._worker is worker:
                self._worker = None
            self._scheduled_at.clear()
        self._shutdown_event_dispatcher()

    def create(self, request: SeedanceRequest) -> dict[str, Any]:
        """Copy and save the draft before its one and only remote POST."""
        return self._create(request)

    def _create(self, request: SeedanceRequest, retry_of: str | None = None) -> dict[str, Any]:
        if request.source == PLATFORM_SOURCE:
            return self._create_platform(request, retry_of)
        task = self._repository.create_draft(request)
        if retry_of is not None:
            task = self._repository.update(task.local_id, lambda current: setattr(current, "retry_of", retry_of))
        payload = build_api_payload(self._request_from_task(task))
        try:
            remote = self._client.create_task(payload)
            remote_id = remote.get("id")
            if not isinstance(remote_id, str) or not remote_id:
                raise SubmissionUnknownError("Ark accepted the request without a task ID")
        except ArkResponseError:
            unknown = SubmissionUnknownError("Ark task submission outcome is unknown")
            task = self._repository.update(
                task.local_id, lambda current, caught=unknown: self._mark_submission_unknown(current, caught)
            )
        except (SubmissionUnknownError, OSError, TimeoutError) as error:
            task = self._repository.update(
                task.local_id, lambda current, caught=error: self._mark_submission_unknown(current, caught)
            )
        except ArkAPIError as error:
            task = self._repository.update(
                task.local_id, lambda current, caught=error: self._mark_create_error(current, caught)
            )
        else:
            task = self._repository.update(task.local_id, lambda current: self._mark_created(current, remote))
            if task.remote_status == "succeeded":
                task = self._download_succeeded(task)
            elif task.remote_status in _ACTIVE_STATUSES:
                self._schedule(task.local_id, 0)
        self._emit("seedance-task-updated", task)
        return self.public_task(task)

    def _create_platform(self, request: SeedanceRequest, retry_of: str | None = None) -> dict[str, Any]:
        """Persist the draft, upload input images, then the one platform create call."""
        if self._platform is None:
            raise ValueError("Platform generation is not configured; sign in first")
        task = self._repository.create_draft(request)
        if retry_of is not None:
            task = self._repository.update(task.local_id, lambda current: setattr(current, "retry_of", retry_of))
        try:
            platform_request = self._build_platform_video_request(task)
            remote = self._platform.create_task(platform_request)
        except PlatformUnauthorizedError as error:
            task = self._repository.update(
                task.local_id, lambda current, caught=error: self._mark_create_error(current, caught)
            )
            self._emit("seedance-task-updated", task)
            raise
        except (PlatformError, ValueError) as error:
            task = self._repository.update(
                task.local_id, lambda current, caught=error: self._mark_create_error(current, caught)
            )
            self._emit("seedance-task-updated", task)
            return self.public_task(task)
        except (OSError, TimeoutError) as error:
            task = self._repository.update(
                task.local_id, lambda current, caught=error: self._mark_submission_unknown(current, caught)
            )
            self._emit("seedance-task-updated", task)
            return self.public_task(task)
        task = self._repository.update(task.local_id, lambda current: self._mark_created(current, remote))
        if task.remote_status == "succeeded":
            task = self._download_succeeded(task)
        elif task.remote_status in _ACTIVE_STATUSES:
            self._schedule(task.local_id, 0)
        self._emit("seedance-task-updated", task)
        return self.public_task(task)

    def _build_platform_video_request(self, task: SeedanceTask) -> dict[str, Any]:
        """Upload draft input images and assemble the platform job request JSON."""
        assert self._platform is not None
        from backend.seedance.models import MODEL_CAPABILITIES

        request = self._request_from_task(task)
        if request.return_last_frame:
            raise ValueError("平台模式不支持 return_last_frame（平台一任务一制品）")
        if request.duration == -1 or not PLATFORM_MIN_DURATION <= request.duration <= PLATFORM_MAX_DURATION:
            raise ValueError("平台模式时长须为 4~15 秒")
        if request.resolution not in PLATFORM_RESOLUTIONS:
            raise ValueError(f"平台模式分辨率仅支持 480p/720p/1080p：{request.resolution}")
        if request.ratio not in PLATFORM_RATIOS:
            raise ValueError(f"平台模式画面比例仅支持 adaptive/16:9/1:1/4:3：{request.ratio}")
        content: list[dict[str, Any]] = []
        prompt = request.prompt.strip()
        if prompt:
            content.append({"type": "text", "text": prompt})
        content.append({
            "type": "image_url",
            "assetId": self._upload_platform_asset(request.first_frame),
            "role": "first_frame",
        })
        if request.last_frame is not None:
            content.append({
                "type": "image_url",
                "assetId": self._upload_platform_asset(request.last_frame),
                "role": "last_frame",
            })
        return {
            "idemKey": new_idem_key(),
            "model": platform_model_id(request.model),
            "content": content,
            "resolution": request.resolution,
            "ratio": request.ratio,
            "duration": request.duration,
            "generate_audio": request.generate_audio,
        }

    def _upload_platform_asset(self, path: Path) -> str:
        assert self._platform is not None
        asset = self._platform.upload_asset(path)
        return str(asset["assetId"])

    def list_tasks(self) -> list[dict[str, Any]]:
        return [self.public_task(task) for task in self._repository.list()]

    def get_task(self, local_id: str) -> dict[str, Any]:
        return self.public_task(self._repository.get(local_id))

    def local_asset_paths(self, local_id: str) -> dict[str, dict[str, str]]:
        """Return existing, repository-contained local assets for trusted automation."""
        task = self._repository.get(local_id)

        def resolve_existing(paths: dict[str, str]) -> dict[str, str]:
            resolved_paths: dict[str, str] = {}
            for asset_key, relative_path in paths.items():
                if not isinstance(asset_key, str) or not isinstance(relative_path, str):
                    continue
                try:
                    asset_path = self._repository.resolve_asset(task.local_id, relative_path)
                except (FileNotFoundError, ValueError):
                    continue
                if asset_path.is_file() or asset_path.is_dir():
                    resolved_paths[asset_key] = str(asset_path.resolve())
            return resolved_paths

        return {
            "input_paths": resolve_existing(task.input_paths),
            "output_paths": resolve_existing(task.output_paths),
        }

    def sync_task(self, local_id: str) -> dict[str, Any]:
        task, _ = self._sync(local_id)
        return self.public_task(task)

    def cancel(self, local_id: str) -> dict[str, Any]:
        task = self._repository.get(local_id)
        if task.source == PLATFORM_SOURCE:
            return self._cancel_platform(local_id)
        return self._cancel_ark(local_id)

    def _cancel_platform(self, local_id: str) -> dict[str, Any]:
        """Platform cancel: QUEUED cancels immediately; in-flight becomes a
        cancel request that the poller confirms (CANCELLED/FAILED) later."""
        if self._platform is None:
            raise ValueError("Platform generation is not configured; sign in first")

        def claim(current: SeedanceTask) -> None:
            if current.remote_status in _TERMINAL_STATUSES:
                raise ValueError("已结束的任务无法取消")
            if current.remote_status == _CANCELLING_STATUS:
                return
            if current.remote_status not in _ACTIVE_STATUSES:
                raise ValueError("Only active Seedance tasks can be cancelled")
            current.remote_status = _CANCELLING_STATUS
            current.sync_status = {"state": _CANCELLING_STATUS, "last_synced_at": self._iso_now()}

        task = self._repository.update(local_id, claim)
        with self._scheduler_lock:
            self._cancelling_inflight.add(local_id)
        self._emit("seedance-task-updated", task)

        try:
            outcome = self._platform.delete_task(task.remote_id or "")
        except PlatformError as error:
            def restore(current: SeedanceTask, caught: Exception = error) -> None:
                if current.remote_status != _CANCELLING_STATUS:
                    return
                current.remote_status = "queued"
                current.sync_status = {
                    "state": "error",
                    "last_synced_at": self._iso_now(),
                    "error": self._error_dict(caught),
                }

            restored = self._repository.update(local_id, restore)
            self._emit("seedance-task-updated", restored)
            raise
        finally:
            with self._scheduler_lock:
                self._cancelling_inflight.discard(local_id)

        if outcome.get("status") == "cancelled":
            task = self._repository.update(local_id, self._mark_cancelled_after_recovery)
            self._unschedule(local_id)
            self._emit("seedance-task-updated", task)
            return self.public_task(task)
        # CANCEL_REQUESTED: keep polling until the platform confirms the cancel.
        task = self._repository.update(
            local_id,
            lambda current: setattr(current, "sync_status", {"state": "ok", "last_synced_at": self._iso_now()}),
        )
        self._schedule(local_id, _SUCCESS_INTERVAL_SECONDS)
        self._emit("seedance-task-updated", task)
        return self.public_task(task)

    def _cancel_ark(self, local_id: str) -> dict[str, Any]:
        def claim(current: SeedanceTask) -> None:
            if current.remote_status != "queued":
                raise ValueError("Only queued Seedance tasks can be cancelled")
            if current.remote_id is None:
                raise ValueError("Queued Seedance task has no remote ID")
            current.remote_status = _CANCELLING_STATUS
            current.sync_status = {"state": _CANCELLING_STATUS, "last_synced_at": self._iso_now()}

        task = self._repository.update(local_id, claim)
        with self._scheduler_lock:
            self._cancelling_inflight.add(local_id)
        self._emit("seedance-task-updated", task)

        def mark_cancelled(current: SeedanceTask) -> None:
            if current.remote_id != task.remote_id:
                return
            current.remote_status = "cancelled"
            current.finished_at = self._iso_now()
            current.sync_status = {"state": "ok", "last_synced_at": self._iso_now()}

        try:
            self._client.delete_task(task.remote_id)
        except Exception as error:
            def restore(current: SeedanceTask, caught: Exception = error) -> None:
                if current.remote_status != _CANCELLING_STATUS:
                    return
                current.remote_status = "queued"
                current.sync_status = {
                    "state": "error",
                    "last_synced_at": self._iso_now(),
                    "error": self._error_dict(caught),
                }

            restored = self._repository.update(local_id, restore)
            self._emit("seedance-task-updated", restored)
            raise
        finally:
            with self._scheduler_lock:
                self._cancelling_inflight.discard(local_id)

        task = self._repository.update(local_id, mark_cancelled)
        self._unschedule(local_id)
        self._emit("seedance-task-updated", task)
        return self.public_task(task)

    def retry_generation(self, local_id: str) -> dict[str, Any]:
        task = self._repository.get(local_id)
        request = self._request_from_task(task)
        return self._create(request, retry_of=task.local_id)

    def continue_generation(self, local_id: str) -> dict[str, Any]:
        """Create a new generation from a locally downloaded returned last frame."""
        with self._repository.task_lock(local_id):
            task = self._repository._read_unlocked(local_id)
            if task.remote_status != "succeeded" or task.download_status != "downloaded":
                raise ValueError("Only downloaded successful tasks can continue from a returned frame")
            if task.cache_status != "complete":
                raise ValueError("Cannot continue after task cache has been cleared")
            if task.source == PLATFORM_SOURCE:
                return self._continue_platform_unlocked(task)
            returned_relative_path = task.output_paths.get("returned_last_frame")
            if not isinstance(returned_relative_path, str):
                raise ValueError("Task does not have a returned last frame")
            try:
                returned_frame = self._repository.resolve_asset(task.local_id, returned_relative_path)
            except (FileNotFoundError, ValueError) as error:
                raise ValueError("Task returned last frame is unavailable") from error
            if not returned_frame.is_file():
                raise ValueError("Task returned last frame is unavailable")
            request = SeedanceRequest.from_dict({
                **task.request,
                "first_frame": str(returned_frame),
                "last_frame": None,
            })
            validate_request(request)
            return self._create(request, retry_of=task.local_id)

    def _continue_platform_unlocked(self, task: SeedanceTask) -> dict[str, Any]:
        """Derive the next segment's first frame locally (the platform does not
        return last frames), record it for preview, and create the follow-up job."""
        frame_path = self._extract_continuation_frame(task)
        task.output_paths["continuation_frame"] = "output/continuation_frame.png"
        task.updated_at = self._iso_now()
        self._repository._write_unlocked(task)
        request = SeedanceRequest.from_dict({
            **task.request,
            "first_frame": str(frame_path),
            "last_frame": None,
            "source": PLATFORM_SOURCE,
        })
        validate_request(request)
        return self._create(request, retry_of=task.local_id)

    def ensure_continuation_frame(self, local_id: str) -> Path:
        """Return the locally extracted continuation frame, deriving it on demand."""
        with self._repository.task_lock(local_id):
            task = self._repository._read_unlocked(local_id)
            existing = task.output_paths.get("continuation_frame")
            if isinstance(existing, str):
                try:
                    existing_path = self._repository.resolve_asset(local_id, existing)
                except (FileNotFoundError, ValueError):
                    existing_path = None
                if existing_path is not None and existing_path.is_file():
                    return existing_path
            frame_path = self._extract_continuation_frame(task)
            task.output_paths["continuation_frame"] = "output/continuation_frame.png"
            task.updated_at = self._iso_now()
            self._repository._write_unlocked(task)
            return frame_path

    def _extract_continuation_frame(self, task: SeedanceTask) -> Path:
        video_relative = task.output_paths.get("video")
        if not isinstance(video_relative, str):
            raise ValueError("任务没有可续跑的本地视频")
        try:
            video_path = self._repository.resolve_asset(task.local_id, video_relative)
        except (FileNotFoundError, ValueError) as error:
            raise ValueError("上一段成品不在本地缓存，无法续跑") from error
        if not video_path.is_file():
            raise ValueError("上一段成品不在本地缓存，无法续跑")
        frame_path = self._repository.resolve_asset(task.local_id, "output/continuation_frame.png")
        try:
            return extract_last_frame(video_path, frame_path)
        except ValueError as error:
            raise ValueError(f"无法从上一段视频抽取末帧：{error}") from error

    def retry_download(self, local_id: str) -> dict[str, Any]:
        task = self._repository.get(local_id)
        if task.remote_status != "succeeded":
            raise ValueError("Only succeeded Seedance tasks can retry downloads")
        self._require_output_urls(task)
        downloaded = self._downloader_for(task).download_task(task)
        self._emit("seedance-task-updated", downloaded)
        return self.public_task(downloaded)

    def wait(self, local_id: str, timeout_seconds: float) -> dict[str, Any]:
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds must not be negative")
        deadline = self._monotonic() + timeout_seconds
        task = self._repository.get(local_id)
        while task.remote_status not in _TERMINAL_STATUSES:
            if self._monotonic() >= deadline:
                return {"task": self.public_task(task), "timed_out": True}
            task, _ = self._sync(local_id)
            if task.remote_status in _TERMINAL_STATUSES:
                break
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                return {"task": self.public_task(task), "timed_out": True}
            self._stop_event.wait(min(0.1, remaining))
            task = self._repository.get(local_id)
        return {"task": self.public_task(task), "timed_out": False}

    def cache_status(self) -> dict[str, int]:
        return self._cache_manager.status()

    def clean_cache(self, older_than_days: int | None = None) -> dict[str, int]:
        days = self._retention_days() if older_than_days is None else older_than_days
        if days <= 0:
            return {"files_removed": 0, "bytes_released": 0, "tasks_cleared": 0, "protected_tasks_skipped": 0}
        return self._cache_manager.clean(days)

    def delete_task(self, local_id: str, allow_protected: bool = False) -> None:
        self._cache_manager.delete_task(local_id, allow_protected)

    def handoff(self, local_id: str, role: str, action: str) -> dict[str, Any]:
        """Create a project from a downloaded cached video and retain the link."""
        if not isinstance(role, str) or not role.strip():
            raise ValueError("role must not be empty")
        if not isinstance(action, str) or not action.strip():
            raise ValueError("action must not be empty")

        # Project creation performs full Step 1 extraction from this path. Holding
        # this task's lock prevents cache cleanup from removing the video midway.
        with self._repository.task_lock(local_id):
            task = self._repository._read_unlocked(local_id)
            video_path = self._handoff_video_path(task)
            project = self._cache_manager.project_api.create_project(
                role.strip(), action.strip(), str(video_path), frame_interval=1
            )
            project_id = project.get("id") if isinstance(project, dict) else None
            step1 = project.get("steps", {}).get("1", {}) if isinstance(project, dict) else {}
            if not isinstance(project_id, str) or not project_id:
                raise RuntimeError("Project creation did not return a project ID")
            if step1.get("data_ready") is not True:
                self._rollback_unready_project(project_id)
                raise RuntimeError("Project creation did not prepare Step 1 data")

            handoff = {
                "project_id": project_id,
                "role": project.get("role", role.strip()),
                "action": project.get("action", action.strip()),
                "created_at": self._iso_now(),
            }
            if not any(existing.get("project_id") == project_id for existing in task.handoffs):
                task.handoffs.append(handoff)
                task.updated_at = self._iso_now()
                self._repository._write_unlocked(task)

        self._emit("seedance-task-updated", task)
        return {"project_id": project_id, "task": self.public_task(task)}

    def public_task(self, task: SeedanceTask) -> dict[str, Any]:
        content = task.remote.get("content") if isinstance(task.remote.get("content"), dict) else {}
        output_urls = {
            key: value
            for key, value in content.items()
            if key in {"video_url", "last_frame_url"} and isinstance(value, str)
        }
        remote = {key: value for key, value in task.remote.items() if key != "content" and key != "error"}
        request = {
            key: value
            for key, value in task.request.items()
            if key not in {"first_frame", "last_frame", "api_key", "authorization"}
        }
        return deepcopy({
            "local_id": task.local_id,
            "remote_id": task.remote_id,
            "remote_status": task.remote_status,
            "source": task.source,
            "sync_status": task.sync_status,
            "download_status": task.download_status,
            "cache_status": task.cache_status,
            "protected": bool(task.handoffs),
            "request": request,
            "input_urls": {},
            "output_urls": output_urls,
            "file_size_bytes": self._video_file_size(task),
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "finished_at": task.finished_at,
            "download_url_received_at": task.download_url_received_at,
            "elapsed_seconds": self._elapsed_seconds(task),
            "remote": remote,
            "error": task.error,
            "retry_of": task.retry_of,
            "handoffs": task.handoffs,
        })

    def _video_file_size(self, task: SeedanceTask) -> int | None:
        video_asset = task.output_paths.get("video")
        if not isinstance(video_asset, str):
            return None
        try:
            video_path = self._repository.resolve_asset(task.local_id, video_asset)
            return video_path.stat().st_size if video_path.is_file() else None
        except (FileNotFoundError, OSError, ValueError):
            return None

    def _handoff_video_path(self, task: SeedanceTask):
        if task.download_status != "downloaded":
            raise ValueError("Seedance task video must be downloaded before handoff")
        video_asset = task.output_paths.get("video")
        if not isinstance(video_asset, str):
            raise ValueError("Seedance task no longer retains its cached video")
        try:
            video_path = self._repository.resolve_asset(task.local_id, video_asset)
        except (FileNotFoundError, ValueError) as error:
            raise ValueError("Seedance task no longer retains its cached video") from error
        if not video_path.is_file():
            raise ValueError("Seedance task no longer retains its cached video")
        try:
            with video_path.open("rb") as video_file:
                video_file.read(1)
        except OSError as error:
            raise ValueError("Seedance task cached video is not readable") from error
        return video_path

    def _rollback_unready_project(self, project_id: str) -> None:
        try:
            deleted = self._cache_manager.project_api.delete_project(project_id)
        except Exception as error:
            raise RuntimeError(f"Project creation did not prepare Step 1 data; rollback failed: {error}") from error
        if not deleted:
            raise RuntimeError("Project creation did not prepare Step 1 data; rollback failed")

    def _sync_for_worker(self, local_id: str) -> tuple[SeedanceTask, int | None]:
        persisted = self._repository.get(local_id)
        if persisted.remote_status == "succeeded" and persisted.cache_status == "complete":
            return self._recover_succeeded_download(persisted), None
        task, succeeded = self._sync(local_id)
        if task.remote_status not in _POLLABLE_STATUSES or task.remote_id is None:
            return task, None
        if succeeded:
            self._failure_counts.pop(local_id, None)
            return task, _SUCCESS_INTERVAL_SECONDS
        failures = self._failure_counts.get(local_id, 0) + 1
        self._failure_counts[local_id] = failures
        return task, min(10 * (2 ** (failures - 1)), _MAX_FAILURE_INTERVAL_SECONDS)

    def _remote_client_for(self, task: SeedanceTask):
        if task.source == PLATFORM_SOURCE:
            if self._platform is None:
                raise ValueError("Platform generation is not configured; sign in first")
            return self._platform
        return self._client

    def _downloader_for(self, task: SeedanceTask) -> ResultDownloader:
        if task.source == PLATFORM_SOURCE and self._platform_downloader is not None:
            return self._platform_downloader
        return self._downloader

    def _sync(self, local_id: str) -> tuple[SeedanceTask, bool]:
        task = self._repository.get(local_id)
        if task.remote_status not in _POLLABLE_STATUSES or task.remote_id is None:
            return task, True
        with self._scheduler_lock:
            if task.remote_status == _CANCELLING_STATUS and local_id in self._cancelling_inflight:
                return task, True
        try:
            response = self._remote_client_for(task).get_task(task.remote_id)
        except PlatformError as error:
            updated = self._repository.update(
                local_id, lambda current, caught=error: self._mark_sync_error(current, caught)
            )
            self._emit("seedance-task-updated", updated)
            return updated, False
        except ArkAPIError as error:
            if error.status == 404 and task.remote_status == _CANCELLING_STATUS:
                updated = self._repository.update(local_id, self._mark_cancelled_after_recovery)
                self._emit("seedance-task-updated", updated)
                return updated, True
            if error.status == 404 and self._created_before(task, self._now() - _RETRY_AGE):
                updated = self._repository.update(
                    local_id, lambda current, caught=error: self._mark_expired(current, caught)
                )
                self._emit("seedance-task-updated", updated)
                return updated, True
            updated = self._repository.update(
                local_id, lambda current, caught=error: self._mark_sync_error(current, caught)
            )
            self._emit("seedance-task-updated", updated)
            return updated, False
        except (ArkResponseError, OSError, TimeoutError) as error:
            updated = self._repository.update(
                local_id, lambda current, caught=error: self._mark_sync_error(current, caught)
            )
            self._emit("seedance-task-updated", updated)
            return updated, False

        updated = self._repository.update(local_id, lambda current: self._apply_remote(current, response))
        if updated.remote_status == "succeeded":
            updated = self._download_succeeded(updated)
        self._emit("seedance-task-updated", updated)
        return updated, True

    def _recover_tasks(self) -> None:
        for task in self._repository.list():
            if task.remote_status == "submitting":
                task = self._repository.update(
                    task.local_id,
                    lambda current: self._mark_submission_unknown(
                        current, SubmissionUnknownError("Application stopped during submission")
                    ),
                )
                self._emit("seedance-task-updated", task)
            elif task.remote_status in _POLLABLE_STATUSES and task.remote_id is not None:
                self._schedule(task.local_id, 0)
            elif task.remote_status == "succeeded" and task.cache_status == "complete":
                self._schedule(task.local_id, 0)

    def _recover_succeeded_download(self, task: SeedanceTask) -> SeedanceTask:
        if task.download_status == "failed" or self._downloader_for(task).is_download_confirmed(task):
            return task
        task = self._repository.update(
            task.local_id,
            lambda current: setattr(current, "download_status", "pending"),
        )
        recovered = self._download_succeeded(task)
        self._emit("seedance-task-updated", recovered)
        return recovered

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            now = self._monotonic()
            with self._scheduler_lock:
                due = [task_id for task_id, at in self._scheduled_at.items() if at <= now]
            if not due:
                self._stop_event.wait(self._next_wait_seconds(now))
                continue
            for local_id in due:
                if self._stop_event.is_set():
                    return
                try:
                    task, delay = self._sync_for_worker(local_id)
                except Exception:
                    self._unschedule(local_id)
                    continue
                if delay is None:
                    self._unschedule(local_id)
                else:
                    self._schedule(local_id, delay)

    def _next_wait_seconds(self, now: float) -> float:
        with self._scheduler_lock:
            if not self._scheduled_at:
                return 1.0
            return max(0.0, min(self._scheduled_at.values()) - now)

    def _schedule(self, local_id: str, delay: float) -> None:
        with self._scheduler_lock:
            self._scheduled_at[local_id] = self._monotonic() + delay

    def _unschedule(self, local_id: str) -> None:
        with self._scheduler_lock:
            self._scheduled_at.pop(local_id, None)
            self._failure_counts.pop(local_id, None)

    def _run_due_cleanup(self) -> None:
        last_cleanup = self._parse_time(self._config.get("last_cleanup_at"))
        if last_cleanup is not None and self._now() - last_cleanup < timedelta(days=1):
            return
        retention_days = self._retention_days()
        if retention_days > 0:
            self._cache_manager.clean(retention_days)
        timestamp = self._iso_now()
        updated_config = deepcopy(self._config)
        updated_config["last_cleanup_at"] = timestamp
        if self._config_saver is not None:
            self._config_saver(deepcopy(updated_config))
        self._config.clear()
        self._config.update(updated_config)

    def _retention_days(self) -> int:
        value = self._config.get("retention_days", 90)
        return value if isinstance(value, int) and value >= 0 else 90

    def _request_from_task(self, task: SeedanceTask) -> SeedanceRequest:
        request = SeedanceRequest.from_dict(task.request)
        try:
            request.first_frame = self._repository.resolve_asset(task.local_id, task.input_paths["first_frame"])
            last_frame = task.input_paths.get("last_frame")
            request.last_frame = self._repository.resolve_asset(task.local_id, last_frame) if last_frame else None
        except (KeyError, FileNotFoundError, ValueError) as error:
            raise ValueError("Seedance task no longer retains its input assets") from error
        if not request.first_frame.is_file() or (request.last_frame is not None and not request.last_frame.is_file()):
            raise ValueError("Seedance task no longer retains its input assets")
        return request

    @staticmethod
    def _require_output_urls(task: SeedanceTask) -> None:
        content = task.remote.get("content")
        if not isinstance(content, dict) or not isinstance(content.get("video_url"), str):
            raise ValueError("Succeeded Seedance task no longer retains its output URLs")
        if "last_frame_url" in content and not isinstance(content["last_frame_url"], str):
            raise ValueError("Succeeded Seedance task has an invalid returned-frame URL")

    def _mark_created(self, task: SeedanceTask, response: dict[str, Any]) -> None:
        task.remote_id = response["id"]
        task.remote_status = self._remote_status(response.get("status"))
        task.remote = self._mapped_remote(task, response)
        self._record_download_url_received_at(task)
        task.error = None
        task.sync_status = {"state": "ok", "last_synced_at": self._iso_now()}
        if task.remote_status in _TERMINAL_STATUSES:
            task.finished_at = self._iso_now()

    def _mark_submission_unknown(self, task: SeedanceTask, error: Exception) -> None:
        task.remote_status = "submission_unknown"
        task.sync_status = {"state": "error", "last_synced_at": self._iso_now(), "error": self._error_dict(error)}
        task.error = self._error_dict(error)

    def _mark_create_error(self, task: SeedanceTask, error: ArkAPIError) -> None:
        task.remote_status = "failed"
        task.error = self._error_dict(error)
        task.remote = {"error": task.error}
        task.sync_status = {"state": "error", "last_synced_at": self._iso_now(), "error": task.error}
        task.finished_at = self._iso_now()

    def _mark_sync_error(self, task: SeedanceTask, error: Exception) -> None:
        task.sync_status = {"state": "error", "last_synced_at": self._iso_now(), "error": self._error_dict(error)}

    def _mark_expired(self, task: SeedanceTask, error: ArkAPIError) -> None:
        task.remote_status = "expired"
        task.error = self._error_dict(error)
        task.remote["error"] = task.error
        task.sync_status = {"state": "error", "last_synced_at": self._iso_now(), "error": task.error}
        task.finished_at = self._iso_now()

    def _mark_cancelled_after_recovery(self, task: SeedanceTask) -> None:
        if task.remote_status != _CANCELLING_STATUS:
            return
        task.remote_status = "cancelled"
        task.finished_at = self._iso_now()
        task.sync_status = {"state": "ok", "last_synced_at": self._iso_now()}

    def _download_succeeded(self, task: SeedanceTask) -> SeedanceTask:
        try:
            return self._downloader_for(task).download_task(task)
        except Exception:
            return self._repository.get(task.local_id)

    def _apply_remote(self, task: SeedanceTask, response: dict[str, Any]) -> None:
        task.remote = self._mapped_remote(task, response)
        self._record_download_url_received_at(task)
        task.remote_status = self._remote_status(response.get("status"))
        remote_error = task.remote.get("error")
        task.error = remote_error if isinstance(remote_error, dict) else None
        task.sync_status = {"state": "ok", "last_synced_at": self._iso_now()}
        if task.remote_status in _TERMINAL_STATUSES and task.finished_at is None:
            task.finished_at = self._iso_now()

    def _record_download_url_received_at(self, task: SeedanceTask) -> None:
        content = task.remote.get("content")
        video_url = content.get("video_url") if isinstance(content, dict) else None
        if task.download_url_received_at is None and isinstance(video_url, str) and video_url.strip():
            task.download_url_received_at = self._iso_now()

    @staticmethod
    def _remote_status(value: Any) -> str:
        return value if value in _REMOTE_STATUSES else "queued"

    @staticmethod
    def _mapped_remote(task: SeedanceTask, response: dict[str, Any]) -> dict[str, Any]:
        remote = {key: response[key] for key in _REMOTE_FIELDS if key in response}
        remote.update({key: response[key] for key in _OUTPUT_FIELDS if key in response})
        if task.source == PLATFORM_SOURCE:
            # Platform facts the UI surfaces (状态确认中 / 服务端报价).
            for key in ("platform_status", "remote_status", "quote"):
                value = response.get(key)
                if value is not None:
                    remote[key] = value
        return remote

    @staticmethod
    def _error_dict(error: Exception) -> dict[str, Any]:
        if isinstance(error, ArkAPIError):
            return {"code": error.code, "message": error.message, "status": error.status}
        if isinstance(error, PlatformError):
            code = "UNAUTHORIZED" if isinstance(error, PlatformUnauthorizedError) else error.code
            return {"code": code, "message": error.message, "status": error.status}
        return {"code": type(error).__name__, "message": str(error)}

    def _elapsed_seconds(self, task: SeedanceTask) -> int:
        created = self._parse_time(task.created_at)
        if created is None:
            return 0
        finished = self._parse_time(task.finished_at) if task.finished_at else None
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

    def _created_before(self, task: SeedanceTask, cutoff: datetime) -> bool:
        created = self._parse_time(task.created_at)
        return created is not None and created <= cutoff

    def _iso_now(self) -> str:
        current = self._now()
        current = current.replace(tzinfo=UTC) if current.tzinfo is None else current.astimezone(UTC)
        return current.isoformat().replace("+00:00", "Z")

    def _emit(self, event_name: str, task: SeedanceTask) -> None:
        payload = self.public_task(task)
        with self._event_lock:
            if self._event_sink is None:
                return
            self._ensure_event_worker_locked()
            with suppress(queue.Full):
                self._event_queue.put_nowait((event_name, payload))

    def _ensure_event_worker_locked(self) -> None:
        if self._event_worker is not None and self._event_worker.is_alive():
            return
        self._event_stop.clear()
        self._event_worker = threading.Thread(
            target=self._event_loop, name="seedance-event-dispatcher", daemon=True
        )
        self._event_worker.start()

    def _event_loop(self) -> None:
        while not self._event_stop.is_set():
            try:
                event_name, payload = self._event_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if self._event_stop.is_set():
                return
            with self._event_lock:
                sink = self._event_sink
            if sink is not None:
                with suppress(Exception):
                    sink(event_name, payload)

    def _shutdown_event_dispatcher(self) -> None:
        with self._event_lock:
            worker = self._event_worker
            self._event_stop.set()
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=_EVENT_SHUTDOWN_TIMEOUT_SECONDS)
        with self._event_lock:
            if self._event_worker is worker and (worker is None or not worker.is_alive()):
                self._event_worker = None
