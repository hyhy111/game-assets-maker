"""Original media imports survive a restart and expose only their recorded files."""

import base64
import subprocess
import threading
from io import BytesIO
from pathlib import Path
from queue import Queue
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import imageio_ffmpeg
import pytest
from PIL import Image

from backend.api.project_api import ProjectAPI
from backend.main import API, start_assets_server
from src.utils.app_config import save_app_config
from src.utils.storage_migration import AI_CACHE_LOCATION, LocationMigration, StorageMigrationCoordinator


class PickerWindow:
    def __init__(self, paths):
        self.paths = paths

    def create_file_dialog(self, _dialog, *, allow_multiple, file_types):
        assert allow_multiple
        assert "*.png" in file_types[0] and "*.mp4" in file_types[0]
        return self.paths


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path / "gam-data"))
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    monkeypatch.setenv("GAM_CONFIG", str(tmp_path / "gam-data" / "config.json"))
    return tmp_path / "gam-data"


def test_mixed_native_import_copies_originals_and_persists_metadata(library, tmp_path):
    configured_cache = tmp_path / "素材 缓存"
    save_app_config({"seedance": {"cache_dir": str(configured_cache)}})
    image = tmp_path / "角色 A.PNG"
    Image.new("RGBA", (600, 480), (30, 60, 90, 140)).save(image)
    video = tmp_path / "步行 A.mp4"
    subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=green:s=64x48:r=5:d=1",
            "-pix_fmt",
            "yuv420p",
            str(video),
        ],
        check=True,
        capture_output=True,
    )
    invalid = tmp_path / "损坏.png"
    invalid.write_bytes(b"not an image")
    api = API(window=PickerWindow((str(image), str(invalid), str(video))))
    result = api.source_media_import()
    assert result["failed"] == [invalid.name]
    picture, clip = result["items"]
    assert (picture["name"], picture["kind"], picture["width"], picture["height"]) == (image.name, "image", 600, 480)
    assert picture["duration"] is None
    assert (clip["name"], clip["kind"], clip["duration"]) == (video.name, "video", pytest.approx(1))
    for item, path in ((picture, image), (clip, video)):
        original = api._source_media.resolve(item["id"], "original")
        root_name = "local-images" if item["kind"] == "image" else "local-videos"
        assert original.is_relative_to(configured_cache / root_name)
        assert original.read_bytes() == path.read_bytes()
        path.unlink()
        with Image.open(api._source_media.resolve(item["id"], "thumbnail")) as thumbnail:
            assert thumbnail.width <= 480 and thumbnail.height <= 360
    assert not list(configured_cache.glob("*/.import-*"))

    restarted = API(assets_base_url="http://127.0.0.1:42110")
    assert [item["id"] for item in restarted.source_media_list()] == [clip["id"], picture["id"]]
    imported_video = restarted.source_media_get(clip["id"])
    assert imported_video["url"] == f"http://127.0.0.1:42110/source-media/{clip['id']}/original"
    assert restarted.source_media_get("../private") is None
    project = restarted.source_media_create_project(clip["id"], "角色", "步行")
    assert project["steps"]["1"]["data_ready"]
    project_video = Path(project["video_path"])
    assert project_video.parent == Path(project["path"]) / "input"
    assert restarted.source_media_delete(clip["id"])
    assert project_video.is_file()
    moved_root = tmp_path / "项目新位置"
    restarted.storage_locations.projects_root.rename(moved_root)
    moved = ProjectAPI(moved_root).get_project(project["id"])
    assert Path(moved["video_path"]).is_relative_to(moved_root)
    assert Path(moved["video_path"]).is_file()
    assert API(window=PickerWindow(None)).source_media_import() == {"items": [], "failed": []}


