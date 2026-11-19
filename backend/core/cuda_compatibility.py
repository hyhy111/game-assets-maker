"""Check the Windows CUDA driver before acquiring the pinned runtime."""

import ctypes
import sys
from ctypes import wintypes
from itertools import count

_SYSTEM32 = 0x00000800
_CUDA_13 = 13000
_MIN_COMPUTE_CAPABILITY = (7, 5)
_COMPUTE_CAPABILITY_MAJOR = 75
_COMPUTE_CAPABILITY_MINOR = 76
_CUDA_ERROR_NO_DEVICE = 100


class _DisplayDevice(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("DeviceName", wintypes.WCHAR * 32),
        ("DeviceString", wintypes.WCHAR * 128),
        ("StateFlags", wintypes.DWORD),
        ("DeviceID", wintypes.WCHAR * 128),
        ("DeviceKey", wintypes.WCHAR * 128),
    ]


def _display_status():
    """Identify an NVIDIA display adapter even if its CUDA driver cannot load."""
    enumerate_display = ctypes.WinDLL("user32.dll", winmode=_SYSTEM32).EnumDisplayDevicesW
    seen_pci_adapter = False
    for index in count():
        adapter = _DisplayDevice(cb=ctypes.sizeof(_DisplayDevice))
        if not enumerate_display(None, index, ctypes.byref(adapter), 0):
            return {"state": "no_nvidia" if seen_pci_adapter else "unknown"}
        device_id = adapter.DeviceID.upper()
        if device_id.startswith("PCI\\VEN_10DE") or "NVIDIA" in adapter.DeviceString.upper():
            return {"state": "driver"}
        seen_pci_adapter |= device_id.startswith("PCI\\VEN_")


def detect_cuda_compatibility() -> dict:
    if sys.platform != "win32":
        return {"state": "unknown"}

    try:
        try:
            driver = ctypes.WinDLL("nvcuda.dll", winmode=_SYSTEM32)
        except OSError:
            return _display_status()

        result = driver.cuInit(0)
        if result == _CUDA_ERROR_NO_DEVICE:
            return _display_status()
        if result:
            return {"state": "unknown"}

        # ONNX Runtime uses CUDA device 0 unless configured otherwise.
        device = ctypes.c_int()
        version = ctypes.c_int()
        major = ctypes.c_int()
        minor = ctypes.c_int()
        if (
            driver.cuDeviceGet(ctypes.byref(device), 0)
            or driver.cuDriverGetVersion(ctypes.byref(version))
            or driver.cuDeviceGetAttribute(ctypes.byref(major), _COMPUTE_CAPABILITY_MAJOR, device)
            or driver.cuDeviceGetAttribute(ctypes.byref(minor), _COMPUTE_CAPABILITY_MINOR, device)
        ):
            return {"state": "unknown"}

        # The CUDA 13 wheels require Turing (compute capability 7.5) or newer.
        if (major.value, minor.value) < _MIN_COMPUTE_CAPABILITY:
            return {"state": "unsupported"}
        if version.value < _CUDA_13:
            return {"state": "driver"}

        name = ctypes.create_string_buffer(256)
        if driver.cuDeviceGetName(name, len(name), device) == 0 and name.value:
            return {"state": "compatible", "name": name.value.decode("utf-8", errors="replace")}
        return {"state": "compatible"}
    except (OSError, AttributeError):
        return {"state": "unknown"}
