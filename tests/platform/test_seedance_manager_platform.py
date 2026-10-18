"""SeedanceTaskManager platform-source routing (task 2.x verification).

The platform client is faked at the PlatformVideoClient boundary; the real
repository/manager/downloader stack runs against a tmp cache root.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from backend.platform.client import PlatformError, PlatformUnauthorizedError
from backend.platform.video import artifact_url
from backend.seedance.manager import PLATFORM_SOURCE, SeedanceTaskManager
from backend.seedance.models import SeedanceRequest, SeedanceTask
from backend.seedance.repository import TaskRepository


class FakePlatformVideo:
    """Records calls; scripted upload/create/get/delete outcomes."""

    def __init__(self) -> None:
        self.uploaded: list[Path] = []
        self.created_payloads: list[dict[str, Any]] = []
        self.create_result: dict[str, Any] | Exception = {"id": "job-1", "status": "queued",
                                                            "platform_status": "QUEUED", "quote": 100}
        self.get_results: list[dict[str, Any] | Exception] = []
        self.cancel_result: dict[str, Any] | Exception = {"id": "job-1", "status": "cancelled",
                                                            "platform_status": "CANCELLED"}
        self.download_bytes = b""

    def upload_asset(self, path) -> dict[str, Any]:
        self.uploaded.append(Path(path))
        return {"assetId": "asset-1"}

    def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.created_payloads.append(payload)
        if isinstance(self.create_result, Exception):
            raise self.create_result
        return self.create_result

    def get_task(self, remote_id: str) -> dict[str, Any]:
        result = self.get_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def delete_task(self, remote_id: str) -> dict[str, Any]:
        if isinstance(self.cancel_result, Exception):
            raise self.cancel_result
        return self.cancel_result

    def download_artifact(self, job_id: str) -> bytes:
        return self.download_bytes


class FakePlatformDownloader:
    """Mimics ResultDownloader against platform:// URLs using FakePlatformVideo bytes."""

    def __init__(self, platform: FakePlatformVideo) -> None:
        self.platform = platform
        self.downloaded: list[str] = []

    def download_task(self, task: SeedanceTask) -> SeedanceTask:
        self.downloaded.append(task.local_id)
        content = task.remote["content"]
        assert content["video_url"].startswith("platform://artifact/")
        video_path = self._repo.resolve_asset(task.local_id, "output/video.mp4")
        video_path.write_bytes(self.platform.download_artifact("job-1"))
        return self._repo.update(
            task.local_id,
            lambda current: (
                setattr(current, "output_paths", {**current.output_paths, "video": "output/video.mp4"}),
                setattr(current, "download_status", "downloaded"),
            ),
        )

    def is_download_confirmed(self, task: SeedanceTask) -> bool:
        return task.download_status == "downloaded"


class FakeCacheManager:
    def status(self) -> dict[str, int]:
        return {"total_bytes": 0, "task_count": 0, "protected_task_count": 0, "clearable_bytes": 0}

    def clean(self, older_than_days: int) -> dict[str, int]:
        return {"files_removed": 0, "bytes_released": 0, "tasks_cleared": 0, "protected_tasks_skipped": 0}


class FakeArkClient:
    """Ark path must never be touched in platform tests."""

    audit = None

    def __getattr__(self, name):
        raise AssertionError(f"Ark client must not be used for platform tasks: {name}")


@pytest.fixture
def repository(tmp_path: Path) -> TaskRepository:
    return TaskRepository(tmp_path / "seedance-cache")


@pytest.fixture
def platform() -> FakePlatformVideo:
    return FakePlatformVideo()


@pytest.fixture
def platform_downloader(platform, repository) -> FakePlatformDownloader:
    downloader = FakePlatformDownloader(platform)
    downloader._repo = repository
    return downloader


@pytest.fixture
def manager(repository, platform, platform_downloader):
    return SeedanceTaskManager(
        FakeArkClient(),
        repository,
        platform_downloader,
        FakeCacheManager(),
        {"retention_days": 90, "last_cleanup_at": None},
        platform=platform,
        platform_downloader=platform_downloader,
    )


