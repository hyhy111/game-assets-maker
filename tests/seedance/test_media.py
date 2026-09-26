import threading
import time
from pathlib import Path
from queue import Queue
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pytest
from PIL import Image

from backend.seedance.models import SeedanceRequest
from backend.seedance.repository import TaskRepository


def _image(path: Path) -> Path:
    Image.new("RGB", (300, 300), "white").save(path)
    return path


def test_media_resolver_allows_only_persisted_assets_and_rejects_traversal(tmp_path):
    from backend.seedance.media import SeedanceMediaResolver

    repository = TaskRepository(tmp_path / "cache")
    task = repository.create_draft(SeedanceRequest(first_frame=_image(tmp_path / "first.png")))
    resolver = SeedanceMediaResolver(repository)

    assert resolver.resolve(task.local_id, "first_frame").name == "first_frame.png"
    with pytest.raises(ValueError, match="Unknown"):
        resolver.resolve(task.local_id, "not-an-asset")

    repository.update(task.local_id, lambda current: current.input_paths.__setitem__("first_frame", "../outside.png"))
    with pytest.raises(ValueError, match="relative|escapes"):
        resolver.resolve(task.local_id, "first_frame")


def test_media_resolver_thumbnail_requires_a_persisted_path(tmp_path):
    from backend.seedance.media import SeedanceMediaResolver

    repository = TaskRepository(tmp_path / "cache")
    task = repository.create_draft(SeedanceRequest(first_frame=_image(tmp_path / "first.png")))
    resolver = SeedanceMediaResolver(repository)

    with pytest.raises(FileNotFoundError):
        resolver.resolve(task.local_id, "thumbnail")

    thumbnail = repository.resolve_asset(task.local_id, "output/thumbnail.jpg")
    _image(thumbnail)
    repository.update(
        task.local_id,
        lambda current: current.output_paths.__setitem__("thumbnail", "output/thumbnail.jpg"),
    )
    assert resolver.resolve(task.local_id, "thumbnail") == thumbnail


