"""Shared fakes for the platform integration tests."""

from __future__ import annotations

import json
from typing import Any, Callable

from PIL import Image

from backend.platform.client import HttpResponse


def json_response(payload: dict[str, Any], status: int = 200) -> HttpResponse:
    return HttpResponse(status, {"Content-Type": "application/json"}, json.dumps(payload).encode("utf-8"))


def ajax_ok(data: dict[str, Any]) -> HttpResponse:
    return json_response({"code": 200, "msg": "操作成功", "data": data})


def ajax_error(code: int, msg: str, status: int | None = None) -> HttpResponse:
    http_status = status if status is not None else (401 if code == 401 else 200)
    return json_response({"code": code, "msg": msg}, status=http_status)


class FakeTransport:
    """Records requests and serves scripted or routed responses."""

    def __init__(self, handler: Callable[[str, str, dict[str, str], bytes | None], HttpResponse] | None = None):
        self.requests: list[tuple[str, str, dict[str, str], bytes | None]] = []
        self._handler = handler
        self._script: list[HttpResponse] = []

    def script(self, *responses: HttpResponse) -> None:
        self._script.extend(responses)

    def request(
        self, method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float
    ) -> HttpResponse:
        self.requests.append((method, url, headers, body))
        if self._handler is not None:
            return self._handler(method, url, headers, body)
        if self._script:
            return self._script.pop(0)
        return ajax_ok({})

    @property
    def last(self) -> tuple[str, str, dict[str, str], bytes | None]:
        return self.requests[-1]

    def last_authorization(self) -> str | None:
        return self.last[2].get("Authorization")


def png_bytes() -> bytes:
    """Render a small valid PNG (64x64 green) as bytes."""
    import io

    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), (20, 160, 60)).save(buffer, format="PNG")
    return buffer.getvalue()


def make_video_bytes(path) -> bytes:
    """Write a tiny valid mp4 (320x320, 8 frames, green square) and return bytes."""
    import cv2
    import numpy as np

    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 6, (320, 320))
    assert writer.isOpened(), f"Cannot create test video: {path}"
    for i in range(8):
        frame = np.full((320, 320, 3), (30, 180, 40), dtype=np.uint8)
        frame[80:220, 50 + i * 10 : 170 + i * 10] = (200, 60, 20)
        writer.write(frame)
    writer.release()
    return path.read_bytes()


def reset_trace_logger() -> None:
    """Drop the platform trace handler so the next record re-resolves its path.

    Deliberately not `importlib.reload`: `platform/client.py` binds the trace
    functions at import time, so reloading the module would leave callers
    pointing at the stale function objects.
    """
    import logging

    from backend.platform import trace as trace_module

    logger = logging.getLogger(trace_module._LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    trace_module._logger = None
