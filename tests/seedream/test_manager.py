from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest
from PIL import Image

from backend.seedream.client import ArkAPIError, HttpResponse, SubmissionUnknownError
from backend.seedream.downloader import ImageDownloader
from backend.seedream.manager import SeedreamBatchManager
from backend.seedream.models import SeedreamRequest
from backend.seedream.repository import BatchRepository
from backend.seedream.validation import build_api_payload


class FakeTransport:
    def __init__(self, response: HttpResponse):
        self._response = response
        self.calls: list[tuple[str, str, dict[str, str], bytes | None, float]] = []

    def request(self, method, url, headers, body, timeout):
        self.calls.append((method, url, headers, body, timeout))
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class FakeDownloadTransport:
    def __init__(self, content: bytes = b""):
        self._content = content
        self.calls: list[str] = []

    def download(self, url: str) -> bytes:
        self.calls.append(url)
        return self._content


def _ok_response(usage=None) -> HttpResponse:
    body = {
        "created": int(time.time()),
        "data": [{"url": "https://ark.example.com/image.jpg", "image_type": "JPEG", "image_width": 1024, "image_height": 576}],
        "usage": usage or {"total_tokens": 42, "generated_images": 1},
    }
    return HttpResponse(200, {}, json.dumps(body).encode("utf-8"))


def _error_response(status: int, code="ERROR", message="failed") -> HttpResponse:
    body = {"error": {"code": code, "message": message}}
    return HttpResponse(status, {}, json.dumps(body).encode("utf-8"))


def _jpeg_bytes(path: Path) -> bytes:
    Image.new("RGB", (64, 64), "red").save(path, format="JPEG")
    return path.read_bytes()


def _wait_for_terminal(manager: SeedreamBatchManager, batch_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        batch = manager.get_batch(batch_id)
        if batch["attempts"][0]["status"] in ("succeeded", "failed", "unknown", "download_failed"):
            # Also wait for the worker thread's finally block to release the
            # active-attempt lock, so delete_batch doesn't race with cleanup.
            if not manager.has_active_batches():
                return batch
        time.sleep(0.01)
    return manager.get_batch(batch_id)


def _make_manager(tmp_path, transport, download_content=b""):
    from backend.seedream.client import ArkClient

    repository = BatchRepository(tmp_path / "cache")
    jpeg_path = tmp_path / "test.jpg"
    if download_content:
        jpeg_bytes = download_content
    else:
        jpeg_bytes = _jpeg_bytes(jpeg_path)
    downloader = ImageDownloader(repository, transport=FakeDownloadTransport(jpeg_bytes))
    client = ArkClient("test-key", transport=transport, timeout=1500.0)
    return SeedreamBatchManager(client, repository, downloader)


def test_manager_creates_batch_with_one_queued_attempt_before_remote_call(tmp_path):
    """Use a blocking transport so the batch stays pre-terminal while we verify persistence."""
    block = threading.Event()
    transport_called = threading.Event()

    class BlockingTransport:
        def __init__(self):
            self.calls = []

        def request(self, method, url, headers, body, timeout):
            self.calls.append((method, url, headers, body, timeout))
            transport_called.set()
            block.wait(timeout=30.0)
            return _ok_response()

    transport = BlockingTransport()
    manager = _make_manager(tmp_path, transport)

    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))

    # Batch returned immediately with queued status (before Ark call completes).
    assert batch["attempts"][0]["status"] == "queued"
    assert len(batch["attempts"]) == 1

    # Wait for the Ark call to start, then verify the batch is persisted and pre-terminal.
    assert transport_called.wait(timeout=5.0)
    repository = manager._repository
    persisted = repository.get(batch["local_id"])
    assert persisted.attempts[0].status in ("queued", "generating")

    # Release the block and wait for completion.
    block.set()
    _wait_for_terminal(manager, batch["local_id"])


def test_in_flight_attempt_keeps_original_client_after_update(tmp_path):
    """A credential swap must not change the key an already-running attempt uses."""
    from backend.seedream.client import ArkClient

    block = threading.Event()
    started = threading.Event()

    class BlockingTransport:
        def __init__(self):
            self.calls = []

        def request(self, method, url, headers, body, timeout):
            self.calls.append(headers)
            started.set()
            block.wait(timeout=30.0)
            return _ok_response()

    old_transport = BlockingTransport()
    manager = _make_manager(tmp_path, old_transport)

    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))
    assert started.wait(timeout=5.0)

    new_transport = FakeTransport(_ok_response())
    manager.update_client(ArkClient("new-key", transport=new_transport, timeout=1500.0))
    block.set()
    _wait_for_terminal(manager, batch["local_id"])

    # The attempt that started before the swap kept the original credentials.
    assert old_transport.calls[0]["Authorization"] == "Bearer test-key"

    second = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))
    _wait_for_terminal(manager, second["local_id"])
    assert new_transport.calls[0][2]["Authorization"] == "Bearer new-key"


def test_manager_success_persists_response_then_downloads_then_succeeds(tmp_path):
    transport = FakeTransport(_ok_response())
    manager = _make_manager(tmp_path, transport)

    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))
    result = _wait_for_terminal(manager, batch["local_id"])

    assert result["attempts"][0]["status"] == "succeeded"
    assert result["attempts"][0]["local_path"] == "images/0.jpg"
    assert result["attempts"][0]["finished_at"] is not None
    assert result["attempts"][0]["error"] is None

    # Full usage object is preserved.
    assert result["attempts"][0]["usage"] == {"total_tokens": 42, "generated_images": 1}
    assert result["attempts"][0]["total_tokens"] == 42

    # Response contains the URL and full Ark response.
    response = result["attempts"][0]["response"]
    assert response["data"][0]["url"] == "https://ark.example.com/image.jpg"

    # Image file was downloaded and validated.
    image_path = manager._repository.resolve_asset(batch["local_id"], "images/0.jpg")
    assert image_path.is_file()
    generation_layout = {
        "source_width": 64,
        "source_height": 64,
        "measured_top": 4,
        "measured_bottom": 52,
        "measured_height": 48,
        "target_height": 24,
        "character_height_ratio": 0.375,
        "bottom_distance": 8,
        "bottom_margin_ratio": 0.125,
        "scale": 0.5,
    }
    image_path.with_name(f"{image_path.name}.layout.json").write_text(
        json.dumps(generation_layout), encoding="utf-8"
    )
    assert manager.get_batch(batch["local_id"])["attempts"][0]["generation_layout"] == generation_layout

    # Request body sent to Ark was correct.
    method, url, headers, body, timeout = transport.calls[0]
    sent = json.loads(body)
    assert sent["model"] == "doubao-seedream-5-0-pro-260628"
    assert sent["response_format"] == "url"
    assert sent["watermark"] is False
    assert "sequential_image_generation" not in sent
    assert sent["size"] == "1K"
    assert sent["prompt"] == "图片比例 16:9，hero"
    assert headers["X-Ark-Max-Wait-Timeout-Ms"] == "300000"


