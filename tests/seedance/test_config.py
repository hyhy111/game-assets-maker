import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from backend.api.config_api import ConfigAPI
from src.utils.app_config import (
    ark_audit_available,
    ark_audit_enabled,
    get_app_config_path,
    load_app_config,
    merge_app_config,
    public_app_config,
    save_app_config,
    save_ark_audit_enabled,
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


# ==================== Project directory storage setting ====================


def test_default_config_exposes_relative_project_dir(runtime_config_path: Path):
    assert load_app_config()["project_dir"] == "project"
    assert merge_app_config()["project_dir"] == "project"


def test_existing_config_without_project_dir_loads_the_default(runtime_config_path: Path):
    runtime_config_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_config_path.write_text(json.dumps({"language": "en"}), encoding="utf-8")

    config = load_app_config()

    assert config["language"] == "en"
    assert config["project_dir"] == "project"
    # Loading alone must not rewrite the tracked config file.
    assert "project_dir" not in json.loads(runtime_config_path.read_text(encoding="utf-8"))


def test_partial_update_preserves_project_dir(runtime_config_path: Path):
    custom = "/data/chosen-projects"
    save_app_config({"project_dir": custom})

    saved = save_app_config({"language": "en"})

    assert saved["project_dir"] == custom
    on_disk = json.loads(runtime_config_path.read_text(encoding="utf-8"))
    assert on_disk["project_dir"] == custom
    assert on_disk["language"] == "en"


def test_normal_save_keeps_relative_storage_values(runtime_config_path: Path, monkeypatch, tmp_path: Path):
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path / "data-root"))

    save_app_config({"language": "en"})

    on_disk = json.loads(runtime_config_path.read_text(encoding="utf-8"))
    assert on_disk["project_dir"] == "project"
    assert on_disk["seedance"]["cache_dir"] == "cache"


def test_saved_config_file_contains_the_full_merged_config(runtime_config_path: Path):
    save_app_config({"theme": "light"})

    on_disk = json.loads(runtime_config_path.read_text(encoding="utf-8"))

    assert on_disk["theme"] == "light"
    assert on_disk["project_dir"] == "project"
    assert on_disk["seedance"]["cache_dir"] == "cache"
    assert on_disk["language"] == "zh"


def test_public_config_includes_project_dir(runtime_config_path: Path):
    assert ConfigAPI().get_config()["project_dir"] == "project"


@pytest.mark.parametrize("value", [None, 1, "true", [], {}])
def test_invalid_audit_setting_defaults_off(value):
    assert merge_app_config({"ark_audit_enabled": value})["ark_audit_enabled"] is False
    assert merge_app_config()["ark_audit_enabled"] is False


def test_audit_runtime_qualification(runtime_config_path, monkeypatch):
    monkeypatch.setenv("GAM_DATA_MODE", "dev")
    monkeypatch.delenv("DEV_MODE", raising=False)
    save_app_config({"ark_audit_enabled": True})
    assert not ark_audit_available()
    assert not ark_audit_enabled()
    monkeypatch.setenv("DEV_MODE", "1")
    assert ark_audit_available()
    assert ark_audit_enabled()
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    assert not ark_audit_available()
    assert not ark_audit_enabled()
    monkeypatch.setenv("GAM_DATA_MODE", "dev")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert not ark_audit_available()
    assert not ark_audit_enabled()


def test_immediate_audit_save_changes_only_audit_setting(runtime_config_path, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "1")
    monkeypatch.setenv("GAM_DATA_MODE", "dev")
    save_app_config({"language": "en", "logger_enabled": True})
    saved = save_ark_audit_enabled(True)
    assert saved["ark_audit_available"] is True
    assert saved["ark_audit_enabled"] is True
    assert load_app_config()["language"] == "en"
    assert load_app_config()["logger_enabled"] is True
    with pytest.raises(ValueError):
        save_ark_audit_enabled("true")
    monkeypatch.delenv("DEV_MODE")
    with pytest.raises(ValueError):
        save_ark_audit_enabled(False)
    assert load_app_config()["ark_audit_enabled"] is True


def test_concurrent_settings_save_cannot_lose_immediate_audit_toggle(runtime_config_path, monkeypatch):
    from src.utils import app_config

    save_app_config({"ark_audit_enabled": False})
    first_write = threading.Event()
    release_write = threading.Event()
    second_write = threading.Event()
    original_write = app_config._write_config

    def delayed_write(path, config):
        if config["ark_audit_enabled"]:
            second_write.set()
        else:
            first_write.set()
            assert release_write.wait(2)
        original_write(path, config)

    monkeypatch.setattr(app_config, "_write_config", delayed_write)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(save_app_config, {"logger_enabled": True})
        assert first_write.wait(2)
        second = executor.submit(save_app_config, {"ark_audit_enabled": True})
        try:
            assert not second_write.wait(0.05)
        finally:
            release_write.set()
        first.result(timeout=2)
        second.result(timeout=2)
    saved = load_app_config()
    assert saved["logger_enabled"] is True
    assert saved["ark_audit_enabled"] is True
