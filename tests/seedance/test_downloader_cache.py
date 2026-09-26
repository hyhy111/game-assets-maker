from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path
from shutil import rmtree
from time import sleep

import cv2
import numpy as np
import pytest
from PIL import Image

from backend.seedance.cache import CacheManager
from backend.seedance.downloader import ResultDownloader
from backend.seedance.models import SeedanceRequest, SeedanceTask
from backend.seedance.repository import TaskRepository


class FakeDownloadTransport:
    def __init__(self, responses: dict[str, bytes | BaseException], *, delay: float = 0) -> None:
        self.responses = responses
        self.delay = delay
        self.urls: list[str] = []

    def download(self, url: str) -> bytes:
        self.urls.append(url)
        if self.delay:
            sleep(self.delay)
        response = self.responses[url]
        if isinstance(response, BaseException):
            raise response
        return response


class ScriptedDownloadTransport:
    def __init__(self, responses: list[bytes | BaseException]) -> None:
        self.responses = responses
        self.urls: list[str] = []

    def download(self, url: str) -> bytes:
        self.urls.append(url)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class FakeProjectAPI:
    def __init__(self, existing_ids: set[str] | None = None) -> None:
        self.existing_ids = existing_ids or set()

    def get_project(self, project_id: str) -> dict[str, str] | None:
        return {"id": project_id} if project_id in self.existing_ids else None


def _write_image(path: Path, color: str = "white") -> Path:
    Image.new("RGB", (8, 8), color).save(path)
    return path


def _video_bytes(path: Path) -> bytes:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (16, 16))
    assert writer.isOpened()
    writer.write(np.zeros((16, 16, 3), dtype=np.uint8))
    writer.release()
    return path.read_bytes()


@pytest.fixture
def repository(tmp_path: Path) -> TaskRepository:
    return TaskRepository(tmp_path / "seedance-cache")


@pytest.fixture
def task(repository: TaskRepository, tmp_path: Path) -> SeedanceTask:
    return repository.create_draft(SeedanceRequest(first_frame=_write_image(tmp_path / "first.png"), prompt="keep me"))


def _succeeded_task(
    repository: TaskRepository,
    task: SeedanceTask,
    *,
    video_url: str = "https://downloads.example/video.mp4",
    last_frame_url: str | None = None,
    finished_at: str | None = None,
    handoffs: list[dict[str, str]] | None = None,
) -> SeedanceTask:
    def mark_succeeded(current: SeedanceTask) -> None:
        current.remote_status = "succeeded"
        current.remote = {"content": {"video_url": video_url}, "usage": {"total_tokens": 12}}
        if last_frame_url:
            current.remote["content"]["last_frame_url"] = last_frame_url
        current.finished_at = finished_at or (datetime.now(UTC) - timedelta(days=8)).isoformat()
        current.handoffs = handoffs or []
        current.error = {"code": "previous", "message": "preserve this"}

    return repository.update(task.local_id, mark_succeeded)


def _asset_bytes(repository: TaskRepository, task: SeedanceTask) -> int:
    task_dir = repository.cache_root / "tasks" / task.local_id
    return sum(
        path.stat().st_size
        for directory in (task_dir / "input", task_dir / "output")
        for path in directory.rglob("*")
        if path.is_file() and not path.is_symlink()
    )


def test_download_writes_valid_video_and_returned_last_frame_atomically(
    repository: TaskRepository, task: SeedanceTask, tmp_path: Path
):
    task = _succeeded_task(
        repository,
        task,
        last_frame_url="https://downloads.example/returned-last-frame.png",
    )
    video = _video_bytes(tmp_path / "remote.mp4")
    image = _write_image(tmp_path / "returned.png", "red").read_bytes()
    transport = FakeDownloadTransport(
        {
            "https://downloads.example/video.mp4": video,
            "https://downloads.example/returned-last-frame.png": image,
        }
    )

    downloaded = ResultDownloader(repository, transport).download_task(task)

    video_path = repository.resolve_asset(downloaded.local_id, downloaded.output_paths["video"])
    last_frame_path = repository.resolve_asset(downloaded.local_id, downloaded.output_paths["returned_last_frame"])
    assert downloaded.download_status == "downloaded"
    assert downloaded.cache_status == "complete"
    assert cv2.VideoCapture(str(video_path)).isOpened()
    with Image.open(last_frame_path) as returned_last_frame:
        returned_last_frame.verify()
    assert not video_path.with_suffix(".mp4.part").exists()
    assert not last_frame_path.with_suffix(".png.part").exists()
    assert ResultDownloader(repository, transport).is_download_confirmed(downloaded) is True


