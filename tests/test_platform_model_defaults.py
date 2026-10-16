"""Client-local model preferences stay independent across generation sources."""

import json

import pytest

from backend.api.seedance_api import SeedanceAPI
from backend.api.seedream_api import SeedreamAPI
from backend.api.storage_settings_api import StorageSettingsAPI
from src.utils.app_config import get_app_config_path, load_app_config, merge_app_config, save_app_config
from src.utils.storage_migration import StorageMigrationCoordinator


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("GAM_CONFIG", str(tmp_path / "config.json"))


def test_legacy_config_gets_empty_platform_preferences_without_rewriting_file():
    path = get_app_config_path()
    path.write_text(json.dumps({"seedance": {"default_model": "fast"}, "seedream": {"default_model": "flash"}}))
    before = path.read_bytes()
    config = load_app_config()
    assert config["seedance"]["platform_default_model"] == ""
    assert config["seedream"]["platform_default_model"] == ""
    assert config["seedance"]["default_model"] == "fast"
    assert config["seedream"]["default_model"] == "flash"
    assert path.read_bytes() == before


def test_both_settings_apis_preserve_independent_defaults_and_partial_updates():
    video = SeedanceAPI()
    image = SeedreamAPI()
    result = video.save_settings({"default_model": "fast", "platform_default_model": "doubao-seedance-preferred"})
    assert result["success"] is True
    assert result["settings"]["platform_default_model"] == "doubao-seedance-preferred"
    result = image.save_settings({"default_model": "flash", "platform_default_model": "doubao-seedream-preferred"})
    assert result["success"] is True
    assert result["settings"]["platform_default_model"] == "doubao-seedream-preferred"
    assert image.save_settings({"default_count": 2})["success"] is True
    assert video.save_settings({"default_duration": 6})["success"] is True
    assert SeedanceAPI().get_settings()["platform_default_model"] == "doubao-seedance-preferred"
    assert SeedreamAPI().get_settings()["settings"]["platform_default_model"] == "doubao-seedream-preferred"
    # Platform settings never replace API-key aliases or fields from the other media kind.
    assert load_app_config()["seedance"]["default_model"] == "fast"
    assert load_app_config()["seedream"]["default_model"] == "flash"
    assert load_app_config()["seedream"]["platform_default_model"] == "doubao-seedream-preferred"


@pytest.mark.parametrize("value", [None, 5, [], {}, "bad model", "bad\x00model", "x" * 257])
def test_invalid_new_preferences_are_rejected_without_writing(value):
    save_app_config({"seedream": {"platform_default_model": "saved-model"}})
    before = get_app_config_path().read_bytes()
    assert SeedreamAPI().save_settings({"platform_default_model": value})["success"] is False
    assert SeedanceAPI().save_settings({"platform_default_model": value})["success"] is False
    assert get_app_config_path().read_bytes() == before
    assert merge_app_config({"seedance": {"platform_default_model": value}})["seedance"]["platform_default_model"] == ""


def test_plain_and_migration_settings_routes_preserve_and_validate_preferences(tmp_path):
    coordinator = StorageMigrationCoordinator(commit_config=save_app_config)
    api = StorageSettingsAPI(coordinator=coordinator, data_root=tmp_path)
    result = api.save_settings(
        {
            "seedance": {"platform_default_model": "  model-video  "},
            "seedream": {"platform_default_model": "model-image"},
        }
    )
    assert result == {"success": True, "migration_required": False}
    assert load_app_config()["seedance"]["platform_default_model"] == "model-video"
    before = get_app_config_path().read_bytes()
    result = api.save_settings(
        {"project_dir": str(tmp_path / "new-projects"), "seedream": {"platform_default_model": {"bad": "type"}}}
    )
    assert result["success"] is False
    assert get_app_config_path().read_bytes() == before


@pytest.mark.parametrize(
    ("section", "alias", "model_id"),
    [
        ("seedance", "mini", "doubao-seedance-2-0-mini-260615"),
        ("seedance", "fast", "doubao-seedance-2-0-fast-260128"),
        ("seedream", "pro", "doubao-seedream-5-0-pro-260628"),
        ("seedream", "flash", "doubao-seedream-5-0-flash-260915"),
    ],
)
def test_settings_expose_default_model_id_without_persisting_it(section, alias, model_id):
    save_app_config({section: {"default_model": alias, "platform_default_model": ""}})
    before = get_app_config_path().read_bytes()
    api = SeedanceAPI() if section == "seedance" else SeedreamAPI()
    result = api.get_settings()
    settings = result if section == "seedance" else result["settings"]
    assert settings["default_model_id"] == model_id
    assert settings["platform_default_model"] == ""
    assert get_app_config_path().read_bytes() == before
    result = api.save_settings({"default_model_id": "forged"})
    assert result["success"] is True
    assert result["settings"]["default_model_id"] == model_id
    assert "default_model_id" not in json.loads(get_app_config_path().read_text())[section]
