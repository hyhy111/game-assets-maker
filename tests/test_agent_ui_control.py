import json
import sys
import threading
import types
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler

from backend.agent_control.events import build_open_seedance_js, build_open_step_js
from backend.agent_control.server import AgentControlHandler, AgentControlServer, ReusableTCPServer
from src.agent_tools.service import AgentWorkflowService
from src.agent_tools.ui_client import AgentUIClient


def request_json(url, data=None):
    request = urllib.request.Request(url, data=data)
    if data is not None:
        request.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


class RunningHandlerServer:
    def __init__(self, window=None):
        self.previous_window = AgentControlHandler.window
        AgentControlHandler.window = window
        self.httpd = ReusableTCPServer(("127.0.0.1", 0), AgentControlHandler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.port = self.httpd.server_address[1]

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)
        AgentControlHandler.window = self.previous_window

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"


class FakeWindow:
    def __init__(self):
        self.scripts = []

    def evaluate_js(self, script):
        self.scripts.append(script)


class InvalidJsonHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_invalid_json(self):
        body = b"{"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send_invalid_json()

    def do_POST(self):
        self._send_invalid_json()


class RunningInvalidJsonServer:
    def __init__(self):
        self.httpd = ReusableTCPServer(("127.0.0.1", 0), InvalidJsonHandler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.port = self.httpd.server_address[1]

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)


class BadUIClient:
    def open_step(self, project_id, step):
        raise json.JSONDecodeError("bad ui json", "{", 0)


def test_build_open_step_js_escapes_project_id():
    js = build_open_step_js("hero/idle", 2)

    assert "agent-open-step" in js
    assert '"projectId": "hero/idle"' in js
    assert '"step": 2' in js


def test_build_open_seedance_js_escapes_local_task_id():
    js = build_open_seedance_js('task"</script>')

    assert "agent-open-seedance" in js
    assert json.loads(js.split("detail: ", 1)[1].rsplit(" }));", 1)[0]) == {"localTaskId": 'task"</script>'}


def test_handler_parse_open_payload():
    payload = json.dumps({"project_id": "hero/idle", "step": 2}).encode("utf-8")

    parsed = AgentControlHandler.parse_open_payload(payload)

    assert parsed == {"project_id": "hero/idle", "step": 2}


def test_health_returns_service_json():
    with RunningHandlerServer() as server:
        status, payload = request_json(server.url("/health"))

    assert status == 200
    assert payload == {"ok": True, "service": "gam-agent-control"}


def test_open_returns_ui_not_ready_when_window_missing():
    body = json.dumps({"project_id": "hero/idle", "step": 2}).encode("utf-8")

    with RunningHandlerServer(window=None) as server:
        status, payload = request_json(server.url("/ui/open"), body)

    assert status == 503
    assert payload == {"ok": False, "error": "UI_NOT_READY"}


def test_open_calls_window_and_returns_opened_payload():
    window = FakeWindow()
    body = json.dumps({"project_id": "hero/idle", "step": 2}).encode("utf-8")

    with RunningHandlerServer(window=window) as server:
        status, payload = request_json(server.url("/ui/open"), body)

    assert status == 200
    assert payload == {"ok": True, "opened": {"project_id": "hero/idle", "step": 2}}
    assert len(window.scripts) == 1
    assert "agent-open-step" in window.scripts[0]
    assert '"projectId": "hero/idle"' in window.scripts[0]
    assert '"step": 2' in window.scripts[0]


def test_open_seedance_requires_exact_task_payload_and_dispatches_safely():
    window = FakeWindow()
    body = json.dumps({"local_task_id": 'task"</script>'}).encode("utf-8")

    with RunningHandlerServer(window=window) as server:
        status, payload = request_json(server.url("/ui/open-seedance"), body)

    assert status == 200
    assert payload == {"ok": True, "opened": {"local_task_id": 'task"</script>'}}
    assert len(window.scripts) == 1
    assert "agent-open-seedance" in window.scripts[0]


