"""Small HTTP client for the ForFuner platform (ruoyi-app) generation APIs.

Follows the transport pattern of backend.seedance.client: the transport keeps
non-success responses so the client can classify errors itself. All endpoints
speak RuoYi AjaxResult ({code, msg, data}); code !== 200 raises PlatformError,
HTTP/body 401 raises PlatformUnauthorizedError so callers can trigger re-login.
"""

from __future__ import annotations

import json
import mimetypes
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from backend.platform.trace import trace_failure, trace_success

_DEFAULT_TIMEOUT_SECONDS = 30.0
_IMAGE_GENERATION_TIMEOUT_SECONDS = 1500.0  # sync endpoint can hold minutes
# 与 image_input.MAX_IMAGE_BYTES 同值同语义（服务端 GenAssetService 也是 10MB）
_MAX_ASSET_BYTES = 10 * 1024 * 1024


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


class PlatformError(RuntimeError):
    """A platform endpoint returned a business or HTTP error."""

    def __init__(self, status: int, code: str, message: str) -> None:
        self.status = status
        self.code = code
        self.message = message
        super().__init__(f"Platform API returned HTTP {status}: {code}: {message}")


class PlatformUnauthorizedError(PlatformError):
    """The app JWT is missing, expired, or invalid (HTTP/body 401)."""


class PlatformResponseError(ValueError):
    """The platform returned a success response that cannot be interpreted safely."""


def new_idem_key() -> str:
    """Fresh idempotency key (platform limit: 64 chars)."""
    return f"gam-{uuid4().hex}"


