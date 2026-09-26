"""Explicit, bounded manual smoke test for the paid Seedance API."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import cv2

from backend.seedance.client import ArkAPIError, SubmissionUnknownError
from backend.seedance.models import SeedanceRequest
from backend.seedance.validation import ValidationError, build_api_payload
from src.agent_tools.schemas import redact_secret
from src.utils.ai_cache_paths import ai_video_cache_root
from src.utils.app_config import load_app_config


@dataclass(frozen=True, slots=True)
class SmokeOptions:
    first_frame: Path | None = None
    retry_task: str | None = None
    continue_task: str | None = None
    confirm_paid_request: bool = False
    confirm_additional_paid_request: bool = False
    check_connection: bool = False
    timeout_seconds: float = 300.0
    report_path: Path | None = None


class SmokeBackend(Protocol):
    def check_connection(self) -> None: ...

    def create(self, request: SeedanceRequest) -> dict[str, Any]: ...

    def get_task(self, local_id: str) -> dict[str, Any]: ...

    def retry(self, local_id: str) -> dict[str, Any]: ...

    def continue_task(self, local_id: str) -> dict[str, Any]: ...

    def wait(self, local_id: str, timeout_seconds: float) -> dict[str, Any]: ...

    def local_asset_paths(self, local_id: str) -> dict[str, dict[str, str]]: ...

    def close(self) -> None: ...


class _NoProjectAccess:
    def get_project(self, _project_id: str) -> None:
        return None

    def create_project(self, _role: str, _action: str, _video_path: str, frame_interval: int = 1) -> dict:
        raise RuntimeError("Project handoff is not available in the paid smoke command")

    def delete_project(self, _project_id: str) -> bool:
        return False


class ProductionSmokeBackend:
    """Compose real Seedance collaborators only after every paid guard passes."""

    def __init__(self, api_key: str, cache_root: Path) -> None:
        from backend.seedance.cache import CacheManager
        from backend.seedance.client import ArkClient
        from backend.seedance.downloader import ResultDownloader
        from backend.seedance.manager import SeedanceTaskManager
        from backend.seedance.repository import TaskRepository

        self._client = ArkClient(api_key)
        repository = TaskRepository(cache_root)
        self._manager = SeedanceTaskManager(
            self._client,
            repository,
            ResultDownloader(repository),
            CacheManager(repository, _NoProjectAccess()),
            {"retention_days": 0, "last_cleanup_at": None},
        )

    def check_connection(self) -> None:
        self._client.list_tasks(page_size=1)

    def create(self, request: SeedanceRequest) -> dict[str, Any]:
        return self._manager.create(request)

    def get_task(self, local_id: str) -> dict[str, Any]:
        return self._manager.get_task(local_id)

    def retry(self, local_id: str) -> dict[str, Any]:
        return self._manager.retry_generation(local_id)

    def continue_task(self, local_id: str) -> dict[str, Any]:
        return self._manager.continue_generation(local_id)

    def wait(self, local_id: str, timeout_seconds: float) -> dict[str, Any]:
        return self._manager.wait(local_id, timeout_seconds)

    def local_asset_paths(self, local_id: str) -> dict[str, dict[str, str]]:
        return self._manager.local_asset_paths(local_id)

    def close(self) -> None:
        self._manager.shutdown()


ConfigLoader = Callable[[], dict[str, Any]]
BackendFactory = Callable[[str, Path], SmokeBackend]
SummarySink = Callable[[dict[str, Any]], None]


def _create_request(options: SmokeOptions) -> SeedanceRequest:
    if options.first_frame is None:
        raise ValueError("A first frame is required for a new smoke-test task")
    return SeedanceRequest(
        first_frame=options.first_frame.resolve(),
        model="mini",
        resolution="480p",
        ratio="adaptive",
        duration=4,
        generate_audio=False,
        return_last_frame=False,
        priority=0,
        execution_expires_after=3600,
    )


def _create_summary(request: SeedanceRequest) -> dict[str, Any]:
    return {
        "action": "create",
        "model": request.model,
        "resolution": request.resolution,
        "ratio": request.ratio,
        "duration": request.duration,
        "generate_audio": request.generate_audio,
        "return_last_frame": request.return_last_frame,
        "input": request.first_frame.name,
        "request_count": 1,
    }


def _existing_task_summary(action: str, local_id: str, task: dict[str, Any]) -> dict[str, Any]:
    request = task.get("request") if isinstance(task.get("request"), dict) else {}
    return {
        "action": action,
        "model": request.get("model"),
        "resolution": request.get("resolution"),
        "ratio": request.get("ratio"),
        "duration": request.get("duration"),
        "input": f"cached task {local_id}",
        "request_count": 1,
    }


def _selected_action(options: SmokeOptions) -> tuple[str, str | None]:
    selected = [
        ("create", None) if options.first_frame is not None else None,
        ("retry", options.retry_task) if options.retry_task else None,
        ("continue", options.continue_task) if options.continue_task else None,
    ]
    actions = [item for item in selected if item is not None]
    if len(actions) != 1:
        raise ValueError("Select exactly one of first frame, retry task, or continue task")
    return actions[0]


def _media_is_readable(path: Path) -> bool:
    capture = cv2.VideoCapture(str(path))
    try:
        readable, _frame = capture.read()
        return capture.isOpened() and readable
    finally:
        capture.release()


def _finish(result: dict[str, Any], *, secret: str, report_path: Path | None) -> dict[str, Any]:
    safe_result = redact_secret(result, secret)
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(safe_result, ensure_ascii=False, indent=2), encoding="utf-8")
    return safe_result


def run_paid_smoke(
    options: SmokeOptions,
    *,
    config_loader: ConfigLoader = load_app_config,
    backend_factory: BackendFactory,
    summary_sink: SummarySink = lambda _summary: None,
) -> dict[str, Any]:
    config = config_loader().get("seedance", {})
    api_key = config.get("api_key")
    secret = api_key if isinstance(api_key, str) else ""
    try:
        action, source_task = _selected_action(options)
        request = _create_request(options) if action == "create" else None
        if request is not None:
            build_api_payload(request)
    except (ValidationError, ValueError) as error:
        code = error.code if isinstance(error, ValidationError) else "INVALID_SMOKE_ACTION"
        field = error.field if isinstance(error, ValidationError) else None
        return {
            "ok": False,
            "status": "validation_failed",
            "error": {"code": code, "field": field},
        }
    summary: dict[str, Any] = {"action": action, "request_count": 1}

    if not secret:
        return {
            "ok": False,
            "status": "auth_failed",
            "error": {"code": "API_KEY_NOT_CONFIGURED"},
        }

    if request is not None:
        summary = _create_summary(request)
        summary_sink(redact_secret(summary, secret))
        if not options.confirm_paid_request and not options.check_connection:
            return {
                "ok": False,
                "status": "confirmation_required",
                "message": "Refusing to create a paid Seedance task without explicit confirmation.",
                "summary": summary,
            }

    cache_root = ai_video_cache_root(config.get("cache_dir"))
    backend: SmokeBackend | None = None
    stage = "connection"
    try:
        backend = backend_factory(secret, cache_root.resolve())
        if request is None:
            assert source_task is not None
            summary = _existing_task_summary(action, source_task, backend.get_task(source_task))
            summary_sink(redact_secret(summary, secret))
        if options.check_connection:
            backend.check_connection()
        if not options.confirm_paid_request:
            return _finish(
                {
                    "ok": False,
                    "status": "confirmation_required",
                    "message": "Refusing to create a paid Seedance task without explicit confirmation.",
                    "summary": summary,
                },
                secret=secret,
                report_path=options.report_path,
            )
        if request is None and not options.confirm_additional_paid_request:
            return _finish(
                {
                    "ok": False,
                    "status": "confirmation_required",
                    "message": "Retry and continuation require a second explicit paid-request confirmation.",
                    "summary": summary,
                },
                secret=secret,
                report_path=options.report_path,
            )
        stage = "submission"
        if action == "create":
            assert request is not None
            created = backend.create(request)
        elif action == "retry":
            assert source_task is not None
            created = backend.retry(source_task)
        else:
            assert source_task is not None
            created = backend.continue_task(source_task)
        local_id = created.get("local_id")
        if not isinstance(local_id, str) or not local_id:
            raise ValueError("Seedance create result is missing a local task ID")
        if created.get("remote_status") == "submission_unknown":
            return _finish(
                {"ok": False, "status": "submission_unknown", "summary": summary, "task": {"local_id": local_id}},
                secret=secret,
                report_path=options.report_path,
            )
        if created.get("remote_status") == "failed":
            error = created.get("error") if isinstance(created.get("error"), dict) else {}
            status = "auth_failed" if error.get("status") in {401, 403} else "remote_failed"
            return _finish(
                {"ok": False, "status": status, "summary": summary, "task": {"local_id": local_id}},
                secret=secret,
                report_path=options.report_path,
            )
        stage = "polling"
        waited = backend.wait(local_id, options.timeout_seconds)
        task = waited["task"]
        if waited.get("timed_out"):
            return _finish(
                {"ok": False, "status": "timeout", "summary": summary, "task": {"local_id": local_id}},
                secret=secret,
                report_path=options.report_path,
            )
        if task.get("remote_status") != "succeeded":
            return _finish(
                {
                    "ok": False,
                    "status": "remote_failed",
                    "summary": summary,
                    "task": {"local_id": local_id, "remote_status": task.get("remote_status")},
                },
                secret=secret,
                report_path=options.report_path,
            )
        if task.get("download_status") != "downloaded":
            return _finish(
                {
                    "ok": False,
                    "status": "download_failed",
                    "summary": summary,
                    "task": {"local_id": local_id, "download_status": task.get("download_status")},
                },
                secret=secret,
                report_path=options.report_path,
            )
        stage = "download"
        paths = backend.local_asset_paths(local_id)
        video_path = Path(paths["output_paths"]["video"])
        readable = _media_is_readable(video_path)
        result = {
            "ok": readable,
            "status": "success" if readable else "download_failed",
            "summary": summary,
            "task": {
                "local_id": local_id,
                "remote_status": task.get("remote_status"),
                "download_status": task.get("download_status"),
                "media_readable": readable,
            },
        }
        return _finish(result, secret=secret, report_path=options.report_path)
    except ArkAPIError as error:
        status = "auth_failed" if error.status in {401, 403} else "remote_failed"
        return _finish(
            {
                "ok": False,
                "status": status,
                "summary": summary,
                "error": {"code": error.code, "status": error.status},
            },
            secret=secret,
            report_path=options.report_path,
        )
    except SubmissionUnknownError:
        return _finish(
            {"ok": False, "status": "submission_unknown", "summary": summary},
            secret=secret,
            report_path=options.report_path,
        )
    except (OSError, ValueError, KeyError) as error:
        status = "download_failed" if stage == "download" else "remote_failed"
        return _finish(
            {
                "ok": False,
                "status": status,
                "summary": summary,
                "error": {"code": type(error).__name__},
            },
            secret=secret,
            report_path=options.report_path,
        )
    finally:
        if backend is not None:
            with suppress(Exception):
                backend.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gam-seedance-smoke",
        description="Run one explicitly confirmed paid Seedance compatibility smoke test.",
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--first-frame", type=Path)
    action.add_argument("--retry-task")
    action.add_argument("--continue-task")
    parser.add_argument("--confirm-paid-request", action="store_true")
    parser.add_argument("--confirm-additional-paid-request", action="store_true")
    parser.add_argument("--check-connection", action="store_true")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--report", type=Path)
    return parser


def main(
    argv: list[str] | None = None,
    *,
    config_loader: ConfigLoader = load_app_config,
    backend_factory: BackendFactory = ProductionSmokeBackend,
) -> int:
    args = _build_parser().parse_args(argv)
    options = SmokeOptions(
        first_frame=args.first_frame,
        retry_task=args.retry_task,
        continue_task=args.continue_task,
        confirm_paid_request=args.confirm_paid_request,
        confirm_additional_paid_request=args.confirm_additional_paid_request,
        check_connection=args.check_connection,
        timeout_seconds=args.timeout,
        report_path=args.report,
    )
    result = run_paid_smoke(
        options,
        config_loader=config_loader,
        backend_factory=backend_factory,
        summary_sink=lambda summary: print(json.dumps(summary, ensure_ascii=False), file=sys.stderr),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "success" else 1


def installed_main(argv: list[str] | None = None) -> int:
    """Run the installed smoke CLI against the stable per-user GAM data root."""
    os.environ.setdefault("GAM_DATA_MODE", "installed")
    return main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
