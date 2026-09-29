"""Unified active-writer queries that gate storage migration.

Covers the storage-location-management change: project processing, batch
trim, Seedream image generation and Seedance video generation each expose a
single "may still write" query, and the migration coordinator refuses to
precheck or execute while any of them is active.
"""

from pathlib import Path

import pytest
from PIL import Image

from src.utils.storage_migration import (
    PROJECT_LOCATION,
    LocationMigration,
    MigrationError,
    StorageMigrationCoordinator,
)


@pytest.fixture
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path / "data-root"))
    monkeypatch.setenv("GAM_CONFIG", str(tmp_path / "runtime" / "config.json"))
    return tmp_path


# ==================== ProcessAPI ====================


def test_process_api_reports_running_tasks(isolated_config: Path):
    from backend.api.process_api import ProcessAPI, Task

    api = ProcessAPI()
    try:
        assert api.has_active_writes() is False
        task = Task("t1", "mage/walk", 1, {})
        api.tasks["t1"] = task
        task.status = "running"
        assert api.has_active_writes() is True
        task.status = "completed"
        assert api.has_active_writes() is False
        task.status = "pending"
        assert api.has_active_writes() is True
    finally:
        api.shutdown()


# ==================== BatchTrimAPI ====================


def test_batch_trim_reports_in_flight_trim(isolated_config: Path):
    from backend.api.batch_trim_api import BatchTrimAPI

    api = BatchTrimAPI()
    assert api.has_active_writes() is False
    with api._trim_activity():
        assert api.has_active_writes() is True
    assert api.has_active_writes() is False


def test_batch_trim_activity_releases_on_error(isolated_config: Path):
    from backend.api.batch_trim_api import BatchTrimAPI

    api = BatchTrimAPI()
    with pytest.raises(RuntimeError), api._trim_activity():
        raise RuntimeError("boom")
    assert api.has_active_writes() is False


# ==================== Seedream ====================


def test_seedream_api_reports_active_attempts(isolated_config: Path):
    from backend.api.seedream_api import SeedreamAPI

    api = SeedreamAPI(client_factory=lambda key: object())
    try:
        assert api.has_active_writes() is False
        manager = api._ensure_manager()
        manager._active_attempts["batch-1"] = {0}
        assert api.has_active_writes() is True
        manager._active_attempts.clear()
        assert api.has_active_writes() is False
    finally:
        api.shutdown()


# ==================== Seedance ====================


def _make_seedance_manager(tmp_path: Path):
    from backend.seedance.manager import SeedanceTaskManager
    from backend.seedance.repository import TaskRepository

    repository = TaskRepository(tmp_path / "ai-video-cache")
    manager = SeedanceTaskManager(
        object(),
        repository,
        object(),
        object(),
        {"retention_days": 90, "last_cleanup_at": None},
    )
    return manager, repository


def _create_task(repository, tmp_path: Path, remote_status: str, download_status: str) -> None:
    from backend.seedance.models import SeedanceRequest

    image = tmp_path / "frame.png"
    Image.new("RGB", (8, 8), "white").save(image)
    task = repository.create_draft(SeedanceRequest(first_frame=image, prompt="scene"))

    def mark(current) -> None:
        current.remote_status = remote_status
        current.download_status = download_status

    repository.update(task.local_id, mark)


def test_seedance_manager_reports_writable_task_states(tmp_path: Path):
    manager, repository = _make_seedance_manager(tmp_path)
    assert manager.has_active_writes() is False

    _create_task(repository, tmp_path, "queued", "pending")
    assert manager.has_active_writes() is True

    _create_task(repository, tmp_path, "succeeded", "downloaded")
    _create_task(repository, tmp_path, "failed", "pending")
    _create_task(repository, tmp_path, "cancelled", "pending")
    assert manager.has_active_writes() is True  # the queued task still counts


def test_seedance_manager_reports_active_download(tmp_path: Path):
    manager, repository = _make_seedance_manager(tmp_path)
    _create_task(repository, tmp_path, "succeeded", "downloading")
    assert manager.has_active_writes() is True


def test_seedance_api_without_manager_has_no_activity(isolated_config: Path):
    from backend.api.seedance_api import SeedanceAPI

    api = SeedanceAPI(client_factory=lambda key: object())
    assert api.has_active_writes() is False


# ==================== Coordinator blocking ====================


def test_precheck_is_blocked_while_any_writer_is_active(tmp_path: Path):
    flag = {"process": True}
    coordinator = StorageMigrationCoordinator(
        commit_config=lambda draft: draft,
        activity_providers={"process": lambda: flag["process"]},
    )
    source = tmp_path / "project"
    source.mkdir()
    target = tmp_path / "new-project"

    with pytest.raises(MigrationError, match="process"):
        coordinator.precheck([LocationMigration(PROJECT_LOCATION, source, target)], {})

    assert not target.exists()
    flag["process"] = False
    report = coordinator.precheck([LocationMigration(PROJECT_LOCATION, source, target)], {})
    assert report.token


def test_execute_is_blocked_by_late_activity_and_token_survives(tmp_path: Path):
    flag = {"seedance": False}
    coordinator = StorageMigrationCoordinator(
        commit_config=lambda draft: draft,
        activity_providers={"seedance": lambda: flag["seedance"]},
    )
    source = tmp_path / "project"
    source.mkdir()
    (source / "a.txt").write_text("data", encoding="utf-8")
    target = tmp_path / "new-project"

    report = coordinator.precheck([LocationMigration(PROJECT_LOCATION, source, target)], {})
    flag["seedance"] = True
    with pytest.raises(MigrationError, match="seedance"):
        coordinator.execute(report.token)
    assert not target.exists()

    flag["seedance"] = False
    coordinator.execute(report.token)
    assert coordinator.restart_required is True
    assert (target / "a.txt").read_text(encoding="utf-8") == "data"


# ==================== App composition root wiring ====================


def test_main_composition_root_wires_storage_migration(isolated_config: Path, tmp_path: Path):
    from backend.main import API

    api = API()
    try:
        assert api.storage_get_settings()["success"] is True
        assert api.storage_migration_state() == {"success": True, "restart_required": False}

        save = api.storage_save_settings({"project_dir": str(tmp_path / "new-projects")})
        assert save["success"] is True
        assert save["migration_required"] is True
        # Prechecking must not spawn managers just to check activity.
        assert api._process_api_instance is None
        assert api._seedance_api_instance is None
        assert api._seedream_api_instance is None
        assert api._batch_trim_api_instance is None

        from backend.api.process_api import Task

        process_api = api._process_api
        task = Task("t1", "mage/walk", 1, {})
        task.status = "running"
        process_api.tasks["t1"] = task

        blocked = api.storage_save_settings({"project_dir": str(tmp_path / "other-projects")})
        assert blocked["success"] is False
        assert "process" in blocked["error"]["message"]
    finally:
        if api._process_api_instance is not None:
            api._process_api_instance.shutdown()
        if api._seedance_api_instance is not None:
            api._seedance_api_instance.shutdown()
        if api._seedream_api_instance is not None:
            api._seedream_api_instance.shutdown()
