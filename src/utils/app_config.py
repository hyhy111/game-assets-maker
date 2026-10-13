"""Shared application configuration defaults and runtime storage helpers."""

import json
import os
import sys
import tempfile
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

from src.utils.data_paths import DATA_DIR_NAME, DATA_ROOT_ENV_VAR, INSTALLED_MODE, data_mode, data_root
from src.utils.storage_locations import DEFAULT_PROJECT_DIR, StorageLocations, storage_locations_from_config

CONFIG_ENV_VAR = "GAM_CONFIG"
_CONFIG_WRITE_LOCK = threading.Lock()

# Source development keeps a dedicated workspace config so it never reads or
# writes the installed release's per-user configuration.
DEV_CONFIG_FILENAME = "config.dev.json"

DEFAULT_APP_CONFIG: dict[str, Any] = {
    "language": "zh",
    "theme": "dark",
    "logger_enabled": False,
    "ark_audit_enabled": False,
    "cli_generation_enabled": False,
    "paid_generation_confirmation_enabled": True,
    "project_dir": DEFAULT_PROJECT_DIR,
    "logger_config": {
        "log_dir": "logs",
        "max_log_size_mb": 10,
        "max_log_files": 5,
        "auto_cleanup_days": 30,
        "cleanup_interval_hours": 24,
    },
    "seedance": {
        "api_key": "",
        "cache_dir": "cache",
        "default_model": "mini",
        "default_resolution": "720p",
        "default_ratio": "16:9",
        "default_duration": 4,
        "default_generate_audio": True,
        "default_return_last_frame": True,
        "default_priority": 0,
        "default_expires_after": 172800,
        "retention_days": 90,
        "last_cleanup_at": None,
    },
    "seedream": {
        "default_count": 1,
        "default_model": "pro",
        "default_resolution": "2K",
        "default_ratio": "16:9",
    },
}


def _shared_user_config_path() -> Path:
    """Per-user config location used by installed releases."""
    return Path.home() / DATA_DIR_NAME / "config.json"


def get_app_config_path() -> Path:
    """Return the active app config path, honoring an environment override."""
    override = os.environ.get(CONFIG_ENV_VAR)
    if override:
        return Path(override).expanduser()
    if data_mode() == INSTALLED_MODE:
        return data_root() / "config.json"
    return data_root() / DEV_CONFIG_FILENAME


def merge_app_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge a partial config with application defaults."""
    merged = deepcopy(DEFAULT_APP_CONFIG)
    if not config:
        return merged

    _merge_known_keys(merged, config)
    if merged["seedance"]["default_resolution"] == "4k":
        merged["seedance"]["default_resolution"] = "1080p"
    cache_dir = merged["seedance"].get("cache_dir")
    if isinstance(cache_dir, str) and cache_dir:
        legacy_cache = Path(cache_dir).expanduser()
        if legacy_cache.name == "seedance-cache":
            migrated_cache = legacy_cache.parent / "cache"
            merged["seedance"]["cache_dir"] = (
                str(migrated_cache) if legacy_cache.is_absolute() or legacy_cache.parent != Path(".") else "cache"
            )
    return merged


def load_app_config() -> dict[str, Any]:
    """Load the runtime config, migrating the tracked config only on first use."""
    config_path = get_app_config_path()
    if config_path.exists():
        return merge_app_config(_read_config(config_path))

    # Installed launches and isolated automation must not inherit configuration
    # from the launch directory or the developer's shared user settings.
    if data_mode() == INSTALLED_MODE or os.environ.get(DATA_ROOT_ENV_VAR):
        return merge_app_config()

    if _is_workspace_dev_config():
        seeded = _seed_dev_config(config_path)
        if seeded is not None:
            return merge_app_config(seeded)

    legacy_path = Path.cwd() / "config.json"
    legacy_config = _read_config(legacy_path) if legacy_path.exists() else {}
    if legacy_config:
        migrated = merge_app_config(legacy_config)
        migrated["seedance"].pop("api_key", None)
        _write_config(config_path, migrated)
        return merge_app_config(migrated)

    return merge_app_config()


def _is_workspace_dev_config() -> bool:
    """True when a source workspace resolves its default dev config."""
    if os.environ.get(CONFIG_ENV_VAR) or data_mode() == INSTALLED_MODE:
        return False
    return (Path.cwd() / "config.json").exists()


def _seed_dev_config(config_path: Path) -> dict[str, Any] | None:
    """One-time continuity: adopt the per-user config previous dev runs wrote.

    Earlier development stored its runtime config at the location that now
    belongs to installed releases. The first dev run after the split copies it
    (credentials included, they were created by development) so existing
    settings survive. Resource locations stay workspace-local so a dev cleanup
    cannot delete installed generation results. The source is never modified.
    """
    shared_path = _shared_user_config_path()
    try:
        if shared_path.resolve() == config_path.resolve():
            return None
        seeded = _read_config(shared_path) if shared_path.exists() else {}
    except OSError:
        return None
    if not seeded:
        return None
    seeded = merge_app_config(seeded)
    seeded["seedance"]["cache_dir"] = DEFAULT_APP_CONFIG["seedance"]["cache_dir"]
    _write_config(config_path, seeded)
    return seeded


def save_app_config(update: dict[str, Any]) -> dict[str, Any]:
    """Merge and atomically save a partial runtime config update."""
    # WebView calls run concurrently; serialize read-merge-write to keep an
    # independent audit toggle from being lost to another settings save.
    with _CONFIG_WRITE_LOCK:
        config_path = get_app_config_path()
        current = load_app_config()
        _merge_known_keys(current, update)

        if update.get("seedance", {}).get("api_key", object()) is None:
            current["seedance"]["api_key"] = ""

        _write_config(config_path, current)
        return current


def public_app_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return configuration that is safe to expose outside the backend."""
    public = deepcopy(config)
    public["ark_audit_available"] = ark_audit_available()
    public["ark_audit_enabled"] = public.get("ark_audit_enabled") is True
    public["cli_generation_enabled"] = public.get("cli_generation_enabled") is True
    seedance = public.setdefault("seedance", {})
    seedance["api_key_configured"] = bool(seedance.pop("api_key", ""))
    return public


