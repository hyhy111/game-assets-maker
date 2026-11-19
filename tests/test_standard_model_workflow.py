"""Standard ONNX selection and results through the processing service."""

import time

import pytest

from backend.api.process_api import ProcessAPI


def wait_ready(api, model):
    for _ in range(200):
        status = api.get_model_status(model)
        if status["phase"] in ("ready", "failed"):
            return status
        time.sleep(0.01)
    pytest.fail("Model preparation did not finish")


@pytest.mark.parametrize("standard_body, expected", [(b"xyz", "ready"), (b"abc", "failed"), (b"xy", "failed")])
def test_two_models_keep_independent_downloads_and_reuse_cache(tmp_path, monkeypatch, standard_body, expected):
    import hashlib

    import numpy as np
    import onnxruntime
    from PIL import Image

    from backend.api.project_api import ProjectAPI
    from backend.core import birefnet_onnx

    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    monkeypatch.setattr(birefnet_onnx, "WEIGHTS_BYTES", 3)
    monkeypatch.setattr(birefnet_onnx, "WEIGHTS_SHA256", hashlib.sha256(b"abc").hexdigest())
    monkeypatch.setitem(
        birefnet_onnx.MODEL_SPECS,
        "birefnet-standard-onnx",
        {
            "bytes": 3,
            "sha256": hashlib.sha256(b"xyz").hexdigest(),
            "revision": "fixture",
            "repository": "onnx-community/BiRefNet-ONNX",
        },
    )
    downloads = []

    class Response:
        status_code = 200
        headers = {}

        def __init__(self, url):
            self.body = standard_body if "/BiRefNet-ONNX/" in url else b"abc"
            downloads.append(url)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def raise_for_status(self):
            pass

        def iter_content(self, _size):
            yield self.body

    class NativeSession:
        def __init__(self, path, **_kwargs):
            self.standard = "standard" in path

        def get_inputs(self):
            return [type("Input", (), {"name": "input"})()]

        def run(self, _outputs, inputs):
            tensor = inputs["input"]
            assert tensor.shape == (1, 3, 1024, 1024) and tensor.dtype == np.float32
            return [np.full((1, 1, 1024, 1024), 0 if self.standard else 2, dtype=np.float32)]

    monkeypatch.setattr("requests.get", lambda url, **_kwargs: Response(url))
    monkeypatch.setattr(onnxruntime, "InferenceSession", NativeSession)
    api = ProcessAPI(projects_root=tmp_path / "projects")
    lite, standard = "birefnet-lite-onnx", "birefnet-standard-onnx"
    project_api = ProjectAPI(projects_root=tmp_path / "projects")
    project_api.create_project("hero", "idle")
    frame = tmp_path / "projects/hero/idle/output/01_frames/frame.png"
    Image.new("RGBA", (24, 16), (0, 255, 0, 128)).save(frame)
    try:
        assert api.preload_model(standard)["phase"] == "needs_download"
        assert downloads == []
        with pytest.raises(ValueError, match="source"):
            api.preload_model(standard, source="github")
        api.preload_model(lite, source="modelscope")
        assert wait_ready(api, lite)["phase"] == "ready"
        api.preload_model(standard, source="huggingface")
        assert wait_ready(api, standard)["phase"] == expected
        assert api.get_model_status(lite)["phase"] == "ready"
        assert len(downloads) == 2
        if expected == "failed":
            with pytest.raises(RuntimeError, match="MODEL_NOT_READY"):
                api.start_processing("hero/idle", 2, {"model": standard})
            return
        for model, alpha in [(lite, 112), (standard, 63), (lite, 112)]:
            task = api.start_processing("hero/idle", 2, {"model": model, "defringe_enabled": True})
            api.tasks[task].future.result(timeout=5)
            assert api.get_task_status(task)["status"] == "completed"
            assert project_api.get_project("hero/idle")["steps"]["2"]["result_model"] == model
            assert api.get_step_params("hero/idle", 3)["enabled"] is False
            with Image.open(frame.parents[1] / "02_no_bg/frame.png") as result:
                assert result.mode == "RGBA" and result.size == (24, 16)
                assert result.getpixel((0, 0))[3] == alpha
        assert api.save_step_params("hero/idle", 2, {"model": standard})
        assert project_api.get_project("hero/idle")["steps"]["2"]["result_model"] == lite
    finally:
        api.shutdown()
    reopened = ProcessAPI(projects_root=tmp_path / "projects")
    try:
        for model in [standard, lite]:
            reopened.preload_model(model)
            assert wait_ready(reopened, model)["phase"] == "ready"
        assert len(downloads) == 2
        assert reopened.get_step_params("hero/idle", 2)["model"] == standard
        assert reopened.save_step_params("hero/idle", 3, {"enabled": True})
        assert reopened.get_step_params("hero/idle", 3)["enabled"] is True
    finally:
        reopened.shutdown()


