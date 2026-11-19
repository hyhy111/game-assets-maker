"""Task lifecycle through ProcessAPI and the external GPU protocol."""

import sys
import time

import numpy as np
import pytest
from PIL import Image

from backend.api.process_api import ProcessAPI
from backend.core import gpu_runtime
from tests.test_model_preloader import FakeModelLoader


@pytest.fixture
def workflow(tmp_path, monkeypatch):
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    monkeypatch.setattr(gpu_runtime, "runtime_status", lambda: {"phase": "ready"})
    project = tmp_path / "hero/idle"
    (project / "cache").mkdir(parents=True)
    frames = project / "output/01_frames"
    frames.mkdir(parents=True)
    for index in range(3):
        Image.new("RGBA", (24, 16), "green").save(frames / f"{index}.png")
    for directory in ["02_no_bg", "03_hole_punched"]:
        output = project / "output" / directory
        output.mkdir()
        Image.new("RGBA", (24, 16), (255, 0, 0, 42)).save(output / "old.png")
    cpu_calls = []

    class NativeSession:
        def __init__(self, path, **kwargs):
            self.path = path

        def get_inputs(self):
            return [type("Input", (), {"name": "input"})()]

        def run(self, outputs, inputs):
            assert inputs["input"].shape == (1, 3, 1024, 1024)
            cpu_calls.append(self.path)
            return [np.zeros((1, 1, 1024, 1024), dtype=np.float32)]

    import onnxruntime

    from backend.core import birefnet_onnx

    monkeypatch.setattr(onnxruntime, "InferenceSession", NativeSession)
    monkeypatch.setattr(birefnet_onnx, "weights_available", lambda *args: True)
    birefnet_onnx._session.cache_clear()

    def model_path(model=birefnet_onnx.MODEL_ID):
        path = tmp_path / (model + ".onnx")
        if not path.exists():
            path.write_bytes(b"fixture")
        return path

    monkeypatch.setattr(birefnet_onnx, "model_path", model_path)
    api = ProcessAPI(model_loader=FakeModelLoader(available=True), projects_root=tmp_path)
    yield api, project, cpu_calls
    api.shutdown()
    birefnet_onnx._session.cache_clear()


def prepare(api, model):
    api.preload_model(model)
    for _ in range(200):
        if api.get_model_status(model)["phase"] == "ready":
            return
        time.sleep(0.01)
    pytest.fail("Model not ready")


@pytest.mark.parametrize("model", ["birefnet-lite-onnx", "birefnet-standard-onnx"])
@pytest.mark.parametrize(
    "code", ["GPU_MODEL_INITIALIZATION_FAILED", "GPU_OUT_OF_MEMORY", "GPU_PROCESS_FAILED", "GPU_PROTOCOL_FAILED"]
)
def test_failed_gpu_frame_and_remaining_frames_retry_same_model_on_cpu(workflow, monkeypatch, tmp_path, model, code):
    api, project, cpu_calls = workflow
    script = tmp_path / "worker.py"
    script.write_text(
        "import json,sys\nfor line in sys.stdin:\n print(json.dumps({'error': {'code': "
        + repr(code)
        + ", 'message': 'fixture failure'}}),flush=True)\n"
    )
    worker_type = gpu_runtime.GPUWorker
    workers = []

    def worker(**kwargs):
        result = worker_type(tmp_path, command=[sys.executable, str(script)], **kwargs)
        workers.append(result)
        return result

    monkeypatch.setattr(gpu_runtime, "GPUWorker", worker)
    prepare(api, model)
    task = api.start_processing("hero/idle", 2, {"model": model})
    api.tasks[task].future.result(timeout=10)
    status = api.get_task_status(task)
    assert status["status"] == "completed"
    assert status["execution_device"] == "cpu"
    assert status["gpu_fallback"]["code"] == code
    assert len(cpu_calls) == 3
    assert all(("standard" in path) == ("standard" in model) for path in cpu_calls)
    assert len(workers) == 1 and workers[0].process.poll() is not None
    assert api.get_step_params("hero/idle", 2)["result_model"] == model
    assert sorted(p.name for p in (project / "output/02_no_bg").glob("*.png")) == ["0.png", "1.png", "2.png"]


