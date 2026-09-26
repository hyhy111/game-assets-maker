"""Persist non-destructive frame visibility choices for a project."""

import json
from pathlib import Path


def get_hidden_frame_names(project_path: Path) -> list[str]:
    config_path = project_path / "cache" / "steps_config.json"
    if not config_path.exists():
        return []

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    hidden = config.get("hidden_frames", [])
    if not isinstance(hidden, list):
        return []
    return list(dict.fromkeys(name for name in hidden if isinstance(name, str)))


def set_frame_hidden(project_path: Path, filename: str, hidden: bool) -> list[str]:
    if Path(filename).name != filename or Path(filename).suffix.lower() != ".png":
        raise ValueError("Invalid frame filename")

    config_path = project_path / "cache" / "steps_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    hidden_frames = get_hidden_frame_names(project_path)

    if hidden and filename not in hidden_frames:
        hidden_frames.append(filename)
    elif not hidden:
        hidden_frames = [name for name in hidden_frames if name != filename]

    config["hidden_frames"] = hidden_frames
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return hidden_frames


def restore_hidden_frames(project_path: Path) -> list[str]:
    config_path = project_path / "cache" / "steps_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    config["hidden_frames"] = []
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return []
