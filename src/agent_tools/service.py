"""Agent workflow service for CLI-oriented project operations."""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from backend.agent_control.drafts import validate_video_duration
from backend.seedance.validation import ValidationError
from src.agent_tools.explain import explain_step
from src.agent_tools.schemas import AgentErrorCode, error_response, redact_secret, success_response
from src.agent_tools.ui_client import AgentUIClient
from src.utils.data_paths import data_root
from src.utils.storage_locations import StorageLocations, storage_locations_from_config

if TYPE_CHECKING:
    from backend.api.batch_trim_api import BatchTrimAPI
    from backend.api.process_api import ProcessAPI
    from backend.api.project_api import ProjectAPI
    from backend.seedance.manager import SeedanceTaskManager


DEFAULT_STEP_PARAMS: dict[int, dict[str, Any]] = {
    1: {"frame_interval": 1, "start_frame": 0, "end_frame": -1, "fps": 30, "processed": False},
    2: {
        "model": "u2net",
        "post_process_mask": False,
        "alpha_matting": True,
        "alpha_matting_erode_size": 5,
        "alpha_matting_background_threshold": 120,
        "alpha_matting_foreground_threshold": 240,
        "edge_erode": 1,
        "fps": 10,
        "processed": False,
    },
    3: {
        "enabled": True,
        "green_intensity": 3,
        "feather_radius": 3,
        "min_hole_size": 5,
        "align_enabled": False,
        "align_h": False,
        "align_v": False,
        "use_padding": True,
        "padding_bottom": 10,
        "fps": 10,
        "processed": False,
    },
}


