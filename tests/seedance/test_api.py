from __future__ import annotations

import base64
import json
from io import BytesIO
from pathlib import Path

from PIL import Image

from backend.seedance.client import ArkAPIError
from src.utils.app_config import load_app_config, save_app_config


class FakeManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.event_sink = None
        self.started = 0
        self.stopped = 0

    def set_event_sink(self, sink):
        self.event_sink = sink

    def start(self):
        self.started += 1

    def shutdown(self):
        self.stopped += 1

    def create(self, request):
        self.calls.append(("create", request))
        return {"local_id": "task 1", "input_urls": {}, "output_urls": {}}

    def list_tasks(self):
        self.calls.append(("list", None))
        return [{"local_id": "task 1", "input_urls": {}, "output_urls": {}}]

    def get_task(self, local_id):
        self.calls.append(("get", local_id))
        return {"local_id": local_id, "input_urls": {}, "output_urls": {}}

    def local_asset_paths(self, local_id):
        self.calls.append(("local_asset_paths", local_id))
        return {"input_paths": {}, "output_paths": {}}

    def cancel(self, local_id):
        self.calls.append(("cancel", local_id))
        return {"local_id": local_id, "input_urls": {}, "output_urls": {}}

    def retry_generation(self, local_id):
        self.calls.append(("retry", local_id))
        return {"local_id": local_id, "input_urls": {}, "output_urls": {}}

    def retry_download(self, local_id):
        self.calls.append(("retry_download", local_id))
        return {"local_id": local_id, "input_urls": {}, "output_urls": {}}

    def continue_generation(self, local_id):
        self.calls.append(("continue", local_id))
        return {"local_id": "continued", "input_urls": {}, "output_urls": {}}

    def delete_task(self, local_id, allow_protected=False):
        self.calls.append(("delete", (local_id, allow_protected)))

    def handoff(self, local_id, role, action):
        self.calls.append(("handoff", (local_id, role, action)))
        return {"project_id": "hero/run", "task": {"local_id": local_id, "input_urls": {}, "output_urls": {}}}

    def cache_status(self):
        return {"task_count": 1}

    def clean_cache(self, older_than_days=None):
        self.calls.append(("clean", older_than_days))
        return {"tasks_cleared": 1}


class FakeClient:
    def __init__(self, result=None):
        self.result = {} if result is None else result
        self.page_sizes: list[int] = []

    def list_tasks(self, page_size=1):
        self.page_sizes.append(page_size)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class MissingResolver:
    def resolve(self, _local_id, _asset_key):
        raise FileNotFoundError


def _image(path: Path) -> Path:
    Image.new("RGB", (300, 300), "white").save(path)
    return path


def _png_data_url(size: tuple[int, int], color: str = "green") -> str:
    buffer = BytesIO()
    Image.new("RGBA", size, color).save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def test_seedance_image_editor_preserves_source_and_saves_full_size_copy(tmp_path, runtime_config_path):
    from backend.api.seedance_api import SeedanceAPI

    cache_root = tmp_path / "cache"
    save_app_config({"seedance": {"cache_dir": str(cache_root)}})
    source = tmp_path / "source.jpg"
    Image.new("RGB", (120, 80), "red").save(source)
    api = SeedanceAPI(FakeManager(), media_resolver=MissingResolver())

    editable = api.get_editable_image(str(source))
    assert editable["success"] is True
    assert editable["data"]["width"] == 120
    assert editable["data"]["height"] == 80
    assert editable["data"]["image_data_url"].startswith("data:image/png;base64,")
    assert editable["data"]["edit_source_data_url"].startswith("data:image/png;base64,")

    generation_layout = {
        "source_width": 120,
        "source_height": 80,
        "measured_top": 8,
        "measured_bottom": 64,
        "measured_height": 56,
        "target_height": 32,
        "character_height_ratio": 0.4,
        "bottom_distance": 12,
        "bottom_margin_ratio": 0.15,
        "scale": 32 / 56,
    }
    edit_source_data_url = _png_data_url((120, 80), "blue")
    saved = api.save_edited_image(
        str(source), _png_data_url((120, 80)), edit_source_data_url, generation_layout
    )
    assert saved["success"] is True
    destination = Path(saved["data"]["path"])
    assert destination.parent == cache_root / "ai-video-cache" / "edited-inputs"
    assert destination.suffix == ".png"
    assert Image.open(destination).size == (120, 80)
    assert Image.open(source).getpixel((0, 0))[0] > 200

    reopened = api.get_editable_image(str(destination))
    assert reopened["data"]["generation_layout"] == generation_layout
    assert reopened["data"]["edit_source_data_url"] == edit_source_data_url

    mismatch = api.save_edited_image(
        str(source), _png_data_url((60, 40)), _png_data_url((120, 80))
    )
    assert mismatch["success"] is False
    assert "dimensions" in mismatch["error"]["message"].lower()


