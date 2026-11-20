"""Windows Lite background removal through the public processing boundary."""

import pytest

from backend.api.process_api import ProcessAPI
from tests.test_model_preloader import FakeModelLoader


@pytest.mark.parametrize("body, phase", [(b"abc", "ready"), (b"abd", "failed"), (b"ab", "failed")])
def test_explicit_lite_download_validates_content_before_ready(tmp_path, monkeypatch, body, phase):
    import time

    import onnxruntime

    from backend.core import birefnet_onnx

    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    # The transport fixture stands in for the pinned artifact, independently of inference.
    monkeypatch.setattr(birefnet_onnx, "WEIGHTS_BYTES", 3)
    monkeypatch.setattr(
        birefnet_onnx, "WEIGHTS_SHA256", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )

    class Response:
        status_code = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def raise_for_status(self):
            pass

        def iter_content(self, _size):
            yield body

    monkeypatch.setattr("requests.get", lambda *_args, **_kwargs: Response())
    monkeypatch.setattr(onnxruntime, "InferenceSession", lambda *_args, **_kwargs: object())
    api = ProcessAPI(projects_root=tmp_path)
    try:
        with pytest.raises(ValueError, match="source"):
            api.preload_model("birefnet-lite-onnx", source="github")
        api.preload_model("birefnet-lite-onnx", source="modelscope")
        for _ in range(200):
            status = api.get_model_status("birefnet-lite-onnx")
            if status["phase"] in ("ready", "failed"):
                break
            time.sleep(0.01)
        assert status["phase"] == phase
        if phase == "failed":
            assert status["error"]["code"] == "MODEL_DOWNLOAD_FAILED"
            with pytest.raises(RuntimeError, match="MODEL_NOT_READY"):
                api.start_processing("hero/idle", 2, {"model": "birefnet-lite-onnx"})
        else:
            assert status["total_bytes"] == 3
            assert birefnet_onnx.model_path().read_bytes() == b"abc"
    finally:
        api.shutdown()


def test_windows_lite_waits_for_explicit_download(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    loader = FakeModelLoader(available=False)
    api = ProcessAPI(model_loader=loader, projects_root=tmp_path)
    try:
        assert api.preload_model("birefnet-lite-onnx")["phase"] == "needs_download"
        assert loader.download_calls == 0
        with pytest.raises(RuntimeError, match="MODEL_NOT_READY"):
            api.start_processing("hero/idle", 2, {"model": "birefnet-lite-onnx"})
        api.preload_model("birefnet-lite-onnx", source="modelscope")
        assert loader.initialize_started.wait(2)
    finally:
        api.shutdown()


def test_windows_unsaved_selection_defaults_to_lite_and_preserves_u2net(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    cache = tmp_path / "hero/idle/cache"
    cache.mkdir(parents=True)
    api = ProcessAPI(projects_root=tmp_path)
    try:
        assert api.get_step_params("hero/idle", 2)["model"] == "birefnet-lite-onnx"
        assert api.save_step_params("hero/idle", 2, {"model": "u2net"})
        assert api.get_step_params("hero/idle", 2)["model"] == "u2net"
        with pytest.raises(ValueError, match="Unsupported"):
            api.get_model_status("birefnet-comfy")
    finally:
        api.shutdown()


@pytest.mark.parametrize("outcome", ["success", "failure", "cancel"])
def test_lite_publishes_only_a_complete_batch(tmp_path, monkeypatch, outcome):
    import json
    import time

    from PIL import Image

    from backend.api.project_api import ProjectAPI

    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    project = tmp_path / "角色 空格/动作"
    (project / "cache").mkdir(parents=True)
    for stage, color in [("01_frames", "green"), ("02_no_bg", "red"), ("03_hole_punched", "blue")]:
        target = project / "output" / stage
        target.mkdir(parents=True)
        Image.new("RGBA", (24, 16), color).save(target / "frame_000001.png")
    (project / "cache/steps_config.json").write_text(
        json.dumps({"step2": {"model": "u2net", "result_model": "u2net"}, "step3": {"processed": True}})
    )
    old = (project / "output/02_no_bg/frame_000001.png").read_bytes()
    api = ProcessAPI(model_loader=FakeModelLoader(available=True), projects_root=tmp_path)

    def infer(path):
        if outcome == "failure":
            raise RuntimeError("inference failed")
        if outcome == "cancel":
            api.cancel_task(next(iter(api.tasks)))
        return Image.new("RGBA", (24, 16), (255, 255, 0, 128))

    monkeypatch.setattr("backend.core.birefnet_onnx.remove_background", infer)
    try:
        api.preload_model("birefnet-lite-onnx")
        for _ in range(200):
            if api.get_model_status("birefnet-lite-onnx")["phase"] == "ready":
                break
            time.sleep(0.01)
        task = api.start_processing("角色 空格/动作", 2, {"model": "birefnet-lite-onnx"})
        api.tasks[task].future.result(timeout=5)
        status = api.get_task_status(task)["status"]
        if outcome == "success":
            assert status == "completed"
            assert (
                ProjectAPI(projects_root=tmp_path).get_project("角色 空格/动作")["steps"]["2"]["result_model"]
                == "birefnet-lite-onnx"
            )
            assert api.get_step_params("角色 空格/动作", 3)["enabled"] is False
            assert not (project / "output/03_hole_punched").exists()
            assert api.save_step_params("角色 空格/动作", 3, {"enabled": True})
            assert api.get_step_params("角色 空格/动作", 3)["enabled"] is True
        else:
            assert status == ("failed" if outcome == "failure" else "cancelled")
            assert (project / "output/02_no_bg/frame_000001.png").read_bytes() == old
            assert (project / "output/03_hole_punched/frame_000001.png").exists()
    finally:
        api.shutdown()
