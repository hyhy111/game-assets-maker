from __future__ import annotations

import json

import pytest

from backend.seedream.client import (
    ArkAPIError,
    HttpResponse,
    SubmissionUnknownError,
)
from backend.seedream.models import SeedreamRequest
from backend.seedream.validation import build_api_payload


class FakeTransport:
    def __init__(self, response: HttpResponse):
        self._response = response
        self.calls: list[tuple[str, str, dict[str, str], bytes | None, float]] = []

    def request(self, method, url, headers, body, timeout):
        self.calls.append((method, url, headers, body, timeout))
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _ok_response(data=None, usage=None) -> HttpResponse:
    body = {
        "created": 1700000000,
        "data": data
        or [
            {"url": "https://ark.example.com/image.jpg", "image_type": "JPEG", "image_width": 1024, "image_height": 576}
        ],
        "usage": usage or {"total_tokens": 42, "generated_images": 1},
    }
    return HttpResponse(200, {}, json.dumps(body).encode("utf-8"))


def _error_response(status: int, code: str = "ERROR", message: str = "failed") -> HttpResponse:
    body = {"error": {"code": code, "message": message}}
    return HttpResponse(status, {}, json.dumps(body).encode("utf-8"))


def _error_response_with_headers(
    status: int, headers: dict[str, str], code: str = "ERROR", message: str = "failed"
) -> HttpResponse:
    body = {"error": {"code": code, "message": message}}
    return HttpResponse(status, headers, json.dumps(body).encode("utf-8"))


