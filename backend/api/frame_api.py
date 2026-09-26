"""Frame API - Frame retrieval and image operations"""

import base64
import io
from pathlib import Path
from typing import Any

from PIL import Image

from backend.api.frame_visibility import get_hidden_frame_names, restore_hidden_frames, set_frame_hidden
from backend.api.project_paths import resolve_project_path
from src.utils.data_paths import data_root, projects_root


class FrameAPI:
    """API for frame operations"""

    def __init__(self, assets_base_url: str = "http://localhost:8080"):
        self._projects_root = projects_root()
        self._project_root = data_root()
        self.assets_base_url = assets_base_url.rstrip("/")

    def set_assets_base_url(self, assets_base_url: str) -> None:
        self.assets_base_url = assets_base_url.rstrip("/")

    def get_frame_url(self, frame_path: str) -> str:
        """Convert local frame path to HTTP URL for efficient loading"""
        try:
            path = Path(frame_path)
            try:
                relative_path = path.relative_to(self._project_root)
                mtime = int(path.stat().st_mtime) if path.exists() else 0
                return f"{self.assets_base_url}/{relative_path.as_posix()}?t={mtime}"
            except ValueError:
                # Path is not under project root, return as-is
                return frame_path
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
