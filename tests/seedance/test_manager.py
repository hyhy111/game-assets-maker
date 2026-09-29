from __future__ import annotations

import base64
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from backend.seedance.client import ArkAPIError, ArkResponseError, SubmissionUnknownError
from backend.seedance.models import SeedanceRequest, SeedanceTask
from backend.seedance.repository import TaskRepository


class FakeClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 7, 17, tzinfo=UTC)

    def now(self) -> datetime:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += timedelta(seconds=seconds)


class FakeClient:
    def __init__(self) -> None:
        self.create_results: list[dict[str, Any] | Exception | Callable[[dict[str, Any]], dict[str, Any]]] = []
        self.get_results: dict[str, list[dict[str, Any] | Exception]] = {}
        self.created_payloads: list[dict[str, Any]] = []
        self.deleted_ids: list[str] = []
        self.delete_error: Exception | None = None
        self.delete_callback: Callable[[str], None] | None = None

    def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.created_payloads.append(payload)
        result = self.create_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result(payload) if callable(result) else result

    def get_task(self, remote_id: str) -> dict[str, Any]:
        result = self.get_results[remote_id].pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def delete_task(self, remote_id: str) -> None:
        self.deleted_ids.append(remote_id)
        if self.delete_callback is not None:
            self.delete_callback(remote_id)
        if self.delete_error is not None:
            raise self.delete_error


class FakeDownloader:
    def __init__(self) -> None:
        self.downloaded_ids: list[str] = []

    def download_task(self, task: SeedanceTask) -> SeedanceTask:
        self.downloaded_ids.append(task.local_id)
        return task

    def is_download_confirmed(self, task: SeedanceTask) -> bool:
        return task.download_status == "downloaded"


class FakeCacheManager:
    def __init__(self) -> None:
        self.cleaned: list[int] = []

    def status(self) -> dict[str, int]:
        return {"total_bytes": 0, "task_count": 0, "protected_task_count": 0, "clearable_bytes": 0}

    def clean(self, older_than_days: int) -> dict[str, int]:
        self.cleaned.append(older_than_days)
        return {"files_removed": 0, "bytes_released": 0, "tasks_cleared": 0, "protected_tasks_skipped": 0}


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def repository(tmp_path: Path) -> TaskRepository:
    return TaskRepository(tmp_path / "seedance-cache")


@pytest.fixture
def seedance_request(tmp_path: Path) -> SeedanceRequest:
    image = tmp_path / "first.png"
    Image.new("RGB", (300, 300), "white").save(image)
    return SeedanceRequest(first_frame=image, prompt="a generated scene")


@pytest.fixture
def fake_client() -> FakeClient:
    return FakeClient()


@pytest.fixture
def downloader() -> FakeDownloader:
    return FakeDownloader()


@pytest.fixture
def cache_manager() -> FakeCacheManager:
    return FakeCacheManager()


@pytest.fixture
def manager(repository, fake_client, downloader, cache_manager, clock):
    from backend.seedance.manager import SeedanceTaskManager

    return SeedanceTaskManager(
        fake_client,
        repository,
        downloader,
        cache_manager,
        {"retention_days": 90, "last_cleanup_at": None},
        now=clock.now,
    )


def _remote(remote_id: str, status: str, **extra: Any) -> dict[str, Any]:
    return {"id": remote_id, "status": status, **extra}


def _queued_task(manager, fake_client, seedance_request):
    fake_client.create_results.append(_remote("remote-1", "queued"))
    result = manager.create(seedance_request)
    return manager._repository.get(result["local_id"])


def test_create_persists_draft_and_inputs_before_post(manager, fake_client, seedance_request):
    def inspect_draft(_: dict[str, Any]) -> dict[str, Any]:
        task = manager._repository.list()[0]
        assert task.remote_status == "submitting"
        assert manager._repository.resolve_asset(task.local_id, task.input_paths["first_frame"]).is_file()
        return _remote("remote-1", "queued")

    fake_client.create_results.append(inspect_draft)
    created = manager.create(seedance_request)

    assert created["remote_id"] == "remote-1"
    assert manager._repository.get(created["local_id"]).remote_status == "queued"


