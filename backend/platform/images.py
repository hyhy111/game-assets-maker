"""ArkClient-shaped adapter for the synchronous platform image endpoint."""

from __future__ import annotations

from typing import Any

from backend.platform.client import PlatformClient, PlatformResponseError
from backend.platform.video import parse_error_json


class PlatformImageClient:
    """Drop-in replacement for the Seedream ArkClient (generate_image only)."""

    def __init__(self, platform: PlatformClient) -> None:
        self._platform = platform

    def upload_asset(self, path) -> dict[str, Any]:
        """Upload a reference image (图生图); the manager calls this per attempt."""
        return self._platform.upload_asset(path)

    def quote_image(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Read-only price preview; returns the platform's raw quote payload."""
        return self._platform.quote_image(payload)

    def generate_image(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._platform.generate_image(payload)
        job_id = response.get("jobId")
        if not isinstance(job_id, str) or not job_id:
            raise PlatformResponseError("Platform image generation returned no jobId")
        status = str(response.get("status", ""))
        images = response.get("images")
        first_url: str | None = None
        if isinstance(images, list) and images and isinstance(images[0], dict):
            url = images[0].get("url")
            if isinstance(url, str) and url:
                first_url = url
        mapped: dict[str, Any] = {
            "jobId": job_id,
            "platform_status": status,
            "quote": response.get("quote"),
            "data": [],
        }
        if status == "SUCCEEDED" and first_url:
            # v1 契约（artifact-backup-service）：url 即上游地址本身（唯一交付载体），
            # 附新鲜期过期时间；平台不再提供制品副本地址。
            entry: dict[str, Any] = {"url": first_url}
            first_image = images[0]
            upstream = first_image.get("upstreamUrl") if isinstance(first_image, dict) else None
            if isinstance(upstream, str) and upstream:
                entry["upstream_url"] = upstream
                expires = first_image.get("upstreamExpiresAt")
                if expires is not None:
                    entry["upstream_expires_at"] = expires
            mapped["data"] = [entry]
        error = parse_error_json(response.get("error"))
        if error is not None:
            mapped["error"] = error
        return mapped