def test_manager_persists_response_before_download(tmp_path):
    """The fake downloader verifies that the response is already on disk when download starts."""
    transport = FakeTransport(_ok_response(usage={"total_tokens": 7}))
    repository = BatchRepository(tmp_path / "cache")
    jpeg_bytes = _jpeg_bytes(tmp_path / "test.jpg")

    response_on_disk_when_downloading = {}

    class VerifyingDownloader(ImageDownloader):
        def download_image(self, batch_id: str, attempt_index: int, url: str) -> str:
            batch_dir = repository._existing_batch_dir(batch_id)
            with (batch_dir / "batch.json").open() as f:
                raw = json.load(f)
            attempt = raw["attempts"][0]
            response_on_disk_when_downloading["response"] = attempt.get("response")
            response_on_disk_when_downloading["status"] = attempt.get("status")
            return super().download_image(batch_id, attempt_index, url)

    from backend.seedream.client import ArkClient

    downloader = VerifyingDownloader(repository, transport=FakeDownloadTransport(jpeg_bytes))
    client = ArkClient("test-key", transport=transport, timeout=1500.0)
    manager = SeedreamBatchManager(client, repository, downloader)

    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))
    _wait_for_terminal(manager, batch["local_id"])

    # When the downloader ran, the response was already persisted and status was "downloading".
    assert response_on_disk_when_downloading["status"] == "downloading"
    assert response_on_disk_when_downloading["response"]["data"][0]["url"] == "https://ark.example.com/image.jpg"


def test_manager_429_marks_attempt_as_failed(tmp_path):
    transport = FakeTransport(_error_response(429, "RATE_LIMIT", "rate limited"))
    manager = _make_manager(tmp_path, transport)

    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))
    result = _wait_for_terminal(manager, batch["local_id"])

    assert result["attempts"][0]["status"] == "failed"
    assert result["attempts"][0]["error"]["code"] == "RATE_LIMIT"
    assert result["attempts"][0]["error"]["status"] == 429
    assert result["attempts"][0]["local_path"] is None


def test_manager_network_error_marks_attempt_as_unknown(tmp_path):
    transport = FakeTransport(OSError("connection refused"))
    manager = _make_manager(tmp_path, transport)

    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))
    result = _wait_for_terminal(manager, batch["local_id"])

    assert result["attempts"][0]["status"] == "unknown"
    assert result["attempts"][0]["error"]["code"] == "SUBMISSION_UNKNOWN"
    assert result["attempts"][0]["local_path"] is None


def test_manager_local_media_url_generated_on_success(tmp_path):
    transport = FakeTransport(_ok_response())
    manager = _make_manager(tmp_path, transport)

    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))
    result = _wait_for_terminal(manager, batch["local_id"])

    image_url = result["attempts"][0]["image_url"]
    assert image_url == f"/seedream-media/{batch['local_id']}/image/0"


def test_manager_total_tokens_missing_shown_as_none(tmp_path):
    transport = FakeTransport(_ok_response(usage={"generated_images": 1}))
    manager = _make_manager(tmp_path, transport)

    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))
    result = _wait_for_terminal(manager, batch["local_id"])

    assert result["attempts"][0]["total_tokens"] is None
    assert result["attempts"][0]["usage"] == {"generated_images": 1}


def test_manager_event_sink_dispatched_on_state_changes(tmp_path):
    transport = FakeTransport(_ok_response())
    manager = _make_manager(tmp_path, transport)

    events: list[tuple[str, dict]] = []
    event_ready = threading.Event()

    def sink(event_name, payload):
        events.append((event_name, payload))
        if payload.get("attempts", [{}])[0].get("status") in ("succeeded", "failed"):
            event_ready.set()

    manager.set_event_sink(sink)
    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))
    event_ready.wait(timeout=5.0)

    statuses = [e[1]["attempts"][0]["status"] for e in events]
    assert "generating" in statuses
    assert "downloading" in statuses
    assert "succeeded" in statuses


def test_manager_cannot_delete_batch_with_active_attempt(tmp_path):
    """Use a blocking transport to keep the attempt active while we try to delete."""
    block_event = threading.Event()
    entered = threading.Event()

    class BlockingTransport:
        def request(self, method, url, headers, body, timeout):
            entered.set()
            block_event.wait(timeout=30.0)
            return _ok_response()

    transport = BlockingTransport()
    manager = _make_manager(tmp_path, transport)

    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))

    # Wait until the attempt has entered the Ark call so it is reliably active.
    assert entered.wait(timeout=5.0)

    # Attempt is active (blocked in Ark call).
    with pytest.raises(ValueError, match="active"):
        manager.delete_batch(batch["local_id"])

    # Release the block and wait for completion.
    block_event.set()
    _wait_for_terminal(manager, batch["local_id"])

    # Now deletion should succeed.
    manager.delete_batch(batch["local_id"])


# ---------------------------------------------------------------------------
# Multi-attempt batch tests (Issue #4)
# ---------------------------------------------------------------------------


