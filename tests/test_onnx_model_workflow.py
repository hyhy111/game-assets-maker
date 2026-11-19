"""ONNX model validation through the processing service."""

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


def test_windows_rejects_removed_model_without_preparing_it(tmp_path, monkeypatch):
    from backend.core import birefnet_onnx
    from src.utils.background_models import LITE_MODEL, background_models

    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    removed_model = "birefnet-standard-onnx"
    assert background_models() == ("u2net", LITE_MODEL)
    api = ProcessAPI(projects_root=tmp_path)
    try:
        for call in (api.get_model_status, api.preload_model, api.retry_model, api.prepare_gpu_runtime):
            with pytest.raises(ValueError, match="Unsupported"):
                call(removed_model)
        with pytest.raises(ValueError, match="Unsupported"):
            api.start_processing("hero/idle", 2, {"model": removed_model})
        with pytest.raises(ValueError, match="Unsupported"):
            birefnet_onnx.model_path(removed_model)
        assert not list(tmp_path.glob("runtime"))
    finally:
        api.shutdown()


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


@pytest.mark.parametrize("mutation", ["delete", "wrong_digest", "wrong_size"])
@pytest.mark.parametrize("entrypoint", ["get_model_status", "preload_model", "start_processing"])
def test_ready_model_changed_on_disk_is_rejected(tmp_path, monkeypatch, mutation, entrypoint):
    import onnxruntime

    from backend.core import birefnet_onnx

    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    digest = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    monkeypatch.setattr(birefnet_onnx, "WEIGHTS_BYTES", 3)
    monkeypatch.setattr(birefnet_onnx, "WEIGHTS_SHA256", digest)
    model = birefnet_onnx.MODEL_ID
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
