"""Observable rembg model preparation state."""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
from typing import Literal, Protocol, TypedDict

ModelPhase = Literal["needs_download", "downloading", "initializing", "ready", "failed"]


class ModelStatus(TypedDict):
    model: str
    phase: ModelPhase
    downloaded_bytes: int | None
    total_bytes: int | None
    error: dict[str, str] | None


class ModelLoader(Protocol):
    def is_available(self, model: str) -> bool: ...

    def download(self, model: str, progress: Callable[[int, int | None], None], source: str) -> None: ...

    def initialize(self, model: str) -> None: ...


class RembgModelLoader:
    """Use rembg's model registry while keeping download and initialization observable."""

    def is_available(self, model: str) -> bool:
        from backend.core.smart_remove_background import _MODELS_DIR, check_model_available
        from src.core.rembg_model import migrate_legacy_u2net, validate_model

        validate_model(model)
        if check_model_available(model):
            return True
        migrate_legacy_u2net(_MODELS_DIR)
        return check_model_available(model)

    def download(self, model: str, _progress: Callable[[int, int | None], None], source: str) -> None:
        from src.core.rembg_model import download_u2net, validate_model
        from backend.core.smart_remove_background import _MODELS_DIR, check_model_available, get_model_file_size

        validate_model(model)
        download_u2net(_MODELS_DIR, source)
        if not check_model_available(model):
            raise RuntimeError("rembg did not create the requested model file")
        size = get_model_file_size(model)
        if size is not None:
            _progress(size, size)

    def initialize(self, model: str) -> None:
        from backend.core.smart_remove_background import get_rembg_session

        get_rembg_session(model)


class ModelPreloader:
    def __init__(
        self,
        loader: ModelLoader,
        on_status: Callable[[ModelStatus], None] | None = None,
    ) -> None:
        self._loader = loader
        self._on_status = on_status
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rembg-model")
        self._lock = threading.RLock()
        self._statuses: dict[str, ModelStatus] = {}
        self._active: dict[str, Future[None]] = {}

    def get_status(self, model: str) -> ModelStatus:
        with self._lock:
            if model not in self._statuses:
                phase: ModelPhase = "initializing" if self._loader.is_available(model) else "needs_download"
                self._statuses[model] = {
                    "model": model,
                    "phase": phase,
                    "downloaded_bytes": None,
                    "total_bytes": None,
                    "error": None,
                }
            return self._statuses[model].copy()

    def preload(self, model: str, *, retry: bool = False, source: str | None = None) -> ModelStatus:
        from src.core.rembg_model import U2NET_SOURCES

        if source is not None and source not in U2NET_SOURCES:
            raise ValueError("Unsupported model download source")
        with self._lock:
            status = self.get_status(model)
            active = self._active.get(model)
            if active is not None and not active.done():
                return status
            if status["phase"] == "ready" or (status["phase"] == "failed" and not retry):
                return status

            needs_download = not self._loader.is_available(model)
            if needs_download and source is None:
                return self._publish(model, phase="needs_download", error=None)
            phase: ModelPhase = "downloading" if needs_download else "initializing"
            status = self._publish(model, phase=phase, downloaded_bytes=None, total_bytes=None, error=None)
            self._active[model] = self._executor.submit(self._prepare, model, needs_download, source)
            return status

    def retry(self, model: str, source: str | None = None) -> ModelStatus:
        return self.preload(model, retry=True, source=source)

    def wait(self, model: str, timeout: float | None = None) -> ModelStatus:
        with self._lock:
            future = self._active.get(model)
        if future is not None:
            future.result(timeout=timeout)
        return self.get_status(model)

    def _prepare(self, model: str, needs_download: bool, source: str | None) -> None:
        try:
            if needs_download:
                self._loader.download(model, lambda current, total: self._download_progress(model, current, total), source)
                current = self.get_status(model)
                downloaded = current["total_bytes"] if current["total_bytes"] is not None else None
                self._publish(model, phase="initializing", downloaded_bytes=downloaded)
            self._loader.initialize(model)
            self._publish(model, phase="ready", error=None)
        except Exception:
            current = self.get_status(model)
            downloading = current["phase"] == "downloading"
            self._publish(
                model,
                phase="failed",
                error={
                    "code": "MODEL_DOWNLOAD_FAILED" if downloading else "MODEL_INITIALIZATION_FAILED",
                    "message": "Model download failed" if downloading else "Model initialization failed",
                },
            )

    def _download_progress(self, model: str, downloaded: int, total: int | None) -> None:
        self._publish(
            model,
            phase="downloading",
            downloaded_bytes=max(0, downloaded),
            total_bytes=total if total is None or total > 0 else None,
        )

    def _publish(self, model: str, **updates: object) -> ModelStatus:
        with self._lock:
            status = self._statuses.get(model) or self.get_status(model)
            status.update(updates)  # type: ignore[typeddict-item]
            snapshot = status.copy()
        if self._on_status is not None:
            with suppress(Exception):
                self._on_status(snapshot)
        return snapshot

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