def test_standard_selection_survives_reopen_without_replacing_results(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    project = tmp_path / "hero/idle"
    (project / "cache").mkdir(parents=True)
    output = project / "output/02_no_bg/frame.png"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"existing transparent frame")
    api = ProcessAPI(projects_root=tmp_path)
    try:
        assert api.save_step_params("hero/idle", 2, {"model": "birefnet-standard-onnx"})
    finally:
        api.shutdown()
    reopened = ProcessAPI(projects_root=tmp_path)
    try:
        assert reopened.get_step_params("hero/idle", 2)["model"] == "birefnet-standard-onnx"
        assert reopened.get_model_status("birefnet-standard-onnx")["phase"] == "needs_download"
        assert output.read_bytes() == b"existing transparent frame"
    finally:
        reopened.shutdown()


def test_macos_rejects_windows_onnx_choices(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    api = ProcessAPI(projects_root=tmp_path)
    try:
        for model in ["birefnet-lite-onnx", "birefnet-standard-onnx"]:
            with pytest.raises(ValueError, match="Unsupported"):
                api.preload_model(model, source="modelscope")
            with pytest.raises(ValueError, match="Unsupported"):
                api.get_model_status(model)
            with pytest.raises(ValueError, match="Unsupported"):
                api.start_processing("hero/idle", 2, {"model": model})
    finally:
        api.shutdown()


@pytest.mark.parametrize("model", ["birefnet-lite-onnx", "birefnet-standard-onnx"])
@pytest.mark.parametrize("mutation", ["delete", "wrong_digest", "wrong_size"])
@pytest.mark.parametrize("entrypoint", ["get_model_status", "preload_model", "start_processing"])
def test_ready_model_changed_on_disk_is_rejected(tmp_path, monkeypatch, model, mutation, entrypoint):
    import onnxruntime

    from backend.core import birefnet_onnx

    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    digest = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    monkeypatch.setattr(birefnet_onnx, "WEIGHTS_BYTES", 3)
    monkeypatch.setattr(birefnet_onnx, "WEIGHTS_SHA256", digest)
    monkeypatch.setitem(
        birefnet_onnx.MODEL_SPECS, model, {"bytes": 3, "sha256": digest, "repository": "fixture", "revision": "fixture"}
    )
    monkeypatch.setattr(onnxruntime, "InferenceSession", lambda *_args, **_kwargs: object())
    path = birefnet_onnx.model_path(model)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"abc")
    api = ProcessAPI(projects_root=tmp_path / "projects")
    try:
        api.preload_model(model)
        assert wait_ready(api, model)["phase"] == "ready"
        path.unlink()
        if mutation != "delete":
            path.write_bytes(b"xyz" if mutation == "wrong_digest" else b"ab")
        if entrypoint == "start_processing":
            with pytest.raises(RuntimeError, match="MODEL_NOT_READY"):
                api.start_processing("hero/idle", 2, {"model": model})
        else:
            assert getattr(api, entrypoint)(model)["phase"] == "needs_download"
        assert api.get_model_status(model)["phase"] == "needs_download"
    finally:
        api.shutdown()
