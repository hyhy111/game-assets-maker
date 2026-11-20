"""Pinned Windows BiRefNet inference without a PyTorch dependency."""

import hashlib
import threading
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops

from src.core.resumable_download import Resource, ResumableResourceDownloader
from src.utils.background_models import LITE_MODEL
from src.utils.data_paths import models_root

MODEL_ID = LITE_MODEL
REVISION = "7a387b7aa4fa82a33adf7a0f32e2ea6678106a08"
WEIGHTS_BYTES = 114_538_221
WEIGHTS_SHA256 = "d39b897ceb16ae654c1731f3dba0cf9b368d9cae74b5a57459b455cc8bfec402"
WEIGHTS_SOURCES = {
    source: f"https://{host}/onnx-community/BiRefNet_lite-ONNX/resolve/{REVISION}/onnx/model_fp16.onnx"
    for source, host in (("modelscope", "modelscope.cn/models"), ("huggingface", "huggingface.co"))
}
_LOCK = threading.RLock()


def model_spec(model=MODEL_ID):
    if model != MODEL_ID:
        raise ValueError("Unsupported ONNX background-removal model")
    return {"bytes": WEIGHTS_BYTES, "sha256": WEIGHTS_SHA256, "sources": WEIGHTS_SOURCES}


def model_path(model=MODEL_ID) -> Path:
    model_spec(model)
    return models_root().with_name(model) / "model_fp16.onnx"


@lru_cache(maxsize=4)
def _digest(path: Path, modified: int) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def weights_available(model=MODEL_ID) -> bool:
    spec = model_spec(model)
    path = model_path(model)
    try:
        stat = path.stat()
        return stat.st_size == spec["bytes"] and _digest(path, stat.st_mtime_ns) == spec["sha256"]
    except OSError:
        return False


def resource_downloader(model=MODEL_ID):
    spec = model_spec(model)
    return ResumableResourceDownloader(Resource(model, spec["bytes"], spec["sha256"]), model_path(model))


def download_weights(progress, source="modelscope", cancel_event=None, model=MODEL_ID, verifying=None) -> None:
    spec = model_spec(model)
    if source not in spec["sources"]:
        raise ValueError("Unsupported model download source")
    resource_downloader(model).acquire(spec["sources"][source], source, progress, cancel_event, verifying)


@lru_cache(maxsize=1)
def _session(path: Path, modified: int):
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.intra_op_num_threads = 8
    return ort.InferenceSession(str(path), sess_options=options, providers=["CPUExecutionProvider"])


def get_session(model=MODEL_ID):
    with _LOCK:
        if not weights_available(model):
            raise ValueError("BiRefNet model checksum mismatch")
        path = model_path(model)
        return _session(path, path.stat().st_mtime_ns)


def remove_background(path: Path, model=MODEL_ID) -> Image.Image:
    with Image.open(path) as source:
        cutout = source.convert("RGBA")
    resized = cutout.convert("RGB").resize((1024, 1024), Image.Resampling.BILINEAR)
    array = np.asarray(resized, dtype=np.float32) / 255.0
    array = (array - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)
    tensor = np.ascontiguousarray(array.transpose(2, 0, 1)[None])
    with _LOCK:
        session = get_session(model)
        logits = session.run(None, {session.get_inputs()[0].name: tensor})[0][0, 0]
    if not np.isfinite(logits).all():
        raise ValueError(f"BiRefNet returned invalid alpha values: {path.name}")
    # This form of sigmoid avoids overflow for large negative logits.
    alpha = np.exp(-np.logaddexp(0, -logits))
    mask = Image.fromarray((alpha * 255).astype(np.uint8)).resize(cutout.size, Image.Resampling.LANCZOS)
    cutout.putalpha(ImageChops.multiply(cutout.getchannel("A"), mask))
    return cutout