@pytest.fixture
def platform_request(tmp_path: Path) -> SeedanceRequest:
    image = tmp_path / "first.png"
    Image.new("RGB", (300, 300), "white").save(image)
    return SeedanceRequest(first_frame=image, prompt="a generated scene", source=PLATFORM_SOURCE)


def _succeeded_remote() -> dict[str, Any]:
    return {"id": "job-1", "status": "succeeded", "platform_status": "SUCCEEDED",
            "content": {"video_url": artifact_url("job-1")}, "quote": 100}


def test_create_uploads_inputs_and_posts_platform_job(manager, platform, platform_request):
    result = manager.create(platform_request)
    task = manager._repository.get(result["local_id"])

    assert task.source == PLATFORM_SOURCE
    assert task.remote_id == "job-1"
    assert task.remote_status == "queued"
    assert len(platform.uploaded) == 1  # draft-copied first frame, not the original
    payload = platform.created_payloads[0]
    assert payload["idemKey"].startswith("gam-") and len(payload["idemKey"]) <= 64
    assert payload["model"] == "doubao-seedance-2-0-260128"
    assert payload["content"] == [
        {"type": "text", "text": "a generated scene"},
        {"type": "image_url", "assetId": "asset-1", "role": "first_frame"},
    ]
    assert payload["duration"] == 5


def test_create_upload_failure_marks_task_failed(manager, platform, platform_request):
    platform.create_result = PlatformError(400, "INVALID_IMAGE_DIMENSIONS", "图片尺寸不合规")
    result = manager.create(platform_request)
    task = manager._repository.get(result["local_id"])
    assert task.remote_status == "failed"
    assert task.error["message"] == "图片尺寸不合规"


def test_create_unauthorized_raises_for_relogin(manager, platform, platform_request):
    platform.create_result = PlatformUnauthorizedError(401, "401", "未登录")
    with pytest.raises(PlatformUnauthorizedError):
        manager.create(platform_request)
    task = manager._repository.list()[0]
    assert task.remote_status == "failed"
    assert task.error["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda request: setattr(request, "return_last_frame", True),
        lambda request: setattr(request, "duration", -1),
        lambda request: setattr(request, "resolution", "4k"),
        lambda request: setattr(request, "ratio", "9:16"),
    ],
)
def test_create_rejects_unsupported_platform_params(manager, platform, platform_request, mutate):
    mutate(platform_request)
    result = manager.create(platform_request)
    task = manager._repository.get(result["local_id"])
    assert task.remote_status == "failed"
    assert platform.created_payloads == []


def test_sync_polls_platform_until_succeeded_and_downloads(manager, platform, platform_request):
    result = manager.create(platform_request)
    local_id = result["local_id"]
    platform.get_results = [
        {"id": "job-1", "status": "running", "platform_status": "RUNNING", "quote": 100},
        _succeeded_remote(),
    ]
    task, ok = manager._sync(local_id)
    assert ok and task.remote_status == "running"
    assert task.remote["platform_status"] == "RUNNING"

    task, ok = manager._sync(local_id)
    assert ok and task.remote_status == "succeeded"
    assert task.download_status == "downloaded"
    assert task.output_paths["video"] == "output/video.mp4"
    assert task.remote["quote"] == 100


def test_sync_submission_unknown_stays_running(manager, platform, platform_request):
    result = manager.create(platform_request)
    platform.get_results = [{"id": "job-1", "status": "running", "platform_status": "SUBMISSION_UNKNOWN", "quote": 100}]
    task, ok = manager._sync(result["local_id"])
    assert ok and task.remote_status == "running"
    assert task.error is None


