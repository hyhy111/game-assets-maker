"""Read application identity from the canonical project metadata."""

import sys
import tomllib
from importlib.metadata import version
from pathlib import Path


def app_version() -> str:
    """Use bundled metadata when frozen, source metadata or wheel metadata otherwise."""
    if getattr(sys, "frozen", False):
        metadata_path = Path(sys._MEIPASS) / "pyproject.toml"
    else:
        metadata_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
        if not metadata_path.is_file():
            return version("game-assets-maker")
    with metadata_path.open("rb") as stream:
        value = tomllib.load(stream)["project"]["version"]
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Application version is missing from project metadata")
    return value
