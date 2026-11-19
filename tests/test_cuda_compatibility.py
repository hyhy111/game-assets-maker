import ctypes
from types import SimpleNamespace

import pytest

from backend.core import cuda_compatibility


@pytest.mark.parametrize(
    ("capability", "version", "state"),
    [
        ((7, 5), 13000, "compatible"),
        ((8, 9), 13020, "compatible"),
        ((6, 1), 13000, "unsupported"),
        ((8, 9), 12090, "driver"),
    ],
)
def test_preflight_uses_the_default_cuda_devices_capability_and_driver(monkeypatch, capability, version, state):
    def set_value(output, value):
        output._obj.value = value
        return 0

    def read_device(output, ordinal):
        assert ordinal == 0
        return set_value(output, ordinal)

    attributes = {75: capability[0], 76: capability[1]}
    driver = SimpleNamespace(
        cuInit=lambda _: 0,
        cuDeviceGet=read_device,
        cuDriverGetVersion=lambda output: set_value(output, version),
        cuDeviceGetAttribute=lambda output, attribute, _: set_value(output, attributes[attribute]),
        cuDeviceGetName=lambda output, *_: setattr(output, "value", b"GeForce RTX 4060 Ti") or 0,
    )
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_, **__: driver, raising=False)
    result = cuda_compatibility.detect_cuda_compatibility()
    assert result["state"] == state
    if state == "compatible":
        assert result["name"] == "GeForce RTX 4060 Ti"


@pytest.mark.parametrize(
    ("device_ids", "expected"),
    [
        (["PCI\\VEN_1002"], "no_nvidia"),
        (["PCI\\VEN_8086", "PCI\\VEN_10DE"], "driver"),
        (["ROOT\\DISPLAY"], "unknown"),
        ([], "unknown"),
    ],
)
def test_preflight_checks_display_adapters_when_cuda_dll_is_missing(monkeypatch, device_ids, expected):
    def enumerate_display(_name, index, adapter, _flags):
        if index >= len(device_ids):
            return 0
        assert adapter._obj.cb == ctypes.sizeof(adapter._obj)
        adapter._obj.DeviceID = device_ids[index]
        return 1

    def load_dll(name, *, winmode):
        assert winmode == 0x800
        if name == "nvcuda.dll":
            raise OSError("CUDA driver library missing")
        assert name == "user32.dll"
        return SimpleNamespace(EnumDisplayDevicesW=enumerate_display)

    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr(ctypes, "WinDLL", load_dll, raising=False)
    assert cuda_compatibility.detect_cuda_compatibility() == {"state": expected}