def _wait_for_batch_terminal(manager: SeedreamBatchManager, batch_id: str, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        batch = manager.get_batch(batch_id)
        if batch["status"] in ("completed", "partially_complete", "failed", "unknown"):
            # Wait for all worker threads to release the active-attempt lock.
            if not manager.has_active_batches():
                return batch
        time.sleep(0.01)
    return manager.get_batch(batch_id)


class _BarrierTransport:
    """Transport that blocks all calls at a barrier, proving concurrency."""

    def __init__(self, response: HttpResponse, count: int):
        self._response = response
        self._barrier = threading.Barrier(count)
        self.calls: list[tuple[str, str, dict[str, str], bytes | None, float]] = []
        self._lock = threading.Lock()
        self.entered_count = 0

    def request(self, method, url, headers, body, timeout):
        with self._lock:
            self.calls.append((method, url, headers, body, timeout))
            self.entered_count += 1
        # All threads must reach this barrier before any proceeds.
        self._barrier.wait(timeout=30.0)
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def test_concurrent_batch_all_requests_enter_before_any_releases(tmp_path):
    """With a barrier transport, all N requests enter the Ark call before any returns."""
    count = 4
    transport = _BarrierTransport(_ok_response(), count)
    manager = _make_manager(tmp_path, transport)

    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=count))
    result = _wait_for_batch_terminal(manager, batch["local_id"])

    assert result["status"] == "completed"
    assert len(result["attempts"]) == count
    assert transport.entered_count == count
    assert len(transport.calls) == count
    for attempt in result["attempts"]:
        assert attempt["status"] == "succeeded"


def test_concurrency_never_exceeds_four(tmp_path):
    """Even with count=4, concurrency never exceeds 4."""
    count = 4
    max_concurrent = 0
    current_concurrent = 0
    lock = threading.Lock()

    class TrackingTransport:
        def __init__(self):
            self.calls = []

        def request(self, method, url, headers, body, timeout):
            nonlocal max_concurrent, current_concurrent
            with lock:
                current_concurrent += 1
                max_concurrent = max(max_concurrent, current_concurrent)
            time.sleep(0.05)
            with lock:
                current_concurrent -= 1
            self.calls.append((method, url, headers, body, timeout))
            return _ok_response()

    transport = TrackingTransport()
    manager = _make_manager(tmp_path, transport)
    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=count))
    _wait_for_batch_terminal(manager, batch["local_id"])

    assert max_concurrent <= 4
    assert len(transport.calls) == 4


def test_batch_persists_all_attempt_placeholders_before_remote_call(tmp_path):
    """All N attempt placeholders are persisted before any paid request starts."""
    count = 3
    block = threading.Barrier(count + 1)  # +1 for the main thread

    class BlockingTransport:
        def __init__(self):
            self.calls = 0

        def request(self, method, url, headers, body, timeout):
            self.calls += 1
            block.wait(timeout=30.0)
            return _ok_response()

    transport = BlockingTransport()
    manager = _make_manager(tmp_path, transport)

    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=count))

    # Batch returned immediately with all N placeholders queued.
    assert len(batch["attempts"]) == count
    for attempt in batch["attempts"]:
        assert attempt["status"] == "queued"

    # Wait for all transport calls to start (all threads at barrier).
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if transport.calls >= count:
            break
        time.sleep(0.01)

    # All N attempts are persisted on disk before any remote call completes.
    repository = manager._repository
    persisted = repository.get(batch["local_id"])
    assert len(persisted.attempts) == count
    for attempt in persisted.attempts:
        assert attempt.status in ("queued", "generating")

    # Release the barrier so all calls complete.
    block.wait(timeout=30.0)
    _wait_for_batch_terminal(manager, batch["local_id"])


def test_batch_aggregation_all_succeeded(tmp_path):
    count = 2
    transport = FakeTransport(_ok_response())
    manager = _make_manager(tmp_path, transport)
    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=count))
    result = _wait_for_batch_terminal(manager, batch["local_id"])
    assert result["status"] == "completed"


def test_batch_aggregation_partially_complete(tmp_path):
    """One success + one failure = partially_complete."""
    call_count = 0
    lock = threading.Lock()

    class MixedTransport:
        def __init__(self):
            self.calls = []

        def request(self, method, url, headers, body, timeout):
            self.calls.append((method, url, headers, body, timeout))
            with lock:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return _ok_response()
            return _error_response(500, "INTERNAL", "server error")

    transport = MixedTransport()
    manager = _make_manager(tmp_path, transport)
    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=2))
    result = _wait_for_batch_terminal(manager, batch["local_id"])

    assert result["status"] == "partially_complete"
    statuses = sorted(a["status"] for a in result["attempts"])
    assert statuses == ["failed", "succeeded"]


def test_batch_aggregation_all_failed(tmp_path):
    transport = FakeTransport(_error_response(500, "INTERNAL", "server error"))
    manager = _make_manager(tmp_path, transport)
    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=2))
    result = _wait_for_batch_terminal(manager, batch["local_id"])

    assert result["status"] == "failed"
    for attempt in result["attempts"]:
        assert attempt["status"] == "failed"
        assert attempt["error"]["code"] == "INTERNAL"


def test_batch_aggregation_unknown_when_no_success_and_submission_unknown(tmp_path):
    """All unknown -> unknown."""
    transport = FakeTransport(OSError("connection refused"))
    manager = _make_manager(tmp_path, transport)
    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=2))
    result = _wait_for_batch_terminal(manager, batch["local_id"])

    assert result["status"] == "unknown"
    for attempt in result["attempts"]:
        assert attempt["status"] == "unknown"
        assert attempt["error"]["code"] == "SUBMISSION_UNKNOWN"


def test_batch_aggregation_partially_complete_with_unknown(tmp_path):
    """One success + one unknown -> partially_complete (has success)."""
    call_count = 0
    lock = threading.Lock()

    class MixedTransport:
        def __init__(self):
            self.calls = []

        def request(self, method, url, headers, body, timeout):
            self.calls.append((method, url, headers, body, timeout))
            with lock:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return _ok_response()
            raise OSError("connection refused")

    transport = MixedTransport()
    manager = _make_manager(tmp_path, transport)
    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=2))
    result = _wait_for_batch_terminal(manager, batch["local_id"])

    assert result["status"] == "partially_complete"
    statuses = sorted(a["status"] for a in result["attempts"])
    assert statuses == ["succeeded", "unknown"]


def test_batch_aggregation_one_image(tmp_path):
    """Single-image batch: all-succeeded -> completed."""
    transport = FakeTransport(_ok_response())
    manager = _make_manager(tmp_path, transport)
    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))
    result = _wait_for_batch_terminal(manager, batch["local_id"])
    assert result["status"] == "completed"
    assert len(result["attempts"]) == 1


