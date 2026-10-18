"""Upstream-only artifact delivery (artifact-backup-service client side).

v1 contract: the platform hands out ONLY the upstream URL, and only while it
is fresh (24 h). There is no platform copy to fall back to — an expired or
missing direct link means "no download source" (链接已过期). Direct API-key
mode is unaffected: its plain URL remains the sole candidate.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from PIL import Image
from platform_test_helpers import FakeTransport, ajax_ok, make_video_bytes

from backend.platform.client import PlatformClient
from backend.platform.downloads import direct_link_candidates, fresh_upstream_link
from backend.platform.images import PlatformImageClient
from backend.platform.video import PlatformVideoClient, artifact_url
from backend.seedance.downloader import ResultDownloader
from backend.seedance.models import SeedanceRequest, SeedanceTask
from backend.seedance.repository import TaskRepository
from backend.seedream.manager import PLATFORM_SOURCE, SeedreamBatchManager
from backend.seedream.models import SeedreamRequest
from backend.seedream.repository import BatchRepository

FUTURE_MS = int(time.time() * 1000) + 3_600_000
PAST_MS = int(time.time() * 1000) - 60_000
UPSTREAM_VIDEO = "https://upstream.example/video.mp4"


def make_video_client(transport: FakeTransport) -> PlatformVideoClient:
    return PlatformVideoClient(PlatformClient("http://platform.test", "token", transport=transport))


def make_image_client(transport: FakeTransport) -> PlatformImageClient:
    return PlatformImageClient(PlatformClient("http://platform.test", "token", transport=transport))


def describe(status: str, **extra):
    payload = {"jobId": "9001", "jobType": "video", "status": status, "remoteStatus": "queued", "quote": 100,
               "error": None, "createdAt": "2026-09-27T00:00:00Z"}
    payload.update(extra)
    return ajax_ok(payload)


# ---- freshness judgement (downloads.py, the only client-side judge) ----


def test_fresh_upstream_link_within_validity():
    entry = {"upstream_url": UPSTREAM_VIDEO, "upstream_expires_at": FUTURE_MS}
    assert fresh_upstream_link(entry) == UPSTREAM_VIDEO


def test_expired_incomplete_or_blank_links_are_refused():
    assert fresh_upstream_link({"upstream_url": UPSTREAM_VIDEO, "upstream_expires_at": PAST_MS}) is None
    assert fresh_upstream_link({"upstream_url": UPSTREAM_VIDEO}) is None
    assert fresh_upstream_link({"upstream_expires_at": FUTURE_MS}) is None
    assert fresh_upstream_link({"upstream_url": "", "upstream_expires_at": FUTURE_MS}) is None


def test_iso8601_expiry_string_is_accepted():
    entry = {"upstream_url": UPSTREAM_VIDEO, "upstream_expires_at": "2099-01-01T00:00:00Z"}
    assert fresh_upstream_link(entry) == UPSTREAM_VIDEO


def test_candidates_upstream_only_no_platform_fallback():
    """v1：平台无副本——过期/缺失即无下载来源；直连(api-key)模式不受影响。"""
    platform_url = artifact_url("9001")
    fresh = {"upstream_url": UPSTREAM_VIDEO, "upstream_expires_at": FUTURE_MS}
    assert direct_link_candidates(fresh, platform_url) == [UPSTREAM_VIDEO]
    expired = {"upstream_url": UPSTREAM_VIDEO, "upstream_expires_at": PAST_MS}
    assert direct_link_candidates(expired, platform_url) == []
    assert direct_link_candidates({}, platform_url) == []
    # 非平台 fallback（直连模式的真实 URL）仍是唯一候选
    assert direct_link_candidates({}, UPSTREAM_VIDEO) == [UPSTREAM_VIDEO]
    # 图片入口：url 本身就是上游地址，去重后仍只有一个候选
    image_entry = {"url": UPSTREAM_VIDEO, "upstream_url": UPSTREAM_VIDEO, "upstream_expires_at": FUTURE_MS}
    assert direct_link_candidates(image_entry, UPSTREAM_VIDEO) == [UPSTREAM_VIDEO]


# ---- mapping: platform responses carry the link into task remote (2.1 / 2.3) ----


def test_video_mapping_carries_fresh_direct_link_into_content():
    transport = FakeTransport(
        lambda m, u, h, b: describe(
            "SUCCEEDED",
            upstreamUrl=UPSTREAM_VIDEO,
            upstreamExpiresAt=FUTURE_MS,
        )
    )
    mapped = make_video_client(transport).get_task("9001")
    # v1：直链就是唯一交付载体（video_url 直接是上游地址）
    assert mapped["content"]["video_url"] == UPSTREAM_VIDEO
    assert mapped["content"]["upstream_url"] == UPSTREAM_VIDEO
    assert mapped["content"]["upstream_expires_at"] == FUTURE_MS


def test_video_mapping_without_direct_link_keeps_pseudo_placeholder():
    transport = FakeTransport(lambda m, u, h, b: describe("SUCCEEDED"))
    mapped = make_video_client(transport).get_task("9001")
    # 无直链：video_url 退化为伪地址占位标识（下载候选为空 → 链接已过期）
    assert mapped["content"]["video_url"] == artifact_url("9001")
    assert "upstream_url" not in mapped["content"]
    assert "upstream_expires_at" not in mapped["content"]


def test_image_mapping_delivers_upstream_url_as_the_url():
    transport = FakeTransport(
        lambda m, u, h, b: ajax_ok(
            {
                "jobId": "42",
                "status": "SUCCEEDED",
                "quote": 30,
                "images": [
                    {
                        "url": "https://upstream.example/image.png",
                        "upstreamUrl": "https://upstream.example/image.png",
                        "upstreamExpiresAt": FUTURE_MS,
                    }
                ],
                "error": None,
            }
        )
    )
    mapped = make_image_client(transport).generate_image({"idemKey": "gam-i"})
    # v1：url 即上游地址本身（唯一交付载体），不再是平台伪地址
    assert mapped["data"][0]["url"] == "https://upstream.example/image.png"
    assert mapped["data"][0]["upstream_url"] == "https://upstream.example/image.png"
    assert mapped["data"][0]["upstream_expires_at"] == FUTURE_MS


def test_image_mapping_without_direct_link_has_no_upstream_keys():
    transport = FakeTransport(
        lambda m, u, h, b: ajax_ok(
            {"jobId": "42", "status": "SUCCEEDED", "quote": 30,
             "images": [{"url": "https://upstream.example/image.png"}], "error": None}
        )
    )
    mapped = make_image_client(transport).generate_image({"idemKey": "gam-i"})
    assert "upstream_url" not in mapped["data"][0]
    assert "upstream_expires_at" not in mapped["data"][0]


# ---- video downloader: prefer direct, fall back, consume (2.2 / 2.4) ----


class ScriptedTransport:
    def __init__(self, responses: dict[str, bytes | BaseException]):
        self.responses = responses
        self.urls: list[str] = []

    def download(self, url: str) -> bytes:
        self.urls.append(url)
        response = self.responses[url]
        if isinstance(response, BaseException):
            raise response
        return response


@pytest.fixture
def repository(tmp_path: Path) -> TaskRepository:
    return TaskRepository(tmp_path / "seedance-cache")


def _draft(repository: TaskRepository, tmp_path: Path) -> SeedanceTask:
    first = tmp_path / "first.png"
    Image.new("RGB", (8, 8), "white").save(first)
    return repository.create_draft(SeedanceRequest(first_frame=first, prompt="keep me"))


def _succeeded_with_direct(repository: TaskRepository, task: SeedanceTask, *, expires_at: int) -> SeedanceTask:
    def mark(current: SeedanceTask) -> None:
        current.remote_status = "succeeded"
        current.remote = {
            "content": {
                "video_url": artifact_url("9001"),
                "upstream_url": UPSTREAM_VIDEO,
                "upstream_expires_at": expires_at,
            }
        }
        current.finished_at = "2026-09-27T00:00:00Z"

    return repository.update(task.local_id, mark)


def test_download_uses_fresh_direct_link_and_consumes_it(repository, tmp_path):
    task = _succeeded_with_direct(repository, _draft(repository, tmp_path), expires_at=FUTURE_MS)
    video = make_video_bytes(tmp_path / "remote.mp4")
    transport = ScriptedTransport({UPSTREAM_VIDEO: video})
    downloader = ResultDownloader(repository, transport)

    downloaded = downloader.download_task(task)

    assert downloaded.download_status == "downloaded"
    assert transport.urls == [UPSTREAM_VIDEO]
    # 直链一次性：取回成功后从持久化 remote 抹掉
    assert "upstream_url" not in repository.get(task.local_id).remote["content"]
    assert "upstream_expires_at" not in repository.get(task.local_id).remote["content"]


def test_download_direct_failure_marks_failed_no_platform_fallback(repository, tmp_path):
    """v1：直链失败即下载失败——平台副本回退已不存在。"""
    task = _succeeded_with_direct(repository, _draft(repository, tmp_path), expires_at=FUTURE_MS)
    transport = ScriptedTransport({UPSTREAM_VIDEO: OSError("upstream 403")})

    with pytest.raises(OSError):
        ResultDownloader(repository, transport).download_task(task)

    assert repository.get(task.local_id).download_status == "failed"
    assert transport.urls == [UPSTREAM_VIDEO]
    # 失败不得消耗直链（远端记录保持原样，重试仍可用——若仍新鲜）
    assert repository.get(task.local_id).remote["content"]["upstream_url"] == UPSTREAM_VIDEO


def test_expired_direct_link_has_no_download_source(repository, tmp_path):
    """v1：过期即"链接已过期"，不触碰任何 URL。"""
    task = _succeeded_with_direct(repository, _draft(repository, tmp_path), expires_at=PAST_MS)
    transport = ScriptedTransport({})

    with pytest.raises(ValueError, match="URL_EXPIRED"):
        ResultDownloader(repository, transport).download_task(task)

    assert repository.get(task.local_id).download_status == "failed"
    assert transport.urls == []


def test_redownload_after_cache_clear_reports_expired(repository, tmp_path):
    """v1：已成功取回过的任务，重下时直链已被消费 → 明确报链接已过期。"""
    task = _succeeded_with_direct(repository, _draft(repository, tmp_path), expires_at=FUTURE_MS)
    video = make_video_bytes(tmp_path / "remote.mp4")
    transport = ScriptedTransport({UPSTREAM_VIDEO: video})
    downloader = ResultDownloader(repository, transport)

    downloader.download_task(task)
    repository.update(task.local_id, lambda current: setattr(current, "download_status", "pending"))

    with pytest.raises(ValueError, match="URL_EXPIRED"):
        downloader.download_task(repository.get(task.local_id))

    assert transport.urls == [UPSTREAM_VIDEO]


# ---- seedream manager: direct link preferred, fallback without failure (2.3) ----


class _PlatformImages:
    def __init__(self, data_entry: dict) -> None:
        self.data_entry = data_entry

    def upload_asset(self, path) -> dict:
        return {"assetId": "asset-1"}

    def generate_image(self, payload: dict) -> dict:
        return {"jobId": "img-1", "platform_status": "SUCCEEDED", "quote": 30, "data": [self.data_entry]}


class _RecordingDownloader:
    def __init__(self, repository: BatchRepository, image_bytes: bytes, failures: set[str] | None = None):
        self._repository = repository
        self._image_bytes = image_bytes
        self._failures = failures or set()
        self.urls: list[str] = []

    def download_image(self, batch_id: str, attempt_index: int, url: str) -> str:
        self.urls.append(url)
        if url in self._failures:
            raise OSError("direct link failed")
        relative = f"images/{attempt_index}.jpg"
        destination = self._repository.resolve_asset(batch_id, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self._image_bytes)
        return relative


class _NoArkClient:
    audit = None

    def __getattr__(self, name):
        raise AssertionError(f"Ark client must not be used for platform batches: {name}")


def _wait_terminal(repository: BatchRepository, batch_id: str, timeout: float = 5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        batch = repository.get(batch_id)
        if all(attempt.status in {"succeeded", "failed", "unknown", "download_failed"} for attempt in batch.attempts):
            return batch
        time.sleep(0.02)
    raise AssertionError("attempts did not reach a terminal status in time")


def _run_platform_batch(tmp_path: Path, data_entry: dict, image_bytes: bytes, failures: set[str] | None = None):
    repository = BatchRepository(tmp_path / "seedream-cache")
    platform = _PlatformImages(data_entry)
    downloader = _RecordingDownloader(repository, image_bytes, failures)
    manager = SeedreamBatchManager(_NoArkClient(), repository, downloader, platform=platform)
    batch = manager.create_batch(SeedreamRequest(prompt="hero sprite", count=1, source=PLATFORM_SOURCE))
    _wait_terminal(repository, batch["local_id"])
    return repository.get(batch["local_id"]), downloader


def test_platform_image_download_prefers_fresh_direct_link(tmp_path, png_bytes):
    entry = {"url": "https://upstream.example/i.png", "upstream_url": "https://upstream.example/i.png",
             "upstream_expires_at": FUTURE_MS}
    batch, downloader = _run_platform_batch(tmp_path, entry, png_bytes)

    assert all(attempt.status == "succeeded" for attempt in batch.attempts)
    assert downloader.urls == ["https://upstream.example/i.png"]


def test_platform_image_download_direct_failure_is_download_failed(tmp_path, png_bytes):
    """v1：直链失败即 download_failed（无平台副本回退）。"""
    direct = "https://upstream.example/i.png"
    entry = {"url": direct, "upstream_url": direct, "upstream_expires_at": FUTURE_MS}
    batch, downloader = _run_platform_batch(tmp_path, entry, png_bytes, failures={direct})

    assert all(attempt.status == "download_failed" for attempt in batch.attempts)
    assert downloader.urls == [direct]