def test_seedance_settings_migrate_removed_4k_default(runtime_config_path):
    from backend.api.seedance_api import SeedanceAPI

    save_app_config({"seedance": {"default_model": "standard", "default_resolution": "4k"}})

    assert SeedanceAPI(FakeManager()).get_settings()["default_resolution"] == "1080p"


def test_seedance_settings_never_return_api_key(runtime_config_path):
    from backend.api.seedance_api import SeedanceAPI

    save_app_config({"seedance": {"api_key": "secret-key"}})
    settings = SeedanceAPI(FakeManager()).get_settings()

    assert "api_key" not in settings
    assert settings["api_key_configured"] is True
    assert settings["cache_dir"].endswith("cache")


def test_seedance_settings_merge_without_key_and_clear_with_none(runtime_config_path):
    from backend.api.seedance_api import SeedanceAPI

    save_app_config({"seedance": {"api_key": "secret-key", "default_duration": 5}})
    api = SeedanceAPI(FakeManager(), media_resolver=MissingResolver())

    saved = api.save_settings({"default_duration": 6})
    assert saved["success"] is True
    assert saved["settings"]["api_key_configured"] is True
    assert load_app_config()["seedance"]["api_key"] == "secret-key"
    assert load_app_config()["seedance"]["default_duration"] == 6

    assert api.save_settings({"api_key": None})["success"] is True
    assert load_app_config()["seedance"]["api_key"] == ""


def test_seedance_create_delegates_and_decorates_local_media_url(tmp_path, runtime_config_path):
    from backend.api.seedance_api import SeedanceAPI

    class Resolver:
        def resolve(self, _local_id, _asset_key):
            return _image(tmp_path / "persisted.png")

    save_app_config({"seedance": {"api_key": "secret-key"}})
    manager = FakeManager()
    api = SeedanceAPI(manager, media_base_url="http://127.0.0.1:8080", media_resolver=Resolver())
    result = api.create_task({"first_frame": str(_image(tmp_path / "first.png"))})

    assert result["success"] is True
    assert manager.calls[0][0] == "create"
    assert result["task"]["input_urls"]["first_frame"] == "http://127.0.0.1:8080/seedance-media/task%201/first_frame"


def test_seedance_continue_is_an_explicit_safe_facade(runtime_config_path):
    from backend.api.seedance_api import SeedanceAPI

    save_app_config({"seedance": {"api_key": "secret-key"}})
    manager = FakeManager()
    result = SeedanceAPI(manager, media_resolver=MissingResolver()).continue_task("source-task")

    assert result["success"] is True
    assert manager.calls == [("continue", "source-task")]
    assert "first_frame" not in result["task"]