def test_create_sends_the_complete_provider_payload(manager, fake_client, seedance_request, tmp_path):
    last_frame = tmp_path / "last.png"
    Image.new("RGB", (300, 300), "blue").save(last_frame)
    seedance_request.last_frame = last_frame
    seedance_request.prompt = "  animate all fields  "
    seedance_request.model = "standard"
    seedance_request.resolution = "1080p"
    seedance_request.ratio = "16:9"
    seedance_request.duration = 15
    seedance_request.generate_audio = True
    seedance_request.return_last_frame = True
    seedance_request.priority = 9
    seedance_request.execution_expires_after = 3600
    fake_client.create_results.append(_remote("remote-complete", "queued"))

    manager.create(seedance_request)

    payload = fake_client.created_payloads[0]
    assert {key: payload[key] for key in payload if key != "content"} == {
        "model": "doubao-seedance-2-0-260128",
        "resolution": "1080p",
        "ratio": "16:9",
        "duration": 15,
        "generate_audio": True,
        "return_last_frame": True,
        "priority": 9,
        "execution_expires_after": 3600,
        "watermark": False,
    }
    assert payload["content"][0] == {"type": "text", "text": "animate all fields"}
    assert [item["role"] for item in payload["content"][1:]] == ["first_frame", "last_frame"]
    for item, expected in zip(payload["content"][1:], (seedance_request.first_frame, last_frame), strict=True):
        data_url = item["image_url"]["url"]
        assert data_url.startswith("data:image/png;base64,")
        assert base64.b64decode(data_url.partition(",")[2]) == expected.read_bytes()


def test_create_persists_remote_id_and_submission_unknown_without_reposting(manager, fake_client, seedance_request):
    fake_client.create_results.extend([_remote("remote-1", "queued"), SubmissionUnknownError("lost response")])

    successful = manager.create(seedance_request)
    unknown = manager.create(seedance_request)

    assert manager._repository.get(successful["local_id"]).remote_id == "remote-1"
    assert manager._repository.get(unknown["local_id"]).remote_status == "submission_unknown"
    assert len(fake_client.created_payloads) == 2


def test_create_records_invalid_success_response_as_submission_unknown(manager, fake_client, seedance_request):
    fake_client.create_results.append(ArkResponseError("Ark API success response is not valid JSON"))

    created = manager.create(seedance_request)

    assert created["remote_status"] == "submission_unknown"
    assert created["error"]["code"] == "SubmissionUnknownError"


def test_create_initial_succeeded_response_downloads_immediately(manager, fake_client, downloader, seedance_request):
    fake_client.create_results.append(
        _remote("remote-1", "succeeded", content={"video_url": "https://example.invalid/video.mp4"})
    )

    created = manager.create(seedance_request)

    assert downloader.downloaded_ids == [created["local_id"]]
    assert created["download_url_received_at"] == "2026-07-17T00:00:00Z"


def test_sync_maps_remote_transitions_elapsed_and_downloads_success(
    manager, fake_client, downloader, seedance_request, clock
):
    task = _queued_task(manager, fake_client, seedance_request)
    manager._repository.update(task.local_id, lambda current: setattr(current, "created_at", clock.now().isoformat()))
    fake_client.get_results["remote-1"] = [
        _remote("remote-1", "running", created_at="official-created", updated_at="official-running"),
        _remote(
            "remote-1",
            "succeeded",
            created_at="official-created",
            updated_at="official-done",
            content={"video_url": "https://example.invalid/video.mp4"},
            usage={"total_tokens": 23},
            output={"fps": 24, "resolution": "720p"},
        ),
    ]

    clock.advance(12)
    running = manager.sync_task(task.local_id)
    clock.advance(3)
    succeeded = manager.sync_task(task.local_id)
    stored = manager._repository.get(task.local_id)

    assert running["elapsed_seconds"] == 12
    assert succeeded["elapsed_seconds"] == 15
    assert stored.remote == {
        "created_at": "official-created",
        "updated_at": "official-done",
        "content": {"video_url": "https://example.invalid/video.mp4"},
        "usage": {"total_tokens": 23},
        "output": {"fps": 24, "resolution": "720p"},
    }
    assert stored.finished_at == clock.now().isoformat().replace("+00:00", "Z")
    assert stored.download_url_received_at == clock.now().isoformat().replace("+00:00", "Z")
    assert succeeded["download_url_received_at"] == stored.download_url_received_at
    assert downloader.downloaded_ids == [task.local_id]


