"""GPU acquisition observed through the desktop processing API and real HTTP."""

import hashlib
import json
import os
import threading
import zipfile
from contextlib import nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from types import SimpleNamespace

import pytest

from backend.api.process_api import ProcessAPI
from backend.core import gpu_runtime
from src.utils import file_operations
from tests.test_file_operations import windows_error


def wait_finished(api):
    # Join background work before fixture teardown; assertions use the public API.
    api._gpu_prepare_future.result(timeout=10)
    return api.get_gpu_runtime_status()


@pytest.fixture(autouse=True)
def compatible_gpu(monkeypatch):
    monkeypatch.setattr(ProcessAPI, "detect_gpu_compatibility", lambda _self: {"state": "compatible"})


@pytest.fixture
def small_gpu_download(monkeypatch, tmp_path):
    from backend.core import birefnet_onnx
    from tests.test_resumable_model_workflow import Response

    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr("sys.platform", "win32")
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w") as wheel:
        wheel.writestr("fixture.txt", "GPU component")
    payload = archive.getvalue()
    component = {
        "filename": "a.whl",
        "size": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "url": "https://official/a",
        "mirror_url": "https://mirror/a",
    }
    monkeypatch.setattr(gpu_runtime, "GPU_COMPONENTS", (component,))
    monkeypatch.setattr(birefnet_onnx, "weights_available", lambda *_args: True)
    probe = SimpleNamespace(request=lambda _request: {"cuda_nodes": 1})
    monkeypatch.setattr(gpu_runtime, "GPUWorker", lambda *_args, **_kwargs: nullcontext(probe))
    monkeypatch.setattr(file_operations.time, "sleep", lambda _seconds: None)
    requests = []

    def get(url, **_kwargs):
        requests.append(url)
        return Response(payload, headers={"ETag": '"fixture"', "Content-Length": str(len(payload))})

    monkeypatch.setattr("requests.get", get)
    return gpu_runtime.runtime_cache_dir() / component["filename"], payload, requests


@pytest.mark.parametrize(
    ("filename", "winerror"), [("a.whl.download.json", 5), ("a.whl", 32), ("download-state.json", 5)]
)
def test_transient_windows_conflicts_do_not_interrupt_gpu_preparation(
    monkeypatch, tmp_path, small_gpu_download, filename, winerror
):
    wheel, payload, requests = small_gpu_download
    replace = os.replace
    conflicts = 0

    def replace_after_release(source, target):
        nonlocal conflicts
        checkpoint = target.name.endswith(".download.json")
        if (
            target.name == filename
            and conflicts < 5
            and (not checkpoint or json.loads(source.read_text(encoding="utf-8")).get("received"))
        ):
            conflicts += 1
            raise windows_error(winerror)
        return replace(source, target)

    monkeypatch.setattr("os.replace", replace_after_release)
    api = ProcessAPI(projects_root=tmp_path)
    try:
        api.prepare_gpu_runtime(source="aliyun")
        status = wait_finished(api)
        assert status["phase"] == "ready"
        assert status["downloaded_bytes"] == len(payload)
        assert conflicts == 5
        assert requests == ["https://mirror/a"]
        assert wheel.read_bytes() == payload
    finally:
        api.shutdown()


def test_gpu_preparation_reuses_wheel_when_final_checkpoint_fails(monkeypatch, tmp_path, small_gpu_download):
    wheel, payload, requests = small_gpu_download
    replace = os.replace
    blocked = True

    def replace_with_locked_checkpoint(source, target):
        if (
            blocked
            and target.name == "a.whl.download.json"
            and json.loads(source.read_text(encoding="utf-8")).get("received") == len(payload)
        ):
            raise windows_error(5)
        return replace(source, target)

    monkeypatch.setattr("os.replace", replace_with_locked_checkpoint)
    api = ProcessAPI(projects_root=tmp_path)
    try:
        api.prepare_gpu_runtime(source="aliyun")
        assert wait_finished(api)["phase"] == "failed"
        assert wheel.with_suffix(".whl.part").read_bytes() == payload

        blocked = False
        api.prepare_gpu_runtime(source="aliyun")
        assert wait_finished(api)["phase"] == "ready"
        assert wheel.read_bytes() == payload
        assert requests == ["https://mirror/a"]
    finally:
        api.shutdown()