def test_seedance_regeneration_draft_restores_cached_inputs_without_creating_task(tmp_path, runtime_config_path):
    from backend.api.seedance_api import SeedanceAPI

    first_frame = _image(tmp_path / "first.png")
    last_frame = _image(tmp_path / "last.png")

    class Manager(FakeManager):
        def get_task(self, local_id):
            self.calls.append(("get", local_id))
            return {
                "local_id": local_id,
                "request": {
                    "prompt": "Hero attack",
                    "model": "mini",
                    "resolution": "720p",
                    "ratio": "16:9",
                    "duration": 4,
                    "generate_audio": False,
                    "return_last_frame": True,
                    "priority": 2,
                    "execution_expires_after": 3600,
                },
            }

        def local_asset_paths(self, local_id):
            self.calls.append(("local_asset_paths", local_id))
            return {
                "input_paths": {"first_frame": str(first_frame), "last_frame": str(last_frame)},
                "output_paths": {},
            }

    manager = Manager()
    result = SeedanceAPI(
        manager,
        media_base_url="http://127.0.0.1:8080",
        media_resolver=MissingResolver(),
    ).get_regeneration_draft("task 1")

    assert result["success"] is True
    assert result["data"]["request"]["first_frame"] == str(first_frame)
    assert result["data"]["request"]["last_frame"] == str(last_frame)
    assert result["data"]["request"]["prompt"] == "Hero attack"
    assert result["data"]["preview_urls"] == {
        "first_frame": "http://127.0.0.1:8080/seedance-media/task%201/first_frame",
        "last_frame": "http://127.0.0.1:8080/seedance-media/task%201/last_frame",
    }
    assert manager.calls == [("get", "task 1"), ("local_asset_paths", "task 1")]


def test_seedance_continuation_draft_uses_returned_last_frame_and_clears_prompt(tmp_path, runtime_config_path):
    from backend.api.seedance_api import SeedanceAPI

    returned_last_frame = _image(tmp_path / "returned-last.png")

    class Manager(FakeManager):
        def get_task(self, local_id):
            self.calls.append(("get", local_id))
            return {
                "local_id": local_id,
                "request": {
                    "prompt": "Hero attack",
                    "model": "mini",
                    "resolution": "720p",
                    "ratio": "16:9",
                    "duration": 4,
                    "generate_audio": False,
                    "return_last_frame": True,
                    "priority": 2,
                    "execution_expires_after": 3600,
                },
            }

        def local_asset_paths(self, local_id):
            self.calls.append(("local_asset_paths", local_id))
            return {
                "input_paths": {"first_frame": "unused"},
                "output_paths": {"returned_last_frame": str(returned_last_frame)},
            }

    manager = Manager()
    result = SeedanceAPI(
        manager,
        media_base_url="http://127.0.0.1:8080",
        media_resolver=MissingResolver(),
    ).get_continuation_draft("task 1")

    assert result["success"] is True
    assert result["data"]["request"] == {
        "prompt": "",
        "model": "mini",
        "resolution": "720p",
        "ratio": "16:9",
        "duration": 4,
        "generate_audio": False,
        "return_last_frame": True,
        "priority": 2,
        "execution_expires_after": 3600,
        "first_frame": str(returned_last_frame),
        "last_frame": None,
    }
    assert result["data"]["preview_urls"] == {
        "first_frame": "http://127.0.0.1:8080/seedance-media/task%201/returned_last_frame",
    }
    assert manager.calls == [("get", "task 1"), ("local_asset_paths", "task 1")]


def test_seedance_preflight_uses_full_payload_validation_without_creating_task(
    tmp_path, runtime_config_path, monkeypatch
):
    from backend.api import seedance_api
    from backend.api.seedance_api import SeedanceAPI
    from backend.seedance.validation import ValidationError

    manager = FakeManager()
    api = SeedanceAPI(manager, media_resolver=MissingResolver())
    request = {"first_frame": str(_image(tmp_path / "first.png"))}

    assert api.validate_request(request) == {"success": True, "data": {"valid": True}}
    monkeypatch.setattr(
        seedance_api,
        "build_api_payload",
        lambda _request: (_ for _ in ()).throw(ValidationError("payload", "PAYLOAD_TOO_LARGE", "too large")),
    )
    rejected = api.validate_request(request)

    assert rejected["success"] is False
    assert rejected["error"] == {"code": "PAYLOAD_TOO_LARGE", "message": "too large", "field": "payload"}
    assert manager.calls == []


