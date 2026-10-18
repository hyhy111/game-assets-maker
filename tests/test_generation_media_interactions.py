"""Local-only regressions for media handoff, previews, and directory actions."""

import base64
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from backend.api.seedance_api import SeedanceAPI
from backend.api.seedream_api import SeedreamAPI
from backend.seedream.downloader import ImageDownloader
from backend.seedream.manager import SeedreamBatchManager
from backend.seedream.models import SeedreamRequest
from backend.seedream.repository import BatchRepository
from src.utils.storage_locations import StorageLocations


@pytest.fixture
def local_config(tmp_path, monkeypatch):
    monkeypatch.setenv("GAM_CONFIG", str(tmp_path / "config.json"))
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path / "data"))
    return tmp_path


def image_bytes(color="green"):
    buffer = BytesIO()
    Image.new("RGB", (32, 32), color).save(buffer, format="PNG")
    return buffer.getvalue()


class NoGenerationClient:
    def generate_image(self, _payload):
        raise AssertionError("This operation must not generate an image")


def image_api(tmp_path):
    reference = tmp_path / "reference.png"
    reference.write_bytes(image_bytes())
    repository = BatchRepository(tmp_path / "images")
    batch = repository.create_batch(SeedreamRequest(prompt="reference test", count=1, reference_image=str(reference)))
    source = repository.resolve_asset(batch.local_id, "images/0.png")
    source.write_bytes(image_bytes("red"))

    def succeed(current):
        current.attempts[0].status = "succeeded"
        current.attempts[0].local_path = "images/0.png"

    repository.update(batch.local_id, succeed)
    manager = SeedreamBatchManager(NoGenerationClient(), repository, ImageDownloader(repository))
    return SeedreamAPI(manager, media_base_url="http://127.0.0.1:9876"), batch.local_id, source


def test_reference_urls_use_media_server_in_details_and_regeneration(local_config):
    api, local_id, source = image_api(local_config)
    url = f"http://127.0.0.1:9876/seedream-media/{local_id}/reference"
    detail = api.get_batch(local_id)
    assert detail["success"]
    assert detail["batch"]["reference_image_url"] == url
    assert detail["batch"]["attempts"][0]["can_open_directory"] is True
    assert detail["batch"]["attempts"][0]["absolute_path"] == str(source.resolve())
    assert detail["batch"]["attempts"][0]["local_path"] == "images/0.png"
    assert api.get_regeneration_draft(local_id)["data"]["reference_image_url"] == url
    source.unlink()
    assert api.get_batch(local_id)["batch"]["attempts"][0]["can_open_directory"] is False
    assert api.get_batch(local_id)["batch"]["attempts"][0]["absolute_path"] is None


def test_image_directory_and_handoff_use_current_edited_file(local_config, monkeypatch):
    api, local_id, source = image_api(local_config)
    original = source.with_name("0.original.png")
    original.write_bytes(source.read_bytes())
    edited_bytes = image_bytes("blue")
    source.write_bytes(edited_bytes)
    opened = []
    monkeypatch.setattr("backend.api.seedream_api.open_directory", opened.append)
    assert api.open_image_directory(local_id) == {"success": True}
    assert opened == [source.parent]
    handoff = api.get_handoff_image(local_id)
    assert Path(handoff["data"]["local_path"]).read_bytes() == edited_bytes
    assert original.read_bytes() != edited_bytes
    assert api.open_image_directory("../outside")["success"] is False
    assert api.open_image_directory(local_id, 99)["success"] is False
    assert len(opened) == 1


def test_directory_failure_is_reported(local_config, monkeypatch):
    api, local_id, _source = image_api(local_config)

    def fail(_directory):
        raise OSError("File manager is unavailable")

    monkeypatch.setattr("backend.api.seedream_api.open_directory", fail)
    assert api.open_image_directory(local_id)["success"] is False


def test_video_directory_opens_current_source_only(local_config, monkeypatch):
    source = local_config / "cached.mp4"
    source.write_bytes(b"local video fixture")

    class Resolver:
        def resolve(self, local_id, asset_key):
            assert (local_id, asset_key) == ("task-1", "video")
            return source

    api = SeedanceAPI(object(), media_resolver=Resolver())
    opened = []
    monkeypatch.setattr("backend.api.seedance_api.open_directory", opened.append)
    assert api.open_video_directory("task-1") == {"success": True}
    assert opened == [source.parent]
    source.unlink()
    assert api.open_video_directory("task-1")["success"] is False
    assert len(opened) == 1


def test_dropped_image_is_validated_and_stored_under_injected_cache(local_config):
    locations = StorageLocations(projects_root=local_config / "projects", ai_cache_root=local_config / "custom-cache")
    api = SeedreamAPI(storage_locations=locations)
    content = image_bytes()
    result = api.import_reference_image(
        "data:application/octet-stream;base64," + base64.b64encode(content).decode(), "../../escaped.exe"
    )
    assert result["success"]
    path = Path(result["path"])
    assert path.parent == locations.ai_pic_cache_root / "reference-inputs"
    assert path.suffix == ".png"
    assert path.read_bytes() == content
    assert not (local_config / "escaped.exe").exists()
    assert api._manager is None


@pytest.mark.parametrize(
    "data", ["https://example.com/image.png", "data:image/png;base64,%%%", "data:image/png;base64,dGV4dA=="]
)
def test_invalid_drop_does_not_leave_an_input_file(local_config, data):
    locations = StorageLocations(projects_root=local_config / "projects", ai_cache_root=local_config / "custom-cache")
    result = SeedreamAPI(storage_locations=locations).import_reference_image(data, "bad.png")
    assert result["success"] is False
    assert not list(locations.ai_pic_cache_root.rglob("*.*"))


def test_large_drop_is_rejected_before_persistence(local_config, monkeypatch):
    monkeypatch.setattr("backend.api.seedream_api.MAX_IMAGE_BYTES", 8)
    result = SeedreamAPI().import_reference_image("data:image/png;base64," + base64.b64encode(image_bytes()).decode())
    assert result["error"]["code"] == "IMAGE_TOO_LARGE"
    assert not (local_config / "data" / "cache").exists()


def test_file_manager_receives_literal_path_argument(local_config, monkeypatch):
    from src.utils import system_paths

    directory = local_config / 'directory with "quotes" $(not-a-command)'
    directory.mkdir()
    calls = []
    monkeypatch.setattr(system_paths.sys, "platform", "darwin")
    monkeypatch.setattr(system_paths.subprocess, "run", lambda args, **kwargs: calls.append((args, kwargs)))
    system_paths.open_directory(directory)
    assert calls == [(["open", str(directory)], {"check": True})]


def test_generic_config_save_preserves_immediate_audit_toggle(local_config, monkeypatch):
    from backend.api.config_api import ConfigAPI
    from src.utils.app_config import load_app_config, save_ark_audit_enabled

    monkeypatch.setenv("DEV_MODE", "1")
    monkeypatch.setenv("GAM_DATA_MODE", "dev")
    save_ark_audit_enabled(True)
    ConfigAPI().save_config({"ark_audit_enabled": False, "ark_audit_available": False, "language": "en"})
    assert load_app_config()["ark_audit_enabled"] is True
    assert load_app_config()["language"] == "en"
