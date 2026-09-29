"""Restricted project-media mapping on the local assets server.

Covers the storage-location-management change: when the project root lives
outside the data root, project frames and audio are served through an
explicit, allowlisted ``/project-media/`` mapping that is resolved against
the configured project root and re-validated server-side. Traversal and
symlink escapes are refused.
"""

import threading
from pathlib import Path
from queue import Queue
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from backend.main import start_assets_server


@pytest.fixture
def media_server(tmp_path: Path):
    """Run the assets server with an external project media root."""
    data_root = tmp_path / "data-root"
    data_root.mkdir()
    project_root = tmp_path / "external-projects"
    frame = project_root / "mage" / "walk" / "output" / "01_frames" / "frame_000001.png"
    frame.parent.mkdir(parents=True)
    frame.write_bytes(b"png-bytes")

    stop_event = threading.Event()
    startup_queue = Queue()
    thread = threading.Thread(
        target=start_assets_server,
        args=(str(data_root), 0, stop_event, None, None, startup_queue),
        kwargs={"project_media_root": project_root},
        daemon=True,
    )
    thread.start()
    port = startup_queue.get(timeout=1)
    assert isinstance(port, int) and port > 0
    yield port, data_root, project_root
    stop_event.set()


def _status(port: int, path: str) -> int:
    try:
        with urlopen(f"http://127.0.0.1:{port}{path}", timeout=1) as response:
            return response.status
    except HTTPError as error:
        return error.code


def test_serves_legitimate_resource_from_external_project_root(media_server):
    port, _, _ = media_server

    with urlopen(f"http://127.0.0.1:{port}/project-media/mage/walk/output/01_frames/frame_000001.png") as response:
        assert response.read() == b"png-bytes"
        assert response.headers["Content-Type"] == "image/png"


def test_rejects_dotdot_segments_raw_and_encoded(media_server):
    port, _, project_root = media_server
    secret = project_root.parent / "secret.txt"
    secret.write_text("secret")

    assert _status(port, "/project-media/../../secret.txt") == 404
    assert _status(port, "/project-media/%2e%2e/%2e%2e/secret.txt") == 404
    assert _status(port, "/project-media/mage/../../../secret.txt") == 404


def test_rejects_symlink_escaping_the_project_media_root(media_server, tmp_path: Path):
    port, _, project_root = media_server
    outside = tmp_path / "outside.txt"
    outside.write_text("outside")
    link = project_root / "mage" / "walk" / "escape.txt"
    link.symlink_to(outside)

    assert _status(port, "/project-media/mage/walk/escape.txt") == 404


def test_rejects_missing_and_directory_paths(media_server):
    port, _, project_root = media_server

    assert _status(port, "/project-media/mage/walk/output/01_frames/missing.png") == 404
    assert _status(port, "/project-media/mage/walk") == 404


def test_project_media_requires_a_configured_root(tmp_path: Path):
    stop_event = threading.Event()
    startup_queue = Queue()
    thread = threading.Thread(
        target=start_assets_server,
        args=(str(tmp_path), 0, stop_event, None, None, startup_queue),
        daemon=True,
    )
    thread.start()
    port = startup_queue.get(timeout=1)
    try:
        assert _status(port, "/project-media/anything.png") == 404
    finally:
        stop_event.set()


def test_legacy_static_project_prefix_still_served_from_data_root(media_server):
    port, data_root, _ = media_server
    legacy = data_root / "project" / "robot" / "idle" / "output" / "frame.png"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"legacy")

    with urlopen(f"http://127.0.0.1:{port}/project/robot/idle/output/frame.png") as response:
        assert response.read() == b"legacy"


# ==================== Resource identifier generation ====================


def test_frame_url_uses_project_media_prefix_under_custom_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("GAM_CONFIG", str(tmp_path / "cfg.json"))
    from backend.api.frame_api import FrameAPI

    custom = tmp_path / "external-projects"
    api = FrameAPI("http://127.0.0.1:9000", projects_root=custom)
    frame = custom / "mage" / "walk" / "output" / "01_frames" / "frame_000001.png"

    url = api.get_frame_url(str(frame))

    assert url.startswith("http://127.0.0.1:9000/project-media/mage/walk/output/01_frames/frame_000001.png?t=")


def test_frame_url_falls_back_to_data_root_relative_for_legacy_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("GAM_CONFIG", str(tmp_path / "cfg.json"))
    from backend.api.frame_api import FrameAPI

    api = FrameAPI("http://127.0.0.1:9000", projects_root=tmp_path / "external-projects")
    legacy = tmp_path / "data" / "project" / "robot" / "idle" / "output" / "frame.png"

    assert api.get_frame_url(str(legacy)).startswith("http://127.0.0.1:9000/project/robot/idle/output/frame.png")


def test_audio_wav_url_uses_project_media_prefix_under_custom_root(tmp_path: Path):
    from backend.api.audio_api import AudioAPI

    custom = tmp_path / "external-projects"
    api = AudioAPI("http://127.0.0.1:9000", projects_root=custom)
    wav = custom / "mage" / "walk" / "cache" / "01_audio" / "source.wav"

    assert api._wav_url(wav).startswith("http://127.0.0.1:9000/project-media/mage/walk/cache/01_audio/source.wav?t=")