def test_sync_keeps_the_first_download_url_received_time(manager, fake_client, seedance_request, clock):
    task = _queued_task(manager, fake_client, seedance_request)
    first_received_at = clock.now().isoformat().replace("+00:00", "Z")
    fake_client.get_results["remote-1"] = [
        _remote("remote-1", "running", content={"video_url": "https://example.invalid/first.mp4"}),
        _remote("remote-1", "succeeded", content={"video_url": "https://example.invalid/second.mp4"}),
    ]

    manager.sync_task(task.local_id)

    clock.advance(60)
    manager.sync_task(task.local_id)

    assert manager._repository.get(task.local_id).download_url_received_at == first_received_at


@pytest.mark.parametrize("status", ["failed", "cancelled", "expired"])
def test_sync_preserves_each_remote_terminal_status(manager, fake_client, seedance_request, status):
    task = _queued_task(manager, fake_client, seedance_request)
    fake_client.get_results["remote-1"] = [
        _remote("remote-1", status, error={"code": status.upper(), "message": f"remote {status}"})
    ]

    result = manager.sync_task(task.local_id)

    assert result["remote_status"] == status
    assert result["error"] == {"code": status.upper(), "message": f"remote {status}"}
    assert result["finished_at"] is not None


@pytest.mark.parametrize("status", [401, 403])
def test_sync_auth_error_keeps_remote_status_and_records_sync_error(manager, fake_client, seedance_request, status):
    task = _queued_task(manager, fake_client, seedance_request)
    fake_client.get_results["remote-1"] = [ArkAPIError(status, "AUTH", "bad key")]

    result = manager.sync_task(task.local_id)
    stored = manager._repository.get(task.local_id)

    assert result["remote_status"] == "queued"
    assert stored.finished_at is None
    assert stored.sync_status["error"] == {"code": "AUTH", "message": "bad key", "status": status}


def test_sync_invalid_success_response_records_retryable_sync_error(manager, fake_client, seedance_request):
    task = _queued_task(manager, fake_client, seedance_request)
    fake_client.get_results["remote-1"] = [ArkResponseError("Ark API success response must be a JSON object")]

    result = manager.sync_task(task.local_id)

    assert result["remote_status"] == "queued"
    assert result["sync_status"]["state"] == "error"
    assert result["sync_status"]["error"] == {
        "code": "ArkResponseError",
        "message": "Ark API success response must be a JSON object",
    }


def test_sync_404_is_retryable_until_task_is_seven_days_old(manager, fake_client, seedance_request, clock):
    task = _queued_task(manager, fake_client, seedance_request)
    fake_client.get_results["remote-1"] = [ArkAPIError(404, "NOT_FOUND", "gone"), ArkAPIError(404, "NOT_FOUND", "gone")]

    young = manager.sync_task(task.local_id)
    manager._repository.update(
        task.local_id,
        lambda current: setattr(current, "created_at", (clock.now() - timedelta(days=7)).isoformat()),
    )
    old = manager.sync_task(task.local_id)

    assert young["remote_status"] == "queued"
    assert old["remote_status"] == "expired"
    assert manager._repository.get(task.local_id).finished_at == clock.now().isoformat().replace("+00:00", "Z")


def test_failures_back_off_exponentially_and_cap_at_five_minutes(manager, fake_client, seedance_request):
    task = _queued_task(manager, fake_client, seedance_request)
    fake_client.get_results["remote-1"] = [OSError("offline")] * 7

    delays = [manager._sync_for_worker(task.local_id)[1] for _ in range(7)]

    assert delays == [10, 20, 40, 80, 160, 300, 300]


