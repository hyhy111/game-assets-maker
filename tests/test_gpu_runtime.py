"""Public offline GPU preparation contract."""

import pytest

from backend.core.gpu_runtime import activate_runtime, runtime_status


def test_windows_bundle_uses_runtime_beside_executable_and_honors_override(monkeypatch, tmp_path):
    from backend.core.gpu_runtime import runtime_cache_dir

    install_dir = tmp_path / "自定义 GAM 安装"
    launch_dir = tmp_path / "launch"
    launch_dir.mkdir()
    monkeypatch.chdir(launch_dir)
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.executable", str(install_dir / "game-assets-maker.exe"))
    monkeypatch.delenv("GAM_DATA_MODE", raising=False)
    monkeypatch.delenv("GAM_DATA_ROOT", raising=False)

    assert runtime_cache_dir() == install_dir / "runtime" / "cuda13-cp312" / "wheels"

    override = tmp_path / "GPU data"
    monkeypatch.setenv("GAM_DATA_ROOT", str(override))
    assert runtime_cache_dir() == override / "runtime" / "cuda13-cp312" / "wheels"


@pytest.mark.parametrize("mutation", ["delete", "wrong_digest", "wrong_size"])
def test_gpu_adapter_rejects_changed_model_before_sending_frame(monkeypatch, tmp_path, mutation):
    import sys

    import onnxruntime

    from backend.api.process_api import ProcessAPI
    from backend.core import birefnet_onnx, gpu_runtime
    from tests.test_onnx_model_workflow import wait_ready

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
    script = tmp_path / "worker.py"
    marker = tmp_path / "frame-sent"
    script.write_text(
        "import json,sys\nfrom pathlib import Path\n"
        "for line in sys.stdin:\n"
        f" Path({str(marker)!r}).touch()\n"
        " print(json.dumps({'error': {'code': 'GPU_UNEXPECTED_REQUEST', "
        "'message': 'invalid model sent'}}),flush=True)\n"
    )
    api = ProcessAPI(projects_root=tmp_path / "projects")
    try:
        api.preload_model(model)
        assert wait_ready(api, model)["phase"] == "ready"
        with gpu_runtime.GPUWorker(tmp_path, command=[sys.executable, str(script)]) as worker:
            # Mutate after the application's readiness check, at the external process boundary.
            path.unlink()
            if mutation != "delete":
                path.write_bytes(b"xyz" if mutation == "wrong_digest" else b"ab")
            with pytest.raises(gpu_runtime.GPURuntimeError) as error:
                worker.remove_background(tmp_path / "frame.png", model)
            assert error.value.code == "GPU_MODEL_INVALID"
            assert not marker.exists()
    finally:
        api.shutdown()


@pytest.mark.parametrize("preparation_phase", ["ready", "downloading", "failed"])
def test_lite_uses_task_device_snapshot_and_closes_worker(monkeypatch, tmp_path, preparation_phase):
    import time

    from PIL import Image

    from backend.api.process_api import ProcessAPI
    from backend.core import birefnet_onnx, gpu_runtime
    from tests.test_model_preloader import FakeModelLoader

    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    monkeypatch.setattr("sys.platform", "win32")
    project = tmp_path / "hero/idle"
    (project / "cache").mkdir(parents=True)
    frames = project / "output/01_frames"
    frames.mkdir(parents=True)
    for index in range(2):
        Image.new("RGBA", (24, 16), "green").save(frames / f"{index}.png")
    ready = False
    calls = []
    closed = []

    def cpu(path, model=birefnet_onnx.MODEL_ID):
        nonlocal ready
        ready = True
        calls.append(("cpu", model))
        return Image.new("RGBA", (24, 16), (255, 0, 0, 64))

    class Worker:
        def __init__(self, **_kwargs):
            pass

        def remove_background(self, path, model):
            nonlocal ready
            ready = False
            calls.append(("gpu", model))
            return Image.new("RGBA", (24, 16), (0, 0, 255, 128))

        def close(self):
            closed.append(True)

    monkeypatch.setattr(
        gpu_runtime,
        "runtime_status",
        lambda: {"phase": preparation_phase if ready else "needs_download", "gpu_ready": ready},
    )
    monkeypatch.setattr(gpu_runtime, "GPUWorker", Worker)
    monkeypatch.setattr(birefnet_onnx, "remove_background", cpu)
    api = ProcessAPI(model_loader=FakeModelLoader(available=True), projects_root=tmp_path)
    try:
        model = birefnet_onnx.MODEL_ID
        api.preload_model(model)
        for _ in range(200):
            if api.get_model_status(model)["phase"] == "ready":
                break
            time.sleep(0.01)
        for device, alpha in [("cpu", 64), ("gpu", 128)]:
            task = api.start_processing("hero/idle", 2, {"model": model})
            api.tasks[task].future.result(timeout=5)
            assert api.get_task_status(task)["status"] == "completed"
            assert api.get_task_status(task)["execution_device"] == device
            assert calls[-2:] == [(device, model), (device, model)]
            with Image.open(project / "output/02_no_bg/1.png") as result:
                assert result.size == (24, 16) and result.getpixel((0, 0))[3] == alpha
            assert api.get_step_params("hero/idle", 2)["result_model"] == model
        assert len(closed) == 1
    finally:
        api.shutdown()


