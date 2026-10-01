"""Composition-root injection of the unified storage locations.

Covers the storage-location-management change: one resolution result flows
from the app composition root into the project, frame, audio, process,
batch-trim, Seedream and Seedance consumers, while explicit roots passed by
tests or the CLI keep higher priority.
"""

import dataclasses
from pathlib import Path

import pytest

from src.utils.app_config import current_storage_locations, save_app_config
from src.utils.storage_locations import storage_locations_from_config


class CustomRoots:
    def __init__(self, data_root: Path, projects: Path, ai_cache: Path):
        self.data_root = data_root
        self.projects = projects
        self.ai_cache = ai_cache


@pytest.fixture
def custom_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CustomRoots:
    """Configured custom project and AI cache roots, isolated via env."""
    roots = CustomRoots(
        data_root=tmp_path / "data-root",
        projects=tmp_path / "chosen-projects",
        ai_cache=tmp_path / "chosen-ai-cache",
    )
    monkeypatch.setenv("GAM_DATA_ROOT", str(roots.data_root))
    monkeypatch.setenv("GAM_CONFIG", str(tmp_path / "runtime" / "config.json"))
    save_app_config({"project_dir": str(roots.projects), "seedance": {"cache_dir": str(roots.ai_cache)}})
    return roots


# ==================== Config-driven resolution ====================


def test_locations_from_config_read_both_storage_values(tmp_path: Path):
    config = {"project_dir": "/chosen/projects", "seedance": {"cache_dir": "/chosen/cache"}}

    locations = storage_locations_from_config(config, data_root=tmp_path)

    assert locations.projects_root == Path("/chosen/projects")
    assert locations.ai_cache_root == Path("/chosen/cache")


def test_locations_from_config_fall_back_to_defaults(tmp_path: Path):
    locations = storage_locations_from_config({"seedance": None}, data_root=tmp_path)

    assert locations.projects_root == tmp_path / "project"
    assert locations.ai_cache_root == tmp_path / "cache"


def test_current_locations_follow_the_saved_config(custom_roots: CustomRoots):
    locations = current_storage_locations()

    assert locations.projects_root == custom_roots.projects
    assert locations.ai_cache_root == custom_roots.ai_cache


def test_storage_locations_opt_out_of_js_bridge_serialization(tmp_path: Path):
    """PyWebView recursively serializes public js_api attributes; the injected
    StorageLocations must opt out so bridge setup never walks pathlib
    internals (logged as "Error while processing storage_locations...")."""
    locations = storage_locations_from_config({}, data_root=tmp_path)

    assert getattr(locations, "_serializable", True) is False
    # The marker is a class attribute, not a dataclass init field.
    assert {field.name for field in dataclasses.fields(locations)} == {"projects_root", "ai_cache_root"}


# ==================== Project-tree consumers ====================


def test_project_api_crud_uses_the_configured_custom_root(custom_roots: CustomRoots):
    from backend.api.project_api import ProjectAPI

    api = ProjectAPI()
    created = api.create_project("mage", "walk")

    assert created["path"].startswith(str(custom_roots.projects))
    assert (custom_roots.projects / "mage" / "walk" / "cache" / "global_params.json").exists()
    assert [project["id"] for project in api.get_projects()] == ["mage/walk"]
    assert api.get_project("mage/walk")["path"] == created["path"]
    assert api.delete_project("mage/walk") is True
    assert api.get_projects() == []
    # The default data-root project directory stays untouched.
    assert not (custom_roots.data_root / "project").exists()


def test_explicit_projects_root_beats_the_configured_root(custom_roots: CustomRoots, tmp_path: Path):
    from backend.api.project_api import ProjectAPI

    override = tmp_path / "explicit-root"
    api = ProjectAPI(projects_root=override)
    api.create_project("robot", "idle")

    assert (override / "robot" / "idle").is_dir()
    assert not (custom_roots.projects / "robot").exists()


def test_frame_audio_process_and_batch_trim_apis_use_the_configured_root(custom_roots: CustomRoots):
    from backend.api.audio_api import AudioAPI
    from backend.api.batch_trim_api import BatchTrimAPI
    from backend.api.frame_api import FrameAPI
    from backend.api.process_api import ProcessAPI

    assert FrameAPI()._projects_root == custom_roots.projects
    assert AudioAPI()._projects_root == custom_roots.projects
    assert BatchTrimAPI()._projects_root == custom_roots.projects

    process_api = ProcessAPI()
    try:
        assert process_api._projects_root == custom_roots.projects
    finally:
        process_api.shutdown()


# ==================== AI cache consumers ====================


