"""Download transport that resolves platform artifact pseudo-URLs.

Existing downloaders (Seedance ResultDownloader, Seedream ImageDownloader) call
``transport.download(url)`` with the URL persisted in the task/batch record.
Platform artifacts live behind an authenticated endpoint, so platform records
carry ``platform://artifact/<jobId>`` pseudo-URLs that this transport resolves
via PlatformClient; every other URL falls through to plain urllib.
"""

from __future__ import annotations

import time
import urllib.request
from datetime import UTC, datetime
from typing import Any

from backend.platform.client import PlatformClient
from backend.platform.video import ARTIFACT_URL_PREFIX


def _expiry_ms(value: Any) -> int | None:
    """Normalize upstreamExpiresAt (epoch millis number or ISO-8601 string)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return int(text)
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        # naive → assume UTC so the result is clock-independent
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return int(parsed.timestamp() * 1000)
    return None


def fresh_upstream_link(entry: dict[str, Any], *, now_ms: int | None = None) -> str | None:
    """Return the still-fresh upstream direct link carried on a mapped entry.

    The platform hands the upstream URL out together with ``upstreamExpiresAt``
    (server-computed, 24 h). Without a trustworthy expiry we never touch the
    link — the platform artifact URL is always the fallback, and an expired
    direct link must not burn one of the upstream's ~100 download credits.
    """
    upstream = entry.get("upstream_url")
    if not isinstance(upstream, str) or not upstream:
        return None
    expires_ms = _expiry_ms(entry.get("upstream_expires_at"))
    if expires_ms is None:
        return None
    current_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    if expires_ms <= current_ms:
        return None
    return upstream


def direct_link_candidates(entry: dict[str, Any], fallback_url: str) -> list[str]:
    """Download candidates for one mapped entry.

    v1 contract (artifact-backup-service): the platform no longer offers its own
    copy, so a platform entry carries ONLY the fresh upstream direct link — when
    the link is missing/expired there is no download source and the result is
    empty ("链接已过期"). Non-platform fallbacks (direct API-key mode) are still
    the sole URL and always usable.
    """
    direct = fresh_upstream_link(entry)
    candidates: list[str] = []
    if direct is not None:
        candidates.append(direct)
    if fallback_url and not fallback_url.startswith(ARTIFACT_URL_PREFIX) and fallback_url not in candidates:
        candidates.append(fallback_url)
    return candidates


class UrllibFallbackTransport:
    def download(self, url: str) -> bytes:
        with urllib.request.urlopen(url, timeout=60.0) as response:
            return response.read()


class PlatformArtifactTransport:
    def __init__(self, platform: PlatformClient, fallback=None) -> None:
        self._platform = platform
        self._fallback = fallback or UrllibFallbackTransport()

    def download(self, url: str) -> bytes:
        if url.startswith(ARTIFACT_URL_PREFIX):
            job_id = url[len(ARTIFACT_URL_PREFIX):]
            return self._platform.download_artifact(job_id)
        return self._fallback.download(url)