def test_malformed_worker_response_is_classified_and_reaped(tmp_path):
    worker = gpu_runtime.GPUWorker(tmp_path, command=[sys.executable, "-c", "input();print('[]',flush=True);input()"])
    try:
        with pytest.raises(gpu_runtime.GPURuntimeError) as error:
            worker.request({"op": "probe"})
        assert error.value.code == "GPU_PROTOCOL_FAILED"
        assert worker.process.poll() is not None
    finally:
        worker.close()


def test_waiting_for_gpu_slot_can_be_cancelled_without_starting_process(tmp_path):
    import threading

    with gpu_runtime.GPUWorker(tmp_path, command=[sys.executable, "-c", "input();input()"]):
        cancel = threading.Event()
        outcome = []

        def wait():
            try:
                with gpu_runtime.GPUWorker(tmp_path, command=[sys.executable, "-c", "input()"], cancel_event=cancel):
                    outcome.append("started")
            except gpu_runtime.GPURuntimeError as error:
                outcome.append(error.code)

        thread = threading.Thread(target=wait)
        thread.start()
        time.sleep(0.15)
        cancel.set()
        thread.join(timeout=3)
        assert not thread.is_alive()
        assert outcome == ["GPU_CANCELLED"]


@pytest.mark.parametrize("cancel", [False, True])
def test_cancel_or_cpu_failure_keeps_transparency_postprocessing_and_edits(workflow, monkeypatch, tmp_path, cancel):
    api, project, cpu_calls = workflow
    import onnxruntime

    marker = tmp_path / "entered"
    script = tmp_path / "worker.py"
    if cancel:
        script.write_text(
            "from pathlib import Path\nimport sys,time\ninput()\nPath("
            + repr(str(marker))
            + ").write_text('entered')\ntime.sleep(60)\n"
        )
    else:
        script.write_text(
            "import json,sys\nfor line in sys.stdin:\n"
            " print(json.dumps({'error': {'code': 'GPU_OUT_OF_MEMORY', 'message': 'allocation failed'}}),flush=True)\n"
        )

        def failed(*args):
            raise RuntimeError("CPU also failed")

        monkeypatch.setattr(onnxruntime, "InferenceSession", failed)
    worker_type = gpu_runtime.GPUWorker
    workers = []

    def worker(**kwargs):
        result = worker_type(tmp_path, command=[sys.executable, str(script)], **kwargs)
        workers.append(result)
        return result

    monkeypatch.setattr(gpu_runtime, "GPUWorker", worker)
    model = "birefnet-standard-onnx"
    prepare(api, model)
    api.save_step_params("hero/idle", 2, {"processed": True, "result_model": "u2net"})
    api.save_step_params("hero/idle", 3, {"processed": True, "enabled": True})
    before = {str(p.relative_to(project)): p.read_bytes() for p in project.rglob("*") if p.is_file()}
    task = api.start_processing("hero/idle", 2, {"model": model})
    if cancel:
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists()
        assert api.cancel_task(task)
    api.tasks[task].future.result(timeout=10)
    assert api.get_task_status(task)["status"] == ("cancelled" if cancel else "failed")
    assert all((project / path).read_bytes() == content for path, content in before.items())
    assert not list((project / "output").glob(".step2-*"))
    assert len(workers) == 1 and workers[0].process.poll() is not None
    assert workers[0].process.stdin.closed and workers[0].process.stdout.closed
    assert not cpu_calls


