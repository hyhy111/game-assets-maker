import json
from pathlib import Path

from backend.api.config_api import ConfigAPI
from src.utils.app_config import (
    get_app_config_path,
    load_app_config,
    merge_app_config,
    public_app_config,
    save_app_config,
)


def test_get_app_config_path_uses_environment_override(runtime_config_path: Path):
    assert get_app_config_path() == runtime_config_path


def test_get_app_config_path_uses_home_dot_gam(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("GAM_CONFIG", raising=False)
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    monkeypatch.delenv("GAM_DATA_ROOT", raising=False)
    from src.utils import data_paths

    home = tmp_path / "developer-home"
    monkeypatch.setattr(data_paths.Path, "home", classmethod(lambda cls: home))

    assert get_app_config_path() == home / ".gam" / "config.json"


def test_load_migrates_tracked_config_once_without_seedance_api_key(monkeypatch, tmp_path: Path):
    legacy_config = {
        "language": "en",
        "logger_config": {"max_log_files": 3},
        "seedance": {"api_key": "tracked-secret", "default_duration": 6},
    }
    (tmp_path / "config.json").write_text(json.dumps(legacy_config), encoding="utf-8")
    runtime_path = tmp_path / "runtime" / "config.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GAM_CONFIG", str(runtime_path))

    migrated = load_app_config()

    assert migrated["language"] == "en"
    assert migrated["logger_config"]["max_log_files"] == 3
    assert migrated["seedance"]["api_key"] == ""
    assert migrated["seedance"]["default_duration"] == 6
    assert "api_key" not in json.loads(runtime_path.read_text(encoding="utf-8"))["seedance"]

    (tmp_path / "config.json").write_text(json.dumps({"language": "zh"}), encoding="utf-8")
    assert load_app_config()["language"] == "en"


def test_public_config_redacts_seedance_api_key(runtime_config_path: Path):
    save_app_config({"seedance": {"api_key": "secret-key"}})

    public = public_app_config(load_app_config())

    assert "api_key" not in public["seedance"]
    assert public["seedance"]["api_key_configured"] is True


def test_legacy_seedance_cache_path_migrates_to_shared_cache_root(tmp_path: Path):
    legacy = tmp_path / "seedance-cache"

    migrated = merge_app_config({"seedance": {"cache_dir": str(legacy)}})

    assert migrated["seedance"]["cache_dir"] == str(tmp_path / "cache")


def test_removed_default_fps_is_ignored():
    assert "default_fps" not in merge_app_config({"default_fps": 24})


def test_paid_generation_confirmation_defaults_on_and_can_be_disabled(runtime_config_path: Path):
    assert load_app_config()["paid_generation_confirmation_enabled"] is True

    saved = save_app_config({"paid_generation_confirmation_enabled": False})

    assert saved["paid_generation_confirmation_enabled"] is False
    assert load_app_config()["paid_generation_confirmation_enabled"] is False


def test_save_without_api_key_preserves_existing_secret(runtime_config_path: Path):
    save_app_config({"seedance": {"api_key": "secret-key"}})

    saved = save_app_config({"seedance": {"default_duration": 6}})

    assert saved["seedance"]["api_key"] == "secret-key"
    assert saved["seedance"]["default_duration"] == 6


def test_save_with_none_clears_existing_seedance_api_key(runtime_config_path: Path):
    save_app_config({"seedance": {"api_key": "secret-key"}})

    saved = save_app_config({"seedance": {"api_key": None}})

    assert saved["seedance"]["api_key"] == ""


def test_config_api_returns_redacted_config_and_preserves_secret(runtime_config_path: Path):
    save_app_config({"seedance": {"api_key": "secret-key"}})
    api = ConfigAPI()

    assert api.save_config({"seedance": {"default_duration": 7}}) is True
    public = api.get_config()

    assert "api_key" not in public["seedance"]
    assert public["seedance"]["api_key_configured"] is True
    assert load_app_config()["seedance"]["api_key"] == "secret-key"
    assert public["seedance"]["default_duration"] == 7