def test_sync_platform_error_marks_sync_error_and_keeps_status(manager, platform, platform_request):
    result = manager.create(platform_request)
    platform.get_results = [PlatformError(500, "500", "平台暂时不可用")]
    task, ok = manager._sync(result["local_id"])
    assert not ok
    assert task.remote_status == "queued"
    assert task.sync_status["state"] == "error"


def test_cancel_queued_cancels_immediately(manager, platform, platform_request):
    result = manager.create(platform_request)
    platform.cancel_result = {"id": "job-1", "status": "cancelled", "platform_status": "CANCELLED"}
    cancelled = manager.cancel(result["local_id"])
    assert cancelled["remote_status"] == "cancelled"


def test_cancel_running_stays_cancelling_until_confirmed(manager, platform, platform_request):
    result = manager.create(platform_request)
    platform.cancel_result = {"id": "job-1", "status": "cancelling", "platform_status": "CANCEL_REQUESTED"}
    cancelling = manager.cancel(result["local_id"])
    assert cancelling["remote_status"] == "cancelling"

    platform.get_results = [{"id": "job-1", "status": "cancelled", "platform_status": "CANCELLED"}]
    task, _ = manager._sync(result["local_id"])
    assert task.remote_status == "cancelled"


def test_cancel_terminal_task_is_rejected(manager, platform, platform_request):
    result = manager.create(platform_request)
    manager._repository.update(result["local_id"], lambda current: setattr(current, "remote_status", "failed"))
    with pytest.raises(ValueError, match="无法取消"):
        manager.cancel(result["local_id"])


def test_continue_extracts_last_frame_and_creates_followup(manager, platform, platform_request, tmp_path):
    from platform_test_helpers import make_video_bytes

    result = manager.create(platform_request)
    local_id = result["local_id"]
    video_bytes = make_video_bytes(tmp_path / "clip.mp4")
    platform.download_bytes = video_bytes

    def mark_succeeded(current: SeedanceTask) -> None:
        current.remote_status = "succeeded"
        current.remote = {"content": {"video_url": artifact_url("job-1")}}

    manager._repository.update(local_id, mark_succeeded)
    manager._download_succeeded(manager._repository.get(local_id))

    continued = manager.continue_generation(local_id)
    followup = manager._repository.get(continued["local_id"])
    assert followup.retry_of == local_id
    assert followup.source == PLATFORM_SOURCE
    assert followup.remote_status == "queued"
    # Two uploads total: original create + continuation frame upload.
    assert len(platform.uploaded) == 2
    continuation_payload = platform.created_payloads[1]
    assert continuation_payload["content"][1]["role"] == "first_frame"


def test_continue_requires_downloaded_video(manager, platform, platform_request):
    result = manager.create(platform_request)
    with pytest.raises(ValueError, match="downloaded successful"):
        manager.continue_generation(result["local_id"])


def test_ensure_continuation_frame_is_stable(manager, platform, platform_request, tmp_path):
    from platform_test_helpers import make_video_bytes

    result = manager.create(platform_request)
    local_id = result["local_id"]
    platform.download_bytes = make_video_bytes(tmp_path / "clip.mp4")
    manager._repository.update(
        local_id,
        lambda current: setattr(current, "remote_status", "succeeded"),
    )
    manager._repository.update(
        local_id,
        lambda current: setattr(current, "remote", {"content": {"video_url": artifact_url("job-1")}}),
    )
    manager._download_succeeded(manager._repository.get(local_id))

    first = manager.ensure_continuation_frame(local_id)
    second = manager.ensure_continuation_frame(local_id)
    assert first == second and first.is_file()


def test_platform_sync_does_not_write_custom_key_audit(manager, platform, platform_request):
    class RecordingAudit:
        def __init__(self):
            self.events = []

        def record(self, *args, **kwargs):
            self.events.append((args, kwargs))

    audit = RecordingAudit()
    manager._audit = audit
    result = manager.create(platform_request)
    platform.get_results = [_succeeded_remote()]
    task, synced = manager._sync(result["local_id"])
    assert synced and task.download_status == "downloaded"
    assert audit.events == []
