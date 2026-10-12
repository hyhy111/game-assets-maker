"""Bounded, idempotent operations with explicit browser completion receipts."""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from typing import Any

from backend.agent_control.drafts import validate_video_duration
from backend.seedance.validation import ValidationError
from src.agent_tools.schemas import error_response, success_response

NAVIGATION_TARGETS = frozenset(
    {
        "projects",
        "project-create",
        "editor",
        "batch-trim",
        "image-create",
        "video-create",
        "image-detail",
        "video-detail",
        "settings",
    }
)


def submission_receipt(submitted: dict[str, Any]) -> dict[str, Any]:
    """Expose task identity and state, excluding raw provider and delivery data."""
    projected = {"success": submitted.get("success") is True}
    for kind in ("task", "batch"):
        if isinstance(submitted.get(kind), dict):
            projected[kind] = {
                key: value
                for key, value in submitted[kind].items()
                if key
                in {
                    "local_id",
                    "remote_id",
                    "remote_status",
                    "status",
                    "download_status",
                    "created_at",
                    "updated_at",
                    "finished_at",
                    "cache_status",
                }
            }
    if isinstance(submitted.get("error"), dict):
        projected["error"] = {"code": submitted["error"].get("code", "GENERATION_FAILED")}
    return projected


class AgentOperations:
    """Share pending requests between HTTP workers and the WebView bridge."""

    def __init__(self, window, api=None, timeout: float = 10):
        self.window = window
        self.api = api
        self.timeout = timeout
        self._lock = threading.Lock()
        self._requests: dict[str, dict[str, Any]] = {}

    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        operation = request.get("operation", "unknown") if isinstance(request, dict) else "unknown"
        request_id = request.get("request_id") if isinstance(request, dict) else None
        if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
            return error_response(operation, "INPUT_INVALID", "request_id must be a non-empty string (max 128)")
        if not isinstance(operation, str):
            return error_response("unknown", "INPUT_INVALID", "Operation must be a string")
        if operation not in {
            "ui.navigate",
            "generation.submit",
            "generation.permission",
            "draft.get",
            "draft.patch",
            "draft.restore",
            "draft.reuse",
            "step.get",
            "step.set",
            "step.run",
            "step.status",
            "artifacts.list",
            "artifacts.read",
            "roles.list",
            "animations.list",
            "batch.trim",
        }:
            return error_response(operation, "INPUT_INVALID", "Unsupported operation")
        with self._lock:
            existing = self._requests.get(request_id)
            if existing is not None and existing["request"] != request:
                return error_response(operation, "REQUEST_CONFLICT", "request_id already used for different input")
        if existing is not None:
            return self.status(request_id)
        payload = request.get("payload")
        if operation == "generation.permission":
            from src.utils.app_config import cli_generation_enabled

            return success_response(operation, {"enabled": cli_generation_enabled()})
        if operation == "generation.submit":
            from src.utils.app_config import cli_generation_enabled

            if not cli_generation_enabled():
                return error_response(
                    operation,
                    "CLI_GENERATION_DISABLED",
                    "Enable CLI generation in application settings after reviewing its confirmation",
                )
            if (
                not isinstance(payload, dict)
                or payload.get("kind") not in ("image", "video")
                or not isinstance(payload.get("request"), dict)
            ):
                return error_response(operation, "INPUT_INVALID", "Generation requires kind and request object")
            if payload["kind"] == "video":
                try:
                    validate_video_duration(payload["request"].get("duration", 5))
                except ValidationError as error:
                    return error_response(operation, error.code, str(error), {"field": error.field})
        elif operation.startswith(("step.", "artifacts.")) or operation in {
            "roles.list",
            "animations.list",
            "batch.trim",
        }:
            if not isinstance(payload, dict):
                return error_response(operation, "INPUT_INVALID", "Payload must be an object")
        elif operation in {"draft.get", "draft.patch", "draft.restore", "draft.reuse"}:
            if not isinstance(payload, dict) or payload.get("kind") not in ("image", "video"):
                return error_response(operation, "INPUT_INVALID", "Draft requires image or video kind")
            if operation == "draft.patch" and not isinstance(payload.get("patch"), dict):
                return error_response(operation, "INPUT_INVALID", "Draft patch must be an object")
        else:
            if (
                not isinstance(payload, dict)
                or not isinstance(payload.get("target"), str)
                or payload["target"] not in NAVIGATION_TARGETS
            ):
                return error_response(operation, "INPUT_INVALID", "Unsupported navigation target")
            if payload["target"] == "editor" and (
                not isinstance(payload.get("project_id"), str)
                or not payload["project_id"]
                or type(payload.get("step")) is not int
                or payload["step"] not in (1, 2, 3)
            ):
                return error_response(operation, "INPUT_INVALID", "Editor requires project_id and step 1–3")
            if payload["target"] in {"image-detail", "video-detail"} and (
                not isinstance(payload.get("local_id"), str) or not payload["local_id"]
            ):
                return error_response(operation, "INPUT_INVALID", "Detail requires local_id")
        if self.api is not None and request.get("projects_root") is not None:
            from pathlib import Path

            if Path(str(request["projects_root"])).resolve() != self.api.storage_locations.projects_root.resolve():
                return error_response(
                    operation, "ROOT_MISMATCH", "CLI project root differs from the running application"
                )
        if (
            self.api is not None
            and hasattr(self.api, "storage_migration_state")
            and self.api.storage_migration_state().get("restart_required") is True
        ):
            return error_response(operation, "RESTART_REQUIRED", "Restart the application after storage migration")
        if operation in {"roles.list", "animations.list"}:
            if self.api is None:
                return error_response(operation, "UI_NOT_RUNNING", "No application API")
            projects = self.api.get_projects()
            if operation == "roles.list":
                return success_response(operation, {"roles": self.api.get_roles()})
            return success_response(
                operation,
                {
                    "animations": [
                        project
                        for project in projects
                        if payload.get("role") is None or project.get("role") == payload["role"]
                    ]
                },
            )
        if operation.startswith("artifacts."):
            from backend.agent_control.artifacts import LocalArtifacts
            from src.utils.app_config import load_app_config

            try:
                if self.api is None:
                    raise ValueError("UI_NOT_RUNNING")
                artifacts = LocalArtifacts(self.api.storage_locations, (load_app_config()["seedance"]["api_key"],))
                data = artifacts.list(payload) if operation == "artifacts.list" else artifacts.read(payload.get("path"))
                return success_response(operation, data)
            except (ValueError, TypeError, OSError) as error:
                return error_response(operation, str(error), "Cannot read local artifact")
        if operation in {"step.get", "step.status"}:
            try:
                return success_response(operation, self._step_control().apply(operation, payload))
            except (ValueError, OSError, RuntimeError) as error:
                return error_response(operation, str(error), "Cannot read processing state")
        if self.window is None:
            return error_response(operation, "UI_NOT_RUNNING", "Desktop application is not ready")
        with self._lock:
            existing = self._requests.get(request_id)
            if existing is not None:
                if existing["request"] != request:
                    return error_response(operation, "REQUEST_CONFLICT", "request_id already used for different input")
                entry = existing
                dispatch = False
            else:
                # Refuse new work when full; never evict a receipt and silently replay it.
                if len(self._requests) >= 2048:
                    return error_response(
                        operation, "REQUEST_LIMIT", "Request capacity reached; restart the application"
                    )
                entry = {"request": deepcopy(request), "event": threading.Event(), "result": None}
                self._requests[request_id] = entry
                dispatch = True
        if dispatch:
            try:
                if operation == "batch.trim":
                    from backend.agent_control.trim import trim_projects

                    entry["applied"] = trim_projects(
                        self.api, payload.get("project_ids"), payload.get("mode", "global")
                    )
                    request = {**request, "applied": entry["applied"]}
                if operation == "draft.restore":
                    from backend.agent_control.drafts import restore_draft

                    entry["applied"] = restore_draft(self.api, payload["kind"], payload.get("local_id"))
                    request = {**request, "payload": {**payload, "patch": entry["applied"]["patch"]}}
                elif operation == "draft.reuse":
                    from backend.agent_control.artifacts import LocalArtifacts

                    field = payload.get("field")
                    if field not in (
                        {"reference_image"} if payload["kind"] == "image" else {"first_frame", "last_frame"}
                    ):
                        raise ValueError("INPUT_INVALID")
                    asset = LocalArtifacts(self.api.storage_locations).read(payload.get("path"))
                    entry["applied"] = {"provenance": asset}
                    request = {**request, "payload": {**payload, "patch": {field: asset["path"]}}}
                if operation in {"step.set", "step.run"}:
                    applied = self._step_control().apply(operation, payload)
                    entry["applied"] = applied
                    request = {**request, "applied": applied}
                detail = json.dumps(request, ensure_ascii=False)
                self.window.evaluate_js(
                    "window.dispatchEvent(new CustomEvent('agent-operation', { detail: " + detail + " }));"
                )
            except (ValueError, FileNotFoundError) as error:
                code = str(error) if str(error).isupper() else "INPUT_INVALID"
                with self._lock:
                    entry["result"] = error_response(
                        operation,
                        code,
                        str(error),
                        {
                            "request_id": request_id,
                            "ui_sync": "not_applied",
                            "persisted": entry.get("applied", {}).get("persisted", False),
                            "applied": entry.get("applied"),
                        },
                    )
                    entry["event"].set()
            except Exception as error:
                self.acknowledge(request_id, {"ok": False, "error": str(error) or "UI_DISPATCH_FAILED"})
        entry["event"].wait(self.timeout)
        return self.status(request_id)

    def _step_control(self):
        from backend.agent_control.steps import StepControl

        if self.api is None:
            raise ValueError("UI_NOT_RUNNING")
        return StepControl(self.api, self.api._process_api)

    def submit_generation(self, request_id: str, source: str) -> dict[str, Any]:
        """Submit once through the application after checking its current GUI source."""
        from src.utils.app_config import cli_generation_enabled

        with self._lock:
            entry = self._requests.get(request_id)
            if entry is None or entry["request"]["operation"] != "generation.submit":
                return {"success": False, "error": {"code": "REQUEST_NOT_FOUND"}}
            if entry.get("submission_started"):
                return deepcopy(
                    entry.get("submission_result") or {"success": False, "error": {"code": "SUBMISSION_UNKNOWN"}}
                )
            entry["submission_started"] = True
            payload = deepcopy(entry["request"]["payload"])
        if not cli_generation_enabled():
            result = {"success": False, "error": {"code": "CLI_GENERATION_DISABLED"}}
        elif source != "api-key":
            result = {"success": False, "error": {"code": "GENERATION_SOURCE_UNAVAILABLE"}}
        elif self.api is None:
            result = {"success": False, "error": {"code": "UI_NOT_RUNNING"}}
        else:
            try:
                create = self.api.seedance_create_task if payload["kind"] == "video" else self.api.seedream_create_batch
                result = create(payload["request"])
                task = result.get("task", {})
                if task.get("remote_status") == "submission_unknown":
                    result = {**result, "success": False, "error": {"code": "SUBMISSION_UNKNOWN"}}
                elif task.get("remote_status") == "failed":
                    result = {
                        **result,
                        "success": False,
                        "error": {"code": (task.get("error") or {}).get("code", "GENERATION_FAILED")},
                    }
            except Exception:
                result = {"success": False, "error": {"code": "SUBMISSION_UNKNOWN"}}
        with self._lock:
            entry["submission_result"] = deepcopy(result)
        return result

    def acknowledge(self, request_id: str, result: dict[str, Any]) -> bool:
        with self._lock:
            entry = self._requests.get(request_id)
            if entry is None or entry["result"] is not None or not isinstance(result, dict):
                return False
            operation = entry["request"]["operation"]
            submitted = entry.get("submission_result")
            if operation == "generation.submit" and (not submitted or submitted.get("success") is not True):
                code = (submitted or {}).get("error", {}).get("code", "SUBMISSION_UNKNOWN")
                entry["result"] = error_response(
                    operation,
                    code,
                    "Generation was rejected or its outcome is unknown; do not submit again automatically",
                    {
                        "request_id": request_id,
                        "persisted": bool((submitted or {}).get("task", {}).get("local_id")),
                        "local_id": (submitted or {}).get("task", {}).get("local_id"),
                    },
                )
            elif operation == "batch.trim" and entry.get("applied", {}).get("final") is False:
                entry["result"] = error_response(
                    operation,
                    "BATCH_TRIM_PARTIAL",
                    "Some selected animations could not be trimmed",
                    {
                        "request_id": request_id,
                        "ui_sync": "applied" if result.get("ok") else "failed",
                        **entry["applied"],
                    },
                )
            elif result.get("ok") is True:
                entry["result"] = success_response(
                    operation,
                    {
                        "request_id": request_id,
                        "ui_sync": "applied",
                        "persisted": submitted is not None or entry.get("applied", {}).get("persisted", False),
                        "result": submission_receipt(submitted)
                        if submitted is not None
                        else entry.get("applied", result.get("data", {})),
                    },
                )
            else:
                entry["result"] = error_response(
                    operation,
                    "UI_APPLY_FAILED",
                    "Interface could not apply the operation",
                    {
                        "request_id": request_id,
                        "ui_sync": "failed",
                        "persisted": (submitted is not None and submitted.get("success") is True)
                        or entry.get("applied", {}).get("persisted", False),
                        "applied": entry.get("applied"),
                        "submission": submission_receipt(submitted) if submitted is not None else None,
                        "reason": str(result.get("error", "UI_APPLY_FAILED")),
                    },
                )
            entry["event"].set()
            return True

    def status(self, request_id: str) -> dict[str, Any]:
        with self._lock:
            entry = self._requests.get(request_id)
            if entry is None:
                return error_response("request.status", "REQUEST_NOT_FOUND", "Unknown request_id")
            if entry["result"] is not None:
                return deepcopy(entry["result"])
            submitted = entry.get("submission_result") or {}
            local_id = (submitted.get("task") or submitted.get("batch") or {}).get("local_id")
            return error_response(
                entry["request"]["operation"],
                "UI_SYNC_TIMEOUT",
                "Awaiting interface receipt; query request status",
                {
                    "request_id": request_id,
                    "ui_sync": "pending",
                    "persisted": bool(local_id) or entry.get("applied", {}).get("persisted", False),
                    "applied": entry.get("applied"),
                    "local_id": local_id,
                    "submission_success": submitted.get("success"),
                    "submission_error": submitted.get("error", {}).get("code"),
                },
            )