def test_batch_per_attempt_independent_timing(tmp_path):
    """Each attempt records its own elapsed_seconds independently."""
    call_count = 0
    lock = threading.Lock()

    class StaggeredTransport:
        def __init__(self):
            self.calls = []

        def request(self, method, url, headers, body, timeout):
            self.calls.append((method, url, headers, body, timeout))
            with lock:
                nonlocal call_count
                call_count += 1
                idx = call_count
            if idx == 1:
                time.sleep(0.15)
            return _ok_response()

    transport = StaggeredTransport()
    manager = _make_manager(tmp_path, transport)
    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=2))
    result = _wait_for_batch_terminal(manager, batch["local_id"])

    elapsed = [a["elapsed_seconds"] for a in result["attempts"]]
    assert all(e >= 0 for e in elapsed)
    # Each attempt records its own finished_at timestamp.
    assert all(a["finished_at"] is not None for a in result["attempts"])
    # The staggered attempt should have noticeably more elapsed time.
    assert max(elapsed) >= min(elapsed)


def test_batch_cannot_delete_with_active_attempts(tmp_path):
    """Multi-attempt batch cannot be deleted while any attempt is active."""
    block = threading.Event()

    class BlockingTransport:
        def __init__(self):
            self.calls = 0

        def request(self, method, url, headers, body, timeout):
            self.calls += 1
            block.wait(timeout=30.0)
            return _ok_response()

    transport = BlockingTransport()
    manager = _make_manager(tmp_path, transport)
    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=3))

    # Wait for at least one attempt to start.
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if transport.calls > 0:
            break
        time.sleep(0.01)

    with pytest.raises(ValueError, match="active"):
        manager.delete_batch(batch["local_id"])

    block.set()
    _wait_for_batch_terminal(manager, batch["local_id"])
    manager.delete_batch(batch["local_id"])


def test_batch_public_status_included_in_public_batch(tmp_path):
    """public_batch includes the aggregated status field."""
    transport = FakeTransport(_ok_response())
    manager = _make_manager(tmp_path, transport)
    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))
    assert "status" in batch
    assert batch["status"] == "generating"
    result = _wait_for_batch_terminal(manager, batch["local_id"])
    assert result["status"] == "completed"


# ---------------------------------------------------------------------------
# Issue #5: Reliability - download_failed, retry_download, URL expiry
# ---------------------------------------------------------------------------


def test_manager_download_failure_marks_attempt_as_download_failed(tmp_path):
    """When download fails after response is persisted, status is download_failed, not failed."""
    transport = FakeTransport(_ok_response())
    repository = BatchRepository(tmp_path / "cache")

    class FailingDownloader(ImageDownloader):
        def download_image(self, batch_id, attempt_index, url):
            raise OSError("download network error")

    downloader = FailingDownloader(repository, transport=FakeDownloadTransport(b""))
    from backend.seedream.client import ArkClient

    client = ArkClient("test-key", transport=transport, timeout=1500.0)
    manager = SeedreamBatchManager(client, repository, downloader)

    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))
    result = _wait_for_terminal(manager, batch["local_id"])

    assert result["attempts"][0]["status"] == "download_failed"
    assert result["attempts"][0]["error"]["code"] == "OSError"
    # Response was persisted before the download attempt.
    assert result["attempts"][0]["response"]["data"][0]["url"] == "https://ark.example.com/image.jpg"
    assert result["attempts"][0]["local_path"] is None


def test_manager_download_failed_response_persisted_on_disk(tmp_path):
    """The response URL is on disk when download fails, enabling restart recovery."""
    transport = FakeTransport(_ok_response(usage={"total_tokens": 7}))
    repository = BatchRepository(tmp_path / "cache")

    class FailingDownloader(ImageDownloader):
        def download_image(self, batch_id, attempt_index, url):
            raise OSError("download failed")

    downloader = FailingDownloader(repository, transport=FakeDownloadTransport(b""))
    from backend.seedream.client import ArkClient

    client = ArkClient("test-key", transport=transport, timeout=1500.0)
    manager = SeedreamBatchManager(client, repository, downloader)

    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))
    _wait_for_terminal(manager, batch["local_id"])

    persisted = repository.get(batch["local_id"])
    assert persisted.attempts[0].status == "download_failed"
    assert persisted.attempts[0].response["data"][0]["url"] == "https://ark.example.com/image.jpg"


def test_manager_retry_download_fetches_original_url_without_calling_generate(tmp_path):
    """retry_download only fetches the original URL; it does NOT call generate_image."""
    transport = FakeTransport(_ok_response())
    repository = BatchRepository(tmp_path / "cache")
    jpeg_bytes = _jpeg_bytes(tmp_path / "test.jpg")

    download_transport = FakeDownloadTransport(jpeg_bytes)

    class FailingFirstDownloader(ImageDownloader):
        def __init__(self, repo, trans):
            super().__init__(repo, trans)
            self._first_call = True

        def download_image(self, batch_id, attempt_index, url):
            if self._first_call:
                self._first_call = False
                raise OSError("first download failed")
            return super().download_image(batch_id, attempt_index, url)

    downloader = FailingFirstDownloader(repository, download_transport)
    from backend.seedream.client import ArkClient

    client = ArkClient("test-key", transport=transport, timeout=1500.0)
    manager = SeedreamBatchManager(client, repository, downloader)

    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))
    result = _wait_for_terminal(manager, batch["local_id"])
    assert result["attempts"][0]["status"] == "download_failed"

    # Only one generate_image call so far.
    assert len(transport.calls) == 1

    # Retry download.
    retry_result = manager.retry_download(batch["local_id"], 0)
    assert retry_result["attempts"][0]["status"] == "succeeded"
    assert retry_result["attempts"][0]["local_path"] == "images/0.jpg"

    # No new generate_image call was made during retry_download.
    assert len(transport.calls) == 1

    # The download transport was called with the original Ark URL.
    assert "https://ark.example.com/image.jpg" in download_transport.calls