def test_seedance_manager_uses_the_injected_ai_cache_root(custom_roots: CustomRoots):
    from backend.api.seedance_api import SeedanceAPI

    api = SeedanceAPI(client_factory=lambda key: object(), storage_locations=current_storage_locations())
    try:
        manager = api._ensure_manager()
        assert manager._repository.cache_root == custom_roots.ai_cache / "ai-video-cache"
    finally:
        api.shutdown()


def test_seedream_manager_uses_the_injected_ai_cache_root(custom_roots: CustomRoots):
    from backend.api.seedream_api import SeedreamAPI

    api = SeedreamAPI(client_factory=lambda key: object(), storage_locations=current_storage_locations())
    try:
        manager = api._ensure_manager()
        assert manager._repository.cache_root == custom_roots.ai_cache / "ai-pic-cache"
    finally:
        api.shutdown()


def test_seedance_without_injection_still_resolves_from_config(custom_roots: CustomRoots):
    from backend.api.seedance_api import SeedanceAPI

    api = SeedanceAPI(client_factory=lambda key: object())
    try:
        manager = api._ensure_manager()
        assert manager._repository.cache_root == custom_roots.ai_cache / "ai-video-cache"
    finally:
        api.shutdown()


def test_seedance_edited_inputs_use_the_injected_ai_cache_root(custom_roots: CustomRoots, tmp_path: Path):
    import base64
    from io import BytesIO

    from PIL import Image

    from backend.api.seedance_api import SeedanceAPI
    from src.utils.storage_locations import resolve_storage_locations

    def png_data_url(color: str) -> str:
        buffer = BytesIO()
        Image.new("RGBA", (120, 80), color).save(buffer, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")

    source = tmp_path / "source.jpg"
    Image.new("RGB", (120, 80), "red").save(source)
    # The injected root deliberately differs from the configured one; the
    # injection must win for every writer, not just the task repository.
    injected = resolve_storage_locations(None, str(tmp_path / "injected-cache"), data_root=tmp_path / "data-root")
    api = SeedanceAPI(storage_locations=injected)

    saved = api.save_edited_image(str(source), png_data_url("white"), png_data_url("blue"), None)

    assert saved["success"] is True
    assert Path(saved["data"]["path"]).parent == tmp_path / "injected-cache" / "ai-video-cache" / "edited-inputs"


# ==================== Agent / CLI consumers ====================


def test_agent_service_injects_the_root_scoped_resolution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import json

    from src.agent_tools.service import AgentWorkflowService

    root = tmp_path / "cli-root"
    root.mkdir()
    config_path = root / "config.dev.json"
    frozen = tmp_path / "frozen-projects"
    config_path.write_text(json.dumps({"project_dir": str(frozen)}), encoding="utf-8")
    monkeypatch.delenv("GAM_CONFIG", raising=False)
    monkeypatch.delenv("GAM_DATA_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)

    service = AgentWorkflowService(root=root)
    # A later config rewrite must not move an already-composed service: the
    # resolution is frozen at composition time like the app composition root.
    config_path.write_text(json.dumps({"project_dir": str(tmp_path / "moved-projects")}), encoding="utf-8")
    try:
        assert service.project_api._projects_root == frozen
        assert service.batch_trim_api._projects_root == frozen
        process_api = service.process_api
        try:
            assert process_api._projects_root == frozen
        finally:
            process_api.shutdown()
    finally:
        service.close()


# ==================== App composition root ====================


def test_main_composition_root_injects_one_shared_resolution(custom_roots: CustomRoots):
    from backend.main import API

    api = API()
    try:
        assert api._project_api._projects_root == custom_roots.projects
        assert api._frame_api._projects_root == custom_roots.projects
        assert api._audio_api._projects_root == custom_roots.projects
        assert api._batch_trim_api._projects_root == custom_roots.projects
        assert api._process_api._projects_root == custom_roots.projects
        assert api._seedance_api._storage_locations.projects_root == custom_roots.projects
        assert api._seedream_api._storage_locations.ai_cache_root == custom_roots.ai_cache
    finally:
        api._process_api.shutdown()
        api._seedance_api.shutdown()
        api._seedream_api.shutdown()


def test_seedance_key_save_refreshes_seedream_client(custom_roots: CustomRoots):
    """The shared Ark key backs both domains: saving it via the Seedance
    settings must swap the Seedream client for future batches too."""
    from backend.main import API

    save_app_config({"seedance": {"api_key": "old-key"}})
    api = API()
    try:
        seedream_api = api._seedream_api
        seedream_api._ensure_manager()
        manager = seedream_api._manager
        assert manager._client._api_key == "old-key"

        result = api.seedance_save_settings({"api_key": "new-key"})

        assert result["success"] is True
        assert seedream_api._manager is manager
        assert manager._client._api_key == "new-key"
    finally:
        api._seedance_api.shutdown()
        api._seedream_api.shutdown()
