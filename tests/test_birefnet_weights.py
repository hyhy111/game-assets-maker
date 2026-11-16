"""Test download source routing and checksum enforcement without network access."""

import hashlib
from contextlib import contextmanager
from unittest.mock import Mock

import pytest
import requests

from backend.core import birefnet
from backend.core.model_preloader import BackgroundModelLoader


def test_birefnet_sources_use_the_same_verified_checkpoint(tmp_path, monkeypatch):
    checkpoint = tmp_path / birefnet.WEIGHTS_NAME
    weights = b"test weights"
    bad_weights = b"bad contents"
    urls = []
    body = weights

    @contextmanager
    def get(url, **_kwargs):
        urls.append(url)
        yield Mock(iter_content=Mock(return_value=iter([body])))

    monkeypatch.setattr(birefnet, "model_path", lambda: checkpoint)
    monkeypatch.setattr(birefnet, "WEIGHTS_BYTES", len(weights))
    monkeypatch.setattr(birefnet, "WEIGHTS_SHA256", hashlib.sha256(weights).hexdigest())
    monkeypatch.setattr(requests, "get", get)
    loader = BackgroundModelLoader()

    for source in ("modelscope", "huggingface"):
        loader.download(birefnet.MODEL_ID, lambda *_: None, source)
        assert loader.is_available(birefnet.MODEL_ID)
        assert checkpoint.read_bytes() == weights
    assert urls[0].startswith("https://modelscope.cn/")
    assert urls[1] == (
        "https://huggingface.co/Comfy-Org/BiRefNet/resolve/"
        "35767b272f2846752a3aee1259abdd4586f735c8/background_removal/birefnet.safetensors"
    )

    body = bad_weights
    with pytest.raises(ValueError, match="checksum mismatch"):
        loader.download(birefnet.MODEL_ID, lambda *_: None, "huggingface")
    assert checkpoint.read_bytes() == weights
    assert list(tmp_path.iterdir()) == [checkpoint]