def test_manager_retry_download_rejects_non_download_failed_attempt(tmp_path):
    transport = FakeTransport(_ok_response())
    manager = _make_manager(tmp_path, transport)

    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))
    _wait_for_terminal(manager, batch["local_id"])

    with pytest.raises(ValueError, match="download_failed"):
        manager.retry_download(batch["local_id"], 0)


def test_manager_retry_download_rejects_expired_url(tmp_path):
    transport = FakeTransport(_ok_response())
    repository = BatchRepository(tmp_path / "cache")

    class FailingDownloader(ImageDownloader):
        def download_image(self, batch_id, attempt_index, url):
            raise OSError("download failed")

    downloader = FailingDownloader(repository, transport=FakeDownloadTransport(b""))
    from backend.seedream.client import ArkClient

    client = ArkClient("test-key", transport=transport, timeout=1500.0)

    # Use a response created 25 hours ago so the URL is expired at current time.
    from datetime import UTC, datetime, timedelta

    old_time = datetime.now(UTC) - timedelta(hours=25)
    old_timestamp = int(old_time.timestamp())

    class OldTimeTransport:
        def __init__(self):
            self.calls = []

        def request(self, method, url, headers, body, timeout):
            self.calls.append((method, url, headers, body, timeout))
            body_data = {
                "created": old_timestamp,
                "data": [{"url": "https://ark.example.com/image.jpg", "image_type": "JPEG", "image_width": 1024, "image_height": 576}],
                "usage": {"total_tokens": 42, "generated_images": 1},
            }
            return HttpResponse(200, {}, json.dumps(body_data).encode("utf-8"))

    old_transport = OldTimeTransport()
    manager = SeedreamBatchManager(
        ArkClient("test-key", transport=old_transport, timeout=1500.0),
        repository,
        downloader,
    )

    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))
    _wait_for_terminal(manager, batch["local_id"])
    assert manager.get_batch(batch["local_id"])["attempts"][0]["status"] == "download_failed"

    with pytest.raises(ValueError, match="URL_EXPIRED"):
        manager.retry_download(batch["local_id"], 0)


def test_manager_url_expired_flag_in_public_attempt(tmp_path):
    """download_failed attempts expose url_expired for the frontend."""
    repository = BatchRepository(tmp_path / "cache")

    class FailingDownloader(ImageDownloader):
        def download_image(self, batch_id, attempt_index, url):
            raise OSError("download failed")

    downloader = FailingDownloader(repository, transport=FakeDownloadTransport(b""))
    from backend.seedream.client import ArkClient

    from datetime import UTC, datetime, timedelta

    old_time = datetime.now(UTC) - timedelta(hours=25)
    old_timestamp = int(old_time.timestamp())

    class OldTimeTransport:
        def __init__(self):
            self.calls = []

        def request(self, method, url, headers, body, timeout):
            self.calls.append((method, url, headers, body, timeout))
            body_data = {
                "created": old_timestamp,
                "data": [{"url": "https://ark.example.com/image.jpg", "image_type": "JPEG", "image_width": 1024, "image_height": 576}],
                "usage": {"total_tokens": 42, "generated_images": 1},
            }
            return HttpResponse(200, {}, json.dumps(body_data).encode("utf-8"))

    transport = OldTimeTransport()
    manager = SeedreamBatchManager(
        ArkClient("test-key", transport=transport, timeout=1500.0),
        repository,
        downloader,
    )

    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))
    _wait_for_terminal(manager, batch["local_id"])

    result = manager.get_batch(batch["local_id"])
    assert result["attempts"][0]["status"] == "download_failed"
    assert result["attempts"][0]["url_expired"] is True


def test_manager_url_not_expired_in_public_attempt(tmp_path):
    """download_failed attempts show url_expired=False when URL is still valid."""
    transport = FakeTransport(_ok_response())
    repository = BatchRepository(tmp_path / "cache")

    class FailingDownloader(ImageDownloader):
        def download_image(self, batch_id, attempt_index, url):
            raise OSError("download failed")

    downloader = FailingDownloader(repository, transport=FakeDownloadTransport(b""))
    from backend.seedream.client import ArkClient

    client = ArkClient("test-key", transport=transport, timeout=1500.0)
    manager = SeedreamBatchManager(client, repository, downloader)

    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))
    _wait_for_terminal(manager, batch["local_id"])

    result = manager.get_batch(batch["local_id"])
    assert result["attempts"][0]["status"] == "download_failed"
    assert result["attempts"][0]["url_expired"] is False


def test_manager_restart_recovery_download_failed_can_retry(tmp_path):
    """After restart, a download_failed attempt can retry the original URL."""
    transport = FakeTransport(_ok_response())
    repository = BatchRepository(tmp_path / "cache")
    jpeg_bytes = _jpeg_bytes(tmp_path / "test.jpg")

    # First manager: download fails.
    class FailingDownloader(ImageDownloader):
        def download_image(self, batch_id, attempt_index, url):
            raise OSError("download failed")

    downloader1 = FailingDownloader(repository, transport=FakeDownloadTransport(b""))
    from backend.seedream.client import ArkClient

    client = ArkClient("test-key", transport=transport, timeout=1500.0)
    manager1 = SeedreamBatchManager(client, repository, downloader1)

    batch = manager1.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))
    _wait_for_terminal(manager1, batch["local_id"])

    # Simulate restart: new manager with same repository, working downloader.
    downloader2 = ImageDownloader(repository, transport=FakeDownloadTransport(jpeg_bytes))
    manager2 = SeedreamBatchManager(client, repository, downloader2)

    # The persisted attempt is download_failed.
    persisted = manager2.get_batch(batch["local_id"])
    assert persisted["attempts"][0]["status"] == "download_failed"

    # Retry download works with the original URL, no new generation call.
    assert len(transport.calls) == 1
    result = manager2.retry_download(batch["local_id"], 0)
    assert result["attempts"][0]["status"] == "succeeded"
    assert len(transport.calls) == 1  # No new generation


