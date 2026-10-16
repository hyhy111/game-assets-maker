"""Local HTTP control server for driving the PyWebView UI."""

import errno
import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from socketserver import TCPServer, ThreadingMixIn
from uuid import uuid4

from backend.agent_control.events import build_open_seedance_js, build_open_step_js
from src.agent_tools.discovery import DEFAULT_CONTROL_PORT, control_endpoint_path, read_control_endpoint


class ReusableTCPServer(ThreadingMixIn, TCPServer):
    daemon_threads = True
    allow_reuse_address = True


class AgentControlHandler(BaseHTTPRequestHandler):
    window = None
    operations = None

    @staticmethod
    def parse_open_payload(raw_body: bytes) -> dict[str, object]:
        data = json.loads(raw_body.decode("utf-8"))
        return {
            "project_id": str(data["project_id"]),
            "step": int(data["step"]),
        }

    @staticmethod
    def parse_open_seedance_payload(raw_body: bytes) -> dict[str, str]:
        data = json.loads(raw_body.decode("utf-8"))
        if set(data) != {"local_task_id"} or not isinstance(data["local_task_id"], str) or not data["local_task_id"]:
            raise ValueError("local_task_id must be a non-empty string")
        return {"local_task_id": data["local_task_id"]}

    def log_message(self, format, *args):
        pass

    def _send_json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"ok": True, "service": "gam-agent-control"})
            return

        if self.path.startswith("/operations/") and self.operations is not None:
            from urllib.parse import unquote

            self._send_json(200, self.operations.status(unquote(self.path[len("/operations/") :])))
            return
        self._send_json(404, {"ok": False, "error": "NOT_FOUND"})

    def do_POST(self) -> None:
        if self.path == "/operations" and self.operations is not None:
            if self.headers.get("Origin") is not None or self.headers.get("Sec-Fetch-Site") is not None:
                self._send_json(403, {"ok": False, "error": "BROWSER_ORIGIN_REJECTED"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1024 * 1024:
                    raise ValueError("Invalid request size")
                request = json.loads(self.rfile.read(length).decode("utf-8"))
                self._send_json(200, self.operations.execute(request))
            except (ValueError, UnicodeDecodeError):
                self._send_json(400, {"ok": False, "error": "INPUT_INVALID"})
            return
        if self.path not in {"/ui/open", "/ui/open-seedance"}:
            self._send_json(404, {"ok": False, "error": "NOT_FOUND"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)

            if self.path == "/ui/open-seedance":
                payload = self.parse_open_seedance_payload(raw_body)
                if self.window is None:
                    self._send_json(503, {"ok": False, "error": "UI_NOT_READY"})
                    return
                self.window.evaluate_js(build_open_seedance_js(payload["local_task_id"]))
            else:
                payload = self.parse_open_payload(raw_body)
                if self.window is None:
                    self._send_json(503, {"ok": False, "error": "UI_NOT_READY"})
                    return
                self.window.evaluate_js(build_open_step_js(payload["project_id"], payload["step"]))
            self._send_json(200, {"ok": True, "opened": payload})
        except Exception as e:
            self._send_json(400, {"ok": False, "error": str(e)})


class AgentControlServer:
    def __init__(self, window, host: str = "127.0.0.1", port: int | None = None, api=None):
        from backend.agent_control.operations import AgentOperations

        self.operations = AgentOperations(window, api)
        if api is not None:
            api._agent_operations = self.operations
        self.window = window
        self.host = host
        self.port = DEFAULT_CONTROL_PORT if port is None else port
        self._auto_port = port is None
        self._endpoint_path = control_endpoint_path() if self._auto_port else None
        self._instance_id = uuid4().hex
        self.httpd = None
        self.thread = None

    def start(self) -> None:
        handler = type(
            "BoundAgentControlHandler",
            (AgentControlHandler,),
            {
                "window": self.window,
                "operations": self.operations,
            },
        )
        try:
            self.httpd = ReusableTCPServer((self.host, self.port), handler)
        except OSError as error:
            if not self._auto_port or error.errno != errno.EADDRINUSE:
                raise
            self.httpd = ReusableTCPServer((self.host, 0), handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        if self._endpoint_path is not None:
            try:
                self._publish_endpoint()
            except OSError:
                self.stop()
                raise
        print(f"Agent control server started at http://{self.host}:{self.port}")

    def _publish_endpoint(self) -> None:
        self._endpoint_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self._endpoint_path.parent, delete=False
            ) as temporary:
                temporary_path = Path(temporary.name)
                json.dump({"port": self.port, "instance_id": self._instance_id}, temporary)
            temporary_path.replace(self._endpoint_path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def stop(self) -> None:
        if self.httpd is None:
            return

        self.httpd.shutdown()
        self.httpd.server_close()
        if self.thread is not None:
            self.thread.join(timeout=2)
        self.httpd = None
        self.thread = None
        if self._endpoint_path is not None:
            record = read_control_endpoint(self._endpoint_path)
            if record.get("instance_id") == self._instance_id:
                self._endpoint_path.unlink(missing_ok=True)
