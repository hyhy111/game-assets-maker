"""Unified data-location boundary for source development and installed releases.

Source development keeps the existing workspace layout: ``project/`` and
``cache/`` under the current working directory, models under the repository
``models/`` directory. Installed (PyInstaller) builds resolve a stable
per-user data root so projects, generation history, and models survive
installer replacement and never depend on the launch directory, which may be
read-only. Every consumer of writable app data (projects, frame/audio media,
processing, batch trim, AI generation caches, models) must resolve through
this module instead of the process working directory.

Overrides for tests and automation:
- ``GAM_DATA_MODE``: force ``dev`` or ``installed``.
- ``GAM_DATA_ROOT``: pin the data root to an explicit directory.
"""

import os
import sys
from pathlib import Path

APP_NAME = "Game Assets Maker"
DATA_DIR_NAME = ".gam"

DATA_MODE_ENV_VAR = "GAM_DATA_MODE"
DATA_ROOT_ENV_VAR = "GAM_DATA_ROOT"

DEV_MODE = "dev"
INSTALLED_MODE = "installed"


def data_mode() -> str:
    """Return ``installed`` for packaged builds, ``dev`` for source runs."""
    override = os.environ.get(DATA_MODE_ENV_VAR, "").strip().lower()
    if override in {DEV_MODE, INSTALLED_MODE}:
        return override
    return INSTALLED_MODE if getattr(sys, "frozen", False) else DEV_MODE


def data_root() -> Path:
    """Writable data root shared by projects, AI caches, and models."""
    override = os.environ.get(DATA_ROOT_ENV_VAR)
    if override:
        return Path(override).expanduser()
    if data_mode() == INSTALLED_MODE:
        return Path.home() / DATA_DIR_NAME
    return Path.cwd()


def projects_root() -> Path:
    """Root directory holding all video-processing projects."""
    return data_root() / "project"


def models_root() -> Path:
    """Directory holding the rembg model files."""
    if data_mode() == INSTALLED_MODE:
        return data_root() / "models" / "rembg"
    return Path(__file__).resolve().parents[2] / "models" / "rembg"
