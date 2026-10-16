from __future__ import annotations

import base64
import json
import threading
from io import BytesIO
from pathlib import Path

from PIL import Image

from backend.seedream.client import ArkAPIError
from src.utils.app_config import save_app_config


class FakeManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.event_sink = None
        self.active_count = 0
        self.reclassified: dict | None = None

    def set_event_sink(self, sink):
        self.event_sink = sink

    def active_attempt_count(self):
        self.calls.append(("active_count", None))
        return self.active_count

    def reclassify_interrupted_attempts(self):
        self.calls.append(("reclassify", None))
        return self.reclassified if self.reclassified is not None else {"unknown": 0, "download_failed": 0}

    def create_batch(self, request):
        self.calls.append(("create", request))
        return {
            "local_id": "batch-1",
            "request": request.to_dict() if hasattr(request, "to_dict") else request,
            "attempts": [
                {
                    "local_id": "attempt-1",
                    "index": 0,
                    "status": "queued",
                    "request": {},
                    "response": {},
                    "usage": {},
                    "total_tokens": None,
                    "image_url": "",
                    "local_path": None,
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                    "finished_at": None,
                    "elapsed_seconds": 0,
                    "error": None,
                }
            ],
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }

    def get_batch(self, local_id):
        self.calls.append(("get", local_id))
        return self.create_batch.__self__.create_batch.__func__(self, None) if False else {
            "local_id": local_id,
            "request": {},
            "attempts": [],
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }

    def list_batches(self):
        self.calls.append(("list", None))
        return []

    def delete_batch(self, local_id):
        self.calls.append(("delete", local_id))

    def retry_download(self, local_id, attempt_index=0):
        self.calls.append(("retry_download", local_id, attempt_index))
        return {
            "local_id": local_id,
            "request": {},
            "status": "completed",
            "attempts": [
                {
                    "local_id": "attempt-1",
                    "index": attempt_index,
                    "status": "succeeded",
                    "request": {},
                    "response": {},
                    "usage": {},
                    "total_tokens": None,
                    "image_url": f"/seedream-media/{local_id}/image/{attempt_index}",
                    "local_path": f"images/{attempt_index}.jpg",
                    "url_expired": False,
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                    "finished_at": "2026-01-01T00:00:00Z",
                    "elapsed_seconds": 0,
                    "error": None,
                }
            ],
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }


class MissingResolver:
    def resolve(self, _local_id, _asset_key):
        raise FileNotFoundError


def _image(path: Path) -> Path:
    Image.new("RGB", (64, 64), "white").save(path)
    return path