class PlatformClient:
    """REST wrapper over ruoyi-app C-end generation endpoints."""

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        *,
        transport: HttpTransport | None = None,
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._transport = transport or UrllibTransport()
        self._timeout = timeout

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def token(self) -> str | None:
        return self._token

    def set_token(self, token: str | None) -> None:
        self._token = token if isinstance(token, str) and token else None

    def configured(self) -> bool:
        return bool(self._base_url and self._token)

    # ---- assets ----

    def upload_asset(self, path: Path) -> dict[str, Any]:
        """Upload a local image and return the AppGenAsset record (assetId as str)."""
        file_path = Path(path)
        size = file_path.stat().st_size
        if size <= 0:
            raise ValueError("Upload asset is empty")
        if size >= _MAX_ASSET_BYTES:
            # 与另两处统一用 ">="：恰好等于上限的图不应通过客户端预检、却被服务端拒绝
            raise ValueError("Upload asset must be smaller than 10 MB")
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        boundary = uuid4().hex
        head = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode()
        body = head + file_path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        headers = self._headers()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        data = self._request("POST", "/app/gen/assets", body=body, headers=headers, timeout=max(self._timeout, 120.0))
        asset_id = data.get("assetId")
        if not isinstance(asset_id, str) or not asset_id:
            raise PlatformResponseError("Platform asset response has no assetId")
        return data

    # ---- video jobs ----

    def quote_video(self, request_json: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/app/gen/jobs/quote-preview", body=self._json_body(request_json))

    def quote_image(self, request_json: dict[str, Any]) -> dict[str, Any]:
        """Image quote preview (read-only); only model + size are required."""
        return self._request("POST", "/app/image/quote-preview", body=self._json_body(request_json))

    # ---- capabilities ----

    def get_capabilities(self) -> dict[str, Any]:
        """可售能力清单（只读）：平台源下渲染模型与参数选项的唯一来源。

        返回 `{video:{models:[{model,resolutions,durations}],ratios:[...]}, image:{models:[{model,sizes}]}}`。
        """
        return self._request("GET", "/app/gen/capabilities")

    def create_video_job(self, request_json: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/app/gen/jobs", body=self._json_body(request_json))

    def get_job(self, job_id: str) -> dict[str, Any]:
        return self._request("GET", f"/app/gen/jobs/{urllib.parse.quote(str(job_id), safe='')}")

    def list_jobs(self, page: int = 1, size: int = 10) -> dict[str, Any]:
        query = urllib.parse.urlencode({"page": page, "size": size})
        return self._request("GET", f"/app/gen/jobs?{query}")

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        return self._request("POST", f"/app/gen/jobs/{urllib.parse.quote(str(job_id), safe='')}/cancel")

    # ---- image generation (sync) ----

    def generate_image(self, request_json: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            "/app/image/generations",
            body=self._json_body(request_json),
            timeout=_IMAGE_GENERATION_TIMEOUT_SECONDS,
        )

    # ---- artifact download ----

    def download_artifact(self, job_id: str) -> bytes:
        """Download a finished artifact; error bodies map to PlatformError."""
        path = f"/app/artifact/{urllib.parse.quote(str(job_id), safe='')}/download"
        try:
            response = self._transport.request("GET", self._url(path), self._headers(), None, max(self._timeout, 300.0))
        except Exception as error:
            trace_failure("GET", path, type(error).__name__, str(error), secret=self._token)
            raise
        if 200 <= response.status < 300:
            if not response.body:
                trace_failure("GET", path, "PlatformResponseError", "empty artifact body", secret=self._token)
                raise PlatformResponseError("Platform artifact download is empty")
            trace_success("GET", path, response.status, "200", f"{len(response.body)} bytes", secret=self._token)
            return response.body
        error = self._artifact_error(response)
        trace_failure("GET", path, type(error).__name__, error.message, secret=self._token)
        raise error

    # ---- plumbing ----

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        # 整段包住：网络异常、非 JSON、业务错误、缺 data 都落到同一个出口记日志后重抛。
        try:
            response = self._transport.request(
                method, self._url(path), headers or self._headers(), body, timeout or self._timeout
            )
            data = self._json_body_response(response)
            if data.get("code") != 200:
                raise self._ajax_error(response, data)
            payload = data.get("data")
            if not isinstance(payload, dict) or not payload:
                raise PlatformResponseError("Platform success response has no data object")
        except Exception as error:
            trace_failure(method, path, type(error).__name__, str(error), secret=self._token)
            raise
        trace_success(method, path, response.status, data.get("code"), payload, secret=self._token)
        return payload

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _json_body(self, payload: dict[str, Any]) -> bytes:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    def _json_body_response(self, response: HttpResponse) -> dict[str, Any]:
        try:
            data = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PlatformResponseError("Platform API response is not valid JSON") from error
        if not isinstance(data, dict):
            raise PlatformResponseError("Platform API response must be a JSON object")
        return data

    def _ajax_error(self, response: HttpResponse, data: dict[str, Any]) -> PlatformError:
        code = data.get("code")
        message = data.get("msg")
        error_code = str(code) if code is not None else f"HTTP_{response.status}"
        error_message = (
            message if isinstance(message, str) and message else f"Platform API returned HTTP {response.status}"
        )
        if response.status == 401 or code == 401:
            return PlatformUnauthorizedError(response.status, error_code, error_message)
        return PlatformError(response.status, error_code, error_message)

    def _artifact_error(self, response: HttpResponse) -> PlatformError:
        message: str | None = None
        try:
            data = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            data = None
        if isinstance(data, dict) and isinstance(data.get("msg"), str):
            message = data["msg"]
        canonical = {
            401: "登录已过期，请重新登录",
            403: "无权访问该成品",
            404: "成品尚未就绪或已不存在",
            410: "成品已过期，无法下载",
        }.get(response.status)
        if canonical:
            # Canonical message wins; keep the server detail only when it adds information.
            message = canonical if not message or message in canonical else f"{canonical}（{message}）"
        if not message:
            message = f"Platform artifact download failed (HTTP {response.status})"
        code = "ARTIFACT_UNAUTHORIZED" if response.status == 401 else f"HTTP_{response.status}"
        if response.status == 401:
            return PlatformUnauthorizedError(response.status, code, message)
        return PlatformError(response.status, code, message)
