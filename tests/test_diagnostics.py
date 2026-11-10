from __future__ import annotations

import io
import json
import urllib.error
import urllib.request

import pytest

from src.utils.app_config import save_app_config


@pytest.fixture
def diagnostic_root(tmp_path, monkeypatch):
    root = tmp_path / "用户 数据"
    monkeypatch.setenv("GAM_DATA_ROOT", str(root))
    monkeypatch.setenv("GAM_CONFIG", str(root / "config.json"))
    yield root
    import logging

    for channel in ("network", "seedream", "seedance"):
        logger = logging.getLogger(f"gam.diagnostics.{channel}")
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()


@pytest.mark.parametrize("domain", ["seedream", "seedance"])
def test_api_internal_error_records_operation_trace_and_safe_reference(diagnostic_root, domain):
    from backend.api.seedance_api import SeedanceAPI
    from backend.api.seedream_api import SeedreamAPI
    from backend.platform.config import PlatformConfig

    key, token = "private-ark-key", "private-platform-token"
    save_app_config({"seedance": {"api_key": key}, "logger_enabled": False})
    config = PlatformConfig()
    config.set("https://platform.test", token)

    class BrokenManager:
        def list_batches(self):
            raise KeyError(f"bad metadata {key} {token} https://cdn.test/image?signature=private-signature")

        def list_tasks(self):
            return self.list_batches()

    api = (SeedreamAPI if domain == "seedream" else SeedanceAPI)(
        BrokenManager(), platform_config=config, media_resolver=object()
    )
    result = api.list_batches() if domain == "seedream" else api.list_tasks()

    assert not result["success"]
    assert result["error"]["code"] == "INTERNAL_ERROR"
    error_id = result["error"]["error_id"]
    assert error_id in result["error"]["message"]
    log = (diagnostic_root / "logs" / f"{domain}.log").read_text()
    assert error_id in log
    assert "KeyError" in log
    assert "bad metadata" in log
    assert ("list_batches" if domain == "seedream" else "list_tasks") in log
    assert "Traceback" in log
    for secret in (key, token, "private-signature"):
        assert secret not in log
        assert secret not in json.dumps(result)


def test_logged_urlopen_preserves_http_error_body_and_hides_credentials(diagnostic_root, monkeypatch):
    from src.utils.diagnostics import logged_urlopen

    key = "unconfigured-draft-key"
    request = urllib.request.Request(
        "https://cdn.test/file?signature=private-signature", headers={"Authorization": f"Bearer {key}"}
    )
    failure = urllib.error.HTTPError(request.full_url, 403, f"rejected {key}", {}, io.BytesIO(b"original error body"))
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(failure))

    with pytest.raises(urllib.error.HTTPError) as caught, logged_urlopen(request, timeout=1):
        pytest.fail("request must fail")

    assert caught.value is failure
    assert caught.value.read() == b"original error body"
    log = (diagnostic_root / "logs/network.log").read_text()
    assert "403" in log and "cdn.test" in log
    assert key not in log
    assert "private-signature" not in log
    assert "original error body" not in log


def test_stream_failure_is_recorded_and_reraised(diagnostic_root, monkeypatch):
    from src.utils.diagnostics import logged_urlopen

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            raise TimeoutError("stream timed out")

    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: Response())
    with pytest.raises(TimeoutError), logged_urlopen("https://cdn.test/file", timeout=1) as response:
        response.read()
    assert "stream timed out" in (diagnostic_root / "logs/network.log").read_text()


def test_logging_failure_never_masks_the_original_error(diagnostic_root, monkeypatch):
    from src.utils.diagnostics import logged_urlopen

    diagnostic_root.mkdir(parents=True)
    (diagnostic_root / "logs").write_text("blocks log directory")
    failure = TimeoutError("network timed out")
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(failure))
    with pytest.raises(TimeoutError) as caught, logged_urlopen("https://example.test", timeout=1):
        pass
    assert caught.value is failure


def test_frontend_report_bridge_accepts_only_diagnostic_fields(diagnostic_root):
    from backend.main import API

    api = API()
    api._platform_config.set("https://platform.test", "private-platform-token")
    api.report_network_error(
        {
            "method": "POST",
            "url": "https://platform.test/login?token=private-query",
            "http_status": 500,
            "code": 500,
            "error_type": "BusinessError",
            "message": "Bearer private-platform-token unavailable",
            "body": {"password": "private-password"},
            "headers": {"Authorization": "private-header"},
        }
    )
    log = (diagnostic_root / "logs/network.log").read_text()
    assert "POST" in log and "500" in log and "/login" in log
    for secret in ("private-query", "private-platform-token", "private-password", "private-header"):
        assert secret not in log