def test_start_recovers_active_tasks_and_runs_daily_cleanup_once(manager, fake_client, cache_manager, seedance_request):
    task = _queued_task(manager, fake_client, seedance_request)

    manager.start()
    try:
        assert manager._scheduled_at[task.local_id] <= manager._monotonic()
        assert cache_manager.cleaned == [90]
        manager.start()
        assert cache_manager.cleaned == [90]
    finally:
        manager.shutdown()


@pytest.mark.parametrize("download_status", ["pending", "downloading"])
def test_start_recovers_succeeded_tasks_whose_download_was_interrupted(
    manager, fake_client, downloader, seedance_request, download_status
):
    task = _queued_task(manager, fake_client, seedance_request)

    def mark_interrupted(current: SeedanceTask) -> None:
        current.remote_status = "succeeded"
        current.download_status = download_status
        current.remote = {"content": {"video_url": "https://example.invalid/video.mp4"}}

    manager._repository.update(task.local_id, mark_interrupted)

    manager._recover_tasks()
    manager._sync_for_worker(task.local_id)

    assert downloader.downloaded_ids == [task.local_id]
    assert manager._repository.get(task.local_id).download_status == "pending"


def test_start_does_not_automatically_repeat_an_explicitly_failed_download(
    manager, fake_client, downloader, seedance_request
):
    task = _queued_task(manager, fake_client, seedance_request)

    def mark_failed(current: SeedanceTask) -> None:
        current.remote_status = "succeeded"
        current.download_status = "failed"
        current.remote = {"content": {"video_url": "https://example.invalid/video.mp4"}}

    manager._repository.update(task.local_id, mark_failed)

    manager._recover_tasks()
    manager._sync_for_worker(task.local_id)

    assert downloader.downloaded_ids == []


def test_disabled_retention_never_calls_cache_clean_automatically_or_manually(manager, cache_manager):
    manager._config["retention_days"] = 0

    manager._run_due_cleanup()
    manual = manager.clean_cache(0)

    assert cache_manager.cleaned == []
    assert manual == {
        "files_removed": 0,
        "bytes_released": 0,
        "tasks_cleared": 0,
        "protected_tasks_skipped": 0,
    }
    assert manager._config["last_cleanup_at"] is not None


def test_start_marks_interrupted_submission_unknown_without_reposting(
    manager, fake_client, seedance_request
):
    draft = manager._repository.create_draft(seedance_request)

    manager.start()
    try:
        assert manager._repository.get(draft.local_id).remote_status == "submission_unknown"
        assert fake_client.created_payloads == []
    finally:
        manager.shutdown()


def test_shutdown_returns_promptly_when_worker_is_blocked_in_a_request(manager, fake_client, seedance_request):
    request_entered = threading.Event()
    release_request = threading.Event()

    def hanging_get(remote_id: str) -> dict[str, Any]:
        request_entered.set()
        # Simulate a stalled provider response; the HTTP client allows up to
        # 25 minutes, so shutdown must not wait for the worker indefinitely.
        release_request.wait()
        return _remote(remote_id, "queued")

    fake_client.create_results.append(_remote("remote-1", "queued"))
    fake_client.get_task = hanging_get
    task = _queued_task(manager, fake_client, seedance_request)

    manager.start()
    try:
        assert manager._scheduled_at[task.local_id] <= manager._monotonic()
        assert request_entered.wait(timeout=5)

        shutdown_finished = threading.Event()

        def run_shutdown() -> None:
            manager.shutdown()
            shutdown_finished.set()

        threading.Thread(target=run_shutdown, daemon=True).start()

        assert shutdown_finished.wait(timeout=5), "shutdown() blocked on an in-flight provider request"
    finally:
        release_request.set()
        manager.shutdown()