def test_manager_429_error_includes_request_id(tmp_path):
    """429 error saves Request ID in the attempt error metadata."""
    from backend.seedream.client import HttpResponse

    body = {"error": {"code": "RATE_LIMIT", "message": "rate limited", "request_id": "req-429-001"}}
    response = HttpResponse(429, {"X-Request-ID": "req-429-001"}, json.dumps(body).encode("utf-8"))
    transport = FakeTransport(response)
    manager = _make_manager(tmp_path, transport)

    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))
    result = _wait_for_terminal(manager, batch["local_id"])

    assert result["attempts"][0]["status"] == "failed"
    assert result["attempts"][0]["error"]["code"] == "RATE_LIMIT"
    assert result["attempts"][0]["error"]["status"] == 429
    assert result["attempts"][0]["error"]["request_id"] == "req-429-001"


def test_manager_429_without_request_id_has_no_request_id_field(tmp_path):
    """When the server does not provide a Request ID, it is not fabricated."""
    transport = FakeTransport(_error_response(429, "RATE_LIMIT", "rate limited"))
    manager = _make_manager(tmp_path, transport)

    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))
    result = _wait_for_terminal(manager, batch["local_id"])

    assert result["attempts"][0]["status"] == "failed"
    assert result["attempts"][0]["error"]["status"] == 429
    assert "request_id" not in result["attempts"][0]["error"]


# ---------------------------------------------------------------------------
# Issue #6: Protect application close and recover unknown results
# ---------------------------------------------------------------------------


def _persist_batch_with_statuses(
    repository: BatchRepository, statuses: list[str], *, response: dict | None = None
) -> str:
    """Create a persisted batch whose attempts start in the given statuses."""
    request = SeedreamRequest(
        prompt="hero", model="pro", resolution="1K", ratio="16:9", count=len(statuses)
    )
    batch = repository.create_batch(request)

    def apply_statuses(current) -> None:
        for index, status in enumerate(statuses):
            current.attempts[index].status = status
            if response is not None and status == "downloading":
                current.attempts[index].response = response

    repository.update(batch.local_id, apply_statuses)
    return batch.local_id


def test_manager_reclassify_marks_queued_and_generating_as_unknown(tmp_path):
    transport = FakeTransport(_ok_response())
    repository = BatchRepository(tmp_path / "cache")
    manager = _make_manager(tmp_path, transport)

    batch_id = _persist_batch_with_statuses(repository, ["queued", "generating"])

    result = manager.reclassify_interrupted_attempts()

    assert result == {"unknown": 2, "download_failed": 0}
    recovered = manager.get_batch(batch_id)
    assert [a["status"] for a in recovered["attempts"]] == ["unknown", "unknown"]
    for attempt in recovered["attempts"]:
        assert attempt["error"]["code"] == "SUBMISSION_UNKNOWN"
        assert attempt["finished_at"] is not None


def test_manager_reclassify_marks_downloading_as_download_failed(tmp_path):
    transport = FakeTransport(_ok_response())
    repository = BatchRepository(tmp_path / "cache")
    manager = _make_manager(tmp_path, transport)

    persisted_response = {
        "created": int(time.time()),
        "data": [{"url": "https://ark.example.com/image.jpg"}],
        "usage": {"total_tokens": 9},
    }
    batch_id = _persist_batch_with_statuses(
        repository, ["downloading"], response=persisted_response
    )

    result = manager.reclassify_interrupted_attempts()

    assert result == {"unknown": 0, "download_failed": 1}
    recovered = manager.get_batch(batch_id)
    attempt = recovered["attempts"][0]
    assert attempt["status"] == "download_failed"
    assert attempt["error"]["code"] == "DOWNLOAD_INTERRUPTED"
    # The persisted response is preserved so #5 download retry can reuse the URL.
    assert attempt["response"]["data"][0]["url"] == "https://ark.example.com/image.jpg"


def test_manager_reclassify_does_not_touch_terminal_statuses(tmp_path):
    transport = FakeTransport(_ok_response())
    repository = BatchRepository(tmp_path / "cache")
    manager = _make_manager(tmp_path, transport)

    batch_id = _persist_batch_with_statuses(
        repository, ["succeeded", "failed", "unknown", "download_failed"]
    )

    result = manager.reclassify_interrupted_attempts()

    assert result == {"unknown": 0, "download_failed": 0}
    recovered = manager.get_batch(batch_id)
    assert [a["status"] for a in recovered["attempts"]] == [
        "succeeded",
        "failed",
        "unknown",
        "download_failed",
    ]


def test_manager_reclassify_does_not_call_generate_image(tmp_path):
    transport = FakeTransport(_ok_response())
    repository = BatchRepository(tmp_path / "cache")
    manager = _make_manager(tmp_path, transport)

    _persist_batch_with_statuses(repository, ["queued", "generating", "downloading"])

    manager.reclassify_interrupted_attempts()

    # Recovery never submits a paid ImageGenerations request.
    assert transport.calls == []


def test_manager_reclassify_across_multiple_batches(tmp_path):
    transport = FakeTransport(_ok_response())
    repository = BatchRepository(tmp_path / "cache")
    manager = _make_manager(tmp_path, transport)

    batch_a = _persist_batch_with_statuses(repository, ["queued", "downloading"])
    batch_b = _persist_batch_with_statuses(repository, ["generating", "succeeded"])

    result = manager.reclassify_interrupted_attempts()

    assert result == {"unknown": 2, "download_failed": 1}
    recovered_a = manager.get_batch(batch_a)
    recovered_b = manager.get_batch(batch_b)
    assert [a["status"] for a in recovered_a["attempts"]] == ["unknown", "download_failed"]
    assert [a["status"] for a in recovered_b["attempts"]] == ["unknown", "succeeded"]


def test_manager_reclassified_downloading_can_retry_download_without_generation(tmp_path):
    """After reclassify, a recovered download_failed attempt retries the URL only."""
    transport = FakeTransport(_ok_response())
    repository = BatchRepository(tmp_path / "cache")
    jpeg_bytes = _jpeg_bytes(tmp_path / "test.jpg")

    # First manager: persist a downloading attempt (response on disk), then "crash".
    manager1 = _make_manager(tmp_path, transport)
    persisted_response = {
        "created": int(time.time()),
        "data": [{"url": "https://ark.example.com/image.jpg"}],
        "usage": {"total_tokens": 9},
    }
    batch_id = _persist_batch_with_statuses(
        repository, ["downloading"], response=persisted_response
    )

    # Restart: new manager with a working downloader reclassifies then retries.
    from backend.seedream.client import ArkClient

    downloader = ImageDownloader(repository, transport=FakeDownloadTransport(jpeg_bytes))
    manager2 = SeedreamBatchManager(
        ArkClient("test-key", transport=transport, timeout=1500.0),
        repository,
        downloader,
    )

    manager2.reclassify_interrupted_attempts()
    assert manager2.get_batch(batch_id)["attempts"][0]["status"] == "download_failed"

    assert len(transport.calls) == 0
    result = manager2.retry_download(batch_id, 0)
    assert result["attempts"][0]["status"] == "succeeded"
    # Still no ImageGenerations call: only the original URL was refetched.
    assert len(transport.calls) == 0


