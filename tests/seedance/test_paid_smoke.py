from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from backend.seedance.client import ArkAPIError, SubmissionUnknownError
from scripts.run_tests import build_default_stages
from src.cli.seedance_paid_smoke import SmokeOptions, _build_parser, main, run_paid_smoke


def _image(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (300, 300), "white").save(path)
    return path


def _video(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (16, 16))
    assert writer.isOpened()
    writer.write(np.zeros((16, 16, 3), dtype=np.uint8))
    writer.release()
    return path


class FakeBackend:
    def __init__(self, video_path: Path) -> None:
        self.video_path = video_path
        self.calls: list[object] = []

    def check_connection(self) -> None:
        self.calls.append("check_connection")

    def create(self, request):
        self.calls.append(("create", request))
        return {"local_id": "local-1", "remote_status": "queued", "download_status": "pending"}

    def get_task(self, local_id: str):
        self.calls.append(("get_task", local_id))
        return {
            "local_id": local_id,
            "request": {"model": "mini", "resolution": "480p", "ratio": "adaptive", "duration": 4},
        }

    def retry(self, local_id: str):
        self.calls.append(("retry", local_id))
        return {"local_id": "retry-1", "remote_status": "queued", "download_status": "pending"}

    def continue_task(self, local_id: str):
        self.calls.append(("continue", local_id))
        return {"local_id": "continue-1", "remote_status": "queued", "download_status": "pending"}

    def wait(self, local_id: str, timeout_seconds: float):
        self.calls.append(("wait", local_id, timeout_seconds))
        return {
            "task": {"local_id": local_id, "remote_status": "succeeded", "download_status": "downloaded"},
            "timed_out": False,
        }

    def local_asset_paths(self, local_id: str):
        self.calls.append(("local_asset_paths", local_id))
        return {"input_paths": {}, "output_paths": {"video": str(self.video_path)}}

    def close(self) -> None:
        self.calls.append("close")


def test_paid_smoke_refuses_before_constructing_a_client_and_prints_a_safe_summary(tmp_path: Path):
    secret = "private-paid-smoke-key"
    summaries: list[dict] = []
    backend_calls: list[str] = []

    result = run_paid_smoke(
        SmokeOptions(first_frame=_image(tmp_path / "first.png")),
        config_loader=lambda: {"seedance": {"api_key": secret, "cache_dir": str(tmp_path / "cache")}},
        backend_factory=lambda *_args: backend_calls.append("constructed"),
        summary_sink=summaries.append,
    )

    assert result == {
        "ok": False,
        "status": "confirmation_required",
        "message": "Refusing to create a paid Seedance task without explicit confirmation.",
        "summary": {
            "action": "create",
            "model": "mini",
            "resolution": "480p",
            "ratio": "adaptive",
            "duration": 4,
            "generate_audio": False,
            "return_last_frame": False,
            "input": "first.png",
            "request_count": 1,
        },
    }
    assert summaries == [result["summary"]]
    assert backend_calls == []
    assert secret not in json.dumps(result)


def test_paid_smoke_distinguishes_local_validation_failure_without_a_client(tmp_path: Path):
    backend_calls: list[str] = []

    result = run_paid_smoke(
        SmokeOptions(first_frame=tmp_path / "missing.png", confirm_paid_request=True),
        config_loader=lambda: {"seedance": {"api_key": "fake-key"}},
        backend_factory=lambda *_args: backend_calls.append("constructed"),
    )

    assert result["ok"] is False
    assert result["status"] == "validation_failed"
    assert result["error"] == {"code": "IMAGE_NOT_FOUND", "field": "first_frame"}
    assert backend_calls == []


def test_paid_smoke_requires_a_key_from_private_config_and_never_accepts_one_in_options(tmp_path: Path):
    backend_calls: list[str] = []
    options = SmokeOptions(first_frame=_image(tmp_path / "first.png"), confirm_paid_request=True)

    result = run_paid_smoke(
        options,
        config_loader=lambda: {"seedance": {"api_key": ""}},
        backend_factory=lambda *_args: backend_calls.append("constructed"),
    )

    assert "api_key" not in SmokeOptions.__dataclass_fields__
    assert result["status"] == "auth_failed"
    assert result["error"] == {"code": "API_KEY_NOT_CONFIGURED"}
    assert backend_calls == []


