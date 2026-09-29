"""SeedreamBatchManager platform-source attempts (task 3.x verification)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from backend.platform.client import PlatformError, PlatformUnauthorizedError
from backend.seedream.manager import PLATFORM_SOURCE, SeedreamBatchManager
from backend.seedream.models import SeedreamRequest
from backend.seedream.repository import BatchRepository

# v1 契约（artifact-backup-service）：平台只下发新鲜上游直链，url 即上游地址本身
UPSTREAM_IMAGE = "https://upstream.example/i.png"
FUTURE_MS = int(time.time() * 1000) + 3_600_000


class FakePlatformImages:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []
        self.uploaded: list[Path] = []
        self.result: dict[str, Any] | Exception = {
            "jobId": "img-1",
            "platform_status": "SUCCEEDED",
            "quote": 30,
            "data": [{"url": UPSTREAM_IMAGE, "upstream_url": UPSTREAM_IMAGE,
                      "upstream_expires_at": FUTURE_MS}],
        }
        self.image_bytes = b""

    def upload_asset(self, path) -> dict[str, Any]:
        self.uploaded.append(Path(path))
        return {"assetId": "asset-1"}

    def generate_image(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.payloads.append(payload)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeDownloader:
    def __init__(self, platform: FakePlatformImages) -> None:
        self.platform = platform
        self.downloaded_urls: list[str] = []

    def download_image(self, batch_id: str, attempt_index: int, url: str) -> str:
        self.downloaded_urls.append(url)
        assert url == UPSTREAM_IMAGE, "v1：唯一下载来源是新鲜上游直链"
        relative = f"images/{attempt_index}.jpg"
        destination = self._repo.resolve_asset(batch_id, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.platform.image_bytes)
        return relative


class FakeArkClient:
    def __getattr__(self, name):
        raise AssertionError(f"Ark client must not be used for platform batches: {name}")


@pytest.fixture
def repository(tmp_path: Path) -> BatchRepository:
    return BatchRepository(tmp_path / "seedream-cache")


@pytest.fixture
def platform() -> FakePlatformImages:
    return FakePlatformImages()


@pytest.fixture
def manager(repository, platform):
    downloader = FakeDownloader(platform)
    downloader._repo = repository
    return SeedreamBatchManager(FakeArkClient(), repository, downloader, platform=platform)


@pytest.fixture
def png_bytes() -> bytes:
    import io

    buffer = io.BytesIO()
    Image.new("RGB", (300, 300), (10, 120, 40)).save(buffer, format="PNG")
    return buffer.getvalue()


def _wait_terminal(repository: BatchRepository, batch_id: str, timeout: float = 5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        batch = repository.get(batch_id)
        if all(attempt.status in {"succeeded", "failed", "unknown", "download_failed"} for attempt in batch.attempts):
            return batch
        time.sleep(0.02)
    raise AssertionError("attempts did not reach a terminal status in time")


def _platform_request(tmp_path: Path, **kwargs) -> SeedreamRequest:
    return SeedreamRequest(prompt="hero sprite", count=2, source=PLATFORM_SOURCE, **kwargs)


def test_platform_attempt_success_downloads_image(manager, repository, platform, png_bytes):
    platform.image_bytes = png_bytes
    batch = manager.create_batch(_platform_request(Path(".")))
    _wait_terminal(repository, batch["local_id"])

    persisted = repository.get(batch["local_id"])
    assert all(attempt.status == "succeeded" for attempt in persisted.attempts)
    assert len(platform.payloads) == 2  # one platform job per image
    for payload in platform.payloads:
        assert payload["idemKey"].startswith("gam-")
        assert payload["size"] == "1K"
        assert "图片比例 16:9" in payload["prompt"]
    assert all(attempt.local_path for attempt in persisted.attempts)


def test_platform_attempt_uploads_reference_image(manager, repository, platform, png_bytes, tmp_path):
    platform.image_bytes = png_bytes
    reference = tmp_path / "ref.png"
    reference.write_bytes(png_bytes)
    batch = manager.create_batch(_platform_request(tmp_path, reference_image=str(reference)))
    _wait_terminal(repository, batch["local_id"])

    # One upload per attempt: the reference image is re-uploaded for each image
    # in the batch (each platform job is independent).
    assert len(platform.uploaded) == 2
    assert platform.payloads[0]["image"] == "asset-1"


def test_platform_attempt_failed_sets_error(manager, repository, platform):
    platform.result = {"jobId": "img-2", "platform_status": "FAILED", "quote": 0,
                       "error": {"class": "RATE_LIMITED", "message": "触发限流"}}
    batch = manager.create_batch(_platform_request(Path(".")))
    _wait_terminal(repository, batch["local_id"])

    persisted = repository.get(batch["local_id"])
    assert all(attempt.status == "failed" for attempt in persisted.attempts)
    assert persisted.attempts[0].error["message"] == "触发限流"


def test_platform_attempt_submission_unknown_stays_unknown(manager, repository, platform):
    platform.result = {"jobId": "img-3", "platform_status": "SUBMISSION_UNKNOWN", "quote": 30,
                       "error": {"code": "SUBMISSION_UNKNOWN", "message": "上游未返回确定结果"}}
    batch = manager.create_batch(_platform_request(Path(".")))
    _wait_terminal(repository, batch["local_id"])

    persisted = repository.get(batch["local_id"])
    assert all(attempt.status == "unknown" for attempt in persisted.attempts)
    assert persisted.attempts[0].error["code"] == "SUBMISSION_UNKNOWN"


def test_platform_attempt_unauthorized_maps_code(manager, repository, platform):
    platform.result = PlatformUnauthorizedError(401, "401", "未登录")
    batch = manager.create_batch(_platform_request(Path(".")))
    _wait_terminal(repository, batch["local_id"])

    persisted = repository.get(batch["local_id"])
    assert all(attempt.status == "failed" for attempt in persisted.attempts)
    assert persisted.attempts[0].error["code"] == "UNAUTHORIZED"


def test_platform_attempt_business_error_surfaces_message(manager, repository, platform):
    platform.result = PlatformError(400, "400", "该参数组合暂未定价")
    batch = manager.create_batch(_platform_request(Path(".")))
    _wait_terminal(repository, batch["local_id"])

    persisted = repository.get(batch["local_id"])
    assert all(attempt.status == "failed" for attempt in persisted.attempts)
    assert persisted.attempts[0].error["message"] == "该参数组合暂未定价"


def test_platform_partial_failure_aggregates_partially_complete(manager, repository, platform, png_bytes):
    platform.image_bytes = png_bytes
    batch = manager.create_batch(_platform_request(Path(".")))
    _wait_terminal(repository, batch["local_id"])
    # Flip one attempt to failed as if one of two jobs errored upstream.
    persisted = repository.get(batch["local_id"])
    manager._update_attempt(
        batch["local_id"], 1,
        lambda a: (setattr(a, "status", "failed"), setattr(a, "error", {"code": "X", "message": "boom"})),
    )
    public = manager.get_batch(batch["local_id"])
    assert public["status"] == "partially_complete"
    assert persisted.attempts[0].status == "succeeded"


def test_download_failed_can_retry_upstream_url(manager, repository, platform, png_bytes):
    platform.image_bytes = png_bytes
    batch = manager.create_batch(_platform_request(Path(".")))
    _wait_terminal(repository, batch["local_id"])
    local_id = batch["local_id"]
    manager._update_attempt(
        local_id, 0,
        lambda a: (setattr(a, "status", "download_failed"), setattr(a, "error", {"code": "D", "message": "lost"})),
    )
    retried = manager.retry_download(local_id, 0)
    attempt = next(a for a in retried["attempts"] if a["index"] == 0)
    assert attempt["status"] == "succeeded"
    # 刚生成的任务：上游直链仍在 24h 新鲜期内，不算过期
    assert attempt["url_expired"] is False
