"""Frame API - Frame retrieval and image operations"""

import base64
import binascii
import hashlib
import io
import os
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image

from backend.api.frame_visibility import get_hidden_frame_names, restore_hidden_frames, set_frame_hidden
from backend.api.project_paths import media_url_for_path, resolve_project_path
from src.utils.app_config import default_projects_root
from src.utils.data_paths import data_root


class FrameAPI:
    """API for frame operations"""

    def __init__(self, assets_base_url: str = "http://localhost:8080", *, projects_root: Path | None = None):
        self._projects_root = projects_root if projects_root is not None else default_projects_root()
        self._project_root = data_root()
        self.assets_base_url = assets_base_url.rstrip("/")

    def set_assets_base_url(self, assets_base_url: str) -> None:
        self.assets_base_url = assets_base_url.rstrip("/")

    def get_frame_url(self, frame_path: str) -> str:
        """Convert local frame path to HTTP URL for efficient loading"""
        try:
            return media_url_for_path(
                Path(frame_path),
                projects_root=self._projects_root,
                data_root=self._project_root,
                base_url=self.assets_base_url,
            )
        except Exception as e:
            print(f"Error converting frame path: {e}")
            return frame_path

    def get_frames(
        self, project_id: str, step: int, page: int = 1, page_size: int = 50, use_cache: bool = True
    ) -> dict[str, Any]:
        """Get frames for a project at specific step with pagination"""
        project_path = resolve_project_path(self._projects_root, project_id)

        # Determine directory based on step
        if step == 1:
            # Step 1: always show cache frames for preview so users can adjust range/interval
            cache_dir = project_path / "cache" / "01_frames_cache"
            output_dir = project_path / "output" / "01_frames"

            frames_dir = cache_dir if use_cache and cache_dir.exists() else output_dir
        elif step == 2:
            frames_dir = project_path / "output" / "02_no_bg"
        elif step == 3:
            frames_dir = project_path / "output" / "03_hole_punched"
        else:
            return {"success": False, "error": "Invalid step"}

        if not frames_dir.exists():
            return {
                "success": True,
                "frames": [],
                "total": 0,
                "timeline_total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 0,
                "hidden_count": 0,
            }

        # Step 2/3 share a project-level non-destructive visibility list.
        all_frame_files = sorted(frames_dir.glob("*.png"))
        timeline_indices = {frame: index for index, frame in enumerate(all_frame_files)}
        hidden_frames = set(get_hidden_frame_names(project_path)) if step in {2, 3} else set()
        frame_files = [frame for frame in all_frame_files if frame.name not in hidden_frames]

        # Calculate pagination
        total = len(frame_files)
        total_pages = (total + page_size - 1) // page_size
        start_idx = (page - 1) * page_size
        end_idx = min(start_idx + page_size, total)

        # Build frame list
        frames = []
        for i, frame_file in enumerate(frame_files[start_idx:end_idx], start=start_idx):
            frame_path = str(frame_file)
            frames.append(
                {
                    "index": i,
                    "timeline_index": timeline_indices[frame_file],
                    "name": frame_file.stem,
                    "path": frame_path,
                    "filename": frame_file.name,
                    "url": self.get_frame_url(frame_path),
                }
            )

        return {
            "success": True,
            "frames": frames,
            "total": total,
            "timeline_total": len(all_frame_files),
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "hidden_count": len(hidden_frames),
        }

    def get_hidden_frames(self, project_id: str) -> list[str]:
        project_path = resolve_project_path(self._projects_root, project_id)
        return get_hidden_frame_names(project_path)

    def set_frame_hidden(self, project_id: str, filename: str, hidden: bool = True) -> dict[str, Any]:
        project_path = resolve_project_path(self._projects_root, project_id)
        hidden_frames = set_frame_hidden(project_path, filename, hidden)
        return {"success": True, "hidden_frames": hidden_frames}

    def restore_hidden_frames(self, project_id: str) -> dict[str, Any]:
        project_path = resolve_project_path(self._projects_root, project_id)
        return {"success": True, "hidden_frames": restore_hidden_frames(project_path)}

    def _editable_frame_path(self, project_id: str, filename: str, step: int = 3) -> Path:
        if type(step) is not int or step not in (2, 3):
            raise ValueError("FRAME_EDIT_INVALID_STEP")
        if (
            not isinstance(filename, str)
            or not filename
            or Path(filename).name != filename
            or "/" in filename
            or "\\" in filename
            or Path(filename).suffix.lower() != ".png"
        ):
            raise ValueError("FRAME_EDIT_INVALID_FILENAME")
        if (
            not isinstance(project_id, str)
            or "\\" in project_id
            or len(project_id.split("/")) not in (1, 2)
            or any(part in ("", ".", "..") for part in project_id.split("/"))
        ):
            raise ValueError("FRAME_EDIT_INVALID_PROJECT")
        project = resolve_project_path(self._projects_root, project_id).resolve()
        if not project.is_relative_to(self._projects_root.resolve()) or project == self._projects_root.resolve():
            raise ValueError("FRAME_EDIT_INVALID_PROJECT")
        directory = project / "output" / {2: "02_no_bg", 3: "03_hole_punched"}[step]
        frame = directory / filename
        if directory.resolve() != directory or frame.is_symlink() or not frame.is_file():
            raise ValueError("FRAME_EDIT_NOT_FOUND")
        return frame

    def get_editable_frame(self, project_id: str, filename: str, step: int = 3) -> dict[str, Any]:
        """Open a Step 2/3 output frame with an optimistic concurrency revision."""
        frame = self._editable_frame_path(project_id, filename, step)
        payload = frame.read_bytes()
        with Image.open(io.BytesIO(payload)) as image:
            width, height = image.size
        return {
            "image_data_url": "data:image/png;base64," + base64.b64encode(payload).decode("ascii"),
            "revision": hashlib.sha256(payload).hexdigest(),
            "width": width,
            "height": height,
        }

    def save_frame_edit(
        self, project_id: str, filename: str, image_data_url: str, revision: str, step: int = 3
    ) -> dict[str, Any]:
        """Validate dimensions and preserve the pre-edit frame before an atomic PNG replacement."""
        frame = self._editable_frame_path(project_id, filename, step)
        current = frame.read_bytes()
        if not isinstance(revision, str) or hashlib.sha256(current).hexdigest() != revision:
            raise ValueError("FRAME_EDIT_STALE")
        prefix = "data:image/png;base64,"
        if (
            not isinstance(image_data_url, str)
            or not image_data_url.startswith(prefix)
            or len(image_data_url) > 64 * 1024 * 1024
        ):
            raise ValueError("FRAME_EDIT_INVALID_PNG")
        try:
            payload = base64.b64decode(image_data_url[len(prefix) :], validate=True)
            with Image.open(io.BytesIO(payload)) as opened:
                if opened.format != "PNG":
                    raise ValueError("FRAME_EDIT_INVALID_PNG")
                edited = opened.convert("RGBA")
            with Image.open(io.BytesIO(current)) as original:
                if edited.size != original.size:
                    raise ValueError("FRAME_EDIT_SIZE_CHANGED")
        except (OSError, binascii.Error) as error:
            raise ValueError("FRAME_EDIT_INVALID_PNG") from error
        project = resolve_project_path(self._projects_root, project_id).resolve()
        backups = project / "cache" / "frame_edits" / revision
        if not backups.resolve().is_relative_to(project):
            raise ValueError("FRAME_EDIT_INVALID_BACKUP")
        backups.mkdir(parents=True, exist_ok=True)
        backup = backups / filename
        if not backup.exists():
            backup.write_bytes(current)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=frame.parent, prefix=".frame-edit-", suffix=".tmp", delete=False
            ) as temporary:
                temporary_path = Path(temporary.name)
                edited.save(temporary, format="PNG")
            os.replace(temporary_path, frame)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return {"success": True, "path": str(frame), "revision": hashlib.sha256(frame.read_bytes()).hexdigest()}

    def get_frame_image(self, frame_path: str) -> str:
        """Get frame image as base64 encoded string"""
        try:
            with open(frame_path, "rb") as f:
                data = f.read()
                return base64.b64encode(data).decode("utf-8")
        except FileNotFoundError:
            # Silent fallback for deleted/temporarily missing frames during processing
            return "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        except Exception as e:
            print(f"Error reading frame: {e}")
            # Return 1x1 transparent pixel
            return "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

    def get_frame_thumbnail(self, frame_path: str, size: int = 128) -> str:
        """Get frame thumbnail as base64 encoded string"""
        try:
            with open(frame_path, "rb") as f:
                img = Image.open(f)
                img.thumbnail((size, size), Image.LANCZOS)

                buffer = io.BytesIO()
                img.save(buffer, format="PNG")
                return base64.b64encode(buffer.getvalue()).decode("utf-8")
        except Exception as e:
            print(f"Error creating thumbnail: {e}")
            return self.get_frame_image(frame_path)

    def get_first_frame(self, project_id: str, step: int) -> str | None:
        """Get first frame path for a project step"""
        result = self.get_frames(project_id, step, page=1, page_size=1)
        if result["success"] and result["frames"]:
            return result["frames"][0]["path"]
        return None