def test_paid_smoke_runs_one_minimal_task_through_download_and_media_validation(tmp_path: Path):
    secret = "private-paid-smoke-key"
    backend = FakeBackend(_video(tmp_path / "result.mp4"))
    report_path = tmp_path / "smoke-report.json"

    result = run_paid_smoke(
        SmokeOptions(
            first_frame=_image(tmp_path / "first.png"),
            confirm_paid_request=True,
            check_connection=True,
            timeout_seconds=12,
            report_path=report_path,
        ),
        config_loader=lambda: {"seedance": {"api_key": secret, "cache_dir": str(tmp_path / "cache")}},
        backend_factory=lambda api_key, cache_root: (
            backend
            if (api_key, cache_root) == (secret, (tmp_path / "cache" / "ai-video-cache").resolve())
            else (_ for _ in ()).throw(AssertionError("unexpected private config"))
        ),
    )

    assert result == {
        "ok": True,
        "status": "success",
        "summary": {
            "action": "create",
            "model": "mini",
            "resolution": "480p",
            "ratio": "adaptive",
            "duration": 4,
            "generate_audio": False,
            "return_last_frame": False,
            "input": "first.png",
            "request_count": 1,
        },
        "task": {
            "local_id": "local-1",
            "remote_status": "succeeded",
            "download_status": "downloaded",
            "media_readable": True,
        },
    }
    create_calls = [call for call in backend.calls if isinstance(call, tuple) and call[0] == "create"]
    assert len(create_calls) == 1
    request = create_calls[0][1]
    assert (request.model, request.resolution, request.duration) == ("mini", "480p", 4)
    assert backend.calls[0] == "check_connection"
    assert backend.calls[-1] == "close"
    assert json.loads(report_path.read_text(encoding="utf-8")) == result
    assert secret not in report_path.read_text(encoding="utf-8")


class OutcomeBackend(FakeBackend):
    def __init__(self, video_path: Path, *, create_result=None, create_error=None, wait_result=None) -> None:
        super().__init__(video_path)
        self.create_result = create_result
        self.create_error = create_error
        self.wait_result = wait_result

    def create(self, request):
        self.calls.append(("create", request))
        if self.create_error is not None:
            raise self.create_error
        return self.create_result or {
            "local_id": "local-1",
            "remote_status": "queued",
            "download_status": "pending",
        }

    def wait(self, local_id: str, timeout_seconds: float):
        self.calls.append(("wait", local_id, timeout_seconds))
        return self.wait_result or {
            "task": {"local_id": local_id, "remote_status": "succeeded", "download_status": "downloaded"},
            "timed_out": False,
        }


def _run_outcome(tmp_path: Path, backend: OutcomeBackend, *, secret: str = "private-paid-smoke-key"):
    return run_paid_smoke(
        SmokeOptions(
            first_frame=_image(tmp_path / "first.png"),
            confirm_paid_request=True,
            report_path=tmp_path / "report.json",
        ),
        config_loader=lambda: {"seedance": {"api_key": secret}},
        backend_factory=lambda *_args: backend,
    )


def test_paid_smoke_distinguishes_auth_failure_and_redacts_recursive_output(tmp_path: Path):
    secret = "private-paid-smoke-key"
    backend = OutcomeBackend(
        tmp_path / "unused.mp4",
        create_error=ArkAPIError(401, f"AUTH_{secret}", f"nested {secret}"),
    )

    result = _run_outcome(tmp_path, backend, secret=secret)

    assert result["status"] == "auth_failed"
    assert result["error"]["status"] == 401
    assert secret not in json.dumps(result)
    assert secret not in (tmp_path / "report.json").read_text(encoding="utf-8")
    assert backend.calls[-1] == "close"


def test_paid_smoke_distinguishes_submission_unknown(tmp_path: Path):
    backend = OutcomeBackend(
        tmp_path / "unused.mp4",
        create_error=SubmissionUnknownError("outcome unknown"),
    )

    result = _run_outcome(tmp_path, backend)

    assert result["status"] == "submission_unknown"
    assert result["ok"] is False
    assert [call[0] for call in backend.calls if isinstance(call, tuple) and call[0] == "create"] == ["create"]


def test_paid_smoke_distinguishes_remote_failure_timeout_and_download_failure(tmp_path: Path):
    remote_failed = OutcomeBackend(
        tmp_path / "unused-remote.mp4",
        wait_result={
            "task": {"local_id": "local-1", "remote_status": "failed", "download_status": "pending"},
            "timed_out": False,
        },
    )
    timed_out = OutcomeBackend(
        tmp_path / "unused-timeout.mp4",
        wait_result={
            "task": {"local_id": "local-1", "remote_status": "running", "download_status": "pending"},
            "timed_out": True,
        },
    )
    download_failed = OutcomeBackend(
        tmp_path / "missing.mp4",
        wait_result={
            "task": {"local_id": "local-1", "remote_status": "succeeded", "download_status": "failed"},
            "timed_out": False,
        },
    )

    assert _run_outcome(tmp_path / "remote", remote_failed)["status"] == "remote_failed"
    assert _run_outcome(tmp_path / "timeout", timed_out)["status"] == "timeout"
    assert _run_outcome(tmp_path / "download", download_failed)["status"] == "download_failed"


