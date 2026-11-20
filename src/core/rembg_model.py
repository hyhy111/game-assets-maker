"""U2Net weights downloaded from ModelScope without its SDK."""

import hashlib
import os
import shutil
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path

from src.core.model_download import ModelDownloadCancelledError
from src.utils.data_paths import INSTALLED_MODE, data_mode
from src.utils.diagnostics import record_network_error

U2NET_URL = "https://modelscope.cn/models/AI-ModelScope/u2net/resolve/master/u2net.onnx"
U2NET_HASH = "md5:60024c5c889badc19c04ad937298a77b"


def validate_model(model: str) -> None:
    if model != "u2net":
        raise ValueError("Only u2net is supported")


U2NET_SOURCES = {
    "modelscope": U2NET_URL,
    "github": "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx",
}


def is_valid_u2net(path: Path) -> bool:
    if not path.is_file():
        return False
    from pooch import file_hash

    return file_hash(str(path), alg="md5") == U2NET_HASH.split(":", 1)[1]


def migrate_legacy_u2net(directory: Path) -> Path | None:
    """Copy a valid legacy Windows model into GAM User Data once."""
    destination = directory / "u2net.onnx"
    if is_valid_u2net(destination):
        return destination
    if data_mode() != INSTALLED_MODE:
        return None

    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        return None
    legacy_model = Path(local_appdata) / "VideoToSheet" / "models" / "rembg" / "u2net.onnx"
    if not is_valid_u2net(legacy_model):
        return None

    directory.mkdir(parents=True, exist_ok=True)
    staging = directory / "u2net.onnx.migrating"
    try:
        shutil.copy2(legacy_model, staging)
        if not is_valid_u2net(staging):
            return None
        os.replace(staging, destination)
        return destination
    finally:
        staging.unlink(missing_ok=True)


def download_u2net(
    directory: Path,
    source: str = "modelscope",
    progress: Callable[[int, int | None], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> str:
    """Stream the checkpoint to a temporary file, verify it, and move it into place atomically.

    A cancelled or failed download removes the temporary file so no residue remains.
    """
    import requests

    if source not in U2NET_SOURCES:
        raise ValueError("Unsupported model download source")
    url = U2NET_SOURCES[source]
    expected_md5 = U2NET_HASH.split(":", 1)[1]
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / "u2net.onnx"
    if is_valid_u2net(destination):
        return str(destination)
    temporary = None
    try:
        with (
            requests.get(url, stream=True, timeout=(10, 60)) as response,
            tempfile.NamedTemporaryFile(dir=directory, prefix=".u2net-", delete=False) as stream,
        ):
            temporary = Path(stream.name)
            response.raise_for_status()
            content_length = response.headers.get("Content-Length")
            total = int(content_length) if content_length and content_length.isdigit() else None
            received = 0
            digest = hashlib.md5(usedforsecurity=False)
            for chunk in response.iter_content(1024 * 1024):
                if cancel_event is not None and cancel_event.is_set():
                    raise ModelDownloadCancelledError("u2net download cancelled")
                received += len(chunk)
                digest.update(chunk)
                stream.write(chunk)
                if progress is not None:
                    progress(received, total)
        if digest.hexdigest() != expected_md5:
            raise ValueError("u2net model hash mismatch")
        os.replace(temporary, destination)
        return str(destination)
    except ModelDownloadCancelledError:
        raise
    except Exception as error:
        record_network_error("GET", url, error)
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