def test_seedance_api_serializes_validation_and_ark_errors(tmp_path, runtime_config_path):
    from backend.api.seedance_api import SeedanceAPI

    api = SeedanceAPI(FakeManager(), media_resolver=MissingResolver())
    validation = api.create_task({"first_frame": str(tmp_path / "missing.png")})
    assert validation == {
        "success": False,
        "error": {"code": "IMAGE_NOT_FOUND", "message": "Image file does not exist", "field": "first_frame"},
    }

    api._client_factory = lambda _key: FakeClient(ArkAPIError(401, "AUTH", "bad key"))
    save_app_config({"seedance": {"api_key": "secret-key"}})
    connection = api.test_connection()
    assert connection["success"] is False
    assert connection["error"] == {"code": "AUTH", "message": "bad key", "field": None}
    assert "secret-key" not in json.dumps(connection)


def test_seedance_frontend_task_payloads_recursively_redact_configured_api_key(runtime_config_path):
    from backend.api.seedance_api import SeedanceAPI

    secret = "secret-key"
    save_app_config({"seedance": {"api_key": secret}})
    leaky_task = {
        "local_id": "task-1",
        "error": {"message": f"remote echoed {secret}"},
        "sync_status": {
            "error": {"detail": f"nested {secret}"},
            "attempts": ["safe", {"message": secret}],
        },
        "remote": {
            "content": {"diagnostic": f"content-like {secret}"},
            "error": secret,
            "mapping": {secret: "first", "[REDACTED]": "already-safe", f"nested-{secret}": "nested-safe"},
        },
    }
    manager = FakeManager()
    manager.list_tasks = lambda: [leaky_task]
    manager.get_task = lambda _local_id: leaky_task
    manager.cancel = lambda _local_id: leaky_task
    api = SeedanceAPI(manager, media_resolver=MissingResolver())

    responses = [api.list_tasks(), api.get_task("task-1"), api.cancel_task("task-1")]

    for response in responses:
        serialized = json.dumps(response)
        assert secret not in serialized
        assert "[REDACTED]" in serialized
    assert responses[0]["tasks"][0]["remote"]["mapping"] == {
        "[REDACTED]": "first",
        "[REDACTED]#2": "already-safe",
        "nested-[REDACTED]": "nested-safe",
    }
    assert leaky_task["sync_status"]["attempts"][1]["message"] == secret


def test_seedance_event_payload_recursively_redacts_configured_api_key(runtime_config_path):
    from backend.api.seedance_api import SeedanceAPI

    secret = "secret-key"
    save_app_config({"seedance": {"api_key": secret}})

    class Window:
        def __init__(self):
            self.scripts = []

        def evaluate_js(self, script):
            self.scripts.append(script)

    manager = FakeManager()
    api = SeedanceAPI(manager, media_resolver=MissingResolver())
    api.set_window(Window())
    manager.event_sink(
        "seedance-task-updated",
        {
            "local_id": "task-1",
            "sync_status": {"nested": [f"event {secret}"], f"event-key-{secret}": "safe"},
            "error": {"message": secret},
        },
    )

    assert secret not in json.dumps(api._window.scripts)
    assert "[REDACTED]" in api._window.scripts[0]


def test_seedance_connection_uses_one_list_request_only_when_configured(runtime_config_path):
    from backend.api.seedance_api import SeedanceAPI

    client = FakeClient()
    api = SeedanceAPI(FakeManager(), client_factory=lambda _key: client)
    assert api.test_connection()["error"]["code"] == "API_KEY_NOT_CONFIGURED"
    assert client.page_sizes == []

    save_app_config({"seedance": {"api_key": "secret-key"}})
    assert api.test_connection() == {"success": True, "data": {"configured": True}}
    assert client.page_sizes == [1]


