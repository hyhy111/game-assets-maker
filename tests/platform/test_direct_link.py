"""Fresh upstream direct-link delivery (gen-artifact-direct-link client side).

The platform hands out the upstream URL only while it is fresh (24 h). The
client must prefer it (saves the server's egress bandwidth), fall back to the
platform ``platform://artifact/<jobId>`` pseudo-URL on any direct failure,
and never re-attempt a link it already consumed.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from PIL import Image

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

from platform_test_helpers import FakeTransport, ajax_ok, make_video_bytes, png_bytes

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


def test_candidates_prefer_direct_link_then_platform_url():
    platform_url = artifact_url("9001")
    fresh = {"upstream_url": UPSTREAM_VIDEO, "upstream_expires_at": FUTURE_MS}
    assert direct_link_candidates(fresh, platform_url) == [UPSTREAM_VIDEO, platform_url]
    expired = {"upstream_url": UPSTREAM_VIDEO, "upstream_expires_at": PAST_MS}
    assert direct_link_candidates(expired, platform_url) == [platform_url]
    assert direct_link_candidates({}, platform_url) == [platform_url]


# ---- mapping: platform responses carry the link into task remote (2.1 / 2.3) ----


def test_video_mapping_carries_fresh_direct_link_into_content():
    transport = FakeTransport(
        lambda m, u, h, b: describe(
            "SUCCEEDED",
            downloadUrl="/app/artifact/9001/download",
            upstreamUrl=UPSTREAM_VIDEO,
            upstreamExpiresAt=FUTURE_MS,
        )
    )
    mapped = make_video_client(transport).get_task("9001")
    assert mapped["content"]["video_url"] == artifact_url("9001")
    assert mapped["content"]["upstream_url"] == UPSTREAM_VIDEO
    assert mapped["content"]["upstream_expires_at"] == FUTURE_MS


def test_video_mapping_without_direct_link_has_no_upstream_keys():
    transport = FakeTransport(lambda m, u, h, b: describe("SUCCEEDED", downloadUrl="/app/artifact/9001/download"))
    mapped = make_video_client(transport).get_task("9001")
    assert mapped["content"]["video_url"] == artifact_url("9001")
    assert "upstream_url" not in mapped["content"]
    assert "upstream_expires_at" not in mapped["content"]


def test_image_mapping_carries_direct_link_into_first_data_entry():
    transport = FakeTransport(
        lambda m, u, h, b: ajax_ok(
            {
                "jobId": "42",
                "status": "SUCCEEDED",
                "quote": 30,
                "images": [
                    {
                        "url": "/app/artifact/42/download",
                        "upstreamUrl": "https://upstream.example/image.png",
                        "upstreamExpiresAt": FUTURE_MS,
                    }
                ],
                "error": None,
            }
        )
    )
    mapped = make_image_client(transport).generate_image({"idemKey": "gam-i"})
    assert mapped["data"][0]["url"] == artifact_url("42")
    assert mapped["data"][0]["upstream_url"] == "https://upstream.example/image.png"
    assert mapped["data"][0]["upstream_expires_at"] == FUTURE_MS


def test_image_mapping_without_direct_link_has_no_upstream_keys():
    transport = FakeTransport(
        lambda m, u, h, b: ajax_ok(
            {"jobId": "42", "status": "SUCCEEDED", "quote": 30,
             "images": [{"url": "/app/artifact/42/download"}], "error": None}
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


def test_download_falls_back_to_platform_url_when_direct_fails(repository, tmp_path):
    task = _succeeded_with_direct(repository, _draft(repository, tmp_path), expires_at=FUTURE_MS)
    video = make_video_bytes(tmp_path / "remote.mp4")
    transport = ScriptedTransport({UPSTREAM_VIDEO: OSError("upstream 403"), artifact_url("9001"): video})

    downloaded = ResultDownloader(repository, transport).download_task(task)

    assert downloaded.download_status == "downloaded"  # 回退成功不算下载失败
    assert transport.urls == [UPSTREAM_VIDEO, artifact_url("9001")]
    # 平台兜底成功后同样消耗直链：重下不再浪费上游下载额度
    assert "upstream_url" not in repository.get(task.local_id).remote["content"]


def test_expired_direct_link_is_skipped_without_touching_upstream(repository, tmp_path):
    task = _succeeded_with_direct(repository, _draft(repository, tmp_path), expires_at=PAST_MS)
    video = make_video_bytes(tmp_path / "remote.mp4")
    transport = ScriptedTransport({artifact_url("9001"): video})

    downloaded = ResultDownloader(repository, transport).download_task(task)

    assert downloaded.download_status == "downloaded"
    assert transport.urls == [artifact_url("9001")]


def test_redownload_after_cache_clear_uses_platform_url_only(repository, tmp_path):
    """2.4：已成功取回过的任务，重新下载（缓存被清理）一律走平台地址。"""
    task = _succeeded_with_direct(repository, _draft(repository, tmp_path), expires_at=FUTURE_MS)
    video = make_video_bytes(tmp_path / "remote.mp4")
    transport = ScriptedTransport({UPSTREAM_VIDEO: video, artifact_url("9001"): video})
    downloader = ResultDownloader(repository, transport)

    downloader.download_task(task)
    repository.update(task.local_id, lambda current: setattr(current, "download_status", "pending"))

    again = downloader.download_task(repository.get(task.local_id))

    assert again.download_status == "downloaded"
    assert transport.urls == [UPSTREAM_VIDEO, artifact_url("9001")]


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
    entry = {"url": artifact_url("img-1"), "upstream_url": "https://upstream.example/i.png",
             "upstream_expires_at": FUTURE_MS}
    batch, downloader = _run_platform_batch(tmp_path, entry, png_bytes)

    assert all(attempt.status == "succeeded" for attempt in batch.attempts)
    assert downloader.urls == ["https://upstream.example/i.png"]


def test_platform_image_download_falls_back_to_platform_url(tmp_path, png_bytes):
    direct = "https://upstream.example/i.png"
    entry = {"url": artifact_url("img-1"), "upstream_url": direct, "upstream_expires_at": FUTURE_MS}
    batch, downloader = _run_platform_batch(tmp_path, entry, png_bytes, failures={direct})

    assert all(attempt.status == "succeeded" for attempt in batch.attempts)
    assert downloader.urls == [direct, artifact_url("img-1")]