def test_incomplete_cache_does_not_enable_gpu_or_remove_cpu(monkeypatch, tmp_path):
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path / "中文 用户"))
    result = activate_runtime(cache_dir=tmp_path / "empty")
    assert result["phase"] == "failed"
    assert result["error"]["code"] == "GPU_COMPONENT_INVALID"
    assert runtime_status()["phase"] != "ready"
    assert not (tmp_path / "中文 用户" / "runtime" / "cuda13-cp312" / "active.json").exists()


def test_worker_process_failure_is_reported_and_process_closed(tmp_path):
    import sys

    import pytest

    from backend.core.gpu_runtime import GPURuntimeError, GPUWorker

    with (
        GPUWorker(tmp_path, command=[sys.executable, "-c", "import sys;sys.exit(7)"]) as worker,
        pytest.raises(GPURuntimeError, match="exited"),
    ):
        worker.request({"op": "probe"})
    assert worker.process.poll() is not None


def test_cancelled_preparation_preserves_cache_and_cpu(monkeypatch, tmp_path):
    import threading

    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    cancel = threading.Event()
    cancel.set()
    result = activate_runtime(cache_dir=tmp_path, cancel_event=cancel)
    assert result["phase"] == "paused"
    assert result["error"]["code"] == "GPU_CANCELLED"


def test_worker_cancellation_terminates_blocked_native_process(tmp_path):
    import sys
    import threading

    import pytest

    from backend.core.gpu_runtime import GPURuntimeError, GPUWorker

    cancel = threading.Event()
    with GPUWorker(tmp_path, command=[sys.executable, "-c", "input();input()"], cancel_event=cancel) as worker:
        cancel.set()
        with pytest.raises(GPURuntimeError, match="cancelled"):
            worker.request({"op": "probe"})
        assert worker.process.poll() is not None


def test_public_process_api_reports_component_failure_without_blocking_model(monkeypatch, tmp_path):
    import time

    from backend.api.process_api import ProcessAPI

    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    api = ProcessAPI(projects_root=tmp_path)
    try:
        assert api.get_gpu_runtime_status()["phase"] == "needs_download"
        api.prepare_gpu_runtime()
        deadline = time.monotonic() + 5
        while api.get_gpu_runtime_status()["phase"] not in {"failed", "ready"} and time.monotonic() < deadline:
            time.sleep(0.01)
        assert api.get_gpu_runtime_status()["error"]["code"] == "GPU_COMPONENT_INVALID"
        assert api.get_model_status("birefnet-lite-onnx")["phase"] != "failed"
    finally:
        api.shutdown()


def test_checked_archive_cannot_escape_preparation_directory(monkeypatch, tmp_path):
    import hashlib
    import zipfile

    from backend.core import birefnet_onnx, gpu_runtime

    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path / "user data"))
    wheel = tmp_path / "test.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("../../../escaped.txt", "unsafe")
    monkeypatch.setattr(
        gpu_runtime,
        "GPU_COMPONENTS",
        (
            {
                "filename": wheel.name,
                "size": wheel.stat().st_size,
                "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
            },
        ),
    )
    monkeypatch.setattr(birefnet_onnx, "weights_available", lambda: True)
    result = activate_runtime(cache_dir=tmp_path)
    assert result["error"]["code"] == "GPU_UNPACK_FAILED"
    assert not (tmp_path / "user data" / "escaped.txt").exists()
    assert not list((tmp_path / "user data").rglob("escaped.txt"))


def test_complete_size_with_wrong_digest_is_never_unpacked(monkeypatch, tmp_path):
    from backend.core import gpu_runtime

    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path / "user"))
    wheel = tmp_path / "test.whl"
    wheel.write_bytes(b"wrong")
    monkeypatch.setattr(
        gpu_runtime,
        "GPU_COMPONENTS",
        (
            {
                "filename": wheel.name,
                "size": 5,
                "sha256": "0" * 64,
            },
        ),
    )
    result = activate_runtime(cache_dir=tmp_path)
    assert result["error"]["code"] == "GPU_COMPONENT_INVALID"
    assert not (tmp_path / "user").exists()


def test_ready_runtime_detects_same_size_damage(monkeypatch, tmp_path):
    import hashlib
    import json

    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    root = tmp_path / "runtime" / "cuda13-cp312"
    directory = root / "verified-test"
    directory.mkdir(parents=True)
    library = directory / "library.dll"
    library.write_bytes(b"valid")
    (directory / "verified.json").write_text(
        json.dumps(
            {
                "cuda_nodes": 1,
                "files": [{"path": "library.dll", "size": 5, "sha256": hashlib.sha256(b"valid").hexdigest()}],
            }
        )
    )
    (root / "active.json").write_text(json.dumps({"directory": directory.name}))
    assert runtime_status()["phase"] == "ready"
    import threading

    cancel = threading.Event()
    cancel.set()
    activate_runtime(cache_dir=tmp_path, cancel_event=cancel)
    assert runtime_status()["phase"] == "paused"
    assert runtime_status()["gpu_ready"] is True
    library.write_bytes(b"wrong")
    assert runtime_status()["phase"] != "ready"
    assert runtime_status()["gpu_ready"] is False