def test_download_confirmation_rejects_a_missing_or_unreadable_local_video(
    repository: TaskRepository, task: SeedanceTask, tmp_path: Path
):
    task = _succeeded_task(repository, task)
    video = _video_bytes(tmp_path / "remote.mp4")
    downloader = ResultDownloader(
        repository,
        FakeDownloadTransport({"https://downloads.example/video.mp4": video}),
    )
    downloaded = downloader.download_task(task)
    video_path = repository.resolve_asset(downloaded.local_id, downloaded.output_paths["video"])

    video_path.write_bytes(b"not a video")

    assert downloader.is_download_confirmed(repository.get(task.local_id)) is False


def test_download_rejects_zero_byte_video_without_creating_final_file(repository: TaskRepository, task: SeedanceTask):
    task = _succeeded_task(repository, task)

    with pytest.raises(ValueError, match="empty"):
        ResultDownloader(repository, FakeDownloadTransport({"https://downloads.example/video.mp4": b""})).download_task(
            task
        )

    task_dir = repository.cache_root / "tasks" / task.local_id
    stored = repository.get(task.local_id)
    assert not (task_dir / "output" / "video.mp4").exists()
    assert (task_dir / "output" / "video.mp4.part").exists()
    assert stored.download_status == "failed"
    assert stored.request["prompt"] == "keep me"
    assert stored.remote["usage"] == {"total_tokens": 12}


def test_download_rejects_non_video_content_without_replacing_final_file(
    repository: TaskRepository, task: SeedanceTask
):
    task = _succeeded_task(repository, task)

    with pytest.raises(ValueError, match="readable MP4"):
        ResultDownloader(
            repository, FakeDownloadTransport({"https://downloads.example/video.mp4": b"not a video"})
        ).download_task(task)

    assert not (repository.cache_root / "tasks" / task.local_id / "output" / "video.mp4").exists()


def test_download_url_failure_preserves_existing_valid_video_and_remote_metadata(
    repository: TaskRepository, task: SeedanceTask, tmp_path: Path
):
    task = _succeeded_task(repository, task)
    output_path = repository.cache_root / "tasks" / task.local_id / "output" / "video.mp4"
    existing = _video_bytes(tmp_path / "existing.mp4")
    output_path.write_bytes(existing)

    with pytest.raises(OSError, match="expired"):
        ResultDownloader(
            repository, FakeDownloadTransport({"https://downloads.example/video.mp4": OSError("expired")})
        ).download_task(task)

    stored = repository.get(task.local_id)
    assert output_path.read_bytes() == existing
    assert stored.remote_status == "succeeded"
    assert stored.remote["content"]["video_url"] == "https://downloads.example/video.mp4"
    assert stored.remote["usage"] == {"total_tokens": 12}
    assert stored.error == {"code": "previous", "message": "preserve this"}


def test_failed_download_can_retry_the_same_result_and_restore_complete_cache(
    repository: TaskRepository, task: SeedanceTask, tmp_path: Path
):
    task = _succeeded_task(repository, task)
    transport = ScriptedDownloadTransport([TimeoutError("temporary timeout"), _video_bytes(tmp_path / "remote.mp4")])
    downloader = ResultDownloader(repository, transport)

    with pytest.raises(TimeoutError, match="temporary timeout"):
        downloader.download_task(task)
    assert repository.get(task.local_id).download_status == "failed"

    downloaded = downloader.download_task(repository.get(task.local_id))

    assert downloaded.download_status == "downloaded"
    assert downloaded.cache_status == "complete"
    assert transport.urls == ["https://downloads.example/video.mp4"] * 2


def test_second_concurrent_download_rechecks_task_and_avoids_duplicate_transport_call(
    repository: TaskRepository, task: SeedanceTask, tmp_path: Path
):
    task = _succeeded_task(repository, task)
    transport = FakeDownloadTransport(
        {"https://downloads.example/video.mp4": _video_bytes(tmp_path / "remote.mp4")}, delay=0.1
    )
    downloader = ResultDownloader(repository, transport)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(downloader.download_task, (task, task)))

    assert len(transport.urls) == 1
    assert repository.get(task.local_id).download_status == "downloaded"
    assert {result.download_status for result in results} <= {"downloading", "downloaded"}


