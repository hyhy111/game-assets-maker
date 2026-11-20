"""Model recovery tested through the application's public preparation API."""

import time

import pytest
import requests

from backend.api.process_api import ProcessAPI
from backend.core import birefnet_onnx

MODEL = "birefnet-lite-onnx"


def wait(api, phases=("ready", "failed", "paused")):
    for _ in range(400):
        status = api.get_model_status(MODEL)
        if status["phase"] in phases:
            return status
        time.sleep(0.005)
    raise AssertionError(status)


class Response:
    def __init__(self, body, status=200, headers=None, interrupt=False):
        self.body, self.status_code = body, status
        self.headers = headers or {"ETag": '"abc-v1"', "Content-Length": "3"}
        self.interrupt = interrupt

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def raise_for_status(self):
        pass

    def iter_content(self, _size):
        yield self.body
        if self.interrupt:
            raise requests.ConnectionError("connection interrupted")


@pytest.fixture
def model(tmp_path, monkeypatch):
    import onnxruntime

    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path / "中文 空格"))
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    monkeypatch.setattr(birefnet_onnx, "WEIGHTS_BYTES", 3)
    monkeypatch.setattr(
        birefnet_onnx, "WEIGHTS_SHA256", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    monkeypatch.setattr(onnxruntime, "InferenceSession", lambda *_a, **_k: object())
    return tmp_path


def test_restart_remembers_source_and_resumes_only_on_user_request(model, monkeypatch):
    calls = []
    responses = iter(
        [
            Response(b"a", interrupt=True),
            Response(b"bc", 206, {"ETag": '"abc-v1"', "Content-Range": "bytes 1-2/3", "Content-Length": "2"}),
        ]
    )

    def get(url, **kwargs):
        calls.append((url, kwargs.get("headers", {})))
        return next(responses)

    monkeypatch.setattr("requests.get", get)
    api = ProcessAPI(projects_root=model)
    api.preload_model(MODEL, source="huggingface")
    assert wait(api, ("failed",))["downloaded_bytes"] == 1
    api.shutdown()
    api = ProcessAPI(projects_root=model)
    try:
        status = api.get_model_status(MODEL)
        assert status["phase"] == "paused"
        assert status["source"] == "huggingface"
        assert status["downloaded_bytes"] == 1
        assert api.preload_model(MODEL)["phase"] == "paused"
        assert len(calls) == 1
        api.retry_model(MODEL, source="huggingface")
        assert wait(api)["phase"] == "ready"
        assert calls[1][1]["Range"] == "bytes=1-"
        assert calls[1][1]["If-Range"] == '"abc-v1"'
        assert birefnet_onnx.model_path().read_bytes() == b"abc"
    finally:
        api.shutdown()


@pytest.mark.parametrize("kind", ["ignore", "bad_range", "changed", "weak", "switch"])
def test_unproven_range_is_restarted_without_appending(model, monkeypatch, kind):
    calls = []
    first_headers = {"ETag": 'W/"abc"' if kind == "weak" else '"abc-v1"'}
    if kind == "ignore" or kind == "weak":
        continuation = [Response(b"abc")]
    else:
        continuation = [
            Response(
                b"bc",
                206,
                {
                    "ETag": '"different"' if kind == "changed" else '"abc-v1"',
                    "Content-Range": "bytes 0-1/3" if kind == "bad_range" else "bytes 1-2/3",
                },
            ),
            Response(b"abc"),
        ]
        if kind == "switch":
            continuation = continuation[:1]
    responses = iter([Response(b"a", headers=first_headers, interrupt=True), *continuation])

    def get(url, **kwargs):
        calls.append((url, kwargs["headers"]))
        return next(responses)

    monkeypatch.setattr("requests.get", get)
    api = ProcessAPI(projects_root=model)
    try:
        api.preload_model(MODEL, source="modelscope")
        assert wait(api, ("failed",))["phase"] == "failed"
        api.retry_model(MODEL, source="huggingface" if kind == "switch" else "modelscope")
        assert wait(api)["phase"] == "ready"
        assert birefnet_onnx.model_path().read_bytes() == b"abc"
        if kind == "weak":
            assert "Range" not in calls[1][1]
        elif kind in ("bad_range", "changed"):
            assert "Range" not in calls[2][1]
        elif kind == "switch":
            assert "huggingface.co" in calls[1][0]
    finally:
        api.shutdown()


@pytest.mark.parametrize("action", ["cancel", "shutdown"])
def test_pause_and_shutdown_keep_prefix_for_restart(model, monkeypatch, action):
    import threading

    written = threading.Event()
    proceed = threading.Event()

    class BlockedResponse(Response):
        def iter_content(self, _size):
            yield b"a"
            written.set()
            assert proceed.wait(3)
            yield b"bc"

    responses = iter([BlockedResponse(b""), Response(b"bc", 206, {"ETag": '"abc-v1"', "Content-Range": "bytes 1-2/3"})])
    monkeypatch.setattr("requests.get", lambda *_a, **_k: next(responses))
    api = ProcessAPI(projects_root=model)
    try:
        api.preload_model(MODEL, source="modelscope")
        assert written.wait(2)
        if action == "cancel":
            api.cancel_model_download(MODEL)
        else:
            api.shutdown()
        proceed.set()
        assert wait(api)["phase"] == "paused"
    finally:
        proceed.set()
        api.shutdown()
    api = ProcessAPI(projects_root=model)
    try:
        assert api.get_model_status(MODEL)["downloaded_bytes"] == 1
        api.retry_model(MODEL, source="modelscope")
        assert wait(api)["phase"] == "ready"
    finally:
        api.shutdown()


def test_valid_model_is_reused_and_source_is_validated_before_persistence(model, monkeypatch):
    path = birefnet_onnx.model_path()
    path.parent.mkdir(parents=True)
    path.write_bytes(b"abc")
    monkeypatch.setattr("requests.get", lambda *_a, **_k: pytest.fail("valid file must not download"))
    api = ProcessAPI(projects_root=model)
    try:
        with pytest.raises(ValueError):
            api.preload_model(MODEL, source="pypi")
        api.preload_model(MODEL)
        assert wait(api)["phase"] == "ready"
        assert path.read_bytes() == b"abc"
    finally:
        api.shutdown()


@pytest.mark.parametrize("body", [b"abd", b"abcd", b"ab"])
def test_rejected_content_reports_actual_recoverable_bytes(model, monkeypatch, body):
    monkeypatch.setattr("requests.get", lambda *_a, **_k: Response(body, headers={}))
    api = ProcessAPI(projects_root=model)
    try:
        api.preload_model(MODEL, source="modelscope")
        status = wait(api)
        assert status["phase"] == "failed"
        assert status["downloaded_bytes"] == 0
        assert not birefnet_onnx.model_path().exists()
    finally:
        api.shutdown()


def test_windows_locked_destination_can_retry_verified_file_without_network(model, monkeypatch):
    import os

    destination = birefnet_onnx.model_path()
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"old")
    original_replace = os.replace
    locked = True

    def replace(source, target):
        if target == destination and locked:
            raise PermissionError("Windows sharing violation")
        return original_replace(source, target)

    monkeypatch.setattr("os.replace", replace)
    monkeypatch.setattr("requests.get", lambda *_a, **_k: Response(b"abc"))
    api = ProcessAPI(projects_root=model)
    try:
        api.preload_model(MODEL, source="modelscope")
        assert wait(api)["phase"] == "failed"
        assert destination.read_bytes() == b"old"
        locked = False
        monkeypatch.setattr("requests.get", lambda *_a, **_k: pytest.fail("verified bytes should be reused"))
        api.retry_model(MODEL, source="modelscope")
        assert wait(api)["phase"] == "ready"
        assert destination.read_bytes() == b"abc"
    finally:
        api.shutdown()


