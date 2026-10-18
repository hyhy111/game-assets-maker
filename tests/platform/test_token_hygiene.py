"""Token hygiene: the platform JWT never reaches logs or task payloads (task 1.2)."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from PIL import Image
from platform_test_helpers import FakeTransport, ajax_error, ajax_ok

from backend.api.seedance_api import SeedanceAPI
from backend.platform.client import PlatformError
from backend.platform.config import PlatformConfig


class StubManager:
    """Minimal manager stand-in: accepts the create request and returns a task."""

    def __init__(self) -> None:
        self.requests: list[Any] = []

    def create(self, request):
        self.requests.append(request)
        return _public_task()

    def get_task(self, local_id: str):
        return _public_task()

    def start(self) -> None:
        pass

    def shutdown(self) -> None:
        pass


class MissingResolver:
    def resolve(self, local_id: str, kind: str):
        return None


def _public_task() -> dict[str, Any]:
    return {
        "local_id": "task-1",
        "remote_id": "job-9",
        "remote_status": "queued",
        "submission_unknown": False,
        "source": "forfuner-ai",
        "request": {"prompt": "p", "source": "forfuner-ai"},
        "output_paths": {},
        "output_urls": {},
        "error": None,
        "created_at": "2026-09-27T00:00:00Z",
        "updated_at": "2026-09-27T00:00:00Z",
        "retry_of": None,
    }


TOKEN = "gam-jwt-secret-substring-1234567890"


def _make_api() -> SeedanceAPI:
    return SeedanceAPI(
        StubManager(),
        media_resolver=MissingResolver(),
        platform_config=PlatformConfig(),
    )


def test_update_platform_never_logs_token(caplog):
    api = _make_api()
    with caplog.at_level(logging.DEBUG):
        api.update_platform("http://platform.test", TOKEN)
        api.update_platform("http://platform.test", None)
    blob = "\n".join(f"{record.levelname}:{record.getMessage()}" for record in caplog.records)
    assert TOKEN not in blob


def test_create_task_response_and_manager_payload_carry_no_token(caplog, tmp_path):
    api = _make_api()
    # Keep the stub manager in place: this test targets the API/token surface,
    # not the manager wiring (covered by test_seedance_manager_platform.py).
    api._replace_manager = lambda: None  # noqa: SLF001
    api.update_platform("http://platform.test", TOKEN)
    image = tmp_path / "first.png"
    Image.new("RGB", (320, 320), (20, 160, 60)).save(image, format="PNG")
    with caplog.at_level(logging.DEBUG):
        result = api.create_task({"prompt": "a scene", "first_frame": str(image)}, source="forfuner-ai")
    assert result["success"] is True
    assert TOKEN not in str(result)
    assert TOKEN not in str(api._ensure_manager().requests)  # noqa: SLF001
    blob = "\n".join(record.getMessage() for record in caplog.records)
    assert TOKEN not in blob


def test_platform_config_holds_token_in_memory_only():
    config = PlatformConfig()
    config.set("http://platform.test", TOKEN)
    base_url, token = config.snapshot()
    assert token == TOKEN and base_url == "http://platform.test"
    config.clear_token()
    assert config.snapshot()[1] is None


# --------------------------------------------------------------------------
# 文件追踪日志（backend/platform/trace.py）
# --------------------------------------------------------------------------

def test_platform_trace_file_never_contains_token(tmp_path):
    """落盘的追踪日志里绝不能出现 token（含异常消息夹带的情形）。

    路径隔离由 conftest 的 `isolate_platform_trace_log` 保证（GAM_DATA_ROOT → tmp_path）。
    """
    from backend.platform import trace as trace_module
    from backend.platform.client import PlatformClient

    transport = FakeTransport(lambda m, u, h, b: ajax_ok({"jobId": "1", "status": "QUEUED"}))
    client = PlatformClient("http://platform.test", TOKEN, transport=transport)
    client.get_job("1")
    # 业务错误：后端 msg 里若夹带 token，也必须被 scrub 掉
    transport._handler = lambda m, u, h, b: ajax_error(500, f"boom {TOKEN}")
    with pytest.raises(PlatformError):
        client.get_job("2")

    log_file = trace_module.log_path()
    assert log_file.is_file(), "追踪日志未落盘"
    assert str(tmp_path) in str(log_file), "追踪日志必须写在隔离目录内"
    content = log_file.read_text(encoding="utf-8")
    assert TOKEN not in content
    assert "[REDACTED]" in content
    assert "GET /app/gen/jobs/1" in content
