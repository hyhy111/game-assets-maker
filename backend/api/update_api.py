"""Check stable GitHub releases without blocking local processing or installing software."""

import json
import os
import re
import threading
import urllib.error
import urllib.request
import webbrowser
from typing import Any
from urllib.parse import urlsplit

from src.utils.app_config import load_app_config, save_app_config
from src.utils.app_version import app_version

REPOSITORY = "hyhy111/game-assets-maker"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
_VERSION = re.compile(r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:\+[0-9A-Za-z.-]+)?")


def release_version(value: str) -> tuple[int, int, int]:
    match = _VERSION.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        raise ValueError("Invalid stable version")
    return tuple(int(part) for part in match.groups())


class UpdateAPI:
    """Cache one startup check and persist only the explicitly ignored version."""

    def __init__(self):
        self._lock = threading.Lock()
        self._state = None

    def check(self) -> dict[str, Any]:
        with self._lock:
            if self._state is None:
                self._state = self._fetch_release()
            return self._public_state()

    def _public_state(self) -> dict[str, Any]:
        state = dict(self._state)
        if state["status"] == "available":
            ignored = load_app_config().get("ignored_update_version")
            if ignored == state["latest_version"]:
                state["status"] = "ignored"
        return state

    def _fetch_release(self) -> dict[str, Any]:
        state = {
            "current_version": app_version(),
            "latest_version": "",
            "release_notes": "",
            "release_url": "",
            "status": "error",
            "error": "",
        }
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "Game-Assets-Maker"}
        # Private-release testing is opt-in and never persists credentials or exposes them to JS.
        token = os.environ.get("GAM_UPDATE_GITHUB_TOKEN", "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(LATEST_RELEASE_URL, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError("Release response too large")
            release = json.loads(raw)
            if not isinstance(release, dict):
                raise ValueError("Invalid release response")
            tag = release.get("tag_name")
            latest = release_version(tag)
            current = release_version(state["current_version"])
            if release.get("draft") is not False or release.get("prerelease") is not False:
                raise ValueError("Not a published stable release")
            url = release.get("html_url", "")
            parsed = urlsplit(url)
            if (
                parsed.scheme != "https"
                or parsed.netloc != "github.com"
                or not parsed.path.startswith(f"/{REPOSITORY}/releases/tag/")
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("Invalid release page")
            notes = release.get("body") or ""
            if not isinstance(notes, str):
                raise ValueError("Invalid release notes")
            state.update(
                latest_version=tag.removeprefix("v").split("+", 1)[0],
                release_notes=notes,
                release_url=url,
                status="available" if latest > current else "up_to_date",
            )
        except urllib.error.HTTPError as error:
            if error.code == 404:
                state["error"] = "NOT_FOUND_OR_PRIVATE"
            elif error.code == 429 or (error.code == 403 and error.headers.get("X-RateLimit-Remaining") == "0"):
                state["error"] = "RATE_LIMITED"
            elif error.code in (401, 403):
                state["error"] = "ACCESS_DENIED"
            else:
                state["error"] = "NETWORK_ERROR"
        except (urllib.error.URLError, TimeoutError, OSError):
            state["error"] = "NETWORK_ERROR"
        except (ValueError, TypeError):
            state["error"] = "INVALID_RELEASE"
        return state

    def ignore(self, version: str) -> bool:
        with self._lock:
            if self._state is None or self._state["status"] != "available":
                return False
            if version != self._state["latest_version"]:
                return False
            try:
                save_app_config({"ignored_update_version": version})
            except (OSError, ValueError):
                return False
            return True

    def open_release(self) -> bool:
        with self._lock:
            if self._state is None or self._state["status"] != "available":
                return False
            try:
                return webbrowser.open(self._state["release_url"])
            except (OSError, webbrowser.Error):
                return False
