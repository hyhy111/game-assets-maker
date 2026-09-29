"""Shared project path helpers for role/action project layout."""

import json
from pathlib import Path

UNKNOWN_ROLE = "未知"
LEGACY_ROLE = "未迁移"


def sanitize_segment(value: str, fallback: str) -> str:
    """Sanitize one filesystem path segment."""
    invalid_chars = '<>:"/\\|?*'
    value = (value or "").strip()
    for char in invalid_chars:
        value = value.replace(char, "_")
    return value or fallback


def make_project_id(role: str, action: str) -> str:
    return f"{sanitize_segment(role, UNKNOWN_ROLE)}/{sanitize_segment(action, 'untitled_project')}"


def split_project_id(project_id: str) -> tuple[str | None, str]:
    parts = [part for part in project_id.split("/") if part]
    if len(parts) >= 2:
        return parts[0], parts[1]
    return None, parts[0] if parts else ""


def is_project_dir(path: Path) -> bool:
    return (path / "cache" / "global_params.json").exists() or (path / "cache").exists()


def is_legacy_import_project_dir(path: Path) -> bool:
    """Return whether a directory has valid metadata from a legacy project."""
    metadata_path = path / "cache" / "global_params.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    project_name = metadata.get("project_name") if isinstance(metadata, dict) else None
    return isinstance(project_name, str) and bool(project_name.strip())


def resolve_project_path(projects_root: Path, project_id: str) -> Path:
    """Resolve nested project ids while preserving legacy flat ids."""
    role, action = split_project_id(project_id)
    if role:
        return projects_root / role / action
    return projects_root / action


def media_url_for_path(path: Path, *, projects_root: Path, data_root: Path, base_url: str) -> str:
    """Build the assets-server URL for a local media file.

    Paths under the project root use the restricted ``/project-media/``
    mapping so custom roots outside the data root stay servable; other
    data-root paths keep the legacy static scheme; anything else is returned
    as a plain local path.
    """
    mtime = int(path.stat().st_mtime) if path.exists() else 0
    try:
        relative = path.relative_to(projects_root)
        return f"{base_url}/project-media/{relative.as_posix()}?t={mtime}"
    except ValueError:
        pass
    try:
        relative = path.relative_to(data_root)
        return f"{base_url}/{relative.as_posix()}?t={mtime}"
    except ValueError:
        return str(path)


def find_project_path(projects_root: Path, project_id: str) -> Path | None:
    path = resolve_project_path(projects_root, project_id)
    if path.exists():
        return path
    return None
