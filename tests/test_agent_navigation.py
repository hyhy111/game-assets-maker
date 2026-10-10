"""Navigation contract tests across the local HTTP/WebView boundary."""

import threading
import time

from backend.agent_control.server import AgentControlServer
from src.agent_tools.ui_client import AgentUIClient


class BrowserWindow:
    def __init__(self):
        self.scripts = []

    def evaluate_js(self, script):
        self.scripts.append(script)


def test_navigation_waits_for_browser_receipt_and_reuses_request():
    window = BrowserWindow()
    server = AgentControlServer(window, port=0)
    server.start()
    client = AgentUIClient(port=server.httpd.server_address[1], timeout=3)
    results = []
    try:
        request = {"request_id": "nav-1", "operation": "ui.navigate", "payload": {"target": "settings"}}
        thread = threading.Thread(target=lambda: results.append(client.operation(request)))
        thread.start()
        deadline = time.monotonic() + 2
        while not window.scripts and time.monotonic() < deadline:
            time.sleep(0.01)
        assert window.scripts
        assert not results
        server.operations.acknowledge("wrong-id", {"ok": True})
        assert not results
        server.operations.acknowledge("nav-1", {"ok": True, "data": {"path": "/ai-creation/settings"}})
        thread.join(2)
        assert results[0]["ok"] is True
        assert results[0]["data"]["ui_sync"] == "applied"
        assert client.operation(request) == results[0]
        assert len(window.scripts) == 1
    finally:
        server.stop()


def test_missing_window_and_invalid_target_are_explicit():
    server = AgentControlServer(None, port=0)
    request = {"request_id": "absent", "operation": "ui.navigate", "payload": {"target": "settings"}}
    assert server.operations.execute(request)["error"]["code"] == "UI_NOT_RUNNING"
    request["payload"]["target"] = "arbitrary-code"
    assert server.operations.execute(request)["error"]["code"] == "INPUT_INVALID"


def test_timeout_can_be_queried_later_without_redispatch():
    server = AgentControlServer(BrowserWindow(), port=0)
    server.operations.timeout = 0.01
    request = {"request_id": "slow", "operation": "ui.navigate", "payload": {"target": "projects"}}
    assert server.operations.execute(request)["error"]["code"] == "UI_SYNC_TIMEOUT"
    assert server.operations.execute(request)["error"]["code"] == "UI_SYNC_TIMEOUT"
    assert len(server.window.scripts) == 1
    server.operations.acknowledge("slow", {"ok": False, "error": "PROJECT_NOT_FOUND"})
    assert server.operations.status("slow")["error"]["details"]["ui_sync"] == "failed"
    changed = {**request, "payload": {"target": "settings"}}
    assert server.operations.execute(changed)["error"]["code"] == "REQUEST_CONFLICT"


def test_online_root_mismatch_does_not_dispatch(tmp_path):
    from types import SimpleNamespace

    api = SimpleNamespace(storage_locations=SimpleNamespace(projects_root=tmp_path))
    server = AgentControlServer(BrowserWindow(), api=api, port=0)
    request = {
        "request_id": "roots",
        "operation": "ui.navigate",
        "projects_root": str(tmp_path / "different"),
        "payload": {"target": "settings"},
    }
    assert server.operations.execute(request)["error"]["code"] == "ROOT_MISMATCH"
    assert not server.window.scripts


def test_malformed_navigation_never_runs_browser_code():
    server = AgentControlServer(BrowserWindow(), port=0)
    for payload in ({"target": []}, {"target": {}}, {"target": "editor", "project_id": "", "step": True}):
        result = server.operations.execute({"request_id": "invalid", "operation": "ui.navigate", "payload": payload})
        assert result["error"]["code"] == "INPUT_INVALID"
    assert not server.window.scripts


def test_disconnected_navigation_has_application_not_running_code():
    response = AgentUIClient(port=9).operation(
        {"request_id": "offline", "operation": "ui.navigate", "payload": {"target": "settings"}}
    )
    assert response["error"]["code"] == "UI_NOT_RUNNING"


def test_browser_origin_cannot_submit_control_requests():
    import urllib.error
    import urllib.request

    import pytest

    from backend.agent_control.server import AgentControlServer

    server = AgentControlServer(BrowserWindow(), port=0)
    server.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.httpd.server_address[1]}/operations",
            data=b"{}",
            headers={"Origin": "https://example.com", "Content-Type": "application/json"},
        )
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request)
        assert caught.value.code == 403
    finally:
        server.stop()