def test_persistent_progress_file_conflict_reports_gpu_preparation_failure(monkeypatch, tmp_path, small_gpu_download):
    _, _, requests = small_gpu_download
    replace = os.replace

    def replace_with_locked_progress(source, target):
        if target.name == "download-state.json":
            raise windows_error(5)
        return replace(source, target)

    monkeypatch.setattr("os.replace", replace_with_locked_progress)
    api = ProcessAPI(projects_root=tmp_path)
    try:
        api.prepare_gpu_runtime(source="aliyun")
        status = wait_finished(api)
        assert status["phase"] == "failed"
        assert status["error"]["code"] == "GPU_DOWNLOAD_FAILED"
        assert requests == []
    finally:
        api.shutdown()


@pytest.mark.parametrize("state", ["no_nvidia", "unsupported", "driver", "unknown"])
def test_ineligible_hardware_does_not_start_a_download(monkeypatch, tmp_path, small_gpu_download, state):
    _, _, requests = small_gpu_download
    api = ProcessAPI(projects_root=tmp_path)
    monkeypatch.setattr(api, "detect_gpu_compatibility", lambda: {"state": state})
    try:
        status = api.prepare_gpu_runtime(source="huawei")
        assert status["device"] == {"state": state}
        assert status["phase"] == "needs_download"
        assert api._gpu_prepare_future is None
        assert requests == []
        assert not gpu_runtime.runtime_cache_dir().exists()
    finally:
        api.shutdown()


def test_huawei_resolves_pinned_wheel_and_is_remembered(monkeypatch, tmp_path, small_gpu_download):
    from tests.test_resumable_model_workflow import Response

    wheel, payload, _ = small_gpu_download
    record = dict(gpu_runtime.GPU_COMPONENTS[0], name="test-component")
    monkeypatch.setattr(gpu_runtime, "GPU_COMPONENTS", (record,))
    index_url = "https://repo.huaweicloud.com/repository/pypi/simple/test-component/"
    file_url = "https://cdn.example/files/a.whl"
    links = (
        '<a href="https://cdn.example/files/other.whl">other</a>'
        '<a href="https://cdn.example/wrong/a.whl#sha256=bad">bad digest</a>'
        f'<a href="//cdn.example/files/a.whl#sha256={record["sha256"]}">correct</a>'
    )
    calls = []

    def get(url, **_kwargs):
        calls.append(url)
        if url == index_url:
            return nullcontext(SimpleNamespace(url=url, text=links, raise_for_status=lambda: None))
        assert url == file_url
        return Response(payload, headers={"Content-Length": str(len(payload))})

    monkeypatch.setattr("requests.get", get)
    api = ProcessAPI(projects_root=tmp_path)
    try:
        api.prepare_gpu_runtime(source="huawei")
        status = wait_finished(api)
        assert status["phase"] == "ready", status["error"]
        assert status["source"] == "huawei"
        assert wheel.read_bytes() == payload
        assert calls == [index_url, file_url]

        api.prepare_gpu_runtime(source="huawei")
        assert wait_finished(api)["phase"] == "ready"
        assert calls == [index_url, file_url]
    finally:
        api.shutdown()


@pytest.mark.parametrize("initial_source", ["aliyun", "tuna"])
@pytest.mark.parametrize("action", ["cancel", "shutdown", "network"])
def test_multifile_restart_changes_source_and_retains_valid_prefix(monkeypatch, tmp_path, action, initial_source):
    from tests.test_resumable_model_workflow import Response

    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr(
        gpu_runtime,
        "GPU_COMPONENTS",
        tuple(
            dict(
                filename=name + ".whl",
                size=3,
                sha256=hashlib.sha256(data).hexdigest(),
                url="https://official/" + name,
                mirror_url="https://mirror/" + name,
            )
            for name, data in [("a", b"abc"), ("b", b"xyz")]
        ),
    )
    written, proceed = threading.Event(), threading.Event()

    class Partial(Response):
        def iter_content(self, _size):
            yield b"x"
            written.set()
            assert proceed.wait(3)
            if action == "network":
                import requests

                raise requests.ConnectionError("interrupted")
            yield b"yz"

    responses = iter(
        [
            Response(b"abc"),
            Partial(b""),
            Response(
                b"yz",
                206,
                {
                    "ETag": '"abc-v1"',
                    "Content-Range": "bytes 1-2/3",
                    "Content-Length": "2",
                },
            ),
        ]
    )
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs["headers"]))
        return next(responses)

    monkeypatch.setattr("requests.get", get)
    api = ProcessAPI(projects_root=tmp_path)
    try:
        api.prepare_gpu_runtime(source=initial_source)
        assert written.wait(3)
        assert api.get_gpu_runtime_status()["downloaded_bytes"] == 4
        assert api.get_gpu_runtime_status()["source"] == "aliyun"
        if action == "cancel":
            api.cancel_gpu_runtime_prepare()
        elif action == "shutdown":
            api.shutdown()
        proceed.set()
        wait_finished(api)
        assert api.get_gpu_runtime_status()["phase"] == ("failed" if action == "network" else "paused")
        api.shutdown()
        api = ProcessAPI(projects_root=tmp_path)
        assert api.get_gpu_runtime_status()["downloaded_bytes"] == 4
        assert api.get_gpu_runtime_status()["source"] == "aliyun"
        assert len(calls) == 2
        api.prepare_gpu_runtime(source="pypi")
        wait_finished(api)
        assert calls[-1][0] == "https://official/b"
        assert calls[-1][1]["Range"] == "bytes=1-"
        assert len(calls) == 3
        assert api.get_gpu_runtime_status()["downloaded_bytes"] == 6
    finally:
        proceed.set()
        api.shutdown()


