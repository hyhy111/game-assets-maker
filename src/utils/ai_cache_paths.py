"""Shared cache paths for AI image and video generation."""

from pathlib import Path

from src.utils.data_paths import data_root

AI_PIC_CACHE_DIRNAME = "ai-pic-cache"
AI_VIDEO_CACHE_DIRNAME = "ai-video-cache"


def ai_cache_root(configured_dir: object, *, base_dir: Path | None = None) -> Path:
    base = base_dir or data_root()
    if isinstance(configured_dir, str) and configured_dir:
        configured = Path(configured_dir).expanduser()
        # Relative configured directories resolve against the data root, never
        # against the launch directory of an installed release.
        return configured if configured.is_absolute() else base / configured
    return base / "cache"


def ai_pic_cache_root(configured_dir: object, *, base_dir: Path | None = None) -> Path:
    return ai_cache_root(configured_dir, base_dir=base_dir) / AI_PIC_CACHE_DIRNAME


def ai_video_cache_root(configured_dir: object, *, base_dir: Path | None = None) -> Path:
    return ai_cache_root(configured_dir, base_dir=base_dir) / AI_VIDEO_CACHE_DIRNAME
