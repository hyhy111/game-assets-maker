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

from src.utils.data_paths import models_root
from src.utils.diagnostics import record_network_error

MODEL_ID = "birefnet-comfy"
WEIGHTS_NAME = "birefnet.safetensors"
WEIGHTS_URL = "https://modelscope.cn/models/Comfy-Org/BiRefNet/resolve/master/background_removal/birefnet.safetensors"
WEIGHTS_SHA256 = "9ab37426bf4de0567af6b5d21b16151357149139362e6e8992021b8ce356a154"
WEIGHTS_BYTES = 444_473_596

_INFERENCE_LOCK = threading.Lock()


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


def download_weights(progress: Callable[[int, int | None], None]) -> None:
    import requests

    path = model_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with (
            requests.get(WEIGHTS_URL, stream=True, timeout=(10, 60)) as response,
            tempfile.NamedTemporaryFile(dir=path.parent, prefix=".birefnet-", delete=False) as stream,
        ):
            temporary = Path(stream.name)
            response.raise_for_status()
            received = 0
            digest = hashlib.sha256()
            for chunk in response.iter_content(1024 * 1024):
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
        record_network_error("GET", WEIGHTS_URL, error)
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@lru_cache(maxsize=1)
def get_session():
    import torch
    from safetensors.torch import load_file
    from torchvision import transforms

    from backend.core._vendor.birefnet import BiRefNet

    path = model_path()
    if not weights_available():
        raise ValueError("BiRefNet checkpoint checksum mismatch")
    model = BiRefNet().eval()
    model.load_state_dict(load_file(str(path)), strict=True)
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    dtype = torch.float16 if device.type == "mps" else torch.float32
    model.to(device=device, dtype=dtype)
    transform = transforms.Compose(
        [
            transforms.Resize((1024, 1024)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]
    )
    return model, device, dtype, transform


def remove_background(path: Path) -> Image.Image:
    import torch

    model, device, dtype, transform = get_session()
    with Image.open(path) as source:
        cutout = source.convert("RGBA")
    with _INFERENCE_LOCK, torch.inference_mode():
        tensor = transform(cutout.convert("RGB")).unsqueeze(0).to(device=device, dtype=dtype)
        alpha = model(tensor)[-1].sigmoid()[0, 0].float().cpu().numpy()
    if not np.isfinite(alpha).all():
        raise ValueError(f"BiRefNet returned invalid alpha values: {path.name}")
    mask = Image.fromarray((alpha * 255).astype(np.uint8)).resize(cutout.size, Image.Resampling.LANCZOS)
    cutout.putalpha(ImageChops.multiply(cutout.getchannel("A"), mask))
    return cutout
