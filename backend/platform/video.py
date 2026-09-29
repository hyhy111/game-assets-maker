"""ArkClient-shaped adapter over the platform video-job endpoints.

The Seedance task manager speaks the Ark task contract
({id, status, content: {video_url, ...}, error}). This adapter translates
platform job rows ({jobId, status, remoteStatus, quote, error, downloadUrl})
into that contract so the manager lifecycle (poll, recover, download, cancel)
works unchanged. Platform status values map onto local ones:

    QUEUED/SUBMITTING/RUNNING -> queued/running (kept pollable)
    SUBMISSION_UNKNOWN        -> running (platform verifying; surfaced via
                                 platform_status, never failed locally)
    SUCCEEDED                 -> succeeded (content.video_url points at the
                                 authenticated platform artifact endpoint)
    FAILED/CANCELLED          -> failed/cancelled

content.video_url uses the ``platform://artifact/<jobId>`` pseudo-URL; the
platform artifact transport resolves it (the endpoint needs a Bearer token).
"""

from __future__ import annotations

from typing import Any

from backend.platform.client import PlatformClient

ARTIFACT_URL_PREFIX = "platform://artifact/"

_PLATFORM_TO_LOCAL_STATUS = {
    "QUEUED": "queued",
    "SUBMITTING": "running",
    "SUBMISSION_UNKNOWN": "running",
    "RUNNING": "running",
    "SUCCEEDED": "succeeded",
    "FAILED": "failed",
    "CANCELLED": "cancelled",
    "CANCEL_REQUESTED": "cancelling",
}


def artifact_url(job_id: str) -> str:
    return f"{ARTIFACT_URL_PREFIX}{job_id}"


def local_status(platform_status: Any) -> str:
    return _PLATFORM_TO_LOCAL_STATUS.get(str(platform_status), "running")


def parse_error_json(error: Any) -> dict[str, Any] | None:
    """Platform error is a JSON string (errorJson); normalize to a dict."""
    if isinstance(error, dict):
        return dict(error)
    if isinstance(error, str) and error.strip():
        import json

        try:
            parsed = json.loads(error)
        except json.JSONDecodeError:
            return {"code": "PLATFORM_ERROR", "message": error}
        if isinstance(parsed, dict):
            return parsed
    return None


class PlatformVideoClient:
    """Drop-in replacement for ArkClient against the platform job API."""

    def __init__(self, platform: PlatformClient) -> None:
        self._platform = platform

    def upload_asset(self, path) -> dict[str, Any]:
        return self._platform.upload_asset(path)

    def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._platform.create_video_job(payload)
        job_id = response.get("jobId")
        if not isinstance(job_id, str) or not job_id:
            raise ValueError("Platform job creation returned no jobId")
        return self._mapped(response)

    def get_task(self, remote_id: str) -> dict[str, Any]:
        return self._mapped(self._platform.get_job(remote_id))

    def delete_task(self, remote_id: str) -> dict[str, Any]:
        """Platform cancel; returns the describe map mapped to Ark shape."""
        return self._mapped(self._platform.cancel_job(remote_id))

    def _mapped(self, job: dict[str, Any]) -> dict[str, Any]:
        job_id = str(job.get("jobId", ""))
        platform_status = str(job.get("status", ""))
        mapped: dict[str, Any] = {
            "id": job_id,
            "status": local_status(platform_status),
            "platform_status": platform_status,
            "remote_status": job.get("remoteStatus"),
            "quote": job.get("quote"),
        }
        if mapped["status"] == "succeeded":
            # v1 契约（artifact-backup-service）：平台只下发新鲜期内的上游直链，
            # 无平台副本回退——直链存在即新鲜（新鲜判定在服务端 ArtifactDirectLink）。
            # video_url 仅在无直链时保留 platform:// 伪地址作占位标识，
            # 下载器对伪地址候选为空即报"链接已过期"。
            upstream = job.get("upstreamUrl")
            fresh_upstream = upstream if isinstance(upstream, str) and upstream else None
            content: dict[str, Any] = {"video_url": fresh_upstream or artifact_url(job_id)}
            if fresh_upstream is not None:
                content["upstream_url"] = fresh_upstream
                expires = job.get("upstreamExpiresAt")
                if expires is not None:
                    content["upstream_expires_at"] = expires
            mapped["content"] = content
        error = parse_error_json(job.get("error"))
        if error is not None:
            mapped["error"] = error
        return mapped