def test_bad_component_retries_only_bad_file_and_rejects_foreign_source(monkeypatch, tmp_path):
    from tests.test_resumable_model_workflow import Response

    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr(
        gpu_runtime,
        "GPU_COMPONENTS",
        tuple(
            dict(
                filename=name + ".whl",
                size=3,
                sha256=hashlib.sha256(data).hexdigest(),
                url="https://official/" + name,
                mirror_url="https://mirror/" + name,
            )
            for name, data in [("a", b"abc"), ("b", b"xyz")]
        ),
    )
    calls = []
    responses = iter([Response(b"abc"), Response(b"bad"), Response(b"xyz")])

    def get(url, **kwargs):
        calls.append(url)
        return next(responses)

    monkeypatch.setattr("requests.get", get)
    api = ProcessAPI(projects_root=tmp_path)
    try:
        with pytest.raises(ValueError):
            api.prepare_gpu_runtime(source="modelscope")
        with pytest.raises(ValueError):
            api.prepare_gpu_runtime(source="tsinghua")
        api.prepare_gpu_runtime(source="aliyun")
        wait_finished(api)
        assert api.get_gpu_runtime_status()["phase"] == "failed"
        assert api.get_gpu_runtime_status()["downloaded_bytes"] == 3
        api.prepare_gpu_runtime(source="pypi")
        wait_finished(api)
        assert calls == ["https://mirror/a", "https://mirror/b", "https://official/b"]
        assert api.get_gpu_runtime_status()["source"] == "pypi"
    finally:
        api.shutdown()


def test_explicit_source_downloads_fixed_files_once_and_remembers_source(monkeypatch, tmp_path):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            data = b"abc" if self.path.endswith("a") else b"xyz"
            self.send_response(200)
            self.send_header("Content-Length", "3")
            self.send_header("ETag", '"fixed"')
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr("sys.platform", "win32")
    base = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setattr(
        gpu_runtime,
        "GPU_COMPONENTS",
        tuple(
            dict(
                filename=name + ".whl",
                size=3,
                sha256=hashlib.sha256(data).hexdigest(),
                url=base + "/official/" + name,
                mirror_url=base + "/mirror/" + name,
            )
            for name, data in [("a", b"abc"), ("b", b"xyz")]
        ),
    )
    api = ProcessAPI(projects_root=tmp_path)
    try:
        assert api.get_gpu_runtime_status()["total_bytes"] == 6
        assert requests == []
        api.prepare_gpu_runtime(source="aliyun")
        wait_finished(api)
        status = api.get_gpu_runtime_status()
        assert status["downloaded_bytes"] == 6, status["error"]
        assert status["source"] == "aliyun"
        assert requests == ["/mirror/a", "/mirror/b"]
        api.shutdown()
        api = ProcessAPI(projects_root=tmp_path)
        assert api.get_gpu_runtime_status()["source"] == "aliyun"
        api.prepare_gpu_runtime(source="pypi")
        wait_finished(api)
        assert requests == ["/mirror/a", "/mirror/b"]
        assert api.get_gpu_runtime_status()["source"] == "pypi"
    finally:
        api.shutdown()
        server.shutdown()
        server.server_close()
