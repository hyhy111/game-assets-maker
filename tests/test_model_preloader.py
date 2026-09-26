from __future__ import annotations

import threading
import time
from collections.abc import Callable

import pytest

from backend.api.process_api import ProcessAPI
from backend.core.model_preloader import ModelPreloader


class FakeModelLoader:
    def __init__(self, *, available: bool, blocked: bool = False) -> None:
        self.available = available
        self.blocked = blocked
        self.download_calls = 0
        self.download_sources = []
        self.initialize_calls = 0
        self.download_started = threading.Event()
        self.allow_download = threading.Event()
        self.initialize_started = threading.Event()
        self.allow_initialize = threading.Event()
        self.download_errors: list[Exception] = []
        self.initialize_errors: list[Exception] = []

    def is_available(self, _model: str) -> bool:
        return self.available

    def download(self, _model: str, _progress: Callable[[int, int | None], None], source: str) -> None:
        self.download_calls += 1
        self.download_sources.append(source)
        _progress(4, 10)
        self.download_started.set()
        if self.download_errors:
            raise self.download_errors.pop(0)
        if self.blocked:
            assert self.allow_download.wait(2)
        self.available = True

    def initialize(self, _model: str) -> None:
        self.initialize_calls += 1
        self.initialize_started.set()
        if self.initialize_errors:
            raise self.initialize_errors.pop(0)
        if self.blocked:
            assert self.allow_initialize.wait(2)


def test_missing_model_reports_that_a_download_is_needed() -> None:
    preloader = ModelPreloader(FakeModelLoader(available=False))
    try:
        assert preloader.get_status("u2net") == {
            "model": "u2net",
            "phase": "needs_download",
            "downloaded_bytes": None,
            "total_bytes": None,
            "error": None,
        }
    finally:
        preloader.shutdown()


def test_existing_model_skips_download_and_initializes() -> None:
    loader = FakeModelLoader(available=True)
    preloader = ModelPreloader(loader)
    try:
        assert preloader.get_status("u2net")["phase"] == "initializing"
        preloader.preload("u2net", source="modelscope")
        assert preloader.wait("u2net", timeout=1)["phase"] == "ready"
        assert loader.download_calls == 0
        assert loader.initialize_calls == 1
    finally:
        preloader.shutdown()


def test_failed_download_has_safe_error_and_concurrent_retry_is_deduplicated() -> None:
    loader = FakeModelLoader(available=False)
    loader.download_errors.append(OSError("private path and provider details"))
    preloader = ModelPreloader(loader)
    try:
        preloader.preload("u2net", source="modelscope")
        assert preloader.wait("u2net", timeout=1) == {
            "model": "u2net",
            "phase": "failed",
            "downloaded_bytes": 4,
            "total_bytes": 10,
            "error": {"code": "MODEL_DOWNLOAD_FAILED", "message": "Model download failed"},
        }

        loader.blocked = True
        loader.download_started.clear()
        first_retry = preloader.retry("u2net", source="modelscope")
        second_retry = preloader.retry("u2net", source="modelscope")
        assert first_retry["phase"] == "downloading"
        assert second_retry["phase"] == "downloading"
        assert loader.download_started.wait(1)
        assert loader.download_calls == 2

        loader.allow_download.set()
        loader.allow_initialize.set()
        assert preloader.wait("u2net", timeout=1)["phase"] == "ready"
    finally:
        preloader.shutdown()


def test_failed_initialization_is_distinguished_from_download_failure() -> None:
    loader = FakeModelLoader(available=True)
    loader.initialize_errors.append(RuntimeError("provider-specific failure"))
    preloader = ModelPreloader(loader)
    try:
        preloader.preload("u2net", source="modelscope")
        status = preloader.wait("u2net", timeout=1)
        assert status["phase"] == "failed"
        assert status["error"] == {
            "code": "MODEL_INITIALIZATION_FAILED",
            "message": "Model initialization failed",
        }
    finally:
        preloader.shutdown()


