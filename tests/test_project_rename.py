"""Renaming preserves project data and never overwrites another directory."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from backend.api.project_api import ProjectAPI
from backend.api.project_paths import LEGACY_ROLE


@pytest.fixture
def projects(tmp_path):
    return ProjectAPI(tmp_path / "custom-projects")


def populate(projects, role="hero", action="idle"):
    project = projects.create_project(role, action)
    path = Path(project["path"])
    Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(path / "output/02_no_bg/frame_000001.png")
    (path / "cache/hidden_frames.json").write_text('["frame_000002.png"]')
    (path / "cache/audio_timeline.json").write_text('{"clips": [], "source_wav": "cache/01_audio/source.wav"}')
    return path


def test_role_rename_preserves_all_animations_and_metadata(projects):
    first = populate(projects)
    populate(projects, action="walk")
    outside = populate(projects, role="enemy")
    metadata_path = first / "cache/global_params.json"
    meta = json.loads(metadata_path.read_text())
    meta.update(video_path=str(first / "cache/source.mp4"), project_name="Idle display")
    metadata_path.write_text(json.dumps(meta))
    original = {p.relative_to(first): p.read_bytes() for p in first.rglob("*") if p.is_file() and p != metadata_path}

    result = projects.rename_role("hero", "骑士")

    assert result["idMap"] == {"hero/idle": "骑士/idle", "hero/walk": "骑士/walk"}
    assert {p["id"] for p in result["projects"]} == {"骑士/idle", "骑士/walk"}
    assert not first.parent.exists()
    assert outside.exists()
    target = projects._projects_root / "骑士/idle"
    assert original == {p: (target / p).read_bytes() for p in original}
    updated = projects.get_project("骑士/idle")
    assert updated["name"] == "Idle display"
    assert updated["video_path"] == str(target / "cache/source.mp4")
    fresh = ProjectAPI(projects._projects_root)
    assert {p["role"] for p in fresh.get_projects()} == {"骑士", "enemy"}
    assert fresh.get_project("hero/idle") is None


def test_animation_rename_updates_name_and_keeps_external_input(projects):
    source = populate(projects)
    populate(projects, action="walk")
    populate(projects, role="enemy", action="attack")
    metadata = source / "cache/global_params.json"
    meta = json.loads(metadata.read_text())
    meta["video_path"] = "/external/source.mp4"
    metadata.write_text(json.dumps(meta))
    result = projects.rename_project("hero/idle", " attack ")
    assert result["idMap"] == {"hero/idle": "hero/attack"}
    assert result["projects"][0]["name"] == "attack"
    assert result["projects"][0]["video_path"] == "/external/source.mp4"
    assert projects.get_project("hero/walk") is not None
    assert projects.get_project("enemy/attack") is not None
    assert projects.get_project("hero/idle") is None


@pytest.mark.parametrize(
    "name",
    [
        "",
        " ",
        ".",
        "..",
        "../escape",
        "a/b",
        "a\\b",
        "x:y",
        "x?",
        "x\x00",
        "x\n",
        "CON",
        "con.png",
        "LPT1",
        "COM¹",
        "end.",
        LEGACY_ROLE,
    ],
)
def test_invalid_names_leave_data_untouched(projects, name):
    source = populate(projects)
    before = (source / "cache/global_params.json").read_bytes()
    with pytest.raises(ValueError, match="RENAME_INVALID"):
        projects.rename_project("hero/idle", name)
    assert (source / "cache/global_params.json").read_bytes() == before


@pytest.mark.parametrize(
    "operation,identifier,name", [("rename_role", "hero", "ENEMY"), ("rename_project", "hero/idle", "WALK")]
)
def test_conflicts_never_overwrite(projects, operation, identifier, name):
    populate(projects)
    populate(projects, action="walk")
    populate(projects, role="enemy")
    before = {
        p.relative_to(projects._projects_root): p.read_bytes()
        for p in projects._projects_root.rglob("*")
        if p.is_file()
    }
    with pytest.raises(ValueError, match="RENAME_CONFLICT"):
        getattr(projects, operation)(identifier, name)
    assert before == {
        p.relative_to(projects._projects_root): p.read_bytes()
        for p in projects._projects_root.rglob("*")
        if p.is_file()
    }


def test_nonproject_target_directory_is_a_conflict(projects):
    populate(projects)
    (projects._projects_root / "hero/batch-trim").mkdir()
    with pytest.raises(ValueError, match="RENAME_CONFLICT"):
        projects.rename_project("hero/idle", "batch-trim")


def test_original_name_is_noop_and_case_only_changes_survive_refresh(projects, monkeypatch):
    populate(projects)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "rename", lambda *_: pytest.fail("unchanged names must not move files"))
        result = projects.rename_project("hero/idle", " idle ")
        assert result["idMap"] == {"hero/idle": "hero/idle"}
    projects.rename_project("hero/idle", "Idle")
    projects.rename_role("hero", "Hero")
    assert [p["id"] for p in ProjectAPI(projects._projects_root).get_projects()] == ["Hero/Idle"]


def test_legacy_animation_keeps_flat_layout_and_can_migrate(projects):
    source = populate(projects)
    source.rename(projects._projects_root / "legacy")
    result = projects.rename_project("legacy", "旧动画")
    assert result["idMap"] == {"legacy": "旧动画"}
    assert result["projects"][0]["legacy"] is True
    with pytest.raises(ValueError, match="RENAME_INVALID"):
        projects.rename_role(LEGACY_ROLE, "新角色")
    migrated = projects.migrate_legacy_projects([{"projectId": "旧动画", "targetRole": "new", "targetAction": "walk"}])
    assert migrated["success"] is True
    assert projects.get_project("new/walk") is not None


@pytest.mark.parametrize("identifier", ["../hero", "hero/../idle", "/hero/idle", "hero/idle/extra", "hero//idle"])
def test_source_identifier_cannot_escape_or_be_silently_truncated(projects, identifier):
    populate(projects)
    with pytest.raises(ValueError, match="RENAME_INVALID"):
        projects.rename_project(identifier, "other")


def test_symlink_source_and_linked_metadata_are_rejected(projects, tmp_path):
    source = populate(projects)
    (projects._projects_root / "link").symlink_to(source.parent, target_is_directory=True)
    with pytest.raises(ValueError, match="RENAME_INVALID"):
        projects.rename_project("link/idle", "other")
    target = tmp_path / "external.json"
    target.write_text("{}")
    (source / "cache/global_params.json").unlink()
    (source / "cache/global_params.json").symlink_to(target)
    with pytest.raises(ValueError, match="RENAME_INVALID"):
        projects.rename_project("hero/idle", "other")
    assert target.read_text() == "{}"


def test_role_failure_rolls_back_directory_and_already_written_metadata(projects, monkeypatch):
    populate(projects)
    populate(projects, action="walk")
    original = {
        p.relative_to(projects._projects_root): p.read_bytes()
        for p in projects._projects_root.rglob("*")
        if p.is_file()
    }
    writer = projects._write_rename_metadata
    writes = 0

    def fail_second(path, content):
        nonlocal writes
        writes += 1
        if writes == 2:
            raise PermissionError("simulated metadata write failure")
        writer(path, content)

    monkeypatch.setattr(projects, "_write_rename_metadata", fail_second)
    with pytest.raises(RuntimeError, match="RENAME_FAILED"):
        projects.rename_role("hero", "knight")
    assert not (projects._projects_root / "knight").exists()
    assert original == {
        p.relative_to(projects._projects_root): p.read_bytes()
        for p in projects._projects_root.rglob("*")
        if p.is_file()
    }


def test_directory_move_failure_keeps_original(projects, monkeypatch):
    populate(projects)
    monkeypatch.setattr(Path, "rename", lambda *_: (_ for _ in ()).throw(PermissionError("locked")))
    with pytest.raises(RuntimeError, match="RENAME_FAILED"):
        projects.rename_project("hero/idle", "other")
    assert projects.get_project("hero/idle") is not None


def test_recovery_failure_reports_retained_location(projects, monkeypatch):
    populate(projects)
    monkeypatch.setattr(projects, "_write_rename_metadata", lambda *_: (_ for _ in ()).throw(PermissionError("locked")))
    with pytest.raises(RuntimeError, match="RENAME_RECOVERY.*hero"):
        projects.rename_project("hero/idle", "other")
    assert projects.get_project("hero/idle") is not None


def test_bridge_rejects_active_processing_and_pending_restart(api):
    populate(api._project_api)
    api._process_api_instance = SimpleNamespace(has_active_writes=lambda: True, shutdown=lambda: None)
    with pytest.raises(ValueError, match="RENAME_BUSY"):
        api.rename_role("hero", "other")
    api._process_api_instance = None
    api._storage_migration_coordinator._restart_required = True
    with pytest.raises(ValueError, match="RENAME_RESTART"):
        api.rename_project("hero/idle", "other")
    assert api.get_project("hero/idle") is not None


def test_bridge_blocks_rename_during_sync_writer(api):
    populate(api._project_api)
    entered, release = threading.Event(), threading.Event()

    def writer():
        with api._project_mutation_lock:
            entered.set()
            assert release.wait(5)

    with ThreadPoolExecutor() as executor:
        future = executor.submit(writer)
        assert entered.wait(5)
        try:
            with pytest.raises(ValueError, match="RENAME_BUSY"):
                api.rename_role("hero", "other")
        finally:
            release.set()
        future.result()


def test_writer_waiting_for_rename_cannot_recreate_old_path(api, monkeypatch):
    populate(api._project_api)
    entered, release, writer_started = threading.Event(), threading.Event(), threading.Event()
    rename = api._project_api.rename_project

    def delayed_rename(*args):
        entered.set()
        assert release.wait(5)
        return rename(*args)

    def stale_save():
        writer_started.set()
        return api.save_step_params("hero/idle", 1, {})

    monkeypatch.setattr(api._project_api, "rename_project", delayed_rename)
    with ThreadPoolExecutor() as executor:
        renaming = executor.submit(api.rename_project, "hero/idle", "other")
        assert entered.wait(5)
        writing = executor.submit(stale_save)
        assert writer_started.wait(5)
        release.set()
        assert renaming.result()["idMap"] == {"hero/idle": "hero/other"}
        with pytest.raises(ValueError, match="RENAME_NOT_FOUND"):
            writing.result()
    assert not (api._project_api._projects_root / "hero/idle").exists()


@pytest.mark.parametrize(
    "method,args,attribute",
    [
        ("save_timeline", ("hero/idle", {}), "_audio_api_instance"),
        ("extract_source_audio", ("hero/idle",), "_audio_api_instance"),
        ("save_step_params", ("hero/idle", 1, {}), "_process_api_instance"),
        ("start_processing", ("hero/idle", 1, {}), "_process_api_instance"),
        ("execute_batch_trim", ({"projectIds": ["hero/idle"]},), "_batch_trim_api_instance"),
        ("seedance_handoff", ("task", "hero", "walk"), "_seedance_api_instance"),
        ("storage_execute_migration", ("token",), "_storage_settings_api_instance"),
    ],
)
def test_project_write_entrypoints_exclude_rename(api, method, args, attribute):
    populate(api._project_api)
    entered, release = threading.Event(), threading.Event()
    target_method = {
        "execute_batch_trim": "execute_trim",
        "seedance_handoff": "handoff",
        "storage_execute_migration": "execute_migration",
    }.get(method, method)

    def writing(*_args):
        entered.set()
        assert release.wait(5)
        return True

    setattr(api, attribute, SimpleNamespace(**{target_method: writing, "shutdown": lambda: None}))
    with ThreadPoolExecutor() as executor:
        pending = executor.submit(getattr(api, method), *args)
        assert entered.wait(5)
        try:
            with pytest.raises(ValueError, match="RENAME_BUSY"):
                api.rename_project("hero/idle", "other")
        finally:
            release.set()
        assert pending.result() is True
    setattr(api, attribute, None)


def test_cancelled_worker_must_finish_before_renaming(api):
    populate(api._project_api)
    api._process_api_instance = SimpleNamespace(
        has_active_writes=lambda: False,
        tasks={"old": SimpleNamespace(future=SimpleNamespace(done=lambda: False))},
        shutdown=lambda: None,
    )
    with pytest.raises(ValueError, match="RENAME_BUSY"):
        api.rename_project("hero/idle", "other")


def test_busy_trim_rejects_rename(api):
    populate(api._project_api)
    api._batch_trim_api_instance = SimpleNamespace(has_active_writes=lambda: True)
    with pytest.raises(ValueError, match="RENAME_BUSY"):
        api.rename_project("hero/idle", "other")


def test_cli_step_access_uses_the_same_rename_lock(api, monkeypatch):
    from backend.agent_control.steps import StepControl

    populate(api._project_api)
    control = StepControl(api, SimpleNamespace())
    entered, release = threading.Event(), threading.Event()

    def applying(*_args):
        entered.set()
        assert release.wait(5)
        return {"saved": True}

    monkeypatch.setattr(control, "_apply", applying)
    with ThreadPoolExecutor() as executor:
        writing = executor.submit(control.apply, "step.set", {})
        assert entered.wait(5)
        try:
            with pytest.raises(ValueError, match="RENAME_BUSY"):
                api.rename_project("hero/idle", "other")
        finally:
            release.set()
        assert writing.result() == {"saved": True}


def test_known_internal_path_is_updated_under_an_aliased_project_root(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    projects = ProjectAPI(alias)
    path = populate(projects)
    metadata_path = path / "cache/global_params.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["video_path"] = str(path / "cache/source.mp4")
    metadata_path.write_text(json.dumps(metadata))
    result = projects.rename_project("hero/idle", "walk")
    assert result["projects"][0]["video_path"] == str(alias / "hero/walk/cache/source.mp4")
