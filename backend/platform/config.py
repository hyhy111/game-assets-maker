"""In-memory platform connection settings injected from the frontend.

The base URL (same value as the frontend's VITE_APP_API_BASE_URL) and the app
JWT are pushed over the pywebview bridge after login/state changes. They are
kept in process memory only: never persisted to disk, never written to logs.
"""

from __future__ import annotations

import threading

from backend.platform.client import PlatformClient


class PlatformConfig:
    """Holds the platform base URL + token and vends configured clients."""

    def __init__(self, *, transport=None) -> None:
        self._lock = threading.Lock()
        self._base_url = ""
        self._token: str | None = None
        # 默认 transport（测试注入用）；显式传入的 transport 优先。
        self._transport = transport

    def set(self, base_url: str, token: str | None) -> None:
        with self._lock:
            self._base_url = base_url.rstrip("/") if isinstance(base_url, str) else ""
            self._token = token if isinstance(token, str) and token else None

    def clear_token(self) -> None:
        with self._lock:
            self._token = None

    def snapshot(self) -> tuple[str, str | None]:
        with self._lock:
            return self._base_url, self._token

    def configured(self) -> bool:
        base_url, token = self.snapshot()
        return bool(base_url and token)

    def client(self, *, transport=None, timeout: float | None = None) -> PlatformClient:
        base_url, token = self.snapshot()
        resolved = transport if transport is not None else self._transport
        kwargs = {"transport": resolved} if resolved is not None else {}
        if timeout is not None:
            kwargs["timeout"] = timeout
        return PlatformClient(base_url, token, **kwargs)