@contextmanager
def _cwd(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class AgentWorkflowService:
    """High-level workflow facade used by the Agent CLI."""

    def __init__(self, root: str | Path | None = None, *, ui_client: AgentUIClient | None = None):
        self.root = Path(root).resolve() if root is not None else data_root().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        # Freeze the storage resolution once, like the app composition root:
        # config is read under the service root, and every consumer shares it.
        from src.utils.app_config import load_app_config

        with _cwd(self.root):
            config = load_app_config()
        self._storage_locations: StorageLocations = storage_locations_from_config(config, data_root=self.root)
        self._project_api: ProjectAPI | None = None
        self._process_api: ProcessAPI | None = None
        self._batch_trim_api: BatchTrimAPI | None = None
        self._seedance_manager: SeedanceTaskManager | None = None
        self.ui_client = ui_client or AgentUIClient()

    @property
    def project_api(self) -> ProjectAPI:
        from backend.api.project_api import ProjectAPI

        if self._project_api is None:
            with _cwd(self.root):
                self._project_api = ProjectAPI(projects_root=self._storage_locations.projects_root)
        return self._project_api

    @property
    def process_api(self) -> ProcessAPI:
        from backend.api.process_api import ProcessAPI

        if self._process_api is None:
            with _cwd(self.root):
                self._process_api = ProcessAPI(window=None, projects_root=self._storage_locations.projects_root)
        return self._process_api

    @property
    def batch_trim_api(self) -> BatchTrimAPI:
        from backend.api.batch_trim_api import BatchTrimAPI

        if self._batch_trim_api is None:
            with _cwd(self.root):
                self._batch_trim_api = BatchTrimAPI(projects_root=self._storage_locations.projects_root)
        return self._batch_trim_api

    @property
    def seedance_manager(self) -> SeedanceTaskManager:
        """Compose the persisted Seedance manager only for a Seedance command."""
        if self._seedance_manager is None:
            from backend.seedance.cache import CacheManager
            from backend.seedance.client import ArkClient
            from backend.seedance.downloader import ResultDownloader
            from backend.seedance.manager import SeedanceTaskManager
            from backend.seedance.repository import TaskRepository
            from src.utils.app_config import load_app_config, save_app_config

            with _cwd(self.root):
                config = load_app_config()
                seedance = config["seedance"]
                cache_root = self._storage_locations.ai_video_cache_root.resolve()
                repository = TaskRepository(cache_root)
                self._seedance_manager = SeedanceTaskManager(
                    ArkClient(seedance["api_key"]),
                    repository,
                    ResultDownloader(repository),
                    CacheManager(repository, self.project_api),
                    config,
                    config_saver=lambda values: save_app_config({"seedance": values}),
                )
        return self._seedance_manager

    def close(self) -> None:
        """Join any Seedance helper threads before the short-lived CLI exits."""
        if self._seedance_manager is not None:
            self._seedance_manager.shutdown()
        if self._process_api is not None:
            self._process_api.shutdown()

    def _seedance_config(self) -> dict[str, Any]:
        from src.utils.app_config import load_app_config

        with _cwd(self.root):
            return load_app_config()["seedance"]

    def _seedance_api_key(self) -> str:
        api_key = self._seedance_config().get("api_key")
        return api_key if isinstance(api_key, str) else ""

    def _seedance_error(self, operation: str, error: Exception) -> dict[str, Any]:
        from backend.seedance.client import ArkAPIError, SubmissionUnknownError
        from backend.seedance.validation import ValidationError

        if isinstance(error, ValidationError):
            return error_response(
                operation=operation,
                code=error.code,
                message="Seedance request validation failed.",
                details={"field": error.field},
            )
        if isinstance(error, FileNotFoundError):
            code = AgentErrorCode.SEEDANCE_NOT_FOUND
            message = "Seedance task or asset was not found."
        elif isinstance(error, SubmissionUnknownError):
            code = AgentErrorCode.SEEDANCE_REQUEST_FAILED
            message = "Seedance task submission outcome is unknown."
        elif isinstance(error, (ArkAPIError, OSError, TimeoutError)):
            code = AgentErrorCode.SEEDANCE_REQUEST_FAILED
            message = "Unable to complete the Seedance request."
        else:
            code = AgentErrorCode.SEEDANCE_REQUEST_FAILED
            message = "Seedance request is invalid."
        return error_response(operation=operation, code=code, message=message)

    def _seedance_success(self, operation: str, data: dict[str, Any]) -> dict[str, Any]:
        return success_response(operation=operation, data=redact_secret(data, self._seedance_api_key()))

    def _project_seedance_task(self, task: dict[str, Any]) -> dict[str, Any]:
        """Allowlist a task for Agent output without exposing remote delivery data."""
        local_id = task.get("local_id")
        if not isinstance(local_id, str) or not local_id:
            raise ValueError("Seedance task is missing a local ID")

        projected: dict[str, Any] = {"local_id": local_id}
        for key in (
            "remote_id",
            "remote_status",
            "download_status",
            "cache_status",
            "created_at",
            "updated_at",
            "finished_at",
        ):
            value = task.get(key)
            if isinstance(value, str) or value is None:
                projected[key] = value
        if isinstance(task.get("elapsed_seconds"), (int, float)):
            projected["elapsed_seconds"] = task["elapsed_seconds"]
        if isinstance(task.get("protected"), bool):
            projected["protected"] = task["protected"]

        request = task.get("request")
        if isinstance(request, dict):
            safe_request = {}
            for key in (
                "prompt",
                "model",
                "resolution",
                "ratio",
                "duration",
                "generate_audio",
                "return_last_frame",
                "priority",
                "execution_expires_after",
            ):
                value = request.get(key)
                if isinstance(value, (str, int, float, bool)) or value is None:
                    safe_request[key] = value
            projected["request"] = safe_request

        sync_status = task.get("sync_status")
        if isinstance(sync_status, dict):
            safe_sync = {
                key: sync_status[key] for key in ("state", "last_synced_at") if isinstance(sync_status.get(key), str)
            }
            sync_error = sync_status.get("error")
            if isinstance(sync_error, dict):
                safe_error = {
                    key: sync_error[key] for key in ("code", "status") if isinstance(sync_error.get(key), (str, int))
                }
                if safe_error:
                    safe_sync["error"] = safe_error
            if safe_sync:
                projected["sync_status"] = safe_sync

        task_error = task.get("error")
        if isinstance(task_error, dict):
            safe_error = {
                key: task_error[key] for key in ("code", "status") if isinstance(task_error.get(key), (str, int))
            }
            if safe_error:
                projected["error"] = safe_error

        if isinstance(task.get("retry_of"), str) or task.get("retry_of") is None:
            projected["retry_of"] = task.get("retry_of")
        handoffs = task.get("handoffs")
        if isinstance(handoffs, list):
            projected["handoffs"] = [
                {
                    key: handoff[key]
                    for key in ("project_id", "role", "action", "created_at")
                    if isinstance(handoff, dict) and isinstance(handoff.get(key), str)
                }
                for handoff in handoffs
                if isinstance(handoff, dict)
            ]

        projected["local_paths"] = self.seedance_manager.local_asset_paths(local_id)
        return projected

    def seedance_create(
        self,
        *,
        first_frame: str,
        last_frame: str | None,
        prompt: str | None,
        model: str | None,
        resolution: str | None,
        ratio: str | None,
        duration: int | None,
        audio: bool,
        return_last_frame: bool,
        priority: int | None,
        expires_after: int | None,
    ) -> dict[str, Any]:
        config = self._seedance_config()
        request = {
            "first_frame": str(self._seedance_path(first_frame)),
            "last_frame": str(self._seedance_path(last_frame)) if last_frame else None,
            "prompt": prompt or "",
            "model": model or config["default_model"],
            "resolution": resolution or config["default_resolution"],
            "ratio": ratio or config["default_ratio"],
            "duration": duration if duration is not None else config["default_duration"],
            "generate_audio": audio or config["default_generate_audio"],
            "return_last_frame": return_last_frame or config["default_return_last_frame"],
            "priority": priority if priority is not None else config["default_priority"],
            "execution_expires_after": expires_after if expires_after is not None else config["default_expires_after"],
        }
        response = self.generation_submit("video", request)
        response["operation"] = "seedance.create"
        return response

    def selection_operation(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        from uuid import uuid4

        if self.ui_client.status().get("connected"):
            return AgentUIClient(host=self.ui_client.host, port=self.ui_client.port, timeout=15).operation(
                {
                    "request_id": str(uuid4()),
                    "operation": operation,
                    "projects_root": str(self._storage_locations.projects_root),
                    "payload": payload,
                }
            )
        if operation == "roles.list":
            return success_response(operation, {"roles": self.project_api.get_roles()})
        projects = self.project_api.get_projects()
        return success_response(
            operation,
            {
                "animations": [
                    item for item in projects if payload.get("role") is None or item.get("role") == payload["role"]
                ]
            },
        )

    def artifact_operation(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        from uuid import uuid4

        if self.ui_client.status().get("connected"):
            return self.ui_client.operation(
                {
                    "request_id": str(uuid4()),
                    "operation": operation,
                    "projects_root": str(self._storage_locations.projects_root),
                    "payload": payload,
                }
            )
        from backend.agent_control.artifacts import LocalArtifacts

        try:
            artifacts = LocalArtifacts(self._storage_locations, (self._seedance_api_key(),))
            data = artifacts.list(payload) if operation == "artifacts.list" else artifacts.read(payload.get("path"))
            return success_response(operation, data)
        except (ValueError, TypeError, OSError) as error:
            return error_response(operation, str(error), "Cannot read local artifact")

    def step_operation(self, operation: str, payload: dict[str, Any], request_id: str | None = None) -> dict[str, Any]:
        from uuid import uuid4

        client = AgentUIClient(host=self.ui_client.host, port=self.ui_client.port, timeout=15)
        status = client.status()
        if status.get("connected"):
            return client.operation(
                {
                    "request_id": request_id or str(uuid4()),
                    "operation": operation,
                    "projects_root": str(self._storage_locations.projects_root),
                    "payload": payload,
                }
            )
        if operation in {"step.get", "step.set"}:
            from backend.agent_control.steps import StepControl

            try:
                data = StepControl(self.project_api, self.process_api).apply(operation, payload)
                return success_response(operation, {**data, "ui_sync": "not_running"})
            except (ValueError, OSError, RuntimeError) as error:
                return error_response(operation, str(error), "Cannot update saved parameters")
        return error_response(operation, "UI_NOT_RUNNING", "Run the desktop application to track a processing task")

    def reuse_draft(
        self, kind: str, local_id: str | None = None, path: str | None = None, field: str | None = None
    ) -> dict[str, Any]:
        from uuid import uuid4

        return AgentUIClient(host=self.ui_client.host, port=self.ui_client.port, timeout=15).operation(
            {
                "request_id": str(uuid4()),
                "operation": "draft.restore" if local_id else "draft.reuse",
                "projects_root": str(self._storage_locations.projects_root),
                "payload": {"kind": kind, "local_id": local_id, "path": path, "field": field},
            }
        )

    def draft_operation(
        self, kind: str, patch: dict[str, Any] | None = None, request_id: str | None = None
    ) -> dict[str, Any]:
        from uuid import uuid4

        if kind == "video" and patch is not None and "duration" in patch:
            try:
                validate_video_duration(patch["duration"])
            except ValidationError as error:
                return error_response("draft.patch", error.code, str(error), {"field": error.field})
        return AgentUIClient(host=self.ui_client.host, port=self.ui_client.port, timeout=15).operation(
            {
                "request_id": request_id or str(uuid4()),
                "operation": "draft.get" if patch is None else "draft.patch",
                "projects_root": str(self._storage_locations.projects_root),
                "payload": {"kind": kind, "patch": patch},
            }
        )

    def generation_submit(self, kind: str, request: dict[str, Any], request_id: str | None = None) -> dict[str, Any]:
        from uuid import uuid4

        if kind == "video":
            try:
                validate_video_duration(request.get("duration", 5))
            except ValidationError as error:
                return error_response("generation.submit", error.code, str(error), {"field": error.field})
        client = AgentUIClient(host=self.ui_client.host, port=self.ui_client.port, timeout=15)
        return client.operation(
            {
                "request_id": request_id or str(uuid4()),
                "operation": "generation.submit",
                "projects_root": str(self._storage_locations.projects_root),
                "payload": {"kind": kind, "request": request},
            }
        )

    def generation_permission(self) -> dict[str, Any]:
        from uuid import uuid4

        return self.ui_client.operation(
            {"request_id": str(uuid4()), "operation": "generation.permission", "payload": {}}
        )

    def seedance_list(self, status: str | None = None) -> dict[str, Any]:
        try:
            tasks = self.seedance_manager.list_tasks()
            if status is not None:
                tasks = [task for task in tasks if task.get("remote_status") == status]
            return self._seedance_success(
                "seedance.list", {"tasks": [self._project_seedance_task(task) for task in tasks]}
            )
        except Exception as error:
            return self._seedance_error("seedance.list", error)

    def seedance_summary(self, local_task_id: str) -> dict[str, Any]:
        try:
            task = self.seedance_manager.get_task(local_task_id)
            return self._seedance_success("seedance.summary", {"task": self._project_seedance_task(task)})
        except Exception as error:
            return self._seedance_error("seedance.summary", error)

    def seedance_wait(self, local_task_id: str, timeout_seconds: float) -> dict[str, Any]:
        last_status: tuple[Any, Any] | None = None

        def report_transition(_event_name: str, task: dict[str, Any]) -> None:
            nonlocal last_status
            status = (task.get("remote_status"), task.get("download_status"))
            if status == last_status:
                return
            last_status = status
            progress = redact_secret(
                {"task": task.get("local_id"), "remote_status": status[0], "download_status": status[1]},
                self._seedance_api_key(),
            )
            print(json.dumps(progress, ensure_ascii=False), file=sys.stderr)

        try:
            manager = self.seedance_manager
            if hasattr(manager, "set_event_sink"):
                manager.set_event_sink(report_transition)
            result = manager.wait(local_task_id, timeout_seconds)
            task = self._project_seedance_task(result["task"])
            if result.get("timed_out"):
                timeout_details = redact_secret(
                    {"task": task, "timeout_seconds": timeout_seconds}, self._seedance_api_key()
                )
                return error_response(
                    operation="seedance.wait",
                    code=AgentErrorCode.WAIT_TIMEOUT,
                    message="Seedance wait timed out; the remote task remains active.",
                    details=timeout_details,
                )
            return self._seedance_success("seedance.wait", {"task": task, "timed_out": False})
        except Exception as error:
            return self._seedance_error("seedance.wait", error)

    def seedance_cancel(self, local_task_id: str) -> dict[str, Any]:
        try:
            task = self.seedance_manager.cancel(local_task_id)
            return self._seedance_success("seedance.cancel", {"task": self._project_seedance_task(task)})
        except Exception as error:
            return self._seedance_error("seedance.cancel", error)

    def seedance_handoff(self, local_task_id: str, role: str, action: str) -> dict[str, Any]:
        try:
            with _cwd(self.root):
                result = self.seedance_manager.handoff(local_task_id, role, action)
            if isinstance(result.get("task"), dict):
                result["task"] = self._project_seedance_task(result["task"])
            return self._seedance_success("seedance.handoff", result)
        except Exception as error:
            return self._seedance_error("seedance.handoff", error)

    def seedance_cache_status(self) -> dict[str, Any]:
        try:
            return self._seedance_success("seedance.cache.status", self.seedance_manager.cache_status())
        except Exception as error:
            return self._seedance_error("seedance.cache.status", error)

    def seedance_cache_clean(self, older_than_days: int | None) -> dict[str, Any]:
        try:
            return self._seedance_success("seedance.cache.clean", self.seedance_manager.clean_cache(older_than_days))
        except Exception as error:
            return self._seedance_error("seedance.cache.clean", error)

    def seedance_ui_open(self, local_task_id: str) -> dict[str, Any]:
        try:
            task = self._project_seedance_task(self.seedance_manager.get_task(local_task_id))
            ui = self.ui_client.open_seedance(local_task_id)
            data = {"task": task, "ui": ui}
            if not ui.get("opened"):
                data["message"] = "The desktop UI is not running; use this task summary locally."
            return self._seedance_success("seedance.ui-open", data)
        except Exception as error:
            return self._seedance_error("seedance.ui-open", error)

    def _seedance_path(self, raw_path: str) -> Path:
        path = Path(raw_path).expanduser()
        return (self.root / path).resolve() if not path.is_absolute() else path.resolve()

    def doctor(self) -> dict[str, Any]:
        from backend.seedance.models import MODEL_CAPABILITIES
        from src.utils.ai_cache_paths import ai_cache_root
        from src.utils.data_paths import models_root

        seedance = self._seedance_config()
        cache_root = ai_cache_root(seedance.get("cache_dir"), base_dir=self.root)
        resources_root = Path(getattr(sys, "_MEIPASS", self.root))
        checks = {
            "pyproject": (resources_root / "pyproject.toml").exists(),
            "backend_dir": (resources_root / "backend").is_dir(),
            "frontend_dir": (resources_root / "frontend").is_dir(),
            "project_dir": (self.root / "project").is_dir(),
            "frontend_dist": (resources_root / "frontend" / "dist").is_dir(),
            "u2net_model": (models_root() / "u2net.onnx").is_file(),
            "seedance_api_key_configured": bool(seedance.get("api_key")),
            "seedance_cache_writable": os.access(cache_root if cache_root.exists() else cache_root.parent, os.W_OK),
            "seedance_default_model_valid": seedance.get("default_model") in MODEL_CAPABILITIES,
        }
        warnings = []
        if not checks["frontend_dist"]:
            warnings.append("Frontend production build is missing: frontend/dist")
        if not checks["u2net_model"]:
            warnings.append("Default rembg model is missing from GAM User Data")

        return success_response(
            operation="doctor",
            data={"project_root": str(self.root), "checks": checks},
            warnings=warnings,
        )

    def create_project(
        self,
        role: str,
        action: str,
        video_path: str | Path,
        frame_interval: int = 1,
    ) -> dict[str, Any]:
        video = Path(video_path).expanduser()
        if not video.is_absolute():
            video = self.root / video
        video = video.resolve()

        if not video.is_file():
            return error_response(
                operation="project.create",
                code=AgentErrorCode.VIDEO_NOT_FOUND,
                message=f"Video file not found: {video}",
                details={"video_path": str(video)},
                next_actions=[{"command": "gam-agent doctor", "reason": "Check workspace"}],
            )

        try:
            with _cwd(self.root):
                project = self.project_api.create_project(role, action, str(video), frame_interval)
        except ValueError as exc:
            return error_response(
                operation="project.create",
                code=AgentErrorCode.PROJECT_EXISTS,
                message=str(exc),
                details={"role": role, "action": action},
            )

        project_id = project["id"]
        return success_response(
            operation="project.create",
            data={
                "project_id": project_id,
                "project_path": project["path"],
                "video_path": project["video_path"],
                "steps": project["steps"],
            },
            next_actions=[
                {
                    "command": f"gam-agent step run --project {project_id} --step 1",
                    "reason": "Run Step 1 frame extraction when you are ready.",
                }
            ],
        )

    def list_projects(self) -> dict[str, Any]:
        with _cwd(self.root):
            projects = self.project_api.get_projects()
        return success_response(operation="project.list", data={"projects": projects})

    def ui_navigate(
        self,
        target: str,
        project_id: str | None = None,
        step: int | None = None,
        local_id: str | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        from uuid import uuid4

        client = AgentUIClient(host=self.ui_client.host, port=self.ui_client.port, timeout=15)
        return client.operation(
            {
                "request_id": request_id or str(uuid4()),
                "operation": "ui.navigate",
                "projects_root": str(self._storage_locations.projects_root),
                "payload": {"target": target, "project_id": project_id, "step": step, "local_id": local_id},
            }
        )

    def ui_status(self) -> dict[str, Any]:
        return success_response(operation="ui.status", data={"ui": self.ui_client.status()})

    def ui_open(self, project_id: str, step: int) -> dict[str, Any]:
        return success_response(
            operation="ui.open",
            data={"ui": self._safe_ui_open(project_id, step)},
        )

    def project_summary(self, project_id: str) -> dict[str, Any]:
        with _cwd(self.root):
            project = self.project_api.get_project(project_id)
        if project is None:
            return error_response(
                operation="project.summary",
                code=AgentErrorCode.PROJECT_NOT_FOUND,
                message=f"Project not found: {project_id}",
                details={"project_id": project_id},
            )
        return success_response(operation="project.summary", data=project)

    def run_step(
        self,
        project_id: str,
        step: int,
        params: dict[str, Any] | None = None,
        timeout_seconds: float = 3600,
    ) -> dict[str, Any]:
        if step not in DEFAULT_STEP_PARAMS:
            return error_response(
                operation="step.run",
                code=AgentErrorCode.INVALID_STEP,
                message=f"Invalid step: {step}",
                details={"step": step},
            )

        with _cwd(self.root):
            project = self.project_api.get_project(project_id)
        if project is None:
            return error_response(
                operation="step.run",
                code=AgentErrorCode.PROJECT_NOT_FOUND,
                message=f"Project not found: {project_id}",
                details={"project_id": project_id},
            )

        from backend.agent_control.steps import merge_params

        try:
            with self.process_api.parameter_transaction(project_id):
                params_used = merge_params(self.process_api.get_step_params(project_id, step), step, params or {})
                if not self.process_api.save_step_params(project_id, step, params_used):
                    return error_response("step.run", "SAVE_FAILED", "Cannot save execution parameters")
        except ValueError as error:
            return error_response("step.run", "INPUT_INVALID", str(error))
        params_used["processed"] = True
        if step == 1:
            params_used["video_path"] = project.get("video_path")

        terminal_statuses = {"completed", "failed", "cancelled"}
        active_statuses = {"pending", "running"}
        deadline = time.monotonic() + timeout_seconds

        with _cwd(self.root):
            task_id = self.process_api.start_processing(project_id, step, params_used)
            while True:
                status = self.process_api.get_task_status(task_id)
                task_status = status.get("status")
                if task_status in terminal_statuses:
                    break
                if task_status not in active_statuses:
                    return error_response(
                        operation="step.run",
                        code=AgentErrorCode.PROCESS_FAILED,
                        message=f"Step {step} returned an unknown task status",
                        details={
                            "project_id": project_id,
                            "step": step,
                            "task_id": task_id,
                            "task": status,
                        },
                    )
                if time.monotonic() >= deadline:
                    self.process_api.cancel_task(task_id)
                    return error_response(
                        operation="step.run",
                        code=AgentErrorCode.PROCESS_FAILED,
                        message=f"Step {step} timed out after {timeout_seconds} seconds",
                        details={
                            "project_id": project_id,
                            "step": step,
                            "task_id": task_id,
                            "timeout_seconds": timeout_seconds,
                        },
                    )
                time.sleep(0.05)

        if status.get("status") != "completed":
            return error_response(
                operation="step.run",
                code=AgentErrorCode.PROCESS_FAILED,
                message=f"Step {step} did not complete",
                details={"project_id": project_id, "step": step, "task_id": task_id, "task": status},
            )

        ui = self._safe_ui_open(project_id, step)

        return success_response(
            operation="step.run",
            data={
                "project_id": project_id,
                "step": step,
                "status": "completed",
                "requires_review": step in {2, 3},
                "task_id": task_id,
                "output_dir": str(
                    Path(project["path"]) / "output" / {1: "01_frames", 2: "02_no_bg", 3: "03_hole_punched"}[step]
                ),
                "params_used": params_used,
                "project": self.project_summary(project_id)["data"],
                "ui": ui,
            },
        )

    def batch_trim(self, project_ids: list[str], mode: str = "global") -> dict[str, Any]:
        if self.ui_client.status().get("connected"):
            return self.selection_operation("batch.trim", {"project_ids": project_ids, "mode": mode})
        if mode not in {"global", "individual"}:
            return error_response(
                operation="batch-trim",
                code=AgentErrorCode.CONFIG_INVALID,
                message=f"Unsupported batch trim mode: {mode}",
                details={"mode": mode},
            )

        with _cwd(self.root):
            source_status = self.batch_trim_api.check_projects(project_ids)

        missing_sources = [item for item in source_status if item.get("status") == "unavailable"]
        if source_status and len(missing_sources) == len(source_status):
            return error_response(
                operation="batch-trim",
                code=AgentErrorCode.BATCH_TRIM_NO_SOURCE,
                message="No projects have Step 2 or Step 3 output to trim.",
                details={"projects": missing_sources},
            )

        with _cwd(self.root):
            raw_results = self.batch_trim_api.execute_trim({"projectIds": project_ids, "mode": mode})

        from backend.agent_control.trim import normalize_trim_results

        normalized = normalize_trim_results(raw_results, project_ids, mode)
        if not normalized["final"]:
            return error_response(
                "batch-trim", "BATCH_TRIM_PARTIAL", "Some selected animations could not be trimmed", normalized
            )
        return success_response(operation="batch-trim", data=normalized)

    def explain(self, step: int, parameter: str | None = None) -> dict[str, Any]:
        try:
            explanation = explain_step(step, parameter)
        except ValueError as exc:
            return error_response(
                operation="step.explain",
                code=AgentErrorCode.INVALID_STEP,
                message=str(exc),
                details={"step": step, "parameter": parameter},
            )
        return success_response(operation="step.explain", data=explanation)

    def _safe_ui_open(self, project_id: str, step: int) -> dict[str, Any]:
        try:
            return self.ui_client.open_step(project_id, step)
        except Exception as exc:
            return {
                "connected": False,
                "opened": False,
                "message": "The UI could not be opened.",
                "error": str(exc),
            }
