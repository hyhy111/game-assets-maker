"""Locate and clean the previous Step 3 frame sequence."""

import re
import shutil
from pathlib import Path

_BACKUP_ID = re.compile(r"[0-9a-f]{32}")


def _backup_root(project: Path) -> Path:
    # Reuse the old snapshot location so obsolete histories can be reclaimed.
    directory = project.resolve() / "cache" / "step3_versions"
    if directory.resolve() != directory:
        raise ValueError("Invalid Step 3 backup path")
    return directory


def processing_backup(project: Path, backup_id: str) -> Path:
    if not isinstance(backup_id, str) or not _BACKUP_ID.fullmatch(backup_id):
        raise ValueError("Invalid Step 3 backup")
    directory = _backup_root(project) / backup_id
    if directory.resolve() != directory:
        raise ValueError("Invalid Step 3 backup path")
    return directory


def clean_processing_backups(project: Path, keep: str | None = None) -> None:
    """Remove obsolete backups after committing the new result."""
    try:
        directories = list(_backup_root(project).iterdir())
    except (OSError, ValueError, RuntimeError):
        return
    for item in directories:
        if item.name == keep or not _BACKUP_ID.fullmatch(item.name):
            continue
        try:
            backup = processing_backup(project, item.name)
        except (OSError, ValueError, RuntimeError):
            continue
        shutil.rmtree(backup, ignore_errors=True)