def test_local_media_route_is_allowlisted_url_decoded_and_stops(tmp_path):
    from backend.main import start_assets_server
    from backend.seedance.media import SeedanceMediaResolver

    repository = TaskRepository(tmp_path / "cache")
    task = repository.create_draft(SeedanceRequest(first_frame=_image(tmp_path / "first.png")))
    stop_event = threading.Event()
    startup_queue = Queue()
    thread = threading.Thread(
        target=start_assets_server,
        args=(str(tmp_path), 0, stop_event, SeedanceMediaResolver(repository), None, startup_queue),
        daemon=True,
    )
    thread.start()
    port = startup_queue.get(timeout=1)
    assert isinstance(port, int) and port > 0
    url = f"http://127.0.0.1:{port}/seedance-media/{task.local_id}/first_frame"
    for _ in range(20):
        try:
            with urlopen(url, timeout=0.2) as response:
                assert response.read() == _image(tmp_path / "first.png").read_bytes()
                assert response.headers["Content-Type"] == "image/png"
                assert response.headers["Content-Length"] == str((tmp_path / "first.png").stat().st_size)
                assert response.headers["Access-Control-Allow-Origin"] == "*"
                assert response.headers["Cache-Control"] == "no-store"
                break
        except OSError:
            time.sleep(0.02)
    else:
        pytest.fail("Seedance local media server did not start")

    wav_path = tmp_path / "project" / "豹子骑士" / "改" / "cache" / "01_audio" / "source.wav"
    wav_path.parent.mkdir(parents=True)
    wav_path.write_bytes(b"RIFF-test-wav")
    wav_url = f"http://127.0.0.1:{port}/{quote(wav_path.relative_to(tmp_path).as_posix(), safe='/')}"
    with urlopen(wav_url, timeout=0.2) as response:
        assert response.read() == b"RIFF-test-wav"

    with pytest.raises(HTTPError) as invalid_asset:
        urlopen(f"http://127.0.0.1:{port}/seedance-media/{task.local_id}/%2e%2e", timeout=0.2)
    assert invalid_asset.value.code == 404

    with pytest.raises(HTTPError) as malformed_route:
        urlopen(f"http://127.0.0.1:{port}/seedance-media/{task.local_id}/first_frame/extra", timeout=0.2)
    assert malformed_route.value.code == 404

    stop_event.set()
    thread.join(timeout=1)
    assert not thread.is_alive()


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_assets_server_serves_only_allowlisted_data_prefixes(tmp_path, method):
    """The data root holds config.json (credentials); only project/ and cache/
    subtrees may be exposed over HTTP."""
    from backend.main import start_assets_server

    (tmp_path / "config.json").write_text('{"seedance": {"api_key": "secret"}}', encoding="utf-8")
    (tmp_path / "notes.txt").write_text("local-only", encoding="utf-8")
    frame = tmp_path / "project" / "mage" / "walk" / "output" / "01_frames" / "frame_000001.png"
    frame.parent.mkdir(parents=True)
    Image.new("RGB", (8, 8), "white").save(frame)
    cached = tmp_path / "cache" / "ai-video-cache" / "clip.mp4"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"fake-video")

    stop_event = threading.Event()
    startup_queue = Queue()
    thread = threading.Thread(
        target=start_assets_server,
        args=(str(tmp_path), 0, stop_event, None, None, startup_queue),
        daemon=True,
    )
    thread.start()
    port = startup_queue.get(timeout=1)
    assert isinstance(port, int) and port > 0

    try:
        with urlopen(f"http://127.0.0.1:{port}/project/mage/walk/output/01_frames/frame_000001.png", timeout=1) as r:
            assert r.status == 200
        with urlopen(f"http://127.0.0.1:{port}/cache/ai-video-cache/clip.mp4", timeout=1) as r:
            assert r.read() == b"fake-video"

        for forbidden in (
            "/config.json",
            "/notes.txt",
            "/%2e%2e/config.json",
            "/project/../../config.json",
            "/project/..%2fconfig.json",
            "/cache/%2e%2e%2fconfig.json",
        ):
            with pytest.raises(HTTPError) as denied:
                urlopen(Request(f"http://127.0.0.1:{port}{forbidden}", method=method), timeout=1)
            assert denied.value.code == 404, forbidden
    finally:
        stop_event.set()
        thread.join(timeout=1)
    assert not thread.is_alive()


@pytest.mark.parametrize("method", ["GET", "HEAD"])
@pytest.mark.parametrize("link_kind", ["file", "directory", "prefix"])
def test_static_media_rejects_symlink_escape(tmp_path, method, link_kind):
    from backend.main import start_assets_server

    root = tmp_path / "data"
    root.mkdir()
    (root / "config.json").write_text("synthetic-config")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("synthetic-outside")
    project = root / "project"
    try:
        if link_kind == "prefix":
            project.symlink_to(outside, target_is_directory=True)
            path = "/project/secret.txt"
        else:
            project.mkdir()
            if link_kind == "file":
                (project / "frame.png").symlink_to(root / "config.json")
                path = "/project/frame.png"
            else:
                (project / "linked").symlink_to(outside, target_is_directory=True)
                path = "/project/linked/secret.txt"
    except OSError:
        pytest.skip("Symlink creation is not available on this test host")

    stop = threading.Event()
    queue = Queue()
    thread = threading.Thread(
        target=start_assets_server,
        args=(str(root), 0, stop, None, None, queue),
        daemon=True,
    )
    thread.start()
    port = queue.get(timeout=2)
    assert isinstance(port, int)
    try:
        with pytest.raises(HTTPError) as denied:
            urlopen(Request(f"http://127.0.0.1:{port}{path}", method=method), timeout=2)
        assert denied.value.code == 404
    finally:
        stop.set()
        thread.join(timeout=2)
