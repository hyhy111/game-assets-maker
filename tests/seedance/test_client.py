import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError

import pytest

from backend.seedance.client import (
    ArkAPIError,
    ArkClient,
    ArkResponseError,
    HttpResponse,
    SubmissionUnknownError,
    UrllibTransport,
)


@dataclass
class CapturedRequest:
    method: str
    url: str
    headers: dict[str, str]
    body: bytes | None
    timeout: float


class FakeTransport:
    def __init__(self) -> None:
        self.requests: list[CapturedRequest] = []
        self.responses: list[HttpResponse | BaseException] = []

    def queue_json(self, status: int, body: dict[str, Any]) -> None:
        self.responses.append(HttpResponse(status, {}, json.dumps(body).encode("utf-8")))

    def queue_empty(self, status: int) -> None:
        self.responses.append(HttpResponse(status, {}, b""))

    def queue_bytes(self, status: int, body: bytes) -> None:
        self.responses.append(HttpResponse(status, {}, body))

    def queue_error(self, error: BaseException) -> None:
        self.responses.append(error)

    def request(
        self, method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float
    ) -> HttpResponse:
        self.requests.append(CapturedRequest(method, url, headers, body, timeout))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


@pytest.fixture
def fake_transport() -> FakeTransport:
    return FakeTransport()


def test_create_task_uses_official_endpoint_and_json_body(fake_transport: FakeTransport):
    payload = {"model": "model-id", "content": []}
    fake_transport.queue_json(200, {"id": "remote-1"})

    result = ArkClient("secret", transport=fake_transport).create_task(payload)

    assert result == {"id": "remote-1"}
    request = fake_transport.requests[0]
    assert request.method == "POST"
    assert request.url == "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks"
    assert request.headers == {"Authorization": "Bearer secret", "Content-Type": "application/json"}
    assert json.loads(request.body or b"{}") == payload
    assert request.timeout == 30.0


def test_get_task_uses_remote_id_path_and_bearer_auth(fake_transport: FakeTransport):
    fake_transport.queue_json(200, {"id": "remote-1", "status": "running"})

    result = ArkClient("secret", transport=fake_transport).get_task("remote-1")

    assert result["status"] == "running"
    request = fake_transport.requests[0]
    assert request.method == "GET"
    assert request.url == "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/remote-1"
    assert request.body is None
    assert request.timeout == 30.0


def test_list_tasks_uses_page_size_query_parameter(fake_transport: FakeTransport):
    fake_transport.queue_json(200, {"data": []})

    result = ArkClient("secret", transport=fake_transport).list_tasks(page_size=3)

    assert result == {"data": []}
    request = fake_transport.requests[0]
    assert request.method == "GET"
    assert request.url == "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks?page_size=3"
    assert request.body is None


def test_delete_task_handles_an_empty_success_response(fake_transport: FakeTransport):
    fake_transport.queue_empty(204)

    result = ArkClient("secret", transport=fake_transport).delete_task("remote-1")

    assert result is None
    request = fake_transport.requests[0]
    assert request.method == "DELETE"
    assert request.url == "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/remote-1"
    assert request.body is None


@pytest.mark.parametrize("status", [400, 500])
def test_delete_task_empty_error_response_uses_safe_api_error_fallback(
    fake_transport: FakeTransport, status: int
):
    fake_transport.queue_empty(status)

    with pytest.raises(ArkAPIError) as raised:
        ArkClient("secret", transport=fake_transport).delete_task("remote-1")

    assert raised.value.status == status
    assert raised.value.code == f"HTTP_{status}"
    assert raised.value.message == f"Ark API returned HTTP {status}"


def test_delete_task_non_empty_error_preserves_ark_error(fake_transport: FakeTransport):
    fake_transport.queue_json(429, {"error": {"code": "RateLimitExceeded", "message": "Try later"}})

    with pytest.raises(ArkAPIError) as raised:
        ArkClient("secret", transport=fake_transport).delete_task("remote-1")

    assert raised.value.status == 429
    assert raised.value.code == "RateLimitExceeded"
    assert raised.value.message == "Try later"


def test_http_error_response_becomes_ark_api_error(fake_transport: FakeTransport):
    fake_transport.queue_json(429, {"error": {"code": "RateLimitExceeded", "message": "Try later"}})

    with pytest.raises(ArkAPIError) as raised:
        ArkClient("secret", transport=fake_transport).get_task("remote-1")

    assert raised.value.status == 429
    assert raised.value.code == "RateLimitExceeded"
    assert raised.value.message == "Try later"


