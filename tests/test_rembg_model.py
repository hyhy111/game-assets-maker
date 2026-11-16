"""Exercise cached downloads, checksum failures, and cancellation without external network."""

import hashlib
import threading
from pathlib import Path

import pytest
import requests

from src.core import rembg_model
from src.core.model_download import ModelDownloadCancelledError


class _FakeStreamResponse:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks
        self.headers = {"Content-Length": str(sum(len(chunk) for chunk in chunks))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def raise_for_status(self) -> None:
        pass

    def iter_content(self, _size: int):
        yield from self._chunks


@pytest.mark.parametrize("source", ["modelscope", "github"])
def test_download_verifies_weights_reuses_cache_and_rejects_bad_content(tmp_path, monkeypatch, source):
    content = b"test model weights"
    calls = []

    def fake_get(url, **_kwargs):
        calls.append(url)
        return _FakeStreamResponse([content])

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(rembg_model, "U2NET_HASH", "md5:" + hashlib.md5(content).hexdigest())
    progress_calls = []
    destination = rembg_model.download_u2net(
        tmp_path, source, progress=lambda current, total: progress_calls.append((current, total))
    )
    assert progress_calls == [(len(content), len(content))]
    assert rembg_model.download_u2net(tmp_path, source) == destination
    assert calls == [rembg_model.U2NET_SOURCES[source]]
    Path(destination).unlink()
    content = b"corrupted response"
    with pytest.raises(ValueError, match="hash"):
        rembg_model.download_u2net(tmp_path, source)
    assert not Path(destination).exists()
    assert not list(tmp_path.glob(".u2net-*"))


def test_cancelled_download_removes_partial_file(tmp_path, monkeypatch):
    cancel_event = threading.Event()

    class CancellableResponse(_FakeStreamResponse):
        def iter_content(self, _size: int):
            for chunk in self._chunks:
                cancel_event.set()  # the user cancels while the first chunk is in flight
                yield chunk

    monkeypatch.setattr(requests, "get", lambda *a, **kw: CancellableResponse([b"partial weights"]))
    with pytest.raises(ModelDownloadCancelledError):
        rembg_model.download_u2net(tmp_path, "modelscope", cancel_event=cancel_event)
    assert not (tmp_path / "u2net.onnx").exists()
    assert not list(tmp_path.glob(".u2net-*"))


def test_inference_does_not_download_missing_model(tmp_path, monkeypatch):
    from backend.core import smart_remove_background as background

    monkeypatch.setattr(background, "_MODELS_DIR", tmp_path)
    monkeypatch.setattr(background, "_session_cache", {})
    with pytest.raises(RuntimeError, match="MODEL_DOWNLOAD_REQUIRED"):
        background.get_rembg_session()


def test_model_availability_migrates_valid_legacy_windows_cache(tmp_path, monkeypatch):
    from backend.core import smart_remove_background as background
    from backend.core.model_preloader import RembgModelLoader

    content = b"legacy u2net weights"
    legacy_model = tmp_path / "LocalAppData" / "VideoToSheet" / "models" / "rembg" / "u2net.onnx"
    legacy_model.parent.mkdir(parents=True)
    legacy_model.write_bytes(content)
    destination = tmp_path / ".gam" / "models" / "rembg"

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path / ".gam"))
    monkeypatch.setattr(background, "_MODELS_DIR", destination)
    monkeypatch.setattr(rembg_model, "U2NET_HASH", "md5:" + hashlib.md5(content).hexdigest())

    assert RembgModelLoader().is_available("u2net") is True
    assert (destination / "u2net.onnx").read_bytes() == content
    assert legacy_model.read_bytes() == content
    assert not list(destination.glob("*.migrating"))


def test_model_availability_rejects_invalid_legacy_windows_cache(tmp_path, monkeypatch):
    from backend.core import smart_remove_background as background
    from backend.core.model_preloader import RembgModelLoader

    legacy_model = tmp_path / "LocalAppData" / "VideoToSheet" / "models" / "rembg" / "u2net.onnx"
    legacy_model.parent.mkdir(parents=True)
    legacy_model.write_bytes(b"corrupted")
    destination = tmp_path / ".gam" / "models" / "rembg"

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path / ".gam"))
    monkeypatch.setattr(background, "_MODELS_DIR", destination)
    monkeypatch.setattr(rembg_model, "U2NET_HASH", "md5:" + hashlib.md5(b"valid").hexdigest())

    assert RembgModelLoader().is_available("u2net") is False
    assert legacy_model.read_bytes() == b"corrupted"
    assert not (destination / "u2net.onnx").exists()
    assert not list(destination.glob("*.migrating"))
