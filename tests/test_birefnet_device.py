"""BiRefNet device selection, without loading the checkpoint or requiring a GPU."""

import numpy as np
import pytest
from PIL import Image

from backend.core import birefnet


class _Flag:
    def __init__(self, available: bool) -> None:
        self.available = available
        self.emptied = False

    def is_available(self) -> bool:
        return self.available

    def empty_cache(self) -> None:
        self.emptied = True


class _Device:
    def __init__(self, name: str) -> None:
        self.type = name


class _Torch:
    def __init__(self, *, cuda: bool = False, mps: bool = False) -> None:
        self.cuda = _Flag(cuda)
        self.backends = type("Backends", (), {"mps": _Flag(mps)})()
        self.float16 = "float16"
        self.float32 = "float32"

    def device(self, name: str) -> _Device:
        return _Device(name)


class _Model:
    def __init__(self) -> None:
        self.moves: list[tuple[str, object]] = []

    def to(self, device=None, dtype=None):
        self.moves.append((device.type, dtype))
        return self

    def __call__(self, *_args, **_kwargs):
        raise AssertionError("model forward is stubbed in these tests")


@pytest.fixture(autouse=True)
def _reset_device_state():
    birefnet._SESSIONS.clear()
    birefnet._CPU_FALLBACK = False
    yield
    birefnet._SESSIONS.clear()
    birefnet._CPU_FALLBACK = False


def test_cuda_wins_over_mps_and_cpu():
    torch_module = _Torch(cuda=True, mps=True)
    assert birefnet.select_inference_device(torch_module).type == "cuda"
    assert birefnet.inference_dtype(torch_module, _Device("cuda")) == "float32"


def test_mps_is_used_when_cuda_is_unavailable():
    torch_module = _Torch(mps=True)
    assert birefnet.select_inference_device(torch_module).type == "mps"
    assert birefnet.inference_dtype(torch_module, _Device("mps")) == "float16"


def test_cpu_is_the_fallback_device():
    torch_module = _Torch()
    assert birefnet.select_inference_device(torch_module).type == "cpu"
    assert birefnet.inference_dtype(torch_module, _Device("cpu")) == "float32"


def test_cuda_can_be_disabled_after_a_memory_failure():
    torch_module = _Torch(cuda=True, mps=True)
    selected = birefnet.select_inference_device(torch_module, allow_cuda=False)
    assert selected.type == "mps"


def test_cuda_placement_failure_sticks_to_cpu(monkeypatch):
    attempts = []

    def build(_torch_module, device_type: str):
        attempts.append(device_type)
        if device_type == "cuda":
            raise RuntimeError("CUDA out of memory")
        return ("cpu-model", _Device(device_type), "float32", "transform")

    def select(*_args, **kwargs):
        return _Device("cuda" if kwargs.get("allow_cuda", True) else "cpu")

    monkeypatch.setattr(birefnet, "select_inference_device", select)
    monkeypatch.setattr(birefnet, "_build_session", build)

    first = birefnet.get_session()
    second = birefnet.get_session()

    assert attempts == ["cuda", "cpu"]
    assert first[1].type == "cpu"
    assert second[1].type == "cpu"
    assert birefnet._CPU_FALLBACK is True


def test_discard_reuses_the_loaded_cuda_module():
    torch_module = _Torch(cuda=True)
    model = _Model()
    birefnet._SESSIONS["cuda"] = (model, _Device("cuda"), "float32", "transform")

    birefnet._discard_cuda(torch_module)

    assert "cuda" not in birefnet._SESSIONS
    kept, device, dtype, transform = birefnet._SESSIONS["cpu"]
    assert kept is model
    assert device.type == "cpu"
    assert dtype == "float32"
    assert transform == "transform"
    assert model.moves == [("cpu", "float32")]
    assert torch_module.cuda.emptied is True
    assert birefnet._CPU_FALLBACK is True


def test_inference_out_of_memory_retries_on_cpu(tmp_path, monkeypatch):
    frame = tmp_path / "frame.png"
    Image.new("RGB", (4, 4), "white").save(frame)
    calls = []

    def get_session():
        device_type = "cpu" if birefnet._CPU_FALLBACK else "cuda"
        return ("model", _Device(device_type), "float32", None)

    def forward(_torch_module, _model, device, _dtype, _transform, image):
        calls.append((device.type, image.size))
        if device.type == "cuda":
            raise RuntimeError("CUDA out of memory. Tried to allocate 20.00 MiB")
        return np.ones((4, 4), dtype=np.float32)

    monkeypatch.setattr(birefnet, "get_session", get_session)
    monkeypatch.setattr(birefnet, "_forward", forward)

    result = birefnet.remove_background(frame)

    assert calls == [("cuda", (4, 4)), ("cpu", (4, 4))]
    assert result.mode == "RGBA"
    assert result.size == (4, 4)
    assert birefnet._CPU_FALLBACK is True


def test_other_cuda_runtime_errors_are_not_retried_on_cpu(tmp_path, monkeypatch):
    frame = tmp_path / "frame.png"
    Image.new("RGB", (4, 4), "white").save(frame)

    monkeypatch.setattr(birefnet, "get_session", lambda: ("model", _Device("cuda"), "float32", None))

    def forward(*_args, **_kwargs):
        raise RuntimeError("CUDA device-side assert triggered")

    monkeypatch.setattr(birefnet, "_forward", forward)

    with pytest.raises(RuntimeError, match="device-side assert"):
        birefnet.remove_background(frame)
    assert birefnet._CPU_FALLBACK is False
