"""Both generation sources share one model preference for each media kind."""

import json

import pytest

from backend.api.seedance_api import SeedanceAPI
from backend.api.seedream_api import SeedreamAPI
from backend.api.storage_settings_api import StorageSettingsAPI
from src.utils.app_config import get_app_config_path, load_app_config, merge_config_update, save_app_config
from src.utils.storage_migration import StorageMigrationCoordinator


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("GAM_CONFIG", str(tmp_path / "config.json"))


def test_legacy_platform_preferences_are_ignored_without_rewriting_file():
    path = get_app_config_path()
    path.write_text(
        json.dumps(
            {
                "seedance": {"default_model": "fast", "platform_default_model": "old-video"},
                "seedream": {"default_model": "flash", "platform_default_model": "old-image"},
            }
        )
    )
    before = path.read_bytes()
    config = load_app_config()
    assert "platform_default_model" not in config["seedance"]
    assert "platform_default_model" not in config["seedream"]
    assert config["seedance"]["default_model"] == "fast"
    assert config["seedream"]["default_model"] == "flash"
    assert SeedanceAPI().get_settings()["default_model_id"] == "doubao-seedance-2-0-fast-260128"
    assert SeedreamAPI().get_settings()["settings"]["default_model_id"] == "doubao-seedream-5-0-flash-260915"
    assert path.read_bytes() == before


def test_both_settings_apis_save_common_defaults_and_preserve_partial_updates():
    video = SeedanceAPI()
    image = SeedreamAPI()
    assert video.save_settings({"default_model": "fast", "platform_default_model": "old-video"})["success"]
    assert image.save_settings({"default_model": "flash", "platform_default_model": "old-image"})["success"]
    assert image.save_settings({"default_count": 2})["success"]
    assert video.save_settings({"default_duration": 6})["success"]
    config = load_app_config()
    assert config["seedance"]["default_model"] == "fast"
    assert config["seedream"]["default_model"] == "flash"
    assert config["seedream"]["default_count"] == 2
    assert config["seedance"]["default_duration"] == 6
    for section in ("seedance", "seedream"):
        assert "platform_default_model" not in config[section]
        assert "platform_default_model" not in json.loads(get_app_config_path().read_text())[section]


def test_storage_settings_and_migration_drafts_ignore_removed_platform_preferences(tmp_path):
    coordinator = StorageMigrationCoordinator(commit_config=save_app_config)
    api = StorageSettingsAPI(coordinator=coordinator, data_root=tmp_path)
    draft = {
        "seedance": {"default_model": "mini", "platform_default_model": "old-video"},
        "seedream": {"default_model": "flash", "platform_default_model": {"obsolete": "value"}},
    }
    merged = merge_config_update(load_app_config(), draft)
    assert merged["seedream"]["default_model"] == "flash"
    assert "platform_default_model" not in merged["seedance"]
    assert "platform_default_model" not in merged["seedream"]
    assert api.save_settings(draft) == {"success": True, "migration_required": False}
    assert load_app_config() == merged


@pytest.mark.parametrize(
    ("section", "alias", "model_id"),
    [
        ("seedance", "mini", "doubao-seedance-2-0-mini-260615"),
        ("seedance", "fast", "doubao-seedance-2-0-fast-260128"),
        ("seedream", "pro", "doubao-seedream-5-0-pro-260628"),
        ("seedream", "flash", "doubao-seedream-5-0-flash-260915"),
    ],
)
def test_settings_derive_platform_model_id_from_common_default_without_persisting_it(section, alias, model_id):
    save_app_config({section: {"default_model": alias}})
    before = get_app_config_path().read_bytes()
    api = SeedanceAPI() if section == "seedance" else SeedreamAPI()
    result = api.get_settings()
    settings = result if section == "seedance" else result["settings"]
    assert settings["default_model_id"] == model_id
    assert "platform_default_model" not in settings
    assert get_app_config_path().read_bytes() == before
    result = api.save_settings({"default_model_id": "forged"})
    assert result["success"] is True
    assert result["settings"]["default_model_id"] == model_id
    assert "default_model_id" not in json.loads(get_app_config_path().read_text())[section]
