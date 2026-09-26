"""Exercise cached downloads and checksum failures without external network."""

import hashlib
from pathlib import Path

import pooch
import pytest

from src.core import rembg_model


@pytest.mark.parametrize("source", ["modelscope", "github"])
def test_download_verifies_weights_reuses_cache_and_rejects_bad_content(tmp_path, monkeypatch, source):
    content = b"test model weights"
    calls = []

    def transfer(url, output_file, pooch_instance, check_only=False):
        calls.append(url)
        with open(output_file, "wb") as output:
            output.write(content)

    monkeypatch.setattr(pooch.core, "choose_downloader", lambda *a, **kw: transfer)
    monkeypatch.setattr(rembg_model, "U2NET_HASH", "md5:" + hashlib.md5(content).hexdigest())
    destination = rembg_model.download_u2net(tmp_path, source)
    assert rembg_model.download_u2net(tmp_path, source) == destination
    assert calls == [rembg_model.U2NET_SOURCES[source]]
    Path(destination).unlink()
    content = b"corrupted response"
    with pytest.raises(ValueError, match="hash"):
        rembg_model.download_u2net(tmp_path, source)
    assert not Path(destination).exists()


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