def test_media_server_supports_ranges_and_does_not_expose_metadata(library, tmp_path: Path):
    image = tmp_path / "ref.png"
    Image.new("RGB", (32, 32)).save(image)
    api = API(window=PickerWindow((str(image),)))
    media_id = api.source_media_import()["items"][0]["id"]
    stop = threading.Event()
    startup = Queue()
    thread = threading.Thread(
        target=start_assets_server,
        args=(str(library), 0, stop),
        kwargs={"startup_queue": startup, "source_media": api._source_media},
        daemon=True,
    )
    thread.start()
    port = startup.get(timeout=2)
    assert isinstance(port, int)
    base = f"http://127.0.0.1:{port}/source-media/{media_id}"
    try:
        raw = image.read_bytes()
        with urlopen(Request(f"{base}/original", headers={"Range": "bytes=2-10"}), timeout=2) as response:
            assert response.status == 206
            assert response.headers["Content-Range"] == f"bytes 2-10/{len(raw)}"
            assert response.read() == raw[2:11]
        with urlopen(Request(f"{base}/thumbnail", method="HEAD"), timeout=2) as response:
            assert response.headers["Content-Type"] == "image/png"
            assert response.read() == b""
        with pytest.raises(HTTPError) as unsatisfiable:
            urlopen(Request(f"{base}/original", headers={"Range": f"bytes={len(raw)}-"}), timeout=2)
        assert unsatisfiable.value.code == 416
        for url in (f"{base}/media.json", f"{base}/%2e%2e", f"{base}/original.png"):
            with pytest.raises(HTTPError) as rejected:
                urlopen(url, timeout=2)
            assert rejected.value.code == 404
    finally:
        stop.set()
        thread.join(timeout=2)


def _image_data_url(color: str, size=(32, 32)) -> str:
    buffer = BytesIO()
    Image.new("RGBA", size, color).save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def test_edit_replaces_preview_and_reference_and_can_restore_without_touching_original(library, tmp_path):
    image = tmp_path / "ref.jpg"
    Image.new("RGB", (32, 32), "white").save(image)
    api = API(window=PickerWindow((str(image),)))
    record = api.source_media_import()["items"][0]
    media_id = record["id"]
    with pytest.raises(ValueError):
        api.source_media_edit_image(media_id, _image_data_url("red", (16, 16)), _image_data_url("red"), None)
    assert api.source_media_get(media_id)["url"] == record["url"]

    edited = api.source_media_edit_image(media_id, _image_data_url("red"), _image_data_url("blue"), None)
    assert edited["url"] != record["url"]
    assert edited["thumbnail_url"] != record["thumbnail_url"]
    assert edited["edit_source_url"]
    current = Path(API().source_media_image_input(media_id))
    assert current.suffix == ".png"
    with Image.open(current) as result:
        assert result.getpixel((0, 0)) == (255, 0, 0, 255)
    with Image.open(api._source_media.resolve(media_id, "edit-source")) as result:
        assert result.getpixel((0, 0)) == (0, 0, 255, 255)
    restored = api.source_media_restore_image(media_id)
    assert restored["url"] == record["url"]
    assert Path(api.source_media_image_input(media_id)).read_bytes() == image.read_bytes()
    assert current.is_file()


def test_legacy_copy_keeps_ids_follows_cache_migration_and_does_not_resurrect_deletions(library, tmp_path):
    image = tmp_path / "old.png"
    Image.new("RGB", (32, 32), "green").save(image)
    api = API(window=PickerWindow((str(image),)))
    media_id = api.source_media_import()["items"][0]["id"]
    legacy = library / "source-media" / media_id
    legacy.parent.mkdir()
    api._source_media.resolve(media_id, "original").parent.rename(legacy)

    restarted = API()
    assert restarted.source_media_get(media_id)["id"] == media_id
    assert (legacy / "original.png").is_file()
    target = tmp_path / "new cache"
    migration = StorageMigrationCoordinator(commit_config=save_app_config)
    report = migration.precheck(
        [LocationMigration(AI_CACHE_LOCATION, restarted.storage_locations.ai_cache_root, target)],
        {"seedance": {"cache_dir": str(target)}},
    )
    migration.execute(report.token)
    moved = API()
    assert Path(moved.source_media_image_input(media_id)).is_relative_to(target / "local-images")
    assert moved.source_media_delete(media_id)
    assert API().source_media_get(media_id) is None
    assert (legacy / "original.png").is_file()