def test_cache_status_counts_all_task_files_but_only_eligible_assets_as_clearable(
    repository: TaskRepository, task: SeedanceTask
):
    old = _succeeded_task(repository, task)
    (repository.cache_root / "tasks" / old.local_id / "output" / "video.mp4").write_bytes(b"old-video")
    active = repository.create_draft(
        SeedanceRequest(first_frame=repository.resolve_asset(old.local_id, old.input_paths["first_frame"]))
    )
    (repository.cache_root / "tasks" / active.local_id / "output" / "partial.part").write_bytes(b"active")
    unknown = repository.create_draft(
        SeedanceRequest(first_frame=repository.resolve_asset(old.local_id, old.input_paths["first_frame"]))
    )
    repository.update(
        unknown.local_id,
        lambda current: (
            setattr(current, "remote_status", "submission_unknown"),
            setattr(current, "finished_at", (datetime.now(UTC) - timedelta(days=8)).isoformat()),
        ),
    )
    (repository.cache_root / "tasks" / unknown.local_id / "output" / "partial.part").write_bytes(b"unknown")
    protected = repository.create_draft(
        SeedanceRequest(first_frame=repository.resolve_asset(old.local_id, old.input_paths["first_frame"]))
    )
    protected = _succeeded_task(repository, protected, handoffs=[{"project_id": "project-1"}])
    (repository.cache_root / "tasks" / protected.local_id / "output" / "video.mp4").write_bytes(b"protected")
    cache_manager = CacheManager(repository, FakeProjectAPI({"project-1"}))

    status = cache_manager.status()

    expected_total = sum(
        path.stat().st_size
        for path in repository.cache_root.joinpath("tasks").rglob("*")
        if path.is_file() and not path.is_symlink()
    )
    assert status == {
        "total_bytes": expected_total,
        "task_count": 4,
        "protected_task_count": 1,
        "clearable_bytes": _asset_bytes(repository, old),
    }


def test_cleanup_uses_finished_at_cutoff_and_preserves_task_metadata(repository: TaskRepository, task: SeedanceTask):
    old = _succeeded_task(repository, task)
    old_dir = repository.cache_root / "tasks" / old.local_id
    (old_dir / "output" / "video.mp4").write_bytes(b"old-video")
    (old_dir / "output" / "video.mp4.part").write_bytes(b"partial")
    released = _asset_bytes(repository, old)
    recent = repository.create_draft(
        SeedanceRequest(first_frame=repository.resolve_asset(old.local_id, old.input_paths["first_frame"]))
    )
    recent = _succeeded_task(repository, recent, finished_at=(datetime.now(UTC) - timedelta(days=6)).isoformat())
    (repository.cache_root / "tasks" / recent.local_id / "output" / "video.mp4").write_bytes(b"recent")
    active = repository.create_draft(
        SeedanceRequest(first_frame=repository.resolve_asset(old.local_id, old.input_paths["first_frame"]))
    )
    (repository.cache_root / "tasks" / active.local_id / "output" / "partial.part").write_bytes(b"active")
    unknown = repository.create_draft(
        SeedanceRequest(first_frame=repository.resolve_asset(old.local_id, old.input_paths["first_frame"]))
    )
    repository.update(
        unknown.local_id,
        lambda current: (
            setattr(current, "remote_status", "submission_unknown"),
            setattr(current, "finished_at", (datetime.now(UTC) - timedelta(days=9)).isoformat()),
        ),
    )
    (repository.cache_root / "tasks" / unknown.local_id / "output" / "partial.part").write_bytes(b"unknown")
    cache_manager = CacheManager(repository, FakeProjectAPI())

    result = cache_manager.clean(older_than_days=7)

    stored = repository.get(old.local_id)
    assert result == {
        "files_removed": 3,
        "bytes_released": released,
        "tasks_cleared": 1,
        "protected_tasks_skipped": 0,
    }
    assert stored.download_status == "cleared"
    assert stored.cache_status == "cleared"
    assert stored.request["prompt"] == "keep me"
    assert stored.remote["usage"] == {"total_tokens": 12}
    assert stored.error == {"code": "previous", "message": "preserve this"}
    assert stored.handoffs == []
    assert (old_dir / "task.json").exists()
    assert not any(path.is_file() for path in (old_dir / "input").rglob("*"))
    assert not any(path.is_file() for path in (old_dir / "output").rglob("*"))
    assert (repository.cache_root / "tasks" / recent.local_id / "output" / "video.mp4").exists()
    assert (repository.cache_root / "tasks" / active.local_id / "output" / "partial.part").exists()
    assert (repository.cache_root / "tasks" / unknown.local_id / "output" / "partial.part").exists()


def test_cleanup_keeps_task_json_and_skips_protected(repository: TaskRepository, task: SeedanceTask):
    protected = _succeeded_task(repository, task, handoffs=[{"project_id": "project-1"}])
    protected_dir = repository.cache_root / "tasks" / protected.local_id
    video_path = protected_dir / "output" / "video.mp4"
    video_path.write_bytes(b"protected")
    cache_manager = CacheManager(repository, FakeProjectAPI({"project-1"}))

    result = cache_manager.clean(older_than_days=7)

    assert result["protected_tasks_skipped"] == 1
    assert video_path.exists()
    assert (protected_dir / "task.json").exists()