def test_missing_model_moves_through_download_initialization_and_ready() -> None:
    loader = FakeModelLoader(available=False, blocked=True)
    preloader = ModelPreloader(loader)
    try:
        assert preloader.preload("u2net", source="modelscope")["phase"] == "downloading"
        assert loader.download_started.wait(1)
        assert preloader.get_status("u2net") == {
            "model": "u2net",
            "phase": "downloading",
            "downloaded_bytes": 4,
            "total_bytes": 10,
            "error": None,
        }

        loader.allow_download.set()
        assert loader.initialize_started.wait(1)
        assert preloader.get_status("u2net")["phase"] == "initializing"

        loader.allow_initialize.set()
        assert preloader.wait("u2net", timeout=1)["phase"] == "ready"
        assert loader.download_calls == 1
        assert loader.initialize_calls == 1
    finally:
        preloader.shutdown()


class FakeWindow:
    def __init__(self) -> None:
        self.scripts: list[str] = []

    def evaluate_js(self, script: str) -> None:
        self.scripts.append(script)


def test_process_api_exposes_status_and_emits_shared_model_status_event(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "project").mkdir()
    loader = FakeModelLoader(available=False)
    window = FakeWindow()
    api = ProcessAPI(window=window, model_loader=loader)
    try:
        assert api.get_model_status("u2net")["phase"] == "needs_download"
        assert api.preload_model("u2net", "modelscope")["phase"] == "downloading"

        deadline = time.monotonic() + 1
        while api.get_model_status("u2net")["phase"] != "ready" and time.monotonic() < deadline:
            time.sleep(0.01)

        assert api.get_model_status("u2net")["phase"] == "ready"
        assert any("model-status" in script and '"phase": "ready"' in script for script in window.scripts)
    finally:
        api.shutdown()


def test_process_api_rejects_unsupported_model(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "project").mkdir()
    loader = FakeModelLoader(available=True)
    api = ProcessAPI(model_loader=loader)
    try:
        api.preload_model("u2net", "modelscope")
        deadline = time.monotonic() + 1
        while api.get_model_status("u2net")["phase"] != "ready" and time.monotonic() < deadline:
            time.sleep(0.01)
        assert api.get_model_status("u2net")["phase"] == "ready"

        with pytest.raises(ValueError, match="Only u2net"):
            api.start_processing("unused", 2, {"model": "isnet-anime"})
    finally:
        api.shutdown()


@pytest.mark.parametrize("method", ["get_model_status", "preload_model", "retry_model"])
def test_model_api_rejects_other_models(method):
    api = ProcessAPI(model_loader=FakeModelLoader(available=True))
    try:
        with pytest.raises(ValueError, match="Only u2net"):
            getattr(api, method)("isnet-anime")
    finally:
        api.shutdown()


def test_step2_requires_ready_u2net():
    api = ProcessAPI(model_loader=FakeModelLoader(available=False))
    try:
        with pytest.raises(RuntimeError, match="MODEL_NOT_READY"):
            api.start_processing("unused", 2, {"model": "u2net"})
    finally:
        api.shutdown()


@pytest.mark.parametrize("source", ["modelscope", "github"])
def test_missing_model_waits_for_explicit_source(source):
    loader = FakeModelLoader(available=False)
    preloader = ModelPreloader(loader)
    try:
        assert preloader.preload("u2net")["phase"] == "needs_download"
        assert preloader.retry("u2net")["phase"] == "needs_download"
        assert loader.download_calls == 0
        preloader.preload("u2net", source=source)
        assert preloader.wait("u2net", timeout=1)["phase"] == "ready"
        assert loader.download_sources == [source]
    finally:
        preloader.shutdown()


def test_existing_model_initializes_without_download_choice():
    loader = FakeModelLoader(available=True)
    preloader = ModelPreloader(loader)
    try:
        preloader.preload("u2net")
        assert preloader.wait("u2net", timeout=1)["phase"] == "ready"
        assert loader.download_calls == 0
    finally:
        preloader.shutdown()


def test_invalid_source_cannot_start_download():
    loader = FakeModelLoader(available=False)
    preloader = ModelPreloader(loader)
    try:
        with pytest.raises(ValueError, match="Unsupported model download source"):
            preloader.preload("u2net", source="https://example.com/model")
        assert loader.download_calls == 0
    finally:
        preloader.shutdown()