@pytest.mark.parametrize("status", [401, 403, 400, 429, 500, 503])
def test_all_provider_http_error_classes_preserve_status(fake_transport: FakeTransport, status: int):
    fake_transport.queue_json(status, {"error": {"code": f"E{status}", "message": "safe failure"}})

    with pytest.raises(ArkAPIError) as raised:
        ArkClient("fake-contract-key", transport=fake_transport).get_task("remote-1")

    assert (raised.value.status, raised.value.code, raised.value.message) == (status, f"E{status}", "safe failure")


@pytest.mark.parametrize("body", [b"not json", b'{"error":"wrong shape"}', b""])
def test_malformed_error_body_keeps_status_and_uses_safe_fallback(fake_transport: FakeTransport, body: bytes):
    fake_transport.responses.append(HttpResponse(500, {}, body))

    with pytest.raises(ArkAPIError) as raised:
        ArkClient("secret", transport=fake_transport).get_task("remote-1")

    assert raised.value.status == 500
    assert raised.value.code == "HTTP_500"
    assert raised.value.message == "Ark API returned HTTP 500"


def test_only_create_task_marks_after_send_transport_failure_as_submission_unknown(fake_transport: FakeTransport):
    fake_transport.queue_error(TimeoutError("timed out"))

    with pytest.raises(SubmissionUnknownError) as raised:
        ArkClient("secret", transport=fake_transport).create_task({"model": "model-id", "content": []})

    assert isinstance(raised.value.__cause__, TimeoutError)
    assert len(fake_transport.requests) == 1


@pytest.mark.parametrize("body", [b"not json", b"[]", b""])
def test_create_task_marks_invalid_success_response_as_submission_unknown(
    fake_transport: FakeTransport, body: bytes
):
    fake_transport.queue_bytes(200, body)

    with pytest.raises(SubmissionUnknownError, match="outcome is unknown"):
        ArkClient("secret", transport=fake_transport).create_task({"model": "model-id", "content": []})


@pytest.mark.parametrize("body", [b"not json", b"[]", b""])
def test_get_task_rejects_invalid_success_response(fake_transport: FakeTransport, body: bytes):
    fake_transport.queue_bytes(200, body)

    with pytest.raises(ArkResponseError, match="Ark API success response"):
        ArkClient("secret", transport=fake_transport).get_task("remote-1")


def test_api_error_does_not_echo_the_bearer_secret(fake_transport: FakeTransport):
    secret = "contract-test-secret"
    fake_transport.queue_json(
        403,
        {"error": {"code": f"DENIED_{secret}", "message": f"Authorization Bearer {secret} rejected"}},
    )

    with pytest.raises(ArkAPIError) as raised:
        ArkClient(secret, transport=fake_transport).get_task("remote-1")

    assert secret not in str(raised.value)
    assert secret not in raised.value.code
    assert secret not in raised.value.message


def test_create_task_does_not_hide_a_non_transport_error(fake_transport: FakeTransport):
    fake_transport.queue_error(ValueError("bad transport implementation"))

    with pytest.raises(ValueError, match="bad transport implementation"):
        ArkClient("secret", transport=fake_transport).create_task({"model": "model-id", "content": []})


@pytest.mark.parametrize("method", ["get_task", "list_tasks", "delete_task"])
def test_read_and_delete_transport_failures_remain_visible(fake_transport: FakeTransport, method: str):
    failure = OSError("network unavailable")
    fake_transport.queue_error(failure)
    client = ArkClient("secret", transport=fake_transport)

    with pytest.raises(OSError, match="network unavailable"):
        if method == "list_tasks":
            client.list_tasks()
        else:
            getattr(client, method)("remote-1")


def test_urllib_transport_turns_http_error_into_response(monkeypatch: pytest.MonkeyPatch):
    error = HTTPError("https://example.invalid", 401, "Unauthorized", {}, __import__("io").BytesIO(b'{"error":{}}'))
    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: (_ for _ in ()).throw(error))

    response = UrllibTransport().request("GET", "https://example.invalid", {}, None, 12.0)

    assert response.status == 401
    assert response.body == b'{"error":{}}'


def test_urllib_transport_propagates_connection_failures(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda request, timeout: (_ for _ in ()).throw(TimeoutError("timed out"))
    )

    with pytest.raises(TimeoutError, match="timed out"):
        UrllibTransport().request("GET", "https://example.invalid", {}, None, 12.0)
