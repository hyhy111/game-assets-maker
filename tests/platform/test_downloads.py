"""Artifact transport routing and local last-frame extraction."""

from __future__ import annotations

import pytest
from platform_test_helpers import FakeTransport, make_video_bytes

from backend.platform.client import HttpResponse, PlatformClient
from backend.platform.downloads import PlatformArtifactTransport
from backend.platform.last_frame import extract_last_frame
from backend.platform.video import ARTIFACT_URL_PREFIX


class StubFallback:
    def __init__(self):
        self.urls: list[str] = []

    def download(self, url: str) -> bytes:
        self.urls.append(url)
        return b"fallback"


def make_transport(fake: FakeTransport) -> PlatformArtifactTransport:
    client = PlatformClient("http://platform.test", "token", transport=fake)
    return PlatformArtifactTransport(client, fallback=StubFallback())


def test_platform_scheme_resolves_via_platform_client():
    fake = FakeTransport(lambda m, u, h, b: HttpResponse(200, {}, b"artifact-bytes"))
    transport = make_transport(fake)
    content = transport.download(f"{ARTIFACT_URL_PREFIX}9001")
    assert content == b"artifact-bytes"
    method, url, _, _ = fake.last
    assert (method, url) == ("GET", "http://platform.test/app/artifact/9001/download")


def test_other_urls_fall_through_to_urllib_fallback():
    fake = FakeTransport()
    transport = make_transport(fake)
    fallback = transport._fallback
    content = fallback.download("https://example.test/video.mp4")
    assert content == b"fallback"
    assert fake.requests == []


def test_extract_last_frame_writes_png(tmp_path):
    video = tmp_path / "clip.mp4"
    make_video_bytes(video)
    output = tmp_path / "frame.png"
    extract_last_frame(video, output)
    assert output.is_file()
    from PIL import Image

    with Image.open(output) as image:
        assert image.size == (320, 320)
        assert image.format == "PNG"


def test_extract_last_frame_rejects_unreadable_video(tmp_path):
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"not a video")
    with pytest.raises(ValueError, match="not readable|no frames"):
        extract_last_frame(broken, tmp_path / "frame.png")
