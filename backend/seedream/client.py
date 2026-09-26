"""Small HTTP client for Ark Seedream image generations."""

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

_IMAGES_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
_DEFAULT_TIMEOUT_SECONDS = 1500.0  # 25 minutes
_MAX_WAIT_TIMEOUT_MS = "300000"  # 5 minutes server-side queue


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
    def __init__(self, status: int, code: str, message: str, request_id: str | None = None) -> None:
        self.status = status
        self.code = code
        self.message = message
        self.request_id = request_id
        super().__init__(f"Ark API returned HTTP {status}: {code}: {message}")


class SubmissionUnknownError(RuntimeError):
    """The submission may have reached Ark, but its response was not received."""


class ArkResponseError(ValueError):
    """Ark returned a success response that cannot be interpreted safely."""


class ArkClient:
    def __init__(
        self, api_key: str, *, transport: HttpTransport | None = None, timeout: float = _DEFAULT_TIMEOUT_SECONDS
    ) -> None:
        self._api_key = api_key
        self._transport = transport or UrllibTransport()
        self._timeout = timeout

    def generate_image(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = self._json_body(payload)
        try:
            response = self._transport.request("POST", _IMAGES_URL, self._headers(), body, self._timeout)
        except OSError as error:
            raise SubmissionUnknownError("Ark image generation outcome is unknown") from error
        try:
            return self._parse_response(response)
        except ArkResponseError as error:
            raise SubmissionUnknownError("Ark image generation outcome is unknown") from error

    def _parse_response(self, response: HttpResponse) -> dict[str, Any]:
        if not 200 <= response.status < 300:
            raise self._api_error(response)
        try:
            data = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ArkResponseError("Ark API success response is not valid JSON") from error
        if not isinstance(data, dict):
            raise ArkResponseError("Ark API success response must be a JSON object")
        data_list = data.get("data")
        if not isinstance(data_list, list) or not data_list:
            raise ArkResponseError("Ark API response missing image data")
        return data

    def _api_error(self, response: HttpResponse) -> ArkAPIError:
        request_id = self._extract_request_id(response)
        fallback_code = f"HTTP_{response.status}"
        fallback_message = f"Ark API returned HTTP {response.status}"
        try:
            data = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return ArkAPIError(response.status, fallback_code, fallback_message, request_id)

        error = data.get("error") if isinstance(data, dict) else None
        if not isinstance(error, dict):
            return ArkAPIError(response.status, fallback_code, fallback_message, request_id)
        code = error.get("code")
        message = error.get("message")
        if not isinstance(code, str) or not isinstance(message, str):
            return ArkAPIError(response.status, fallback_code, fallback_message, request_id)
        return ArkAPIError(
            response.status,
            self._redact_secret(code),
            self._redact_secret(message),
            request_id,
        )

    @staticmethod
    def _extract_request_id(response: HttpResponse) -> str | None:
        """Extract Request ID from response headers or error body, if provided."""
        for key, value in response.headers.items():
            if key.lower() in ("x-request-id", "request-id"):
                if isinstance(value, str) and value:
                    return value
        try:
            data = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        if isinstance(data, dict):
            rid = data.get("request_id")
            if isinstance(rid, str) and rid:
                return rid
            error = data.get("error")
            if isinstance(error, dict):
                rid = error.get("request_id")
                if isinstance(rid, str) and rid:
                    return rid
        return None

    def _redact_secret(self, value: str) -> str:
        return value.replace(self._api_key, "[REDACTED]") if self._api_key else value

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-Ark-Max-Wait-Timeout-Ms": _MAX_WAIT_TIMEOUT_MS,
        }

    @staticmethod
    def _json_body(payload: dict[str, Any]) -> bytes:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