def test_cleanup_can_explicitly_clear_protected_task(repository: TaskRepository, task: SeedanceTask):
    protected = _succeeded_task(repository, task, handoffs=[{"project_id": "project-1"}])
    video_path = repository.cache_root / "tasks" / protected.local_id / "output" / "video.mp4"
    video_path.write_bytes(b"protected")

    result = CacheManager(repository, FakeProjectAPI({"project-1"})).clean(older_than_days=7, allow_protected=True)

    assert result["protected_tasks_skipped"] == 0
    assert not video_path.exists()
    assert repository.get(protected.local_id).cache_status == "cleared"


def test_cleanup_does_not_follow_an_asset_directory_symlink(
    repository: TaskRepository, task: SeedanceTask, tmp_path: Path
):
    task = _succeeded_task(repository, task)
    task_dir = repository.cache_root / "tasks" / task.local_id
    external_dir = tmp_path / "external"
    external_dir.mkdir()
    external_file = external_dir / "outside.png"
    external_file.write_bytes(b"outside")
    rmtree(task_dir / "input")
    (task_dir / "input").symlink_to(external_dir, target_is_directory=True)

    result = CacheManager(repository, FakeProjectAPI()).clean(older_than_days=7)

    assert result["files_removed"] == 0
    assert external_file.exists()


def test_cache_ignores_task_directory_aliased_as_input_root(
    repository: TaskRepository, task: SeedanceTask, monkeypatch: pytest.MonkeyPatch
):
    task = _succeeded_task(repository, task)
    task_dir = repository.cache_root / "tasks" / task.local_id
    task_json = task_dir / "task.json"
    lock_path = task_dir / ".task.lock"
    lock_path.touch()
    rmtree(task_dir / "input")
    (task_dir / "input").symlink_to(task_dir, target_is_directory=True)
    monkeypatch.setattr(repository, "task_lock", lambda local_id: nullcontext())
    cache_manager = CacheManager(repository, FakeProjectAPI())

    status = cache_manager.status()
    result = cache_manager.clean(older_than_days=7)

    assert status["clearable_bytes"] == 0
    assert result["files_removed"] == 0
    assert task_json.exists()
    assert lock_path.exists()


def test_cleanup_skips_assets_while_a_download_claim_is_in_progress(
    repository: TaskRepository, task: SeedanceTask, tmp_path: Path
):
    task = _succeeded_task(repository, task)
    downloader = ResultDownloader(repository, FakeDownloadTransport({}))
    claimed, owns_claim = downloader._claim(task.local_id)
    task_dir = repository.cache_root / "tasks" / task.local_id
    video_path = task_dir / "output" / "video.mp4"
    part_path = task_dir / "output" / "video.mp4.part"
    video_path.write_bytes(_video_bytes(tmp_path / "completed.mp4"))
    part_path.write_bytes(b"in-progress-download")
    cache_manager = CacheManager(repository, FakeProjectAPI())

    status = cache_manager.status()
    result = cache_manager.clean(older_than_days=7)

    assert owns_claim is True
    assert claimed.download_status == "downloading"
    assert status["clearable_bytes"] == 0
    assert result["files_removed"] == 0
    assert repository.get(task.local_id).download_status == "downloading"
    assert video_path.exists()
    assert part_path.exists()


def test_downloader_does_not_finalize_a_claim_cleared_during_download(
    repository: TaskRepository, task: SeedanceTask, tmp_path: Path
):
    task = _succeeded_task(repository, task)
    video = _video_bytes(tmp_path / "remote.mp4")

    class ClearingTransport:
        def download(self, url: str) -> bytes:
            repository.update(
                task.local_id,
                lambda current: (
                    setattr(current, "download_status", "cleared"),
                    setattr(current, "cache_status", "cleared"),
                ),
            )
            return video

    result = ResultDownloader(repository, ClearingTransport()).download_task(task)

    assert result.download_status == "cleared"
    assert result.cache_status == "cleared"
    assert repository.get(task.local_id).download_status == "cleared"


def test_downloader_marks_an_owned_claim_failed_when_final_video_disappears(
    repository: TaskRepository, task: SeedanceTask, tmp_path: Path
):
    task = _succeeded_task(repository, task)
    video = _video_bytes(tmp_path / "remote.mp4")

    class DisappearingDownloader(ResultDownloader):
        def _download_to(self, url: str, destination: Path, validate) -> None:
            super()._download_to(url, destination, validate)
            destination.unlink()

    with pytest.raises(RuntimeError, match="disappeared"):
        DisappearingDownloader(
            repository, FakeDownloadTransport({"https://downloads.example/video.mp4": video})
        ).download_task(task)

    stored = repository.get(task.local_id)
    assert stored.download_status == "failed"
    assert stored.cache_status == "complete"
    assert stored.request["prompt"] == "keep me"
    assert stored.remote["usage"] == {"total_tokens": 12}
