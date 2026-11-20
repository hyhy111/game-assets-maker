"""Run the Comfy-Org BiRefNet checkpoint locally using the author's PyTorch architecture."""

import hashlib
import os
import tempfile
import threading
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops

from src.core.model_download import ModelDownloadCancelledError
from src.utils.data_paths import models_root
from src.utils.diagnostics import record_network_error

MODEL_ID = "birefnet-comfy"
WEIGHTS_NAME = "birefnet.safetensors"
WEIGHTS_SOURCES = {
    "modelscope": "https://modelscope.cn/models/Comfy-Org/BiRefNet/resolve/master/background_removal/birefnet.safetensors",
    "huggingface": "https://huggingface.co/Comfy-Org/BiRefNet/resolve/"
    "35767b272f2846752a3aee1259abdd4586f735c8/background_removal/birefnet.safetensors",
}
WEIGHTS_SHA256 = "9ab37426bf4de0567af6b5d21b16151357149139362e6e8992021b8ce356a154"
WEIGHTS_BYTES = 444_473_596

_INFERENCE_LOCK = threading.Lock()
_SESSION_LOCK = threading.RLock()
_SESSIONS: dict[str, tuple] = {}
# Set after CUDA placement or inference runs out of memory, so later frames stay on CPU.
_CPU_FALLBACK = False


def model_path() -> Path:
    return models_root().with_name(MODEL_ID) / WEIGHTS_NAME


def weights_available() -> bool:
    path = model_path()
    try:
        stat = path.stat()
        return stat.st_size == WEIGHTS_BYTES and _checkpoint_digest(path, stat.st_mtime_ns) == WEIGHTS_SHA256
    except OSError:
        return False


@lru_cache(maxsize=1)
def _checkpoint_digest(path: Path, _modified_at: int) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download_weights(
    progress: Callable[[int, int | None], None],
    source: str = "modelscope",
    cancel_event: threading.Event | None = None,
) -> None:
    import requests

    if source not in WEIGHTS_SOURCES:
        raise ValueError("Unsupported model download source")
    url = WEIGHTS_SOURCES[source]
    path = model_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with (
            requests.get(url, stream=True, timeout=(10, 60)) as response,
            tempfile.NamedTemporaryFile(dir=path.parent, prefix=".birefnet-", delete=False) as stream,
        ):
            temporary = Path(stream.name)
            response.raise_for_status()
            received = 0
            digest = hashlib.sha256()
            for chunk in response.iter_content(1024 * 1024):
                if cancel_event is not None and cancel_event.is_set():
                    raise ModelDownloadCancelledError("BiRefNet checkpoint download cancelled")
                received += len(chunk)
                if received > WEIGHTS_BYTES:
                    raise ValueError("Unexpected BiRefNet checkpoint size")
                digest.update(chunk)
                stream.write(chunk)
                progress(received, WEIGHTS_BYTES)
        if received != WEIGHTS_BYTES or digest.hexdigest() != WEIGHTS_SHA256:
            raise ValueError("BiRefNet checkpoint checksum mismatch")
        os.replace(temporary, path)
    except requests.RequestException as error:
        record_network_error("GET", url, error)
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def select_inference_device(torch_module, *, allow_cuda: bool = True):
    """Prefer CUDA, then MPS, then CPU.

    ``cuda.is_available()`` is true only for a CUDA build of PyTorch with a
    compatible NVIDIA driver. A CPU wheel stays on CPU even if the CUDA toolkit
    is installed on the machine.
    """
    if allow_cuda:
        cuda = getattr(torch_module, "cuda", None)
        if cuda is not None and cuda.is_available():
            return torch_module.device("cuda")
    mps = getattr(getattr(torch_module, "backends", None), "mps", None)
    if mps is not None and mps.is_available():
        return torch_module.device("mps")
    return torch_module.device("cpu")


def inference_dtype(torch_module, device):
    # MPS already runs this checkpoint in float16. CUDA stays in float32 because
    # the upstream config leaves float16 off after it produced NaNs.
    if device.type == "mps":
        return torch_module.float16
    return torch_module.float32


def cuda_memory_error(error: BaseException) -> bool:
    return isinstance(error, RuntimeError) and "out of memory" in str(error).lower()


def get_session():
    import torch

    with _SESSION_LOCK:
        device = select_inference_device(torch, allow_cuda=not _CPU_FALLBACK)
        try:
            return _session_for(torch, device.type)
        except RuntimeError:
            if device.type != "cuda":
                raise
            _discard_cuda(torch)
            return _session_for(torch, "cpu")


def _session_for(torch_module, device_type: str):
    session = _SESSIONS.get(device_type)
    if session is None:
        session = _build_session(torch_module, device_type)
        _SESSIONS[device_type] = session
    return session


def _discard_cuda(torch_module) -> None:
    """Keep later frames on CPU and free the CUDA session.

    When the CUDA weights are already loaded, move that module to CPU instead of
    reading the checkpoint again.
    """
    global _CPU_FALLBACK
    with _SESSION_LOCK:
        _CPU_FALLBACK = True
        session = _SESSIONS.pop("cuda", None)
        if session is not None and "cpu" not in _SESSIONS:
            model, _device, _dtype, transform = session
            device = torch_module.device("cpu")
            dtype = inference_dtype(torch_module, device)
            model.to(device=device, dtype=dtype)
            _SESSIONS["cpu"] = (model, device, dtype, transform)
            session = None
    if session is not None:
        session[0].to(torch_module.device("cpu"))
    cuda = getattr(torch_module, "cuda", None)
    if cuda is not None and cuda.is_available():
        cuda.empty_cache()


def _build_session(torch_module, device_type: str):
    from safetensors.torch import load_file
    from torchvision import transforms

    from backend.core._vendor.birefnet import BiRefNet

    path = model_path()
    if not weights_available():
        raise ValueError("BiRefNet checkpoint checksum mismatch")
    model = BiRefNet().eval()
    model.load_state_dict(load_file(str(path)), strict=True)
    device = torch_module.device(device_type)
    dtype = inference_dtype(torch_module, device)
    model.to(device=device, dtype=dtype)
    transform = transforms.Compose(
        [
            transforms.Resize((1024, 1024)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]
    )
    return model, device, dtype, transform


def _forward(torch_module, model, device, dtype, transform, image: Image.Image):
    with torch_module.inference_mode():
        tensor = transform(image.convert("RGB")).unsqueeze(0).to(device=device, dtype=dtype)
        return model(tensor)[-1].sigmoid()[0, 0].float().cpu().numpy()


def remove_background(path: Path) -> Image.Image:
    import torch

    with Image.open(path) as source:
        cutout = source.convert("RGBA")
    with _INFERENCE_LOCK:
        model, device, dtype, transform = get_session()
        try:
            alpha = _forward(torch, model, device, dtype, transform, cutout)
        except RuntimeError as error:
            if device.type != "cuda" or not cuda_memory_error(error):
                raise
            _discard_cuda(torch)
            model, device, dtype, transform = get_session()
            alpha = _forward(torch, model, device, dtype, transform, cutout)
    if not np.isfinite(alpha).all():
        raise ValueError(f"BiRefNet returned invalid alpha values: {path.name}")
    mask = Image.fromarray((alpha * 255).astype(np.uint8)).resize(cutout.size, Image.Resampling.LANCZOS)
    cutout.putalpha(ImageChops.multiply(cutout.getchannel("A"), mask))
    return cutout