def test_seedream_create_validates_input_before_delegating(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    save_app_config({"seedance": {"api_key": "secret-key"}})
    manager = FakeManager()
    api = SeedreamAPI(manager, media_resolver=MissingResolver())

    result = api.create_batch({"prompt": "", "model": "pro", "resolution": "1K", "ratio": "16:9"})
    assert result["success"] is False
    assert result["error"]["code"] == "PROMPT_REQUIRED"
    assert manager.calls == []


def test_seedream_create_requires_api_key(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    manager = FakeManager()
    api = SeedreamAPI(manager, media_resolver=MissingResolver())

    result = api.create_batch({"prompt": "hero", "model": "pro", "resolution": "1K", "ratio": "16:9"})
    assert result["success"] is False
    assert result["error"]["code"] == "API_KEY_NOT_CONFIGURED"
    assert manager.calls == []


def test_seedream_create_delegates_to_manager(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    save_app_config({"seedance": {"api_key": "secret-key"}})
    manager = FakeManager()
    api = SeedreamAPI(manager, media_base_url="http://127.0.0.1:8080", media_resolver=MissingResolver())

    result = api.create_batch({"prompt": "hero", "model": "pro", "resolution": "1K", "ratio": "16:9"})
    assert result["success"] is True
    assert result["batch"]["local_id"] == "batch-1"
    assert manager.calls[0][0] == "create"


def test_seedream_rejects_retired_lite_model(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    save_app_config({"seedance": {"api_key": "secret-key"}})
    manager = FakeManager()
    api = SeedreamAPI(manager, media_resolver=MissingResolver())

    result = api.create_batch({"prompt": "hero", "model": "lite", "resolution": "2K", "ratio": "16:9"})
    assert result["success"] is False
    assert result["error"]["code"] == "UNSUPPORTED_MODEL"

    assert manager.calls == []


def test_seedream_rejects_custom_ratio(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    save_app_config({"seedance": {"api_key": "secret-key"}})
    api = SeedreamAPI(FakeManager(), media_resolver=MissingResolver())

    result = api.create_batch({"prompt": "hero", "model": "pro", "resolution": "1K", "ratio": "21:9"})
    assert result["success"] is False
    assert result["error"]["code"] == "UNSUPPORTED_RATIO"


def test_seedream_api_key_redacted_in_error_messages(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    secret = "super-secret-key"
    save_app_config({"seedance": {"api_key": secret}})

    manager = FakeManager()
    manager.get_batch = lambda _id: {"local_id": "x", "error": {"message": f"leaked {secret}"}}
    api = SeedreamAPI(manager, media_resolver=MissingResolver())

    result = api.get_batch("batch-1")
    serialized = json.dumps(result)
    assert secret not in serialized
    assert "[REDACTED]" in serialized


def test_seedream_save_image_uses_system_dialog_and_copies_file(tmp_path, runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    source = tmp_path / "cached.jpg"
    source.write_bytes(b"cached image")
    destination = tmp_path / "saved.jpg"

    class Resolver:
        def resolve(self, local_id, asset_key, attempt_index=0):
            assert (local_id, asset_key, attempt_index) == ("batch-1", "image", 0)
            return source

    class Window:
        def create_file_dialog(self, dialog_type, **kwargs):
            self.options = kwargs
            return (str(destination),)

    window = Window()
    api = SeedreamAPI(FakeManager(), window_getter=lambda: window, media_resolver=Resolver())

    result = api.save_image("batch-1", 0)

    assert result == {"success": True, "data": {"saved": True, "path": str(destination)}}
    assert destination.read_bytes() == b"cached image"
    assert window.options["save_filename"] == "seedream-batch-1-0.jpg"


def test_seedream_resize_character_keeps_canvas_and_fills_from_corner_color(tmp_path, runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    source = tmp_path / "candidate.png"
    image = Image.new("RGB", (100, 100), (12, 34, 56))
    for y in range(20, 80):
        for x in range(40, 60):
            image.putpixel((x, y), (220, 30, 20))
    image.save(source)

    class Resolver:
        def resolve(self, local_id, asset_key, attempt_index=0):
            assert (local_id, asset_key, attempt_index) == ("batch-1", "image", 0)
            return source

    original_bytes = source.read_bytes()
    api = SeedreamAPI(FakeManager(), media_resolver=Resolver())
    result = api.resize_character("batch-1", 0, 20, 80, 30)

    assert result["success"] is True
    assert result["data"]["measured_height"] == 60
    assert result["data"]["scale"] == 0.5
    assert result["data"]["background_color"] == [12, 34, 56]
    assert source.with_name("candidate.original.png").is_file()
    assert source.with_name("candidate.png.layout.json").is_file()
    with Image.open(source) as resized:
        assert resized.size == (100, 100)
        assert resized.getpixel((0, 0)) == (12, 34, 56)
        assert resized.getpixel((50, 75))[0] > 150
        assert resized.getpixel((50, 45)) == (12, 34, 56)

    edit_source = source.with_name("candidate.png.edit-source.png")
    Image.new("RGBA", (100, 100), "blue").save(edit_source)
    restored = api.restore_character("batch-1", 0)
    assert restored == {"success": True, "data": {"restored": True, "width": 100, "height": 100}}
    assert source.read_bytes() == original_bytes
    assert not source.with_name("candidate.png.layout.json").exists()
    assert not edit_source.exists()

    moved_to_bottom = api.resize_character("batch-1", 0, 20, 80, 30, bottom_distance=0)
    assert moved_to_bottom["success"] is True
    assert moved_to_bottom["data"]["bottom_distance"] == 0
    with Image.open(source) as resized:
        assert resized.getpixel((50, 95))[0] > 150


def test_seedream_resize_character_rejects_target_not_smaller_than_measurement(tmp_path, runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    source = _image(tmp_path / "candidate.jpg")

    class Resolver:
        def resolve(self, _local_id, _asset_key, _attempt_index=0):
            return source

    api = SeedreamAPI(FakeManager(), media_resolver=Resolver())
    result = api.resize_character("batch-1", 0, 10, 50, 40)

    assert result["success"] is False
    assert result["error"]["code"] == "INVALID_REQUEST"
    assert not source.with_name("candidate.original.jpg").exists()


def test_seedream_restore_character_rejects_missing_original_backup(tmp_path, runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    source = _image(tmp_path / "candidate.jpg")

    class Resolver:
        def resolve(self, _local_id, _asset_key, _attempt_index=0):
            return source

    api = SeedreamAPI(FakeManager(), media_resolver=Resolver())
    result = api.restore_character("batch-1", 0)

    assert result["success"] is False
    assert result["error"]["code"] == "NOT_FOUND"


def _png_data_url(image: Image.Image) -> str:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def test_seedream_apply_eraser_saves_same_size_edit_and_preserves_original(tmp_path, runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    source = tmp_path / "candidate.png"
    Image.new("RGB", (32, 32), (20, 40, 60)).save(source)
    original_bytes = source.read_bytes()
    edited = Image.new("RGB", (32, 32), (20, 40, 60))
    edited.putpixel((16, 16), (200, 10, 10))
    edit_source = Image.new("RGB", (32, 32), (80, 60, 40))

    class Resolver:
        def resolve(self, _local_id, _asset_key, _attempt_index=0):
            return source

    api = SeedreamAPI(FakeManager(), media_resolver=Resolver())
    generation_layout = {
        "source_width": 32,
        "source_height": 32,
        "measured_top": 3,
        "measured_bottom": 27,
        "measured_height": 24,
        "target_height": 12,
        "character_height_ratio": 0.375,
        "bottom_distance": 4,
        "bottom_margin_ratio": 0.125,
        "scale": 0.5,
    }
    result = api.apply_eraser(
        "batch-1", 0, _png_data_url(edited), _png_data_url(edit_source), generation_layout
    )

    assert result == {"success": True, "data": {
        "saved": True,
        "width": 32,
        "height": 32,
        "generation_layout": generation_layout,
    }}
    assert source.with_name("candidate.original.png").read_bytes() == original_bytes
    assert json.loads(source.with_name("candidate.png.layout.json").read_text(encoding="utf-8")) == generation_layout
    with Image.open(source) as saved:
        assert saved.getpixel((16, 16)) == (200, 10, 10)
    with Image.open(source.with_name("candidate.png.edit-source.png")) as saved_source:
        assert saved_source.getpixel((16, 16))[:3] == (80, 60, 40)


def test_seedream_apply_eraser_rejects_changed_canvas_dimensions(tmp_path, runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    source = tmp_path / "candidate.png"
    Image.new("RGB", (32, 32), "white").save(source)

    class Resolver:
        def resolve(self, _local_id, _asset_key, _attempt_index=0):
            return source

    api = SeedreamAPI(FakeManager(), media_resolver=Resolver())
    result = api.apply_eraser(
        "batch-1",
        0,
        _png_data_url(Image.new("RGB", (16, 16), "white")),
        _png_data_url(Image.new("RGB", (32, 32), "white")),
    )

    assert result["success"] is False
    assert result["error"]["code"] == "INVALID_REQUEST"
    assert not source.with_name("candidate.original.png").exists()


def test_seedream_resize_character_rejects_bottom_distance_outside_canvas(tmp_path, runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    source = _image(tmp_path / "candidate.jpg")

    class Resolver:
        def resolve(self, _local_id, _asset_key, _attempt_index=0):
            return source

    api = SeedreamAPI(FakeManager(), media_resolver=Resolver())
    result = api.resize_character("batch-1", 0, 10, 50, 30, bottom_distance=40)

    assert result["success"] is False
    assert result["error"]["code"] == "INVALID_REQUEST"


def test_seedream_event_dispatch_redacts_api_key(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    secret = "secret-key"
    save_app_config({"seedance": {"api_key": secret}})

    class Window:
        def __init__(self):
            self.scripts = []

        def evaluate_js(self, script):
            self.scripts.append(script)

    manager = FakeManager()
    api = SeedreamAPI(manager, media_resolver=MissingResolver())
    api.set_window(Window())
    manager.event_sink(
        "seedream-batch-updated",
        {
            "local_id": "batch-1",
            "attempts": [{"local_path": "images/0.jpg", "image_url": "/seedream-media/batch-1/image/0"}],
            "error": {"message": secret},
        },
    )

    assert secret not in json.dumps(api._window.scripts)
    assert "[REDACTED]" in api._window.scripts[0]
    assert "seedream-batch-updated" in api._window.scripts[0]


def test_seedream_create_rejects_count_below_one(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    save_app_config({"seedance": {"api_key": "secret-key"}})
    api = SeedreamAPI(FakeManager(), media_resolver=MissingResolver())

    result = api.create_batch({"prompt": "hero", "model": "pro", "resolution": "1K", "ratio": "16:9", "count": 0})
    assert result["success"] is False
    assert result["error"]["code"] == "INVALID_COUNT"
    assert result["error"]["field"] == "count"


def test_seedream_create_rejects_count_above_four(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    save_app_config({"seedance": {"api_key": "secret-key"}})
    api = SeedreamAPI(FakeManager(), media_resolver=MissingResolver())

    result = api.create_batch({"prompt": "hero", "model": "pro", "resolution": "1K", "ratio": "16:9", "count": 5})
    assert result["success"] is False
    assert result["error"]["code"] == "INVALID_COUNT"


def test_seedream_get_settings_returns_image_defaults(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    api = SeedreamAPI(FakeManager(), media_resolver=MissingResolver())
    result = api.get_settings()
    assert result["success"] is True
    assert result["settings"] == {
        "default_count": 1,
        "default_model": "pro",
        "platform_default_model": "",
        "default_model_id": "doubao-seedream-5-0-pro-260628",
        "default_resolution": "2K",
        "default_ratio": "16:9",
    }


def test_seedream_save_settings_persists_count(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    api = SeedreamAPI(FakeManager(), media_resolver=MissingResolver())
    result = api.save_settings({"default_count": 3})
    assert result["success"] is True
    assert result["settings"]["default_count"] == 3

    # Verify it was persisted.
    from src.utils.app_config import load_app_config
    config = load_app_config()
    assert config["seedream"]["default_count"] == 3


def test_seedream_save_settings_rejects_removed_4_x_model(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    api = SeedreamAPI(FakeManager(), media_resolver=MissingResolver())
    result = api.save_settings({"default_model": "v45", "default_resolution": "2K"})

    assert result["success"] is False
    assert result["error"]["code"] == "UNSUPPORTED_MODEL"


def test_seedream_save_settings_accepts_flash_model(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    api = SeedreamAPI(FakeManager(), media_resolver=MissingResolver())
    result = api.save_settings({"default_model": "flash", "default_resolution": "1.5K"})

    assert result["success"] is True
    assert result["settings"]["default_model"] == "flash"
    assert result["settings"]["default_resolution"] == "1.5K"


def test_seedream_save_settings_rejects_invalid_count(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    api = SeedreamAPI(FakeManager(), media_resolver=MissingResolver())
    result = api.save_settings({"default_count": 5})
    assert result["success"] is False
    assert result["error"]["code"] == "INVALID_COUNT"


def test_seedream_decorate_batch_assigns_distinct_indexed_image_urls(runtime_config_path):
    """Each successful attempt must keep its own indexed media URL (#4 multi-image)."""
    from backend.api.seedream_api import SeedreamAPI

    save_app_config({"seedance": {"api_key": "secret-key"}})

    class MultiAttemptManager(FakeManager):
        def create_batch(self, request):
            self.calls.append(("create", request))
            base = {
                "local_id": "batch-1",
                "request": {},
                "status": "completed",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
            base["attempts"] = [
                {
                    "local_id": f"attempt-{i}",
                    "index": i,
                    "status": "succeeded",
                    "image_url": f"/seedream-media/batch-1/image/{i}",
                    "local_path": f"images/{i}.jpg",
                    "total_tokens": 10 * (i + 1),
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                    "finished_at": "2026-01-01T00:00:00Z",
                    "elapsed_seconds": i + 1,
                    "error": None,
                }
                for i in range(2)
            ]
            return base

    api = SeedreamAPI(
        MultiAttemptManager(),
        media_base_url="http://127.0.0.1:8080",
        media_resolver=MissingResolver(),
    )
    result = api.create_batch({"prompt": "hero", "model": "pro", "resolution": "1K", "ratio": "16:9", "count": 2})
    assert result["success"] is True
    urls = [attempt["image_url"] for attempt in result["batch"]["attempts"]]
    assert urls == [
        "http://127.0.0.1:8080/seedream-media/batch-1/image/0",
        "http://127.0.0.1:8080/seedream-media/batch-1/image/1",
    ]
    assert len(set(urls)) == 2


def _handoff_batch(local_id: str, *, status: str, index: int = 0) -> dict:
    return {
        "local_id": local_id,
        "request": {},
        "attempts": [
            {
                "local_id": "attempt-1",
                "index": index,
                "status": status,
                "request": {},
                "response": {},
                "usage": {},
                "total_tokens": 10 if status == "succeeded" else None,
                "image_url": f"/seedream-media/{local_id}/image/{index}" if status == "succeeded" else "",
                "local_path": f"images/{index}.jpg" if status == "succeeded" else None,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "finished_at": "2026-01-01T00:00:00Z" if status == "succeeded" else None,
                "elapsed_seconds": 5,
                "error": None,
            }
        ],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }


class _HandoffManager(FakeManager):
    def __init__(self, batch: dict) -> None:
        super().__init__()
        self._batch = batch

    def get_batch(self, local_id):
        self.calls.append(("get", local_id))
        return self._batch


def test_seedream_get_handoff_image_returns_local_path_for_succeeded_attempt(
    tmp_path, runtime_config_path
):
    from backend.api.seedream_api import SeedreamAPI

    source = _image(tmp_path / "candidate.jpg")

    class Resolver:
        def resolve(self, local_id, asset_key, attempt_index=0):
            assert (local_id, asset_key, attempt_index) == ("batch-1", "image", 0)
            return source

    manager = _HandoffManager(_handoff_batch("batch-1", status="succeeded"))
    api = SeedreamAPI(manager, media_resolver=Resolver())

    result = api.get_handoff_image("batch-1", 0)

    assert result["success"] is True
    assert result["data"]["local_path"] == str(source)
    # No generation was triggered, only a read.
    assert [call[0] for call in manager.calls] == ["get"]


def test_seedream_get_handoff_image_rejects_non_succeeded_attempt(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    manager = _HandoffManager(_handoff_batch("batch-1", status="generating"))
    api = SeedreamAPI(manager, media_resolver=MissingResolver())

    result = api.get_handoff_image("batch-1", 0)

    assert result["success"] is False
    assert result["error"]["code"] == "NOT_FOUND"


def test_seedream_get_handoff_image_rejects_failed_attempt(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    manager = _HandoffManager(_handoff_batch("batch-1", status="failed"))
    api = SeedreamAPI(manager, media_resolver=MissingResolver())

    result = api.get_handoff_image("batch-1", 0)

    assert result["success"] is False
    assert result["error"]["code"] == "NOT_FOUND"


def test_seedream_get_handoff_image_rejects_missing_attempt(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    manager = _HandoffManager(_handoff_batch("batch-1", status="succeeded", index=0))
    api = SeedreamAPI(manager, media_resolver=MissingResolver())

    result = api.get_handoff_image("batch-1", 99)

    assert result["success"] is False
    assert result["error"]["code"] == "NOT_FOUND"


def test_seedream_get_handoff_image_rejects_missing_local_file(tmp_path, runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    class Resolver:
        def resolve(self, local_id, asset_key, attempt_index=0):
            raise FileNotFoundError("Seedream media asset is not available")

    manager = _HandoffManager(_handoff_batch("batch-1", status="succeeded"))
    api = SeedreamAPI(manager, media_resolver=Resolver())

    result = api.get_handoff_image("batch-1", 0)

    assert result["success"] is False
    assert result["error"]["code"] == "NOT_FOUND"


def test_seedream_retry_download_delegates_to_manager(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    save_app_config({"seedance": {"api_key": "secret-key"}})
    manager = FakeManager()
    api = SeedreamAPI(manager, media_resolver=MissingResolver())

    result = api.retry_download("batch-1", 0)

    assert result["success"] is True
    assert result["batch"]["local_id"] == "batch-1"
    assert manager.calls[-1] == ("retry_download", "batch-1", 0)


def test_seedream_retry_download_returns_error_on_failure(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    save_app_config({"seedance": {"api_key": "secret-key"}})

    class ErrorManager(FakeManager):
        def retry_download(self, local_id, attempt_index=0):
            raise ValueError("URL_EXPIRED")

    api = SeedreamAPI(ErrorManager(), media_resolver=MissingResolver())

    result = api.retry_download("batch-1", 0)

    assert result["success"] is False
    assert result["error"]["code"] == "INVALID_REQUEST"


# ---------------------------------------------------------------------------
# Issue #6: Protect application close and recover unknown results
# ---------------------------------------------------------------------------


def test_seedream_get_active_attempt_count_delegates_to_manager(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    manager = FakeManager()
    manager.active_count = 3
    api = SeedreamAPI(manager, media_resolver=MissingResolver())

    result = api.get_active_attempt_count()

    assert result == {"success": True, "data": {"active_count": 3}}
    assert ("active_count", None) in manager.calls


def test_seedream_reclassify_interrupted_attempts_delegates_to_manager(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    manager = FakeManager()
    manager.reclassified = {"unknown": 2, "download_failed": 1}
    api = SeedreamAPI(manager, media_resolver=MissingResolver())

    result = api.reclassify_interrupted_attempts()

    assert result == {"success": True, "data": {"unknown": 2, "download_failed": 1}}
    assert ("reclassify", None) in manager.calls


def test_seedream_set_window_reclassifies_once_before_attaching_sink(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    manager = FakeManager()
    api = SeedreamAPI(manager, media_resolver=MissingResolver())

    api.set_window(object())
    api.set_window(object())

    # Reclassify runs exactly once (guarded by _started), then the sink is attached.
    assert manager.calls.count(("reclassify", None)) == 1
    assert manager.event_sink is not None


# ---------------------------------------------------------------------------
# Issue #6: window-close interception (fake window + fake manager)
# ---------------------------------------------------------------------------


class _FakeCloseWindow:
    def __init__(self) -> None:
        self.scripts: list[str] = []
        self.warning_dispatched = threading.Event()
        self.destroyed = 0

    def evaluate_js(self, script: str) -> None:
        self.scripts.append(script)
        self.warning_dispatched.set()

    def destroy(self) -> None:
        self.destroyed += 1


def _make_close_app(manager: FakeManager | None = None) -> tuple:
    from backend.api.seedream_api import SeedreamAPI
    from backend.main import MainApp

    app = MainApp()
    app.api._process_api_instance = type("Process", (), {"shutdown": lambda self: None})()
    fake_manager = manager or FakeManager()
    app.api._seedream_api_instance = SeedreamAPI(fake_manager, media_resolver=MissingResolver())
    window = _FakeCloseWindow()
    app.window = window
    app.api.set_window(window)
    return app, window, fake_manager


def test_window_close_idle_allows_close_without_warning(runtime_config_path):
    app, window, manager = _make_close_app()
    manager.active_count = 0

    result = app.on_window_closing()

    assert result is None
    assert window.scripts == []


def test_window_close_with_active_attempts_cancels_and_warns(runtime_config_path):
    app, window, manager = _make_close_app()
    manager.active_count = 3

    result = app.on_window_closing()

    assert result is False
    assert window.warning_dispatched.wait(timeout=1)
    assert len(window.scripts) == 1
    assert "seedream-close-requested" in window.scripts[0]
    assert '"count": 3' in window.scripts[0]


def test_window_close_without_seedream_manager_allows_close(runtime_config_path):
    from backend.main import MainApp

    app = MainApp()
    app.api._process_api_instance = type("Process", (), {"shutdown": lambda self: None})()
    app.window = _FakeCloseWindow()

    # No Seedream manager was ever created (user never opened image generation).
    result = app.on_window_closing()

    assert result is None


def test_seedream_confirm_exit_sets_flag_and_destroys_window(runtime_config_path):
    app, window, manager = _make_close_app()
    manager.active_count = 1

    # First close attempt is intercepted.
    assert app.on_window_closing() is False

    result = app.api.seedream_confirm_exit()

    assert result == {"success": True}
    assert app.api._seedream_exit_confirmed is True
    assert window.destroyed == 1
    # After confirmation, closing is allowed.
    assert app.on_window_closing() is None


def test_seedream_confirm_exit_is_idempotent(runtime_config_path):
    app, window, _manager = _make_close_app()

    app.api.seedream_confirm_exit()
    app.api.seedream_confirm_exit()

    # destroy is called exactly once; repeated clicks do not repeat cleanup.
    assert window.destroyed == 1
    assert app.api._seedream_exit_confirmed is True


def test_window_close_does_not_send_paid_requests(runtime_config_path):
    app, _window, manager = _make_close_app()
    manager.active_count = 2

    app.on_window_closing()

    # Only an active-count read happened; no batch creation or generation call.
    assert [call[0] for call in manager.calls] == ["reclassify", "active_count"]


def test_window_close_after_exit_still_runs_existing_cleanup(runtime_config_path):
    app, _window, manager = _make_close_app()
    manager.active_count = 1

    # User confirms exit -> destroy -> closed event runs on_window_closed.
    app.api.seedream_confirm_exit()
    app.on_window_closed()

    # Existing cleanup (Seedance, Seedream, process shutdown) still executes.
    assert app.api._seedream_api_instance is not None


# ---------------------------------------------------------------------------
# Issue #7: Regeneration draft, safe delete, board metadata
# ---------------------------------------------------------------------------


class _RegenManager(FakeManager):
    """Fake manager that returns a batch with a real request for draft tests."""

    def __init__(self, request: dict) -> None:
        super().__init__()
        self._request = request
        self.create_called = False

    def get_batch(self, local_id):
        self.calls.append(("get", local_id))
        return {
            "local_id": local_id,
            "request": self._request,
            "status": "completed",
            "sequence": "",
            "attempts": [],
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }

    def get_regeneration_draft(self, local_id):
        self.calls.append(("get_regeneration_draft", local_id))
        return {"request": self._request}

    def create_batch(self, request):
        self.create_called = True
        self.calls.append(("create", request))
        return {
            "local_id": "new-batch",
            "request": request.to_dict() if hasattr(request, "to_dict") else request,
            "status": "generating",
            "sequence": "",
            "attempts": [],
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }


def test_seedream_get_regeneration_draft_returns_original_request(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    request = {
        "prompt": "pixel art hero",
        "model": "pro",
        "resolution": "1K",
        "ratio": "16:9",
        "count": 3,
    }
    manager = _RegenManager(request)
    api = SeedreamAPI(manager, media_resolver=MissingResolver())

    result = api.get_regeneration_draft("batch-1")

    assert result["success"] is True
    draft = result["data"]["request"]
    assert draft["prompt"] == "pixel art hero"
    assert draft["model"] == "pro"
    assert draft["resolution"] == "1K"
    assert draft["ratio"] == "16:9"
    assert draft["count"] == 3
    # Only a draft read happened - no batch creation.
    assert "create" not in [call[0] for call in manager.calls]
    assert manager.create_called is False


def test_seedream_get_regeneration_draft_does_not_require_api_key(runtime_config_path):
    """Restoring a draft must not require an API key since it makes no paid call."""
    from backend.api.seedream_api import SeedreamAPI

    # No api_key configured.
    manager = _RegenManager({"prompt": "hero", "model": "pro", "resolution": "1K", "ratio": "16:9", "count": 1})
    api = SeedreamAPI(manager, media_resolver=MissingResolver())

    result = api.get_regeneration_draft("batch-1")
    assert result["success"] is True


def test_seedream_get_regeneration_draft_returns_not_found_for_missing_batch(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    class NotFoundManager(FakeManager):
        def get_regeneration_draft(self, local_id):
            raise FileNotFoundError("not found")

    api = SeedreamAPI(NotFoundManager(), media_resolver=MissingResolver())
    result = api.get_regeneration_draft("missing")
    assert result["success"] is False
    assert result["error"]["code"] == "NOT_FOUND"


class _DeleteManager(FakeManager):
    def __init__(self, *, active: bool = False) -> None:
        super().__init__()
        self._active = active
        self.deleted: list[str] = []

    def delete_batch(self, local_id):
        self.calls.append(("delete", local_id))
        if self._active:
            raise ValueError("Cannot delete a batch with active generation attempts")
        self.deleted.append(local_id)


def test_seedream_delete_batch_delegates_to_manager(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    manager = _DeleteManager(active=False)
    api = SeedreamAPI(manager, media_resolver=MissingResolver())

    result = api.delete_batch("batch-1")

    assert result["success"] is True
    assert manager.deleted == ["batch-1"]


def test_seedream_delete_batch_rejected_when_active(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    manager = _DeleteManager(active=True)
    api = SeedreamAPI(manager, media_resolver=MissingResolver())

    result = api.delete_batch("batch-1")

    assert result["success"] is False
    assert result["error"]["code"] == "INVALID_REQUEST"
    assert manager.deleted == []


def test_seedream_list_batches_returns_envelope(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    class ListManager(FakeManager):
        def list_batches(self):
            self.calls.append(("list", None))
            return [
                {
                    "local_id": "b1",
                    "request": {"prompt": "hero", "model": "pro", "resolution": "1K", "ratio": "16:9", "count": 2},
                    "status": "completed",
                    "sequence": "",
                    "attempts": [],
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                }
            ]

    api = SeedreamAPI(ListManager(), media_resolver=MissingResolver())
    result = api.list_batches()

    assert result["success"] is True
    assert len(result["batches"]) == 1
    assert result["batches"][0]["local_id"] == "b1"
    assert result["batches"][0]["status"] == "completed"


def test_seedream_create_accepts_reference_image(runtime_config_path, tmp_path):
    from backend.api.seedream_api import SeedreamAPI

    save_app_config({"seedance": {"api_key": "secret-key"}})
    manager = FakeManager()
    api = SeedreamAPI(manager, media_resolver=MissingResolver())
    source = tmp_path / "reference.png"
    Image.new("RGB", (64, 64), "#3156d9").save(source, format="PNG")

    result = api.create_batch({"prompt": "hero", "model": "pro", "resolution": "1K", "ratio": "16:9", "reference_image": str(source)})

    assert result["success"] is True
    assert manager.calls[0][0] == "create"
    assert manager.calls[0][1].reference_image == str(source)


def test_seedream_create_rejects_missing_reference_image_file(runtime_config_path, tmp_path):
    from backend.api.seedream_api import SeedreamAPI

    save_app_config({"seedance": {"api_key": "secret-key"}})
    manager = FakeManager()
    api = SeedreamAPI(manager, media_resolver=MissingResolver())

    result = api.create_batch(
        {"prompt": "hero", "model": "pro", "resolution": "1K", "ratio": "16:9", "reference_image": str(tmp_path / "missing.png")}
    )

    assert result["success"] is False
    assert result["error"]["code"] == "IMAGE_NOT_FOUND"
    assert manager.calls == []


def test_seedream_select_image_file_returns_dialog_choice(tmp_path):
    from backend.api.seedream_api import SeedreamAPI

    class Window:
        def __init__(self, choice):
            self.choice = choice
            self.options = None

        def create_file_dialog(self, dialog_type, **kwargs):
            self.options = (dialog_type, kwargs)
            return self.choice

    window = Window((str(tmp_path / "picked.png"),))
    api = SeedreamAPI(FakeManager(), window_getter=lambda: window, media_resolver=MissingResolver())

    assert api.select_image_file() == str(tmp_path / "picked.png")
    assert "file_types" in window.options[1]

    cancelled = Window(None)
    cancelled_api = SeedreamAPI(FakeManager(), window_getter=lambda: cancelled, media_resolver=MissingResolver())
    assert cancelled_api.select_image_file() is None


def test_seedream_refresh_client_swaps_key_without_replacing_manager(tmp_path, runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI
    from backend.seedream.client import ArkClient

    save_app_config({"seedance": {"api_key": "old-key", "cache_dir": str(tmp_path / "cache")}})
    created: list[str] = []

    def factory(key: str) -> ArkClient:
        created.append(key)
        return ArkClient(key)

    api = SeedreamAPI(client_factory=factory)
    api._ensure_manager()
    manager = api._manager
    assert created == ["old-key"]

    save_app_config({"seedance": {"api_key": "new-key"}})
    api.refresh_client()

    assert created == ["old-key", "new-key"]
    assert api._manager is manager
    assert manager._client._api_key == "new-key"


def test_seedream_refresh_client_is_noop_without_manager(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    save_app_config({"seedance": {"api_key": "secret-key"}})
    created: list[str] = []
    api = SeedreamAPI(client_factory=lambda key: created.append(key))

    api.refresh_client()

    # No manager was built just to swap its client; the first real use reads
    # the fresh config instead.
    assert api._manager is None
    assert created == []


def test_seedream_refresh_client_skips_external_manager(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    save_app_config({"seedance": {"api_key": "secret-key"}})
    manager = FakeManager()
    api = SeedreamAPI(manager, media_resolver=MissingResolver())

    # Injected managers are owned by the caller; refresh must not touch them.
    api.refresh_client()
    assert api._manager is manager


def test_seedream_retired_default_falls_back_without_rewriting_config(runtime_config_path):
    from backend.api.seedream_api import SeedreamAPI

    runtime_config_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_config_path.write_text(json.dumps({"seedream": {"default_model": "lite", "default_resolution": "2K"}}))
    before = runtime_config_path.read_bytes()
    api = SeedreamAPI(FakeManager(), media_resolver=MissingResolver())
    settings = api.get_settings()["settings"]
    assert settings["default_model"] == "pro"
    assert settings["default_resolution"] == "2K"
    assert runtime_config_path.read_bytes() == before
    result = api.save_settings({"default_model": "lite", "default_resolution": "2K"})
    assert result["error"]["code"] == "UNSUPPORTED_MODEL"
    assert runtime_config_path.read_bytes() == before
