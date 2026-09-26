"""U2Net weights downloaded from ModelScope without its SDK."""

import os
import shutil
from pathlib import Path

from src.utils.data_paths import INSTALLED_MODE, data_mode

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


def download_u2net(directory: Path, source: str = "modelscope") -> str:
    import pooch

    if source not in U2NET_SOURCES:
        raise ValueError("Unsupported model download source")
    return pooch.retrieve(
        U2NET_SOURCES[source], known_hash=U2NET_HASH, fname="u2net.onnx",
        path=directory, progressbar=True,
    )