def test_gpu_retries_only_failed_and_later_frames(workflow, monkeypatch, tmp_path):
    api, project, cpu_calls = workflow
    script = tmp_path / "worker.py"
    script.write_text("""import json,sys
from PIL import Image
for index,line in enumerate(sys.stdin):
 request=json.loads(line)
 if index == 0:
  Image.new('RGBA',(24,16),(0,0,255,77)).save(request['output'])
  print(json.dumps({'output':request['output'],'finite_alpha':True}),flush=True)
 else:
  print(json.dumps({'error':{'code':'GPU_OUT_OF_MEMORY','message':'allocation failed'}}),flush=True)
""")
    worker_type = gpu_runtime.GPUWorker
    monkeypatch.setattr(
        gpu_runtime,
        "GPUWorker",
        lambda **kwargs: worker_type(tmp_path, command=[sys.executable, str(script)], **kwargs),
    )
    prepare(api, "birefnet-lite-onnx")
    task = api.start_processing("hero/idle", 2, {"model": "birefnet-lite-onnx"})
    api.tasks[task].future.result(timeout=10)
    assert api.get_task_status(task)["status"] == "completed"
    assert len(cpu_calls) == 2
    with Image.open(project / "output/02_no_bg/0.png") as first:
        assert first.getpixel((0, 0))[3] == 77
    with Image.open(project / "output/02_no_bg/1.png") as retried:
        assert retried.getpixel((0, 0))[3] == 127


def test_concurrent_projects_wait_for_gpu_and_shutdown_reaps_owner(workflow, monkeypatch, tmp_path):
    import shutil

    api, project, cpu_calls = workflow
    shutil.copytree(project, tmp_path / "hero/run")
    marker = tmp_path / "entered"
    script = tmp_path / "worker.py"
    script.write_text(
        "from pathlib import Path\nimport sys,time\ninput()\nPath("
        + repr(str(marker))
        + ").write_text('entered')\ntime.sleep(60)\n"
    )
    worker_type = gpu_runtime.GPUWorker
    workers = []

    def worker(**kwargs):
        result = worker_type(tmp_path, command=[sys.executable, str(script)], **kwargs)
        workers.append(result)
        return result

    monkeypatch.setattr(gpu_runtime, "GPUWorker", worker)
    prepare(api, "birefnet-lite-onnx")
    prepare(api, "birefnet-standard-onnx")
    first = api.start_processing("hero/idle", 2, {"model": "birefnet-lite-onnx"})
    deadline = time.monotonic() + 5
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert marker.exists()
    second = api.start_processing("hero/run", 2, {"model": "birefnet-standard-onnx"})
    time.sleep(0.2)
    assert len(workers) == 1
    assert api.cancel_task(second)
    api.tasks[second].future.result(timeout=3)
    assert api.get_task_status(second)["status"] == "cancelled"
    api.shutdown()
    assert workers[0].process.poll() is not None
    assert workers[0].process.stdin.closed and workers[0].process.stdout.closed
    api.tasks[first].future.result(timeout=10)
    assert api.get_task_status(first)["status"] == "cancelled"
    assert workers[0].process.poll() is not None
    assert not cpu_calls
    with worker_type(tmp_path, command=[sys.executable, "-c", "input();input()"]):
        pass


def test_gpu_spawn_failure_retries_cpu_without_poisoning_model(workflow, monkeypatch):
    api, project, cpu_calls = workflow

    def unavailable(**kwargs):
        raise gpu_runtime.GPURuntimeError("GPU_NATIVE_LOAD_FAILED", "DLL unavailable")

    monkeypatch.setattr(gpu_runtime, "GPUWorker", unavailable)
    prepare(api, "birefnet-standard-onnx")
    task = api.start_processing("hero/idle", 2, {"model": "birefnet-standard-onnx"})
    api.tasks[task].future.result(timeout=10)
    assert api.get_task_status(task)["status"] == "completed"
    assert api.get_task_status(task)["gpu_fallback"]["code"] == "GPU_NATIVE_LOAD_FAILED"
    assert api.get_model_status("birefnet-standard-onnx")["phase"] == "ready"
    assert len(cpu_calls) == 3
