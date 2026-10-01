"""Small HTTP client for Ark Seedance generation tasks."""

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from backend.ark_audit import ArkAudit, provider_request_id, response_fields

_TASKS_URL = "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks"
_DEFAULT_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes


class HttpTransport(Protocol):
    def request(
        self, method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float
    ) -> HttpResponse: ...


class UrllibTransport:
    """HTTP transport that preserves non-success responses for the client."""

    def request(
        self, method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float
    ) -> HttpResponse:
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return HttpResponse(response.status, dict(response.headers.items()), response.read())
        except urllib.error.HTTPError as error:
            return HttpResponse(error.code, dict(error.headers.items()) if error.headers else {}, error.read())


class ArkAPIError(RuntimeError):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status = status
        self.code = code
        self.message = message
        super().__init__(f"Ark API returned HTTP {status}: {code}: {message}")


class SubmissionUnknownError(RuntimeError):
    """The submission may have reached Ark, but its response was not received."""


class ArkResponseError(ValueError):
    """Ark returned a success response that cannot be interpreted safely."""


class ArkClient:
    def __init__(
        self,
        api_key: str,
        *,
        transport: HttpTransport | None = None,
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
        audit: ArkAudit | None = None,
    ) -> None:
        self._api_key = api_key
        self._transport = transport or UrllibTransport()
        self._timeout = timeout
        self.audit = audit

    def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = self._json_body(payload)
        try:
            result = self._call("POST", _TASKS_URL, "video.create", body=body, payload=payload, paid=True)
        except OSError as error:
            raise SubmissionUnknownError("Ark task submission outcome is unknown") from error
        except ArkResponseError as error:
            raise SubmissionUnknownError("Ark task submission outcome is unknown") from error
        assert isinstance(result, dict)
        return result

    def get_task(self, remote_id: str) -> dict[str, Any]:
        result = self._call("GET", self._task_url(remote_id), "video.get")
        assert isinstance(result, dict)
        return result

    def list_tasks(self, page_size: int = 1) -> dict[str, Any]:
        query = urllib.parse.urlencode({"page_size": page_size})
        result = self._call("GET", f"{_TASKS_URL}?{query}", "video.list")
        assert isinstance(result, dict)
        return result

    def delete_task(self, remote_id: str) -> dict[str, Any] | None:
        return self._call("DELETE", self._task_url(remote_id), "video.delete")

    def _call(
        self,
        method: str,
        url: str,
        operation: str,
        *,
        body: bytes | None = None,
        payload: dict[str, Any] | None = None,
        paid: bool = False,
    ) -> dict[str, Any] | None:
        call = self.audit.begin(operation, payload=payload, paid=paid) if self.audit else None
        try:
            response = self._transport.request(method, url, self._headers(), body, self._timeout)
        except OSError as error:
            if call:
                call.event("failure", error_type=type(error).__name__, errno=error.errno)
            raise
        if call:
            call.event(
                "http_response",
                http_status=response.status,
                request_id=provider_request_id(response.headers, response.body, self._api_key),
                response_bytes=len(response.body),
            )
        try:
            if operation == "video.delete" and 200 <= response.status < 300 and not response.body:
                parsed = None
            else:
                parsed = self._json_response(response)
        except (ArkResponseError, ArkAPIError) as error:
            if call:
                fields = {"http_status": response.status, "error_type": type(error).__name__}
                if isinstance(error, ArkAPIError):
                    fields["error_code"] = error.code
                call.event("failure", **fields)
            raise
        if call:
            call.event("parsed_response", **response_fields(operation, parsed or {}))
        return parsed

    def _json_response(self, response: HttpResponse) -> dict[str, Any]:
        if not 200 <= response.status < 300:
            raise self._api_error(response)
        try:
            data = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ArkResponseError("Ark API success response is not valid JSON") from error
        if not isinstance(data, dict):
            raise ArkResponseError("Ark API success response must be a JSON object")
        return data

    def _api_error(self, response: HttpResponse) -> ArkAPIError:
        fallback_code = f"HTTP_{response.status}"
        fallback_message = f"Ark API returned HTTP {response.status}"
        try:
            data = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return ArkAPIError(response.status, fallback_code, fallback_message)

        error = data.get("error") if isinstance(data, dict) else None
        if not isinstance(error, dict):
            return ArkAPIError(response.status, fallback_code, fallback_message)
        code = error.get("code")
        message = error.get("message")
        if not isinstance(code, str) or not isinstance(message, str):
            return ArkAPIError(response.status, fallback_code, fallback_message)
        return ArkAPIError(
            response.status,
            self._redact_secret(code),
            self._redact_secret(message),
        )

    def _redact_secret(self, value: str) -> str:
        return value.replace(self._api_key, "[REDACTED]") if self._api_key else value

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

    @staticmethod
    def _json_body(payload: dict[str, Any]) -> bytes:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    @staticmethod
    def _task_url(remote_id: str) -> str:
        return f"{_TASKS_URL}/{urllib.parse.quote(remote_id, safe='')}"
