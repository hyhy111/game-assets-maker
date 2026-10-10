"""Public configuration and CLI submission permission tests."""

import pytest

from backend.api.config_api import ConfigAPI
from backend.main import API


@pytest.fixture
def config_path(monkeypatch, tmp_path):
    monkeypatch.setenv("GAM_CONFIG", str(tmp_path / "config.json"))
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    return tmp_path / "config.json"


def test_cli_generation_defaults_off_and_stale_config_cannot_enable(config_path):
    api = ConfigAPI()
    assert api.get_config()["cli_generation_enabled"] is False
    api.save_config({"cli_generation_enabled": True, "language": "en"})
    assert api.get_config()["cli_generation_enabled"] is False
    assert api.get_config()["language"] == "en"


def test_confirmed_toggle_saves_only_its_field_and_requires_confirmation(config_path):
    api = API()
    assert api.save_cli_generation_enabled(True, False)["success"] is False
    assert api.save_cli_generation_enabled(True, True)["success"] is True
    ConfigAPI().save_config({"cli_generation_enabled": False})
    assert ConfigAPI().get_config()["cli_generation_enabled"] is True
    assert api.save_cli_generation_enabled(False, False)["success"] is True
    assert ConfigAPI().get_config()["cli_generation_enabled"] is False


@pytest.mark.parametrize("kind", ["image", "video"])
def test_direct_cli_submission_reads_live_permission_before_any_generation(config_path, kind):
    from test_agent_navigation import BrowserWindow

    from backend.agent_control.server import AgentControlServer

    server = AgentControlServer(BrowserWindow(), api=API(), port=0)
    request = {"request_id": "disabled", "operation": "generation.submit", "payload": {"kind": kind, "request": {}}}
    result = server.operations.execute(request)
    assert result["error"]["code"] == "CLI_GENERATION_DISABLED"
    assert not server.window.scripts


def test_cli_cannot_enable_permission_with_control_operation(config_path):
    from backend.agent_control.server import AgentControlServer

    server = AgentControlServer(None, api=API(), port=0)
    result = server.operations.execute(
        {"request_id": "enable", "operation": "generation.enable", "payload": {"enabled": True}}
    )
    assert result["error"]["code"] == "INPUT_INVALID"
    assert ConfigAPI().get_config()["cli_generation_enabled"] is False


@pytest.mark.parametrize("outcome", ["accepted", "unknown"])
def test_submission_uses_real_application_once_and_preserves_unknown_id(config_path, monkeypatch, tmp_path, outcome):
    from PIL import Image
    from test_agent_navigation import BrowserWindow

    from backend.agent_control.server import AgentControlServer
    from backend.seedance.client import HttpResponse, UrllibTransport
    from src.utils.app_config import save_app_config

    calls = []

    def transport(_self, method, _url, _headers, _body, _timeout):
        calls.append(method)
        if outcome == "unknown":
            raise TimeoutError("test transport timeout")
        return HttpResponse(200, {}, b'{"id":"remote-test"}')

    monkeypatch.setattr(UrllibTransport, "request", transport)
    save_app_config({"seedance": {"api_key": "test-key"}})
    image = tmp_path / "first.png"
    Image.new("RGB", (300, 300), "green").save(image)
    api = API()
    api.save_cli_generation_enabled(True, True)
    server = AgentControlServer(BrowserWindow(), api=api, port=0)
    server.operations.timeout = 0
    request = {
        "request_id": "once",
        "operation": "generation.submit",
        "payload": {"kind": "video", "request": {"prompt": "walk", "first_frame": str(image)}},
    }
    server.operations.execute(request)
    result = api.agent_submit_generation("once", "api-key")
    assert result["task"]["local_id"]
    assert api.agent_submit_generation("once", "api-key") == result
    api.agent_acknowledge("once", {"ok": result["success"]})
    receipt = server.operations.status("once")
    if outcome == "unknown":
        assert receipt["error"]["code"] == "SUBMISSION_UNKNOWN"
        assert receipt["error"]["details"]["local_id"] == result["task"]["local_id"]
    else:
        assert receipt["ok"] is True
    server.operations.execute(request)
    assert calls == ["POST"]