def ark_audit_available() -> bool:
    """Only the explicit source-development entrypoint permits audit logging."""
    return os.environ.get("DEV_MODE") == "1" and not getattr(sys, "frozen", False) and data_mode() != INSTALLED_MODE


def ark_audit_enabled() -> bool:
    """Read the live setting at each event boundary, without caching a call's state."""
    return ark_audit_available() and load_app_config().get("ark_audit_enabled") is True


def save_ark_audit_enabled(enabled: bool) -> dict[str, Any]:
    """Persist only the immediate audit setting, independently of settings drafts."""
    if type(enabled) is not bool:
        raise ValueError("Ark audit setting must be a boolean")
    if not ark_audit_available():
        raise ValueError("Ark audit logging is available only in development")
    return public_app_config(save_app_config({"ark_audit_enabled": enabled}))


def cli_generation_enabled() -> bool:
    """Check permission at the submission boundary, with a closed failure default."""
    try:
        return load_app_config().get("cli_generation_enabled") is True
    except (OSError, ValueError):
        return False


def save_cli_generation_enabled(enabled: bool, confirmed: bool = False) -> dict[str, Any]:
    """Persist only this immediate setting after explicit GUI confirmation."""
    if type(enabled) is not bool or (enabled and confirmed is not True):
        raise ValueError("Enabling CLI generation requires confirmation")
    return public_app_config(save_app_config({"cli_generation_enabled": enabled}))


def current_storage_locations() -> StorageLocations:
    """Resolve the storage roots from the live config and stable data root."""
    return storage_locations_from_config(load_app_config(), data_root=data_root())


def default_projects_root() -> Path:
    """Configured project root for consumers constructed without injection."""
    return current_storage_locations().projects_root


def merge_config_update(current: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``current`` with known keys from ``update`` applied."""
    merged = deepcopy(current)
    _merge_known_keys(merged, update)
    return merged


def _merge_known_keys(target: dict[str, Any], update: dict[str, Any]) -> None:
    for key, value in update.items():
        if key not in target:
            continue
        if key == "ark_audit_enabled":
            target[key] = value is True
            continue
        if isinstance(value, dict) and isinstance(target[key], dict):
            _merge_known_keys(target[key], value)
        else:
            target[key] = value


def _read_config(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as file:
            loaded = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _write_config(path: Path, config: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as file:
        json.dump(config, file, ensure_ascii=False, indent=2)
        file.flush()
        os.fsync(file.fileno())
        temporary_path = Path(file.name)
    try:
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