def test_client_sends_correct_request_body_and_headers():
    transport = FakeTransport(_ok_response())
    from backend.seedream.client import ArkClient

    client = ArkClient("secret-key", transport=transport, timeout=1500.0)
    payload = build_api_payload(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9"))
    client.generate_image(payload)

    method, url, headers, body, timeout = transport.calls[0]
    assert method == "POST"
    assert url == "https://ark.cn-beijing.volces.com/api/v3/images/generations"
    assert headers["Authorization"] == "Bearer secret-key"
    assert headers["Content-Type"] == "application/json"
    assert headers["X-Ark-Max-Wait-Timeout-Ms"] == "300000"
    assert timeout == 1500.0

    sent = json.loads(body)
    assert sent["model"] == "doubao-seedream-5-0-pro-260628"
    assert sent["prompt"] == "图片比例 16:9，hero"
    assert sent["size"] == "1K"
    assert sent["response_format"] == "url"
    assert sent["watermark"] is False
    assert "sequential_image_generation" not in sent


def test_client_timeout_is_25_minutes_by_default():
    from backend.seedream.client import _DEFAULT_TIMEOUT_SECONDS, ArkClient

    assert _DEFAULT_TIMEOUT_SECONDS == 1500.0
    client = ArkClient("key")
    assert client._timeout == 1500.0


def test_client_429_raises_ark_api_error():
    transport = FakeTransport(_error_response(429, "RATE_LIMIT", "rate limited"))
    from backend.seedream.client import ArkClient

    client = ArkClient("key", transport=transport)
    with pytest.raises(ArkAPIError) as exc_info:
        client.generate_image({"model": "x", "prompt": "x", "size": "1x1"})
    assert exc_info.value.status == 429
    assert exc_info.value.code == "RATE_LIMIT"


def test_client_network_error_raises_submission_unknown():
    transport = FakeTransport(OSError("connection refused"))
    from backend.seedream.client import ArkClient

    client = ArkClient("key", transport=transport)
    with pytest.raises(SubmissionUnknownError):
        client.generate_image({"model": "x", "prompt": "x", "size": "1x1"})


def test_client_unparseable_response_raises_submission_unknown():
    transport = FakeTransport(HttpResponse(200, {}, b"not json"))
    from backend.seedream.client import ArkClient

    client = ArkClient("key", transport=transport)
    with pytest.raises(SubmissionUnknownError):
        client.generate_image({"model": "x", "prompt": "x", "size": "1x1"})


def test_client_missing_data_raises_submission_unknown():
    transport = FakeTransport(HttpResponse(200, {}, json.dumps({"created": 0}).encode("utf-8")))
    from backend.seedream.client import ArkClient

    client = ArkClient("key", transport=transport)
    with pytest.raises(SubmissionUnknownError):
        client.generate_image({"model": "x", "prompt": "x", "size": "1x1"})


def test_client_redacts_api_key_in_error_message():
    transport = FakeTransport(_error_response(401, "AUTH", "bad key secret-key leaked"))
    from backend.seedream.client import ArkClient

    client = ArkClient("secret-key", transport=transport)
    with pytest.raises(ArkAPIError) as exc_info:
        client.generate_image({"model": "x", "prompt": "x", "size": "1x1"})
    assert "secret-key" not in exc_info.value.message
    assert "[REDACTED]" in exc_info.value.message


def test_client_returns_full_response_with_usage():
    usage = {"total_tokens": 99, "generated_images": 1, "output_tokens": 50}
    transport = FakeTransport(_ok_response(usage=usage))
    from backend.seedream.client import ArkClient

    client = ArkClient("key", transport=transport)
    result = client.generate_image({"model": "x", "prompt": "x", "size": "1x1"})
    assert result["usage"] == usage
    assert result["data"][0]["url"] == "https://ark.example.com/image.jpg"


def test_client_429_saves_request_id_from_header():
    transport = FakeTransport(
        _error_response_with_headers(429, {"X-Request-ID": "req-abc-123"}, "RATE_LIMIT", "rate limited")
    )
    from backend.seedream.client import ArkClient

    client = ArkClient("key", transport=transport)
    with pytest.raises(ArkAPIError) as exc_info:
        client.generate_image({"model": "x", "prompt": "x", "size": "1x1"})
    assert exc_info.value.status == 429
    assert exc_info.value.code == "RATE_LIMIT"
    assert exc_info.value.request_id == "req-abc-123"


def test_client_429_saves_request_id_from_body():
    body = {"error": {"code": "RATE_LIMIT", "message": "rate limited", "request_id": "req-body-456"}}
    transport = FakeTransport(HttpResponse(429, {}, json.dumps(body).encode("utf-8")))
    from backend.seedream.client import ArkClient

    client = ArkClient("key", transport=transport)
    with pytest.raises(ArkAPIError) as exc_info:
        client.generate_image({"model": "x", "prompt": "x", "size": "1x1"})
    assert exc_info.value.request_id == "req-body-456"


def test_client_429_saves_request_id_from_top_level_body():
    body = {"error": {"code": "RATE_LIMIT", "message": "rate limited"}, "request_id": "req-top-789"}
    transport = FakeTransport(HttpResponse(429, {}, json.dumps(body).encode("utf-8")))
    from backend.seedream.client import ArkClient

    client = ArkClient("key", transport=transport)
    with pytest.raises(ArkAPIError) as exc_info:
        client.generate_image({"model": "x", "prompt": "x", "size": "1x1"})
    assert exc_info.value.request_id == "req-top-789"


def test_client_429_without_request_id_sets_none():
    transport = FakeTransport(_error_response(429, "RATE_LIMIT", "rate limited"))
    from backend.seedream.client import ArkClient

    client = ArkClient("key", transport=transport)
    with pytest.raises(ArkAPIError) as exc_info:
        client.generate_image({"model": "x", "prompt": "x", "size": "1x1"})
    assert exc_info.value.request_id is None


def test_client_header_request_id_takes_precedence_over_body():
    body = {"error": {"code": "RATE_LIMIT", "message": "rate limited", "request_id": "from-body"}}
    transport = FakeTransport(HttpResponse(429, {"X-Request-ID": "from-header"}, json.dumps(body).encode("utf-8")))
    from backend.seedream.client import ArkClient

    client = ArkClient("key", transport=transport)
    with pytest.raises(ArkAPIError) as exc_info:
        client.generate_image({"model": "x", "prompt": "x", "size": "1x1"})
    assert exc_info.value.request_id == "from-header"
