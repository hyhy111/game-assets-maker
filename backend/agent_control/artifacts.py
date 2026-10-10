"""Discover bounded local media and sanitize cached JSON before Agent output."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

MEDIA = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".gif",
    ".heic",
    ".heif",
    ".mp4",
    ".mov",
    ".webm",
    ".wav",
    ".mp3",
    ".ogg",
    ".flac",
}
SENSITIVE = {
    "apikey",
    "authorization",
    "token",
    "accesstoken",
    "refreshtoken",
    "password",
    "secret",
    "credential",
    "credentials",
    "headers",
    "cookie",
}


def _sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z]", "", key.lower())
    return normalized in SENSITIVE or (
        normalized != "totaltokens"
        and any(
            word in normalized
            for word in (
                "secret",
                "password",
                "credential",
                "authorization",
                "token",
                "apikey",
                "accesskey",
                "privatekey",
                "cookie",
            )
        )
    )


def safe_metadata(value: Any, secrets: tuple[str, ...] = ()) -> Any:
    if isinstance(value, dict):
        return {key: safe_metadata(item, secrets) for key, item in value.items() if not _sensitive_key(str(key))}
    if isinstance(value, list):
        return [safe_metadata(item, secrets) for item in value]
    if isinstance(value, str):
        value = re.sub(r'https?://[^\s"<>]+', "[REMOTE_URL_REMOVED]", value, flags=re.IGNORECASE)
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
    return value


class LocalArtifacts:
    def __init__(self, locations, secrets: tuple[str, ...] = ()):
        self.locations = locations
        self.secrets = secrets
        self.roots = {
            "project": locations.projects_root.resolve(),
            "image": locations.ai_pic_cache_root.resolve(),
            "video": locations.ai_video_cache_root.resolve(),
        }

    def _files(self):
        for kind, root in self.roots.items():
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in MEDIA | {".json"}:
                    continue
                resolved = path.resolve()
                if not resolved.is_relative_to(root):
                    continue
                parts = path.relative_to(root).parts
                if any(part.startswith(".") for part in parts):
                    continue
                item = {
                    "path": str(resolved),
                    "source": kind,
                    "type": "metadata" if path.suffix == ".json" else "media",
                    "available": True,
                    "size_bytes": path.stat().st_size,
                    "step": None,
                }
                if kind == "project" and len(parts) >= 3:
                    if (root / parts[0] / "cache").is_dir():
                        item.update(project_id=parts[0], role="未迁移")
                    else:
                        animation_parts = (
                            (parts[0], parts[2])
                            if re.fullmatch(r"batch-trim(?:-\d+)?", parts[1]) and len(parts) >= 4
                            else parts[:2]
                        )
                        item.update(project_id="/".join(animation_parts), role=parts[0])
                    for step, directory in ((1, "01_frames"), (2, "02_no_bg"), (3, "03_hole_punched")):
                        if any(part.startswith(directory) for part in parts[2:]):
                            item["step"] = step
                elif kind != "project" and len(parts) >= 3:
                    item["task_id"] = parts[1]
                yield item
                if kind == "project" and path.name == "global_params.json":
                    try:
                        data = json.loads(path.read_text(encoding="utf-8"))
                        source = Path(data.get("video_path", "")).expanduser().resolve()
                        if source.is_file() and source.suffix.lower() in MEDIA and not source.is_relative_to(root):
                            yield {
                                **item,
                                "path": str(source),
                                "type": "media",
                                "size_bytes": source.stat().st_size,
                                "source": "project-input",
                            }
                    except (OSError, ValueError, TypeError):
                        continue

    def list(self, filters: dict[str, Any]) -> dict[str, Any]:
        limit, offset = filters.get("limit", 100), filters.get("offset", 0)
        if type(limit) is not int or not 1 <= limit <= 500 or type(offset) is not int or offset < 0:
            raise ValueError("INPUT_INVALID")
        items = {}
        for item in self._files():
            if any(
                filters.get(key) is not None and item.get(key) != filters[key]
                for key in ("project_id", "role", "step", "task_id", "source", "type")
            ):
                continue
            items[item["path"]] = item
        ordered = sorted(items.values(), key=lambda item: item["path"])
        return {
            "items": ordered[offset : offset + limit],
            "total": len(ordered),
            "offset": offset,
            "limit": limit,
            "next_offset": offset + limit if offset + limit < len(ordered) else None,
            "quality_verified": False,
        }

    def read(self, path: str) -> dict[str, Any]:
        if not isinstance(path, str) or not Path(path).is_absolute() or ".." in Path(path).parts:
            raise ValueError("PATH_NOT_ALLOWED")
        requested = Path(path)
        source = requested.resolve()
        for root in self.roots.values():
            if requested.is_relative_to(root) and not source.is_relative_to(root):
                raise ValueError("PATH_NOT_ALLOWED")
        allowed = next((item for item in self._files() if item["path"] == str(source)), None)
        if allowed is None:
            if not source.exists() and source.suffix.lower() in MEDIA | {".json"}:
                for root in self.roots.values():
                    if source.is_relative_to(root) and not any(
                        part.startswith(".") for part in source.relative_to(root).parts
                    ):
                        raise ValueError("ASSET_MISSING")
            raise ValueError("PATH_NOT_ALLOWED")
        if not source.is_file():
            raise ValueError("ASSET_MISSING")
        if source.suffix.lower() != ".json":
            return allowed
        if source.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("METADATA_TOO_LARGE")
        return {**allowed, "content": safe_metadata(json.loads(source.read_text(encoding="utf-8")), self.secrets)}
