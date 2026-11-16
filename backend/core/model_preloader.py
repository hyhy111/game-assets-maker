"""Observable background-removal model preparation state."""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
from typing import Literal, Protocol, TypedDict

from backend.core import birefnet
from src.core.model_download import ModelDownloadCancelledError
from src.core.rembg_model import U2NET_SOURCES

MODEL_SOURCES = {"u2net": U2NET_SOURCES.keys(), birefnet.MODEL_ID: birefnet.WEIGHTS_SOURCES.keys()}


def validate_background_model(model: str) -> None:
    if not isinstance(model, str) or model not in MODEL_SOURCES:
        raise ValueError("Unsupported background-removal model")


ModelPhase = Literal["needs_download", "downloading", "initializing", "ready", "failed"]


class ModelStatus(TypedDict):
    model: str
    phase: ModelPhase
    downloaded_bytes: int | None
    total_bytes: int | None
    error: dict[str, str] | None


class ModelLoader(Protocol):
    def is_available(self, model: str) -> bool: ...

    def download(
        self,
        model: str,
        progress: Callable[[int, int | None], None],
        source: str,
        cancel_event: threading.Event | None = None,
    ) -> None: ...

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

    def download(
        self,
        model: str,
        progress: Callable[[int, int | None], None],
        source: str,
        cancel_event: threading.Event | None = None,
    ) -> None:
        from backend.core.smart_remove_background import _MODELS_DIR, check_model_available, get_model_file_size
        from src.core.rembg_model import download_u2net, validate_model

        validate_model(model)
        download_u2net(_MODELS_DIR, source, progress=progress, cancel_event=cancel_event)
        if not check_model_available(model):
            raise RuntimeError("rembg did not create the requested model file")
        size = get_model_file_size(model)
        if size is not None:
            progress(size, size)

    def initialize(self, model: str) -> None:
        from backend.core.smart_remove_background import get_rembg_session

        get_rembg_session(model)


class BackgroundModelLoader(RembgModelLoader):
    def is_available(self, model: str) -> bool:
        if model == birefnet.MODEL_ID:
            return birefnet.weights_available()
        return super().is_available(model)

    def download(
        self,
        model: str,
        progress: Callable[[int, int | None], None],
        source: str,
        cancel_event: threading.Event | None = None,
    ) -> None:
        if model == birefnet.MODEL_ID:
            birefnet.download_weights(progress, source, cancel_event)
        else:
            super().download(model, progress, source, cancel_event)

    def initialize(self, model: str) -> None:
        if model == birefnet.MODEL_ID:
            birefnet.get_session()
        else:
            super().initialize(model)


class ModelPreloader:
    def __init__(
        self,
        loader: ModelLoader,
        on_status: Callable[[ModelStatus], None] | None = None,
    ) -> None:
        self._loader = loader
        self._on_status = on_status
        # One worker per known model so both models can download in parallel.
        self._executor = ThreadPoolExecutor(max_workers=len(MODEL_SOURCES), thread_name_prefix="background-model")
        self._lock = threading.RLock()
        self._statuses: dict[str, ModelStatus] = {}
        self._active: dict[str, Future[None]] = {}
        self._cancel_events: dict[str, threading.Event] = {}

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
        if source is not None and source not in MODEL_SOURCES.get(model, ()):
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
            cancel_event = threading.Event()
            self._cancel_events[model] = cancel_event
            self._active[model] = self._executor.submit(self._prepare, model, needs_download, source, cancel_event)
            return status

    def retry(self, model: str, source: str | None = None) -> ModelStatus:
        return self.preload(model, retry=True, source=source)

    def cancel(self, model: str) -> ModelStatus:
        """Interrupt an in-progress download; the loader removes any partial file."""
        with self._lock:
            future = self._active.get(model)
            cancel_event = self._cancel_events.get(model)
            if (
                future is not None
                and not future.done()
                and cancel_event is not None
                and self.get_status(model)["phase"] == "downloading"
            ):
                cancel_event.set()
            return self.get_status(model)

    def wait(self, model: str, timeout: float | None = None) -> ModelStatus:
        with self._lock:
            future = self._active.get(model)
        if future is not None:
            future.result(timeout=timeout)
        return self.get_status(model)

    def _prepare(self, model: str, needs_download: bool, source: str | None, cancel_event: threading.Event) -> None:
        try:
            if needs_download:
                self._loader.download(
                    model,
                    lambda current, total: self._download_progress(model, current, total),
                    source,
                    cancel_event,
                )
                current = self.get_status(model)
                downloaded = current["total_bytes"] if current["total_bytes"] is not None else None
                self._publish(model, phase="initializing", downloaded_bytes=downloaded)
            self._loader.initialize(model)
            self._publish(model, phase="ready", error=None)
        except ModelDownloadCancelledError:
            self._publish(model, phase="needs_download", downloaded_bytes=None, total_bytes=None, error=None)
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
        with self._lock:
            for cancel_event in self._cancel_events.values():
                cancel_event.set()
        self._executor.shutdown(wait=False, cancel_futures=True)