@pytest.mark.parametrize(
    "source,disable,code",
    [
        ("api-key", True, "CLI_GENERATION_DISABLED"),
        ("forfuner-ai", False, "GENERATION_SOURCE_UNAVAILABLE"),
    ],
)
def test_permission_revocation_and_source_are_checked_after_dispatch(config_path, source, disable, code):
    from test_agent_navigation import BrowserWindow

    from backend.agent_control.server import AgentControlServer

    api = API()
    api.save_cli_generation_enabled(True, True)
    server = AgentControlServer(BrowserWindow(), api=api, port=0)
    server.operations.timeout = 0
    server.operations.execute(
        {"request_id": "queued", "operation": "generation.submit", "payload": {"kind": "image", "request": {}}}
    )
    if disable:
        api.save_cli_generation_enabled(False)
    result = api.agent_submit_generation("queued", source)
    assert result["error"]["code"] == code
    api.agent_acknowledge("queued", {"ok": False})
    assert server.operations.status("queued")["error"]["code"] == code


def test_submitted_task_is_recoverable_without_browser_ack(config_path, monkeypatch, tmp_path):
    from PIL import Image
    from test_agent_navigation import BrowserWindow

    from backend.agent_control.server import AgentControlServer
    from backend.seedance.client import HttpResponse, UrllibTransport
    from src.utils.app_config import save_app_config

    monkeypatch.setattr(UrllibTransport, "request", lambda *_: HttpResponse(200, {}, b'{"id":"remote-test"}'))
    save_app_config({"seedance": {"api_key": "test-key"}})
    image = tmp_path / "first.png"
    Image.new("RGB", (300, 300), "green").save(image)
    api = API()
    api.save_cli_generation_enabled(True, True)
    server = AgentControlServer(BrowserWindow(), api=api, port=0)
    server.operations.timeout = 0
    server.operations.execute(
        {
            "request_id": "lost-ack",
            "operation": "generation.submit",
            "payload": {"kind": "video", "request": {"first_frame": str(image)}},
        }
    )
    submitted = api.agent_submit_generation("lost-ack", "api-key")
    receipt = server.operations.status("lost-ack")
    assert receipt["error"]["code"] == "UI_SYNC_TIMEOUT"
    assert receipt["error"]["details"]["persisted"] is True
    assert receipt["error"]["details"]["local_id"] == submitted["task"]["local_id"]


def test_completed_request_remains_queryable_after_permission_revoked(config_path):
    from test_agent_navigation import BrowserWindow

    from backend.agent_control.operations import AgentOperations

    api = API()
    api.save_cli_generation_enabled(True, True)
    operations = AgentOperations(BrowserWindow(), api=api, timeout=0)
    request = {
        "request_id": "completed",
        "operation": "generation.submit",
        "payload": {"kind": "image", "request": {"prompt": "test"}},
    }
    operations.execute(request)
    operations.acknowledge("completed", {"ok": True, "data": {"local_id": "existing"}})
    original = operations.status("completed")
    api.save_cli_generation_enabled(False)
    assert operations.execute(request) == original
    assert len(operations.window.scripts) == 1


@pytest.mark.parametrize("enabled", [1, "true", None])
def test_permission_rejects_non_boolean_values(config_path, enabled):
    assert API().save_cli_generation_enabled(enabled, True)["success"] is False
    assert ConfigAPI().get_config()["cli_generation_enabled"] is False


def test_permission_write_failure_keeps_persisted_value(config_path, monkeypatch):
    api = API()
    assert api.save_cli_generation_enabled(False)["success"]
    before = config_path.read_bytes()

    def fail_write(_patch):
        raise OSError("isolated test write failure")

    monkeypatch.setattr("src.utils.app_config.save_app_config", fail_write)
    assert api.save_cli_generation_enabled(True, True)["success"] is False
    assert config_path.read_bytes() == before