def test_failed_cleanup_does_not_advance_the_cleanup_timestamp(
    manager, cache_manager, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(cache_manager, "clean", lambda _: (_ for _ in ()).throw(OSError("disk unavailable")))

    with pytest.raises(OSError, match="disk unavailable"):
        manager._run_due_cleanup()

    assert manager._config["last_cleanup_at"] is None


def test_retry_generation_creates_new_task_with_retained_inputs(manager, fake_client, seedance_request):
    original = _queued_task(manager, fake_client, seedance_request)
    fake_client.create_results.append(_remote("remote-2", "queued"))

    retried = manager.retry_generation(original.local_id)
    stored = manager._repository.get(retried["local_id"])

    assert stored.local_id != original.local_id
    assert stored.retry_of == original.local_id
    assert stored.remote_id == "remote-2"


def test_continue_generation_uses_persisted_returned_frame_and_creates_new_lineage(
    manager, repository, fake_client, seedance_request
):
    original = _queued_task(manager, fake_client, seedance_request)
    returned_frame = repository.resolve_asset(original.local_id, "output/returned_last_frame.png")
    returned_frame.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (300, 300), "blue").save(returned_frame)

    def mark_returned(current):
        current.remote_status = "succeeded"
        current.download_status = "downloaded"
        current.output_paths["returned_last_frame"] = "output/returned_last_frame.png"

    repository.update(original.local_id, mark_returned)
    fake_client.create_results.append(_remote("continued-remote", "queued"))

    continued = manager.continue_generation(original.local_id)

    assert continued["retry_of"] == original.local_id
    persisted = repository.get(continued["local_id"])
    first_frame = repository.resolve_asset(continued["local_id"], persisted.input_paths["first_frame"])
    assert first_frame.read_bytes() == returned_frame.read_bytes()
    assert persisted.input_paths.get("last_frame") is None


@pytest.mark.parametrize("remote_status,download_status,cache_status", [
    ("failed", "downloaded", "complete"),
    ("succeeded", "pending", "complete"),
    ("succeeded", "downloaded", "cleared"),
])
def test_continue_generation_rejects_ineligible_or_cleared_tasks(
    manager, repository, fake_client, seedance_request, remote_status, download_status, cache_status
):
    original = _queued_task(manager, fake_client, seedance_request)
    repository.update(original.local_id, lambda current: (
        setattr(current, "remote_status", remote_status),
        setattr(current, "download_status", download_status),
        setattr(current, "cache_status", cache_status),
    ))

    with pytest.raises(ValueError):
        manager.continue_generation(original.local_id)
    assert len(fake_client.created_payloads) == 1


def test_retry_generation_persists_lineage_before_transport_unknown(manager, fake_client, seedance_request):
    original = _queued_task(manager, fake_client, seedance_request)

    def inspect_retry(_: dict[str, Any]) -> dict[str, Any]:
        retry = manager._repository.list()[0]
        assert retry.retry_of == original.local_id
        raise SubmissionUnknownError("lost response")

    fake_client.create_results.append(inspect_retry)
    retried = manager.retry_generation(original.local_id)

    stored = manager._repository.get(retried["local_id"])
    assert stored.retry_of == original.local_id
    assert stored.remote_status == "submission_unknown"


def test_retry_download_requires_succeeded_task_and_retained_url(manager, fake_client, downloader, seedance_request):
    task = _queued_task(manager, fake_client, seedance_request)
    manager._repository.update(
        task.local_id,
        lambda current: (
            setattr(current, "remote_status", "succeeded"),
            current.remote.update({"content": {"video_url": "https://example.invalid/video.mp4"}}),
        ),
    )

    result = manager.retry_download(task.local_id)

    assert result["local_id"] == task.local_id
    assert downloader.downloaded_ids == [task.local_id]


def test_wait_timeout_does_not_cancel_remote(manager, fake_client, seedance_request):
    queued_task = _queued_task(manager, fake_client, seedance_request)
    fake_client.get_results["remote-1"] = [_remote("remote-1", "queued")] * 5

    result = manager.wait(queued_task.local_id, timeout_seconds=0.01)

    assert result["timed_out"] is True
    assert fake_client.deleted_ids == []


