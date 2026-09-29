"""Backend storage settings and migration API.

Covers the storage-location-management change: reads expose the persisted
config values plus the resolved absolute display paths (secrets redacted),
saves re-resolve and compare normalized paths so equivalent spellings stay a
plain save, real changes return a precheck summary with a confirmation token,
and only execute(token) commits the whole settings draft.
"""

import json
from pathlib import Path

import pytest

from src.utils.app_config import load_app_config, save_app_config
from src.utils.storage_migration import StorageMigrationCoordinator


@pytest.fixture
def storage_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data_root = tmp_path / "data-root"
    (data_root / "project" / "mage" / "walk").mkdir(parents=True)
    (data_root / "project" / "mage" / "walk" / "global_params.json").write_text(json.dumps({"a": 1}), encoding="utf-8")
    (data_root / "cache" / "ai-video-cache" / "tasks").mkdir(parents=True)
    monkeypatch.setenv("GAM_DATA_ROOT", str(data_root))
    monkeypatch.setenv("GAM_CONFIG", str(tmp_path / "runtime" / "config.json"))
    save_app_config({"seedance": {"api_key": "secret-key"}})
    return data_root


@pytest.fixture
def activity() -> dict[str, bool]:
    return {"process": False}


@pytest.fixture
def api(storage_env: Path, activity: dict[str, bool]):
    from backend.api.storage_settings_api import StorageSettingsAPI

    coordinator = StorageMigrationCoordinator(
        commit_config=save_app_config,
        activity_providers={"process": lambda: activity["process"]},
    )
    return StorageSettingsAPI(coordinator=coordinator, data_root=storage_env)


def _draft(project_dir: object = None, cache_dir: object = None, **extra) -> dict:
    draft: dict = {"language": "en", **extra}
    if project_dir is not None:
        draft["project_dir"] = project_dir
    if cache_dir is not None:
        draft["seedance"] = {"cache_dir": cache_dir, "api_key_configured": True}
    return draft


# ==================== Read: configured values + resolved paths ====================


def test_get_settings_returns_configured_values_and_resolved_paths(api, storage_env: Path):
    result = api.get_settings()

    assert result["success"] is True
    settings = result["settings"]
    assert settings["project_dir"] == "project"
    assert settings["cache_dir"] == "cache"
    assert settings["projects_root"] == str(storage_env / "project")
    assert settings["ai_cache_root"] == str(storage_env / "cache")


def test_get_settings_never_exposes_the_api_key(api):
    save_app_config({"seedance": {"api_key": "secret-key"}})

    result = api.get_settings()

    assert "secret-key" not in json.dumps(result)
    assert "api_key" not in result["settings"]


def test_get_settings_reflects_custom_configured_directories(api, tmp_path: Path):
    custom = tmp_path / "chosen-projects"
    save_app_config({"project_dir": str(custom)})

    settings = api.get_settings()["settings"]

    assert settings["project_dir"] == str(custom)
    assert settings["projects_root"] == str(custom)


# ==================== Save: path change detection ====================


def test_save_with_equivalent_path_spelling_is_a_plain_save(api, storage_env: Path):
    absolute_spelling = str(storage_env / "project")

    result = api.save_settings(_draft(project_dir=absolute_spelling))

    assert result["success"] is True
    assert result["migration_required"] is False
    # The plain save persists the draft as given and copies nothing.
    assert load_app_config()["project_dir"] == absolute_spelling
    assert not (storage_env / "project-migrated").exists()


def test_save_without_path_keys_keeps_locations_unchanged(api):
    result = api.save_settings({"language": "en"})

    assert result["success"] is True
    assert result["migration_required"] is False
    assert load_app_config()["language"] == "en"


def test_save_with_changed_project_dir_returns_precheck_summary(api, tmp_path: Path, storage_env: Path):
    target = tmp_path / "new-projects"

    result = api.save_settings(_draft(project_dir=str(target)))

    assert result["success"] is True
    assert result["migration_required"] is True
    migration = result["migration"]
    assert migration["token"]
    assert migration["entries"] == [
        {
            "kind": "project",
            "source": str(storage_env / "project"),
            "target": str(target),
            "file_count": 1,
            "total_bytes": len(json.dumps({"a": 1})),
        }
    ]
    # Nothing is written or copied before the user confirms.
    assert load_app_config()["project_dir"] == "project"
    assert not target.exists()


def test_save_with_both_locations_changed_summarizes_one_transaction(api, tmp_path: Path):
    project_target = tmp_path / "new-projects"
    cache_target = tmp_path / "new-cache"

    result = api.save_settings(_draft(project_dir=str(project_target), cache_dir=str(cache_target)))

    assert result["migration_required"] is True
    kinds = [entry["kind"] for entry in result["migration"]["entries"]]
    assert kinds == ["project", "ai_cache"]


def test_save_never_persists_api_key_fields(api, tmp_path: Path):
    result = api.save_settings(_draft(cache_dir=str(tmp_path / "new-cache")))

    assert result["success"] is True
    assert load_app_config()["seedance"]["api_key"] == "secret-key"


def test_save_reports_conflicting_targets_without_writing_config(api, tmp_path: Path):
    target = tmp_path / "occupied"
    target.mkdir()
    (target / "mage").write_text("keep", encoding="utf-8")

    result = api.save_settings(_draft(project_dir=str(target)))

    assert result["success"] is False
    assert result["error"]["stage"] == "precheck"
    assert "conflicting path: mage" in result["error"]["message"]
    assert load_app_config()["project_dir"] == "project"


def test_save_is_blocked_by_active_writers(api, activity: dict[str, bool], tmp_path: Path):
    activity["process"] = True

    result = api.save_settings(_draft(project_dir=str(tmp_path / "new-projects")))

    assert result["success"] is False
    assert "process" in result["error"]["message"]
    assert load_app_config()["project_dir"] == "project"


# ==================== Execute ====================


def test_execute_commits_the_whole_draft_and_requires_restart(api, tmp_path: Path, storage_env: Path):
    target = tmp_path / "new-projects"
    save_result = api.save_settings(_draft(project_dir=str(target), cache_dir="cache"))
    token = save_result["migration"]["token"]

    result = api.execute_migration(token)

    assert result["success"] is True
    assert result["restart_required"] is True
    committed = load_app_config()
    assert committed["project_dir"] == str(target)
    assert committed["language"] == "en"
    # Relative values that did not change stay relative.
    assert committed["seedance"]["cache_dir"] == "cache"
    assert (target / "mage" / "walk" / "global_params.json").is_file()
    assert (storage_env / "project" / "mage" / "walk" / "global_params.json").is_file()


def test_execute_with_unknown_token_fails(api):
    result = api.execute_migration("no-such-token")

    assert result["success"] is False
    assert result["error"]["stage"] == "execute"
