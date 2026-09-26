from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from backend.api.project_api import ProjectAPI
from backend.seedance.cache import CacheManager
from backend.seedance.models import SeedanceRequest, SeedanceTask
from backend.seedance.repository import TaskRepository


class _UnusedClient:
    pass


class _UnusedDownloader:
    pass


def _write_video(path: Path) -> Path:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (16, 16))
    assert writer.isOpened()
    writer.write(np.zeros((16, 16, 3), dtype=np.uint8))
    writer.release()
    return path


@pytest.fixture
def project_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ProjectAPI:
    monkeypatch.chdir(tmp_path)
    return ProjectAPI()


@pytest.fixture
def repository(tmp_path: Path) -> TaskRepository:
    source = tmp_path / "first.png"
    Image.new("RGB", (8, 8), "white").save(source)
    return TaskRepository(tmp_path / "seedance-cache")


@pytest.fixture
def downloaded_task(repository: TaskRepository, tmp_path: Path) -> SeedanceTask:
    task = repository.create_draft(SeedanceRequest(first_frame=tmp_path / "first.png"))
    video_path = repository.cache_root / "tasks" / task.local_id / "output" / "video.mp4"
    _write_video(video_path)

    def mark_downloaded(current: SeedanceTask) -> None:
        current.remote_status = "succeeded"
        current.download_status = "downloaded"
        current.cache_status = "complete"
        current.output_paths["video"] = "output/video.mp4"
        current.finished_at = (datetime.now(UTC) - timedelta(days=8)).isoformat()

    return repository.update(task.local_id, mark_downloaded)


@pytest.fixture
def manager(repository: TaskRepository, project_api: ProjectAPI):
    from backend.seedance.manager import SeedanceTaskManager

    return SeedanceTaskManager(
        _UnusedClient(),
        repository,
        _UnusedDownloader(),
        CacheManager(repository, project_api),
        {"retention_days": 90, "last_cleanup_at": None},
    )


def test_handoff_uses_cached_video_without_copy(manager, downloaded_task: SeedanceTask, project_api: ProjectAPI):
    cached_video = manager._repository.resolve_asset(downloaded_task.local_id, downloaded_task.output_paths["video"])

    result = manager.handoff(downloaded_task.local_id, "hero", "attack")

    project = project_api.get_project(result["project_id"])
    assert project is not None
    assert project["video_path"] == str(cached_video)
    assert project["steps"]["1"]["data_ready"] is True
    handoffs = manager._repository.get(downloaded_task.local_id).handoffs
    assert len(handoffs) == 1
    assert {key: value for key, value in handoffs[0].items() if key != "created_at"} == {
        "project_id": result["project_id"],
        "role": "hero",
        "action": "attack",
    }
    assert isinstance(handoffs[0]["created_at"], str)


@pytest.mark.parametrize(
    ("role", "action"),
    [("", "attack"), ("hero", ""), ("hero", "   ")],
)
def test_handoff_requires_non_empty_role_and_action(manager, downloaded_task: SeedanceTask, role: str, action: str):
    with pytest.raises(ValueError, match="role|action"):
        manager.handoff(downloaded_task.local_id, role, action)

    assert manager._repository.get(downloaded_task.local_id).handoffs == []


def test_handoff_rejects_not_downloaded_or_cleared_video(manager, downloaded_task: SeedanceTask):
    manager._repository.update(downloaded_task.local_id, lambda current: setattr(current, "download_status", "pending"))
    with pytest.raises(ValueError, match="downloaded"):
        manager.handoff(downloaded_task.local_id, "hero", "attack")

    manager._repository.update(downloaded_task.local_id, lambda current: setattr(current, "download_status", "cleared"))
    with pytest.raises(ValueError, match="downloaded"):
        manager.handoff(downloaded_task.local_id, "hero", "attack")


def test_handoff_rejects_a_missing_cached_video(manager, downloaded_task: SeedanceTask):
    cached_video = manager._repository.resolve_asset(downloaded_task.local_id, downloaded_task.output_paths["video"])
    cached_video.unlink()

    with pytest.raises(ValueError, match="cached video"):
        manager.handoff(downloaded_task.local_id, "hero", "attack")

    assert manager._repository.get(downloaded_task.local_id).handoffs == []


def test_handoff_leaves_no_record_when_project_creation_fails(
    manager, downloaded_task: SeedanceTask, project_api: ProjectAPI
):
    created = manager.handoff(downloaded_task.local_id, "hero", "attack")

    with pytest.raises(ValueError, match="已存在"):
        manager.handoff(downloaded_task.local_id, "hero", "attack")

    assert len(manager._repository.get(downloaded_task.local_id).handoffs) == 1
    assert project_api.get_project(created["project_id"]) is not None


