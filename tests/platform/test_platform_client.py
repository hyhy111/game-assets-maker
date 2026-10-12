"""PlatformClient endpoint coverage: success / business error / 401 per endpoint."""

from __future__ import annotations

import json

import pytest

from backend.platform.client import (
    PlatformClient,
    PlatformError,
    PlatformResponseError,
    PlatformUnauthorizedError,
    new_idem_key,
)

from platform_test_helpers import FakeTransport, ajax_error, ajax_ok, json_response


def make_client(transport: FakeTransport) -> PlatformClient:
    return PlatformClient("http://platform.test", "token-1", transport=transport)


def test_new_idem_key_format_and_uniqueness():
    keys = {new_idem_key() for _ in range(50)}
    assert len(keys) == 50
    for key in keys:
        assert key.startswith("gam-")
        assert len(key) <= 64


def test_upload_asset_posts_multipart_and_returns_asset_id(png_file):
    transport = FakeTransport(
        lambda method, url, headers, body: ajax_ok({"assetId": "7788", "format": "png", "width": 64, "height": 64})
    )
    client = make_client(transport)
    asset = client.upload_asset(png_file)

    method, url, headers, body = transport.last
    assert method == "POST"
    assert url == "http://platform.test/app/gen/assets"
    assert headers["Authorization"] == "Bearer token-1"
    assert headers["Content-Type"].startswith("multipart/form-data; boundary=")
    assert b'name="file"; filename="input.png"' in body
    assert asset["assetId"] == "7788"


def test_upload_asset_rejects_oversized_file(tmp_path, monkeypatch):
    from backend.platform import client as client_module

    monkeypatch.setattr(client_module, "_MAX_ASSET_BYTES", 10)
    transport = FakeTransport()
    client = make_client(transport)
    oversized = tmp_path / "big.png"
    oversized.write_bytes(b"x" * 64)
    with pytest.raises(ValueError, match="10 MB"):
        client.upload_asset(oversized)


def test_quote_video_hits_preview_endpoint():
    transport = FakeTransport(lambda m, u, h, b: ajax_ok({"quote": 100, "baseCredits": 80, "multiplier": 1.25}))
    client = make_client(transport)
    body = {"model": "doubao-seedance-2-0-260128", "content": [{"type": "text", "text": "quote"}],
            "resolution": "720p", "ratio": "16:9", "duration": 5, "generate_audio": False}
    data = client.quote_video(body)
    assert data["quote"] == 100
    method, url, headers, payload = transport.last
    assert (method, url) == ("POST", "http://platform.test/app/gen/jobs/quote-preview")
    assert json.loads(payload.decode("utf-8"))["model"] == "doubao-seedance-2-0-260128"


def test_create_video_job_returns_job_fields():
    transport = FakeTransport(
        lambda m, u, h, b: ajax_ok({"jobId": "9001", "status": "QUEUED", "quote": 500, "quoteDetail": "{}", "idemReplay": False})
    )
    client = make_client(transport)
    data = client.create_video_job({"idemKey": "gam-x", "model": "m", "content": []})
    assert data["jobId"] == "9001"
    assert transport.last[0] == "POST" and transport.last[1] == "http://platform.test/app/gen/jobs"


def test_get_job_quotes_job_id():
    transport = FakeTransport(lambda m, u, h, b: ajax_ok({"jobId": "9001", "status": "RUNNING"}))
    client = make_client(transport)
    client.get_job("9001")
    assert transport.last[0] == "GET"
    assert transport.last[1] == "http://platform.test/app/gen/jobs/9001"


def test_cancel_job_posts_to_cancel_path():
    transport = FakeTransport(lambda m, u, h, b: ajax_ok({"jobId": "9001", "status": "CANCELLED"}))
    client = make_client(transport)
    client.cancel_job("9001")
    assert transport.last[0] == "POST"
    assert transport.last[1] == "http://platform.test/app/gen/jobs/9001/cancel"


def test_generate_image_uses_sync_endpoint():
    transport = FakeTransport(lambda m, u, h, b: ajax_ok({"jobId": "42", "status": "SUCCEEDED", "quote": 30, "images": [], "error": None}))
    client = make_client(transport)
    client.generate_image({"idemKey": "gam-y", "model": "m", "prompt": "p", "size": "1k"})
    assert transport.last[0] == "POST"
    assert transport.last[1] == "http://platform.test/app/image/generations"


def test_business_error_raises_platform_error_with_message():
    transport = FakeTransport(lambda m, u, h, b: ajax_error(500, "该参数组合暂未定价"))
    client = make_client(transport)
    with pytest.raises(PlatformError) as caught:
        client.create_video_job({"idemKey": "k"})
    assert caught.value.message == "该参数组合暂未定价"
    assert not isinstance(caught.value, PlatformUnauthorizedError)


def test_401_raises_unauthorized():
    transport = FakeTransport(lambda m, u, h, b: ajax_error(401, "未登录"))
    client = make_client(transport)
    with pytest.raises(PlatformUnauthorizedError):
        client.get_job("9001")


def test_success_without_data_object_raises_response_error():
    transport = FakeTransport(lambda m, u, h, b: ajax_ok({}))
    client = make_client(transport)
    with pytest.raises(PlatformResponseError):
        client.get_job("9001")


def test_download_artifact_returns_bytes_on_success():
    transport = FakeTransport(lambda m, u, h, b: _binary(b"mp4-bytes"))
    client = make_client(transport)
    content = client.download_artifact("9001")
    assert content == b"mp4-bytes"
    assert transport.last[0] == "GET"
    assert transport.last[1] == "http://platform.test/app/artifact/9001/download"


def _binary(content: bytes):
    from backend.platform.client import HttpResponse

    return HttpResponse(200, {"Content-Type": "video/mp4"}, content)


def test_download_artifact_maps_expiry_error():
    transport = FakeTransport(lambda m, u, h, b: json_response({"code": 500, "msg": "成品已过有效期"}, status=410))
    client = make_client(transport)
    with pytest.raises(PlatformError) as caught:
        client.download_artifact("9001")
    assert caught.value.status == 410
    assert "过期" in caught.value.message


def test_download_artifact_401_raises_unauthorized():
    transport = FakeTransport(lambda m, u, h, b: json_response({"code": 401, "msg": "未登录"}, status=401))
    client = make_client(transport)
    with pytest.raises(PlatformUnauthorizedError):
        client.download_artifact("9001")


def test_token_updates_apply_to_subsequent_requests():
    transport = FakeTransport(lambda m, u, h, b: ajax_ok({"jobId": "1", "status": "QUEUED"}))
    client = make_client(transport)
    client.set_token("token-2")
    client.get_job("1")
    assert transport.last_authorization() == "Bearer token-2"
    client.set_token(None)
    client.get_job("1")
    assert transport.last_authorization() is None


def test_upload_asset_rejects_exactly_the_limit(tmp_path, monkeypatch):
    """恰好等于上限也拒：三处阈值统一用 >=。

    此前客户端预检用 > 而另两处用 >=，恰好 10MB 的图会被客户端放行、再被服务端拒绝。
    """
    from backend.platform import client as client_module

    monkeypatch.setattr(client_module, "_MAX_ASSET_BYTES", 10)
    client = make_client(FakeTransport())
    exact = tmp_path / "exact.png"
    exact.write_bytes(b"x" * 10)
    with pytest.raises(ValueError, match="10 MB"):
        client.upload_asset(exact)
