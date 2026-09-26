"""Local HTTP control server for driving the PyWebView UI."""

import json
import threading
from http.server import BaseHTTPRequestHandler
from socketserver import TCPServer

from backend.agent_control.events import build_open_seedance_js, build_open_step_js


class ReusableTCPServer(TCPServer):
    allow_reuse_address = True


class AgentControlHandler(BaseHTTPRequestHandler):
    window = None

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

        self._send_json(404, {"ok": False, "error": "NOT_FOUND"})

    def do_POST(self) -> None:
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
    def __init__(self, window, host: str = "127.0.0.1", port: int = 8765):
        self.window = window
        self.host = host
        self.port = port
        self.httpd = None
        self.thread = None

    def start(self) -> None:
        AgentControlHandler.window = self.window
        self.httpd = ReusableTCPServer((self.host, self.port), AgentControlHandler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        if self.httpd is None:
            return

        self.httpd.shutdown()
        self.httpd.server_close()
        if self.thread is not None:
            self.thread.join(timeout=2)
        self.httpd = None
        self.thread = None