def test_open_seedance_rejects_wrong_payload_and_handles_missing_window():
    with RunningHandlerServer(window=FakeWindow()) as server:
        status, payload = request_json(server.url("/ui/open-seedance"), json.dumps({"task": "task-1"}).encode())
    assert status == 400
    assert payload["ok"] is False

    with RunningHandlerServer(window=None) as server:
        status, payload = request_json(
            server.url("/ui/open-seedance"), json.dumps({"local_task_id": "task-1"}).encode()
        )
    assert status == 503
    assert payload == {"ok": False, "error": "UI_NOT_READY"}


def test_open_with_invalid_payload_returns_bad_request():
    with RunningHandlerServer(window=FakeWindow()) as server:
        status, payload = request_json(server.url("/ui/open"), b"{")

    assert status == 400
    assert payload["ok"] is False
    assert "error" in payload


def test_agent_control_server_start_stop_health_on_ephemeral_port():
    server = AgentControlServer(window=None, port=0)

    try:
        server.start()
        port = server.httpd.server_address[1]

        status, payload = request_json(f"http://127.0.0.1:{port}/health")
    finally:
        server.stop()

    assert status == 200
    assert payload == {"ok": True, "service": "gam-agent-control"}


def test_main_app_initializes_agent_control_server_to_none():
    from backend.main import MainApp

    app = MainApp()

    assert app.agent_control_server is None


def test_macos_window_controls_are_dispatched_to_main_thread(monkeypatch):
    from backend.main import MainApp

    scheduled = []

    class FakeAppHelper:
        @staticmethod
        def callAfter(callback):
            scheduled.append(callback)

    fake_pyobjc_tools = types.ModuleType("PyObjCTools")
    fake_pyobjc_tools.AppHelper = FakeAppHelper
    monkeypatch.setitem(sys.modules, "PyObjCTools", fake_pyobjc_tools)
    monkeypatch.setattr(sys, "platform", "darwin")

    class FakeNativeWindow:
        def __init__(self):
            self.title_visibility_calls = 0

        def setTitleVisibility_(self, value):
            self.title_visibility_calls += 1

    app = MainApp()
    native_window = FakeNativeWindow()
    app.window = types.SimpleNamespace(native=native_window)

    app.configure_macos_window_controls()

    assert scheduled == [app._configure_macos_window_controls_on_main_thread]
    assert native_window.title_visibility_calls == 0


def test_ui_client_status_handles_not_running():
    client = AgentUIClient(port=9)

    response = client.status()

    assert response["connected"] is False


def test_ui_client_status_handles_invalid_json_response():
    with RunningInvalidJsonServer() as server:
        client = AgentUIClient(port=server.port)

        response = client.status()

    assert response["connected"] is False
    assert "error" in response


def test_ui_client_open_handles_invalid_json_response():
    with RunningInvalidJsonServer() as server:
        client = AgentUIClient(port=server.port)

        response = client.open_step("hero/idle", 2)

    assert response["connected"] is True
    assert response["opened"] is False
    assert response["payload"]["ok"] is False


def test_run_step_success_survives_bad_ui_client(tmp_path):
    class FakeProjectAPI:
        def get_project(self, project_id):
            return {"id": project_id, "video_path": str(tmp_path / "input.mp4")}

    class FakeProcessAPI:
        def start_processing(self, project_id, step, params):
            return "task-completed"

        def get_task_status(self, task_id):
            return {"success": True, "task_id": task_id, "status": "completed"}

    service = AgentWorkflowService(root=tmp_path)
    service._project_api = FakeProjectAPI()
    service._process_api = FakeProcessAPI()
    service.ui_client = BadUIClient()

    response = service.run_step("hero/idle", 1)

    assert response["ok"] is True
    assert response["data"]["ui"]["connected"] is False
