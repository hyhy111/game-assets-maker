"""HTTP client for the local Agent UI control server."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class AgentUIClient:
    """Small stdlib client for the PyWebView UI control server."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765, timeout: float = 1.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def status(self) -> dict[str, Any]:
        try:
            payload = self._request_json("GET", "/health")
        except urllib.error.URLError:
            return {"connected": False}
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return {"connected": False, "error": str(exc)}

        return {"connected": True, "payload": payload}

    def open_step(self, project_id: str, step: int) -> dict[str, Any]:
        try:
            payload = self._request_json(
                "POST",
                "/ui/open",
                {"project_id": project_id, "step": step},
            )
        except urllib.error.HTTPError as exc:
            return self._http_error_open_response(exc)
        except urllib.error.URLError as exc:
            return self._disconnected_open_response(exc)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return self._malformed_open_response(exc)

        return {
            "connected": True,
            "opened": bool(payload.get("ok")),
            "payload": payload,
        }

    def open_seedance(self, local_task_id: str) -> dict[str, Any]:
        try:
            payload = self._request_json("POST", "/ui/open-seedance", {"local_task_id": local_task_id})
        except urllib.error.HTTPError as exc:
            return self._http_error_open_response(exc)
        except urllib.error.URLError as exc:
            return self._disconnected_open_response(exc)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return self._malformed_open_response(exc)

        return {
            "connected": True,
            "opened": bool(payload.get("ok")),
            "payload": payload,
        }

    def _request_json(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")

        request = urllib.request.Request(f"{self.base_url}{path}", data=data, method=method)
        if data is not None:
            request.add_header("Content-Type", "application/json")

        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _disconnected_open_response(self, exc: urllib.error.URLError) -> dict[str, Any]:
        message = str(getattr(exc, "reason", exc))
        return {
            "connected": False,
            "opened": False,
            "message": "UI is not running or not ready.",
            "error": message,
        }

    def _http_error_open_response(self, exc: urllib.error.HTTPError) -> dict[str, Any]:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {"ok": False, "error": str(exc)}

        return {
            "connected": True,
            "opened": False,
            "payload": payload,
        }

    def _malformed_open_response(self, exc: json.JSONDecodeError | UnicodeDecodeError) -> dict[str, Any]:
        return {
            "connected": True,
            "opened": False,
            "message": "UI returned an invalid response.",
            "payload": {"ok": False, "error": str(exc)},
        }
