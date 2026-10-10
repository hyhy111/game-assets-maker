"""Regression coverage for the JSON-only Seedance Agent workflows."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image

from backend.seedance.models import SeedanceRequest
from backend.seedance.repository import TaskRepository
from src.agent_tools.service import AgentWorkflowService
from src.utils.app_config import save_app_config


def _run_agent_cli(*args: str, cwd: Path, repo_root: Path, config: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "src.cli.agent", *args],
        cwd=cwd,
        env={**os.environ, "PYTHONPATH": str(repo_root), "GAM_CONFIG": str(config)},
        capture_output=True,
        text=True,
        check=False,
    )


def _seed_task(cache_root: Path, image_path: Path, *, secret: str = "") -> str:
    repository = TaskRepository(cache_root)
    task = repository.create_draft(SeedanceRequest(first_frame=image_path, prompt="animate"))
    video_path = repository.resolve_asset(task.local_id, "output/video.mp4")
    video_path.write_bytes(b"local video")
    repository.update(
        task.local_id,
        lambda current: (
            setattr(current, "remote_status", "succeeded"),
            setattr(current, "finished_at", "2026-07-17T00:00:00Z"),
            current.output_paths.update({"video": "output/video.mp4"}),
            current.sync_status.update(
                {"error": {f"key-{secret}": f"nested {secret}", "url": "https://signed.example/video?token=secret"}}
            ),
        ),
    )
    return task.local_id


def test_seedance_summary_stdout_is_json_only_and_recursively_redacts_key(
    isolated_workspace: Path, repo_root: Path
):
    secret = "agent-cli-secret"
    config = isolated_workspace / "runtime-config.json"
    os.environ["GAM_CONFIG"] = str(config)
    save_app_config({"seedance": {"api_key": secret}})
    image_path = isolated_workspace / "first.png"
    Image.new("RGB", (300, 300), "white").save(image_path)
    local_id = _seed_task(isolated_workspace / "cache" / "ai-video-cache", image_path, secret=secret)

    result = _run_agent_cli(
        "seedance", "summary", "--task", local_id, cwd=isolated_workspace, repo_root=repo_root, config=config
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["operation"] == "seedance.summary"
    assert secret not in result.stdout
    assert "https://signed.example" not in result.stdout
    local_video = Path(payload["data"]["task"]["local_paths"]["output_paths"]["video"])
    assert local_video.is_file()
    assert result.stderr == ""


def test_seedance_create_requires_running_permitted_application(
    isolated_workspace: Path, repo_root: Path
):
    config = isolated_workspace / "runtime-config.json"
    image_path = isolated_workspace / "first.png"
    Image.new("RGB", (300, 300), "white").save(image_path)

    result = _run_agent_cli(
        "seedance",
        "create",
        "--first-frame",
        str(image_path),
        cwd=isolated_workspace,
        repo_root=repo_root,
        config=config,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["operation"] == "seedance.create"
    assert payload["error"]["code"] in {"UI_NOT_RUNNING", "CONTROL_UNAVAILABLE", "CLI_GENERATION_DISABLED"}


def test_seedance_wait_timeout_is_non_success_and_never_cancels(tmp_path: Path):
    class FakeManager:
        def __init__(self) -> None:
            self.cancelled = False
            self.stopped = False

        def wait(self, local_id: str, timeout_seconds: float):
            assert local_id == "queued-task"
            assert timeout_seconds == 0
            return {
                "task": {
                    "local_id": local_id,
                    "remote_status": "queued",
                    "output_urls": {"video": "https://signed.example/video"},
                    "remote": {"content": {"video_url": "https://signed.example/video"}},
                },
                "timed_out": True,
            }

        def local_asset_paths(self, local_id: str):
            return {"input_paths": {}, "output_paths": {}}

        def shutdown(self) -> None:
            self.stopped = True

    service = AgentWorkflowService(root=tmp_path)
    manager = FakeManager()
    service._seedance_manager = manager

    response = service.seedance_wait("queued-task", 0)
    service.close()

    assert response["ok"] is False
    assert response["operation"] == "seedance.wait"
    assert response["error"]["code"] == "WAIT_TIMEOUT"
    assert "https://signed.example" not in json.dumps(response)
    assert manager.cancelled is False
    assert manager.stopped is True


def test_seedance_service_maps_all_documented_non_create_commands(tmp_path: Path):
    class FakeManager:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        def list_tasks(self):
            self.calls.append(("list", None))
            return [self._task("task-1")]

        def get_task(self, local_id: str):
            self.calls.append(("summary", local_id))
            return self._task(local_id)

        def cancel(self, local_id: str):
            self.calls.append(("cancel", local_id))
            return self._task(local_id, "cancelled")

        def handoff(self, local_id: str, role: str, action: str):
            self.calls.append(("handoff", (local_id, role, action)))
            return {"project_id": f"{role}/{action}", "task": self._task(local_id)}

        @staticmethod
        def _task(local_id: str, status: str = "queued"):
            return {
                "local_id": local_id,
                "remote_status": status,
                "output_urls": {"video": "https://signed.example/video?token=agent-cli-secret"},
                "remote": {"content": {"video_url": "https://signed.example/video"}},
                "sync_status": {"error": {"message": "https://signed.example/error"}},
                "error": {"message": "https://signed.example/error"},
            }

        @staticmethod
        def local_asset_paths(local_id: str):
            return {"input_paths": {}, "output_paths": {"video": str(tmp_path / f"{local_id}.mp4")}}

        def cache_status(self):
            self.calls.append(("cache.status", None))
            return {"task_count": 1}

        def clean_cache(self, days: int | None):
            self.calls.append(("cache.clean", days))
            return {"tasks_cleared": 1}

        def shutdown(self) -> None:
            pass

    service = AgentWorkflowService(root=tmp_path)
    manager = FakeManager()
    service._seedance_manager = manager
    service.ui_client = type("UI", (), {"open_seedance": lambda *_: {"connected": False, "opened": False}})()

    responses = [
        service.seedance_list("queued"),
        service.seedance_summary("task-1"),
        service.seedance_cancel("task-1"),
        service.seedance_handoff("task-1", "hero", "attack"),
        service.seedance_cache_status(),
        service.seedance_cache_clean(7),
        service.seedance_ui_open("task-1"),
    ]

    assert [response["operation"] for response in responses] == [
        "seedance.list",
        "seedance.summary",
        "seedance.cancel",
        "seedance.handoff",
        "seedance.cache.status",
        "seedance.cache.clean",
        "seedance.ui-open",
    ]
    assert all(response["ok"] for response in responses)
    for response in responses:
        serialized = json.dumps(response)
        assert "https://signed.example" not in serialized
        if "task" in response["data"]:
            assert response["data"]["task"]["local_paths"]["output_paths"]["video"].endswith("task-1.mp4")
    assert manager.calls == [
        ("list", None),
        ("summary", "task-1"),
        ("cancel", "task-1"),
        ("handoff", ("task-1", "hero", "attack")),
        ("cache.status", None),
        ("cache.clean", 7),
        ("summary", "task-1"),
    ]


def test_seedance_parser_accepts_only_documented_create_choices():
    from src.cli.agent import _build_parser

    parser = _build_parser()
    args = parser.parse_args(
        [
            "seedance",
            "create",
            "--first-frame",
            "first.png",
            "--model",
            "fast",
            "--resolution",
            "720p",
            "--ratio",
            "16:9",
        ]
    )

    assert (args.model, args.resolution, args.ratio) == ("fast", "720p", "16:9")