def test_seedance_connection_can_test_an_unsaved_api_key(runtime_config_path):
    from backend.api.seedance_api import SeedanceAPI

    received_keys: list[str] = []
    client = FakeClient()
    api = SeedanceAPI(FakeManager(), client_factory=lambda key: received_keys.append(key) or client)

    assert api.test_connection("draft-key") == {"success": True, "data": {"configured": True}}
    assert received_keys == ["draft-key"]
    assert load_app_config()["seedance"].get("api_key") in {None, ""}


def test_seedance_connection_redacts_an_unsaved_api_key_from_errors(runtime_config_path):
    from backend.api.seedance_api import SeedanceAPI

    api = SeedanceAPI(
        FakeManager(),
        client_factory=lambda _key: FakeClient(ArkAPIError(401, "AUTH", "draft-key is invalid")),
    )

    result = api.test_connection("draft-key")
    assert result["success"] is False
    assert "draft-key" not in json.dumps(result)


def test_seedance_event_sink_uses_json_and_start_requires_a_window(runtime_config_path):
    from backend.main import API

    class Window:
        def __init__(self):
            self.scripts = []

        def evaluate_js(self, script):
            self.scripts.append(script)

    api = API()
    manager = FakeManager()
    api._seedance_api_instance = __import__("backend.api.seedance_api", fromlist=["SeedanceAPI"]).SeedanceAPI(
        manager,
        media_resolver=MissingResolver(),
    )

    window = Window()
    api.set_window(window)
    manager.event_sink("seedance-task-updated", {"label": "quoted </script> \"value\""})

    assert manager.started == 1
    serialized = window.scripts[0].split("detail: ", 1)[1].rsplit(" }));", 1)[0]
    assert json.loads(serialized)["label"] == 'quoted </script> "value"'


def test_window_close_stops_seedance_manager_dispatcher(runtime_config_path):
    from backend.main import MainApp

    app = MainApp()
    app.api._process_api_instance = type("Process", (), {"shutdown": lambda self: None})()
    manager = FakeManager()
    app.api._seedance_api_instance = __import__("backend.api.seedance_api", fromlist=["SeedanceAPI"]).SeedanceAPI(
        manager,
        media_resolver=MissingResolver(),
    )

    app.on_window_closed()

    assert manager.stopped == 1


def test_seedance_image_dialog_is_restricted_and_cancel_is_safe(monkeypatch, runtime_config_path):
    from backend.api.seedance_api import SeedanceAPI

    class Window:
        def create_file_dialog(self, *_args, **kwargs):
            self.file_types = kwargs["file_types"]
            return ()

    window = Window()
    api = SeedanceAPI(FakeManager(), window_getter=lambda: window)
    assert api.select_image_file() is None
    assert "*.heic" in window.file_types[0]
    assert "*.heif" in window.file_types[0]


def test_seedance_save_video_uses_system_dialog_and_copies_cached_file(tmp_path, runtime_config_path):
    from backend.api.seedance_api import SeedanceAPI

    source = tmp_path / "cached-video.mp4"
    source.write_bytes(b"cached video")
    destination = tmp_path / "saved-video.mp4"

    class Resolver:
        def resolve(self, local_id, asset_key):
            assert (local_id, asset_key) == ("task-1", "video")
            return source

    class Window:
        def create_file_dialog(self, dialog_type, **kwargs):
            self.dialog_type = dialog_type
            self.options = kwargs
            return (str(destination),)

    window = Window()
    api = SeedanceAPI(FakeManager(), window_getter=lambda: window, media_resolver=Resolver())

    result = api.save_video("task-1")

    assert result == {"success": True, "data": {"saved": True, "path": str(destination)}}
    assert destination.read_bytes() == b"cached video"
    assert window.options["save_filename"] == "seedance-task-1.mp4"
    assert window.options["file_types"] == ("MP4 video (*.mp4)",)