def test_manager_active_attempt_count_counts_non_terminal_attempts(tmp_path):
    transport = FakeTransport(_ok_response())
    repository = BatchRepository(tmp_path / "cache")
    manager = _make_manager(tmp_path, transport)

    _persist_batch_with_statuses(repository, ["queued", "generating", "downloading"])
    _persist_batch_with_statuses(repository, ["succeeded", "failed"])

    assert manager.active_attempt_count() == 3


def test_manager_active_attempt_count_zero_when_all_terminal(tmp_path):
    transport = FakeTransport(_ok_response())
    repository = BatchRepository(tmp_path / "cache")
    manager = _make_manager(tmp_path, transport)

    _persist_batch_with_statuses(repository, ["succeeded", "unknown", "download_failed"])

    assert manager.active_attempt_count() == 0


def test_manager_active_attempt_count_zero_when_empty(tmp_path):
    transport = FakeTransport(_ok_response())
    manager = _make_manager(tmp_path, transport)

    assert manager.active_attempt_count() == 0



# ---------------------------------------------------------------------------
# Issue #7: Regeneration draft, safe delete terminal validation, sequence
# ---------------------------------------------------------------------------


def test_manager_get_regeneration_draft_returns_original_request(tmp_path):
    """Regeneration draft restores prompt/model/resolution/ratio/count without paid calls."""
    transport = FakeTransport(_ok_response())
    manager = _make_manager(tmp_path, transport)
    request = SeedreamRequest(prompt="pixel art hero", model="pro", resolution="1K", ratio="16:9", count=3)
    batch = manager.create_batch(request)
    _wait_for_terminal(manager, batch["local_id"])

    draft = manager.get_regeneration_draft(batch["local_id"])

    assert draft["request"]["prompt"] == "pixel art hero"
    assert draft["request"]["model"] == "pro"
    assert draft["request"]["resolution"] == "1K"
    assert draft["request"]["ratio"] == "16:9"
    assert draft["request"]["count"] == 3


def test_manager_get_regeneration_draft_makes_no_paid_calls(tmp_path):
    """get_regeneration_draft must not call generate_image or create a new batch."""
    call_count = {"transport": 0}

    class CountingTransport:
        def request(self, method, url, headers, body, timeout):
            call_count["transport"] += 1
            return _ok_response()

    transport = CountingTransport()
    manager = _make_manager(tmp_path, transport)
    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))
    _wait_for_terminal(manager, batch["local_id"])
    paid_calls = call_count["transport"]

    manager.get_regeneration_draft(batch["local_id"])

    # No additional transport calls were made by the draft.
    assert call_count["transport"] == paid_calls


def test_manager_get_regeneration_draft_raises_for_missing_batch(tmp_path):
    transport = FakeTransport(_ok_response())
    manager = _make_manager(tmp_path, transport)

    with pytest.raises(FileNotFoundError):
        manager.get_regeneration_draft("nonexistent")


def test_manager_delete_batch_rejects_non_terminal_persisted_status(tmp_path):
    """Even without in-memory active tracking, non-terminal persisted attempts block deletion."""
    transport = FakeTransport(_ok_response())
    repository = BatchRepository(tmp_path / "cache")
    manager = _make_manager(tmp_path, transport)

    # Persist a batch with a non-terminal status but no active worker (simulates
    # pre-reclassify restart state).
    batch_id = _persist_batch_with_statuses(repository, ["generating"])

    with pytest.raises(ValueError, match="active"):
        manager.delete_batch(batch_id)


def test_manager_delete_batch_removes_batch_directory_and_cache(tmp_path):
    """Terminal batch deletion removes the entire batch directory including images."""
    transport = FakeTransport(_ok_response())
    manager = _make_manager(tmp_path, transport)
    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))
    result = _wait_for_terminal(manager, batch["local_id"])
    assert result["status"] == "completed"

    batch_dir = manager._repository._existing_batch_dir(batch["local_id"])
    assert batch_dir.is_dir()

    manager.delete_batch(batch["local_id"])

    assert not batch_dir.exists()
    with pytest.raises(FileNotFoundError):
        manager.get_batch(batch["local_id"])


def test_manager_list_batches_assigns_sequence_to_duplicate_params(tmp_path):
    """Batches with identical prompt+model+resolution+ratio+count get ①②③ by creation time."""
    transport = FakeTransport(_ok_response())
    manager = _make_manager(tmp_path, transport)

    # Three batches with identical parameters.
    b1 = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=2))
    _wait_for_terminal(manager, b1["local_id"])
    b2 = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=2))
    _wait_for_terminal(manager, b2["local_id"])
    b3 = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=2))
    _wait_for_terminal(manager, b3["local_id"])

    batches = manager.list_batches()
    sequences = {b["local_id"]: b["sequence"] for b in batches}

    # All three have sequence numbers, assigned by creation order.
    assert sequences[b1["local_id"]] == "①"
    assert sequences[b2["local_id"]] == "②"
    assert sequences[b3["local_id"]] == "③"


def test_manager_list_batches_does_not_sequence_different_params(tmp_path):
    """Batches with different parameters don't share a sequence."""
    transport = FakeTransport(_ok_response())
    manager = _make_manager(tmp_path, transport)

    b1 = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=2))
    _wait_for_terminal(manager, b1["local_id"])
    b2 = manager.create_batch(SeedreamRequest(prompt="villain", model="lite", resolution="2K", ratio="1:1", count=1))
    _wait_for_terminal(manager, b2["local_id"])

    batches = manager.list_batches()
    sequences = {b["local_id"]: b["sequence"] for b in batches}

    # Neither has a sequence because they have different parameters.
    assert sequences[b1["local_id"]] == ""
    assert sequences[b2["local_id"]] == ""


