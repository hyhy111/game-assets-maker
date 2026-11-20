"""Manage the rebuildable source-frame cache used by Step 1."""

import json
import re
import tempfile
import threading
from datetime import date, datetime
from pathlib import Path

from backend.api.project_paths import project_video_path
from src.utils.file_operations import rename_path

_CACHE_NAME = "01_frames_cache"
_REBUILD_MARKER = ".rebuild-required"
_FRAME_NAME = re.compile(r"frame_[0-9]{6,}\.png")
_preview_lock = threading.RLock()


def preview_directory(project: Path) -> Path:
    return project / "cache" / _CACHE_NAME


def _safe_directory(directory: Path) -> bool:
    project = directory.parent.parent.resolve()
    return not directory.is_symlink() and directory.resolve() == preview_directory(project)


def _safe_project(projects_root: Path, project: Path) -> bool:
    try:
        relative = project.absolute().relative_to(projects_root.absolute())
    except ValueError:
        return False
    return (
        bool(relative.parts) and ".." not in relative.parts and project.resolve() == projects_root.resolve() / relative
    )


def _cached_frames(directory: Path) -> list[Path]:
    if not _safe_directory(directory) or not directory.is_dir():
        return []
    return [
        path
        for path in directory.iterdir()
        if _FRAME_NAME.fullmatch(path.name) and not path.is_symlink() and path.is_file()
    ]


def visible_preview_frames(project: Path) -> list[Path]:
    directory = preview_directory(project)
    if (directory / _REBUILD_MARKER).exists():
        return []
    return _cached_frames(directory)


def _mark_rebuild_required(directory: Path) -> Path:
    marker = directory / _REBUILD_MARKER
    if marker.is_symlink() or (marker.exists() and not marker.is_file()):
        raise OSError("Invalid preview cache marker")
    marker.touch(exist_ok=True)
    return marker


def ensure_preview_frames(projects_root: Path, project: Path, video_path: str | None = None, progress=None) -> bool:
    """Rebuild a missing preview from the source video without changing processing outputs."""
    with _preview_lock:
        directory = preview_directory(project)
        if visible_preview_frames(project):
            return True
        if not _safe_project(projects_root, project) or not _safe_directory(directory):
            raise OSError("Invalid preview cache directory")
        if not video_path:
            metadata = directory.parent / "global_params.json"
            if metadata.is_file():
                video_path = project_video_path(project, json.loads(metadata.read_text(encoding="utf-8")))
        if not video_path or not Path(video_path).is_file():
            if (directory / _REBUILD_MARKER).exists():
                raise ValueError("The source video for this cleared preview cache is missing")
            return False

        from backend.core.video_utils import process_video_to_cache

        directory.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=directory.parent, prefix=".preview-frames-") as staging:
            result = process_video_to_cache(video_path, staging, frame_interval=1, progress_callback=progress)
            if not result["total_frames"]:
                raise ValueError("No preview frames could be decoded from the source video")
            directory.mkdir(exist_ok=True)
            marker = _mark_rebuild_required(directory)
            new_frames = list(Path(staging).iterdir())
            new_names = {frame.name for frame in new_frames}
            for frame in new_frames:
                rename_path(frame, directory / frame.name, replace=True)
            for frame in _cached_frames(directory):
                if frame.name not in new_names:
                    frame.unlink()
            marker.unlink()
        return True


def _parse_date(value: str) -> date | None:
    if value == "":
        return None
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise ValueError("INVALID_PREVIEW_DATES")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("INVALID_PREVIEW_DATES") from error


def _creation_date(value: str) -> date | None:
    try:
        created = datetime.fromisoformat(value)
        return (created.astimezone() if created.tzinfo else created).date()
    except (TypeError, ValueError):
        return None


def _can_rebuild(video_path: str) -> bool:
    if not video_path or not Path(video_path).is_file():
        return False

    import cv2

    capture = cv2.VideoCapture(video_path)
    try:
        return capture.isOpened() and capture.read()[0]
    except cv2.error:
        return False
    finally:
        capture.release()


def preview_cache_cleanup(
    projects_root: Path, projects: list[dict], created_from: str, created_to: str, only_ids: set[str] | None = None
) -> dict:
    """Estimate an inclusive creation-date range, or clear explicitly confirmed animations."""
    start, end = _parse_date(created_from), _parse_date(created_to)
    if start and end and start > end:
        raise ValueError("INVALID_PREVIEW_DATES")
    result = {"project_ids": [], "frame_count": 0, "bytes": 0, "skipped": 0, "failed": 0}
    with _preview_lock:
        for project in projects:
            project_id = project["id"]
            if only_ids is not None and project_id not in only_ids:
                continue
            if start or end:
                created = _creation_date(project["created_at"])
                if created is None or (start and created < start) or (end and created > end):
                    continue
            try:
                project_path = Path(project["path"])
                directory = preview_directory(project_path)
                if not _safe_project(projects_root, project_path) or not _safe_directory(directory):
                    result["skipped"] += 1
                    continue
                frames = _cached_frames(directory)
                if not frames:
                    continue
                if not _can_rebuild(project["video_path"]):
                    result["skipped"] += 1
                    continue
                entries = [(frame, frame.stat().st_size) for frame in frames]
                if only_ids is not None:
                    _mark_rebuild_required(directory)
            except (OSError, RuntimeError, ValueError):
                result["failed"] += 1
                continue

            processed = failed = False
            for frame, size in entries:
                if only_ids is not None:
                    try:
                        frame.unlink()
                    except OSError:
                        failed = True
                        continue
                processed = True
                result["frame_count"] += 1
                result["bytes"] += size
            if processed:
                result["project_ids"].append(project_id)
            if failed:
                result["failed"] += 1
    return result