def test_public_task_is_redacted_and_cancel_only_allows_queued(manager, fake_client, seedance_request):
    task = _queued_task(manager, fake_client, seedance_request)
    public = manager.get_task(task.local_id)

    assert "input_paths" not in public
    assert "output_paths" not in public
    assert "api_key" not in public
    manager.cancel(task.local_id)
    assert manager._repository.get(task.local_id).remote_status == "cancelled"
    with pytest.raises(ValueError, match="queued"):
        manager.cancel(task.local_id)


def test_cleanup_saves_complete_seedance_config_without_exposing_key(
    repository, fake_client, downloader, cache_manager, clock
):
    from backend.seedance.manager import SeedanceTaskManager

    config = {"api_key": "secret", "default_duration": 6, "retention_days": 7, "last_cleanup_at": None}
    saved: list[dict[str, Any]] = []
    manager = SeedanceTaskManager(
        fake_client, repository, downloader, cache_manager, config, now=clock.now, config_saver=saved.append
    )

    manager._run_due_cleanup()

    assert saved == [manager._config]
    assert saved[0]["api_key"] == "secret"
    assert saved[0]["default_duration"] == 6
    assert manager._config["last_cleanup_at"] is not None


def test_event_sink_mutation_and_blocking_do_not_change_task_or_stall_sync(
    manager, fake_client, seedance_request
):
    task = _queued_task(manager, fake_client, seedance_request)
    fake_client.get_results["remote-1"] = [_remote("remote-1", "running", usage={"total_tokens": 5})]
    entered = threading.Event()
    release = threading.Event()

    def sink(_: str, payload: dict[str, Any]) -> None:
        payload["remote"]["usage"]["total_tokens"] = 999
        entered.set()
        release.wait()

    manager.set_event_sink(sink)
    started = time.monotonic()
    manager.sync_task(task.local_id)
    elapsed = time.monotonic() - started

    assert entered.wait(0.5)
    assert elapsed < 0.1
    assert manager._repository.get(task.local_id).remote["usage"]["total_tokens"] == 5
    release.set()
    manager.shutdown()


def test_cancel_claim_prevents_sync_race_and_marks_terminal_after_delete(manager, fake_client, seedance_request):
    task = _queued_task(manager, fake_client, seedance_request)

    def sync_while_delete(_: str) -> None:
        assert manager.sync_task(task.local_id)["remote_status"] == "cancelling"

    fake_client.delete_callback = sync_while_delete
    cancelled = manager.cancel(task.local_id)

    assert cancelled["remote_status"] == "cancelled"
    assert fake_client.deleted_ids == ["remote-1"]


def test_cancel_success_wins_over_cross_process_sync_race(manager, fake_client, seedance_request):
    task = _queued_task(manager, fake_client, seedance_request)
    fake_client.get_results["remote-1"] = [_remote("remote-1", "running")]

    def cross_process_sync(_: str) -> None:
        with manager._scheduler_lock:
            manager._cancelling_inflight.discard(task.local_id)
        assert manager.sync_task(task.local_id)["remote_status"] == "running"

    fake_client.delete_callback = cross_process_sync
    cancelled = manager.cancel(task.local_id)

    assert cancelled["remote_status"] == "cancelled"
    assert manager._repository.get(task.local_id).remote_status == "cancelled"


def test_cancelling_task_recovers_by_sync_and_delete_error_restores_queued(manager, fake_client, seedance_request):
    task = _queued_task(manager, fake_client, seedance_request)
    manager._repository.update(task.local_id, lambda current: setattr(current, "remote_status", "cancelling"))
    fake_client.get_results["remote-1"] = [_remote("remote-1", "running")]

    recovered = manager.sync_task(task.local_id)
    assert recovered["remote_status"] == "running"

    manager._repository.update(task.local_id, lambda current: setattr(current, "remote_status", "queued"))
    fake_client.delete_error = OSError("delete failed")
    with pytest.raises(OSError, match="delete failed"):
        manager.cancel(task.local_id)

    assert manager._repository.get(task.local_id).remote_status == "queued"
