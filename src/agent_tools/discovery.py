"""Discover the desktop control port within the active application data root."""

import json
from pathlib import Path

from src.utils.data_paths import data_root

DEFAULT_CONTROL_PORT = 8765


def control_endpoint_path() -> Path:
    return data_root() / "cache" / "agent-control.json"


def read_control_endpoint(path: Path) -> dict:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    return record if isinstance(record, dict) else {}