def test_manager_list_batches_sequences_only_matching_groups(tmp_path):
    """Mixed batches: only matching-param groups get sequenced."""
    transport = FakeTransport(_ok_response())
    manager = _make_manager(tmp_path, transport)

    # Two identical + one different.
    b1 = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=2))
    _wait_for_terminal(manager, b1["local_id"])
    b2 = manager.create_batch(SeedreamRequest(prompt="different", model="lite", resolution="2K", ratio="1:1", count=1))
    _wait_for_terminal(manager, b2["local_id"])
    b3 = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=2))
    _wait_for_terminal(manager, b3["local_id"])

    batches = manager.list_batches()
    sequences = {b["local_id"]: b["sequence"] for b in batches}

    assert sequences[b1["local_id"]] == "①"
    assert sequences[b3["local_id"]] == "②"
    assert sequences[b2["local_id"]] == ""


def test_manager_public_batch_includes_image_dimensions(tmp_path):
    """Successful attempts expose server-returned image_width and image_height."""
    transport = FakeTransport(_ok_response())
    manager = _make_manager(tmp_path, transport)
    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))
    result = _wait_for_terminal(manager, batch["local_id"])

    attempt = result["attempts"][0]
    assert attempt["image_width"] == 1024
    assert attempt["image_height"] == 576


def test_manager_public_batch_sequence_defaults_empty_for_single_batch(tmp_path):
    """get_batch (single) returns sequence="" since sequence is a board-level concept."""
    transport = FakeTransport(_ok_response())
    manager = _make_manager(tmp_path, transport)
    batch = manager.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))
    _wait_for_terminal(manager, batch["local_id"])

    single = manager.get_batch(batch["local_id"])
    assert single["sequence"] == ""


# ---------------------------------------------------------------------------
# Reference image (single-image reference generation)
# ---------------------------------------------------------------------------


def _reference_png(path: Path) -> Path:
    Image.new("RGB", (64, 64), "#3156d9").save(path, format="PNG")
    return path


def test_manager_sends_reference_image_data_url_in_payload(tmp_path):
    import base64

    source = _reference_png(tmp_path / "reference.png")
    transport = FakeTransport(_ok_response())
    manager = _make_manager(tmp_path, transport)

    batch = manager.create_batch(SeedreamRequest(prompt="keep the pose", count=1, reference_image=str(source)))
    result = _wait_for_terminal(manager, batch["local_id"])

    assert result["attempts"][0]["status"] == "succeeded"
    method, url, headers, body, timeout = transport.calls[0]
    payload = json.loads(body.decode("utf-8"))
    expected = "data:image/png;base64," + base64.b64encode(source.read_bytes()).decode("ascii")
    assert payload["image"] == [expected]


def test_manager_public_batch_exposes_reference_image_url(tmp_path):
    source = _reference_png(tmp_path / "reference.png")
    transport = FakeTransport(_ok_response())
    manager = _make_manager(tmp_path, transport)

    batch = manager.create_batch(SeedreamRequest(prompt="hero", count=1, reference_image=str(source)))
    _wait_for_terminal(manager, batch["local_id"])

    public = manager.get_batch(batch["local_id"])
    assert public["reference_image_url"] == f"/seedream-media/{batch['local_id']}/reference"

    plain_batch = manager.create_batch(SeedreamRequest(prompt="hero", count=1))
    _wait_for_terminal(manager, plain_batch["local_id"])
    plain = manager.get_batch(plain_batch["local_id"])
    assert plain["reference_image_url"] is None


def test_manager_regeneration_draft_restores_reference_image(tmp_path):
    source = _reference_png(tmp_path / "reference.png")
    transport = FakeTransport(_ok_response())
    manager = _make_manager(tmp_path, transport)

    batch = manager.create_batch(SeedreamRequest(prompt="hero", count=1, reference_image=str(source)))
    _wait_for_terminal(manager, batch["local_id"])

    draft = manager.get_regeneration_draft(batch["local_id"])
    restored = draft["request"]["reference_image"]
    assert isinstance(restored, str)
    assert Path(restored).read_bytes() == source.read_bytes()
    assert draft["reference_image_url"] == f"/seedream-media/{batch['local_id']}/reference"

    plain_batch = manager.create_batch(SeedreamRequest(prompt="plain", count=1))
    _wait_for_terminal(manager, plain_batch["local_id"])
    plain_draft = manager.get_regeneration_draft(plain_batch["local_id"])
    assert plain_draft["request"]["reference_image"] is None
    assert plain_draft["reference_image_url"] is None


def test_manager_reference_image_presence_distinguishes_batch_signatures(tmp_path):
    source = _reference_png(tmp_path / "reference.png")
    transport = FakeTransport(_ok_response())
    manager = _make_manager(tmp_path, transport)

    with_ref = manager.create_batch(
        SeedreamRequest(prompt="hero", count=1, resolution="1K", ratio="16:9", reference_image=str(source))
    )
    without_ref = manager.create_batch(SeedreamRequest(prompt="hero", count=1, resolution="1K", ratio="16:9"))
    _wait_for_terminal(manager, with_ref["local_id"])
    _wait_for_terminal(manager, without_ref["local_id"])

    listed = {item["local_id"]: item for item in manager.list_batches()}
    assert listed[with_ref["local_id"]]["sequence"] == ""
    assert listed[without_ref["local_id"]]["sequence"] == ""


def test_manager_delete_batch_removes_cached_reference_image(tmp_path):
    source = _reference_png(tmp_path / "reference.png")
    transport = FakeTransport(_ok_response())
    manager = _make_manager(tmp_path, transport)

    batch = manager.create_batch(SeedreamRequest(prompt="hero", count=1, reference_image=str(source)))
    _wait_for_terminal(manager, batch["local_id"])
    stored = manager._repository.get(batch["local_id"]).request["reference_image"]
    cached = manager._repository.resolve_asset(batch["local_id"], stored)
    assert cached.is_file()

    manager.delete_batch(batch["local_id"])

    assert not cached.exists()