def test_handoff_rolls_back_an_unready_project_and_allows_retry(
    manager, downloaded_task: SeedanceTask, project_api: ProjectAPI, monkeypatch: pytest.MonkeyPatch
):
    from backend.core import video_utils

    original_extractor = video_utils.process_video_to_cache

    def fail_step1(*_args, **_kwargs):
        raise RuntimeError("forced Step 1 failure")

    monkeypatch.setattr(video_utils, "process_video_to_cache", fail_step1)
    with pytest.raises(RuntimeError, match="Step 1 data"):
        manager.handoff(downloaded_task.local_id, "hero", "attack")

    project_id = "hero/attack"
    assert project_api.get_project(project_id) is None
    assert project_id not in {project["id"] for project in project_api.get_projects()}
    assert not Path("project").joinpath("hero", "attack").exists()
    assert manager._repository.get(downloaded_task.local_id).handoffs == []

    monkeypatch.setattr(video_utils, "process_video_to_cache", original_extractor)
    retried = manager.handoff(downloaded_task.local_id, "hero", "attack")

    assert retried["project_id"] == project_id
    assert project_api.get_project(project_id)["steps"]["1"]["data_ready"] is True


def test_handoff_surfaces_a_step1_and_rollback_failure(
    manager, downloaded_task: SeedanceTask, project_api: ProjectAPI, monkeypatch: pytest.MonkeyPatch
):
    from backend.core import video_utils

    def fail_step1(*_args, **_kwargs):
        raise RuntimeError("forced Step 1 failure")

    monkeypatch.setattr(video_utils, "process_video_to_cache", fail_step1)
    monkeypatch.setattr(project_api, "delete_project", lambda _project_id: False)

    with pytest.raises(RuntimeError, match="Step 1 data.*rollback failed"):
        manager.handoff(downloaded_task.local_id, "hero", "attack")

    assert manager._repository.get(downloaded_task.local_id).handoffs == []


def test_existing_projects_protect_handoffs_until_all_are_deleted(
    manager, downloaded_task: SeedanceTask, project_api: ProjectAPI
):
    first = manager.handoff(downloaded_task.local_id, "hero", "attack")
    second = manager.handoff(downloaded_task.local_id, "hero", "defend")

    assert manager.cache_status()["protected_task_count"] == 1
    assert project_api.delete_project(first["project_id"]) is True
    assert manager.cache_status()["protected_task_count"] == 1
    assert [handoff["project_id"] for handoff in manager._repository.get(downloaded_task.local_id).handoffs] == [
        second["project_id"]
    ]

    assert project_api.delete_project(second["project_id"]) is True
    assert manager.cache_status()["protected_task_count"] == 0
    assert manager._repository.get(downloaded_task.local_id).handoffs == []
    manager.delete_task(downloaded_task.local_id)
    with pytest.raises(FileNotFoundError):
        manager._repository.get(downloaded_task.local_id)


def test_concurrent_handoffs_preserve_every_project_link(manager, downloaded_task: SeedanceTask):
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda action: manager.handoff(downloaded_task.local_id, "hero", action),
                ("attack", "defend"),
            )
        )

    handoffs = manager._repository.get(downloaded_task.local_id).handoffs
    assert {result["project_id"] for result in results} == {handoff["project_id"] for handoff in handoffs}


def test_status_pruning_cannot_erase_a_handoff_appended_after_it_starts(
    manager, downloaded_task: SeedanceTask, project_api: ProjectAPI
):
    manager._repository.update(
        downloaded_task.local_id,
        lambda current: current.handoffs.append({"project_id": "deleted/project"}),
    )
    lookup_started = threading.Event()
    release_lookup = threading.Event()

    class BlockingProjectAPI:
        def get_project(self, project_id: str):
            lookup_started.set()
            assert release_lookup.wait(timeout=2)
            return project_api.get_project(project_id)

        def create_project(self, role: str, action: str, video_path: str, frame_interval: int = 1):
            return project_api.create_project(role, action, video_path, frame_interval)

    manager._cache_manager._project_api = BlockingProjectAPI()
    with ThreadPoolExecutor(max_workers=2) as executor:
        status = executor.submit(manager.cache_status)
        assert lookup_started.wait(timeout=2)
        handoff = executor.submit(manager.handoff, downloaded_task.local_id, "hero", "attack")
        release_lookup.set()
        assert status.result(timeout=2)["protected_task_count"] == 0
        created = handoff.result(timeout=2)

    assert manager._repository.get(downloaded_task.local_id).handoffs[0]["project_id"] == created["project_id"]
