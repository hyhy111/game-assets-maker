"""Unified pure resolution of project and AI cache storage roots.

Every consumer of writable storage resolves through this layer so the project
root and the shared AI cache root come from one contract: configured values,
plus the stable ``data_root`` as the only anchor for relative values. The
layer performs no I/O and never resolves against the launch directory, so
installed releases stay independent of where the app was started.

Normalization is lexical (``normpath``): it makes equivalent spellings of one
physical directory compare equal without touching the filesystem or following
symlinks, which keeps migration change-detection safe to run as a precheck.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from src.utils.ai_cache_paths import AI_PIC_CACHE_DIRNAME, AI_VIDEO_CACHE_DIRNAME

DEFAULT_PROJECT_DIR = "project"
DEFAULT_AI_CACHE_DIR = "cache"


@dataclass(frozen=True)
class StorageLocations:
    """Resolved, normalized roots for project data and the shared AI cache."""

    projects_root: Path
    ai_cache_root: Path

    @property
    def ai_pic_cache_root(self) -> Path:
        return self.ai_cache_root / AI_PIC_CACHE_DIRNAME

    @property
    def ai_video_cache_root(self) -> Path:
        return self.ai_cache_root / AI_VIDEO_CACHE_DIRNAME


def normalize_storage_path(path: Path) -> Path:
    """Lexically normalize a path so equivalent spellings compare equal."""
    return Path(os.path.normpath(path))


def resolve_storage_root(configured: object, *, default: str, data_root: Path) -> Path:
    """Resolve one configured storage root against the stable data root.

    Relative values anchor to ``data_root`` only; absolute values (after
    ``~`` expansion) are the root itself. Blank or non-string values fall
    back to the default relative directory.
    """
    base = normalize_storage_path(Path(data_root).expanduser())
    root = base / default
    if isinstance(configured, str) and configured.strip():
        candidate = Path(configured).expanduser()
        root = candidate if candidate.is_absolute() else base / candidate
    return normalize_storage_path(root)


def resolve_storage_locations(
    project_dir: object,
    ai_cache_dir: object,
    *,
    data_root: Path,
) -> StorageLocations:
    """Resolve both storage roots from configured values and a data root."""
    return StorageLocations(
        projects_root=resolve_storage_root(project_dir, default=DEFAULT_PROJECT_DIR, data_root=data_root),
        ai_cache_root=resolve_storage_root(ai_cache_dir, default=DEFAULT_AI_CACHE_DIR, data_root=data_root),
    )


def storage_locations_from_config(config: Mapping[str, object], *, data_root: Path) -> StorageLocations:
    """Resolve storage roots from a loaded app config mapping.

    The AI cache location keeps living under ``seedance.cache_dir`` for
    compatibility; anything that is not a mapping contributes no override.
    """
    seedance = config.get("seedance")
    cache_dir = seedance.get("cache_dir") if isinstance(seedance, Mapping) else None
    return resolve_storage_locations(config.get("project_dir"), cache_dir, data_root=data_root)