def test_modified_partial_is_restarted_instead_of_appended(model, monkeypatch):
    headers = []
    responses = iter([Response(b"a", interrupt=True), Response(b"abc")])

    def get(_url, **kwargs):
        headers.append(kwargs["headers"])
        return next(responses)

    monkeypatch.setattr("requests.get", get)
    api = ProcessAPI(projects_root=model)
    api.preload_model(MODEL, source="modelscope")
    assert wait(api, ("failed",))["phase"] == "failed"
    api.shutdown()
    destination = birefnet_onnx.model_path()
    destination.with_name(destination.name + ".part").write_bytes(b"z")
    api = ProcessAPI(projects_root=model)
    try:
        assert api.get_model_status(MODEL)["downloaded_bytes"] == 0
        api.retry_model(MODEL, source="modelscope")
        assert wait(api)["phase"] == "ready"
        assert "Range" not in headers[1]
    finally:
        api.shutdown()


def test_model_source_is_remembered_and_filtered_for_u2net(model, monkeypatch):
    monkeypatch.setattr("requests.get", lambda *_a, **_k: Response(b"abc"))
    api = ProcessAPI(projects_root=model)
    try:
        with pytest.raises(ValueError, match="source"):
            api.preload_model(MODEL, source="pypi")
        api.preload_model(MODEL, source="huggingface")
        assert wait(api)["phase"] == "ready"
        assert api.get_model_status("u2net")["source"] == "modelscope"
    finally:
        api.shutdown()
    api = ProcessAPI(projects_root=model)
    try:
        assert api.get_model_status(MODEL)["source"] == "huggingface"
        api.preload_model(MODEL)
        assert wait(api)["phase"] == "ready"
    finally:
        api.shutdown()