def test_retry_and_continue_require_a_second_paid_confirmation(tmp_path: Path):
    secret = "private-paid-smoke-key"
    for action in ("retry_task", "continue_task"):
        backend = FakeBackend(tmp_path / f"{action}.mp4")
        options = SmokeOptions(
            **{action: "source-1"},
            confirm_paid_request=True,
            confirm_additional_paid_request=False,
        )

        result = run_paid_smoke(
            options,
            config_loader=lambda: {"seedance": {"api_key": secret}},
            backend_factory=lambda *_args, selected=backend: selected,
        )

        assert result["status"] == "confirmation_required"
        assert result["summary"]["action"] == ("retry" if action == "retry_task" else "continue")
        assert result["summary"]["request_count"] == 1
        assert not any(isinstance(call, tuple) and call[0] in {"retry", "continue"} for call in backend.calls)
        assert backend.calls[-1] == "close"


def test_retry_and_continue_create_at_most_one_additional_task_after_both_confirmations(tmp_path: Path):
    secret = "private-paid-smoke-key"
    for action, expected_call, created_id in (
        ("retry_task", "retry", "retry-1"),
        ("continue_task", "continue", "continue-1"),
    ):
        action_root = tmp_path / action
        backend = FakeBackend(_video(action_root / "result.mp4"))
        options = SmokeOptions(
            **{action: "source-1"},
            confirm_paid_request=True,
            confirm_additional_paid_request=True,
        )

        result = run_paid_smoke(
            options,
            config_loader=lambda: {"seedance": {"api_key": secret}},
            backend_factory=lambda *_args, selected=backend: selected,
        )

        paid_calls = [
            call for call in backend.calls if isinstance(call, tuple) and call[0] in {"create", "retry", "continue"}
        ]
        assert paid_calls == [(expected_call, "source-1")]
        assert result["status"] == "success"
        assert result["task"]["local_id"] == created_id


def test_manual_cli_is_separate_from_free_suites_and_has_no_api_key_argument(tmp_path: Path, capsys):
    secret = "private-paid-smoke-key"
    backend = FakeBackend(_video(tmp_path / "result.mp4"))
    report = tmp_path / "report.json"

    exit_code = main(
        [
            "--first-frame",
            str(_image(tmp_path / "first.png")),
            "--confirm-paid-request",
            "--report",
            str(report),
        ],
        config_loader=lambda: {"seedance": {"api_key": secret}},
        backend_factory=lambda *_args: backend,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out)["status"] == "success"
    assert json.loads(captured.err)["request_count"] == 1
    assert secret not in captured.out + captured.err + report.read_text(encoding="utf-8")
    assert "--api-key" not in _build_parser().format_help()
    assert all(
        "seedance-smoke" not in " ".join(stage.command)
        for stage in build_default_stages(tmp_path, python_executable="python", npm_executable="npm")
    )


def test_explicit_connection_check_can_run_before_paid_confirmation_without_creating_a_task(tmp_path: Path):
    backend = FakeBackend(tmp_path / "unused.mp4")

    result = run_paid_smoke(
        SmokeOptions(first_frame=_image(tmp_path / "first.png"), check_connection=True),
        config_loader=lambda: {"seedance": {"api_key": "private-key"}},
        backend_factory=lambda *_args: backend,
    )

    assert result["status"] == "confirmation_required"
    assert backend.calls == ["check_connection", "close"]


def test_backend_construction_failure_is_safe_and_recursively_redacted(tmp_path: Path):
    secret = "private-paid-smoke-key"
    report = tmp_path / "report.json"

    result = run_paid_smoke(
        SmokeOptions(
            first_frame=_image(tmp_path / "first.png"),
            confirm_paid_request=True,
            report_path=report,
        ),
        config_loader=lambda: {"seedance": {"api_key": secret}},
        backend_factory=lambda *_args: (_ for _ in ()).throw(OSError(f"private path {secret}")),
    )

    assert result["status"] == "remote_failed"
    assert result["error"] == {"code": "OSError"}
    assert secret not in json.dumps(result) + report.read_text(encoding="utf-8")