@pytest.mark.parametrize("domain", ["platform", "seedance", "seedream"])
def test_provider_and_http_200_business_errors_reach_network_log(diagnostic_root, domain):
    from backend.platform.client import HttpResponse as PlatformResponse
    from backend.platform.client import PlatformClient
    from backend.seedance.client import ArkClient as VideoClient
    from backend.seedance.client import HttpResponse as VideoResponse
    from backend.seedream.client import ArkClient as ImageClient
    from backend.seedream.client import HttpResponse as ImageResponse

    class Transport:
        def request(self, *args):
            if domain == "platform":
                return PlatformResponse(200, {}, b'{"code":500,"msg":"quota exceeded"}')
            body = b'{"error":{"code":"InvalidParameter","message":"quota exceeded"}}'
            return (VideoResponse if domain == "seedance" else ImageResponse)(400, {}, body)

    with pytest.raises((RuntimeError, ValueError)):
        if domain == "platform":
            PlatformClient("https://platform.test", "private-key", transport=Transport()).get_capabilities()
        elif domain == "seedance":
            VideoClient("private-key", transport=Transport()).get_task("task-1")
        else:
            ImageClient("private-key", transport=Transport()).generate_image({"prompt": "private-prompt"})
    log = (diagnostic_root / "logs/network.log").read_text()
    assert "quota exceeded" in log
    assert "private-key" not in log and "private-prompt" not in log


def test_model_download_error_is_recorded_without_changing_exception(diagnostic_root, monkeypatch):
    import pooch

    from src.core.rembg_model import download_u2net

    error = TimeoutError("model connection timed out")
    monkeypatch.setattr(pooch, "retrieve", lambda *args, **kwargs: (_ for _ in ()).throw(error))
    with pytest.raises(TimeoutError) as caught:
        download_u2net(diagnostic_root / "models")
    assert caught.value is error
    assert "model connection timed out" in (diagnostic_root / "logs/network.log").read_text()


def test_http_200_failed_job_is_logged_without_turning_polling_into_an_exception(diagnostic_root):
    from backend.platform.client import HttpResponse, PlatformClient

    payload = {"jobId": "job-1", "status": "FAILED", "error": {"code": "ProviderBusy", "message": "provider busy"}}

    class Transport:
        def request(self, *args):
            return HttpResponse(200, {}, json.dumps({"code": 200, "data": payload}).encode())

    assert PlatformClient("https://platform.test", "private-key", transport=Transport()).get_job("job-1") == payload
    log = (diagnostic_root / "logs/network.log").read_text()
    assert "RemoteJobFailure" in log and "ProviderBusy" in log and "job-1" in log


@pytest.mark.parametrize("status", [200, 410])
def test_artifact_download_failures_include_server_detail_and_job_id(diagnostic_root, status):
    from backend.platform.client import HttpResponse, PlatformClient

    class Transport:
        def request(self, *args):
            return HttpResponse(status, {}, b"" if status == 200 else b'{"msg":"artifact expired"}')

    with pytest.raises((RuntimeError, ValueError)):
        PlatformClient("https://platform.test", "private-key", transport=Transport()).download_artifact("job-1")
    log = (diagnostic_root / "logs/network.log").read_text()
    assert "job-1" in log and str(status) in log
    assert ("empty" if status == 200 else "artifact expired") in log
    assert "private-key" not in log


def test_http_200_per_image_error_is_logged_without_changing_the_response(diagnostic_root):
    from backend.seedream.client import ArkClient, HttpResponse

    payload = {"data": [{"error": {"code": "ImageRejected", "message": "image rejected"}}]}

    class Transport:
        def request(self, *args):
            return HttpResponse(200, {"x-request-id": "provider-request-1"}, json.dumps(payload).encode())

    assert ArkClient("private-key", transport=Transport()).generate_image({"prompt": "private-prompt"}) == payload
    log = (diagnostic_root / "logs/network.log").read_text()
    assert "ImageRejected" in log and "image rejected" in log and "provider-request-1" in log
    assert "private-key" not in log and "private-prompt" not in log
