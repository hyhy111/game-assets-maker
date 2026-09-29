"""Project API - Project management endpoints"""

import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.api.project_paths import (
    LEGACY_ROLE,
    UNKNOWN_ROLE,
    is_legacy_import_project_dir,
    is_project_dir,
    make_project_id,
    resolve_project_path,
    sanitize_segment,
    split_project_id,
)
from src.utils.app_config import default_projects_root


class ProjectAPI:
    """API for project CRUD operations"""

    def __init__(self, projects_root: Path | None = None):
        self._projects_root = projects_root if projects_root is not None else default_projects_root()
        self._projects_root.mkdir(parents=True, exist_ok=True)

    def _get_project_path(self, project_id: str) -> Path:
        """Get full path to project directory"""
        return resolve_project_path(self._projects_root, project_id)

    def _load_project_meta(self, project_path: Path) -> dict[str, Any] | None:
        """Load project metadata from cache directory"""
        meta_path = project_path / "cache" / "global_params.json"
        if meta_path.exists():
            with open(meta_path, encoding="utf-8") as f:
                return json.load(f)
        return None

    def _project_to_dict(self, project_path: Path, role: str, action: str, legacy: bool) -> dict[str, Any]:
        meta = self._load_project_meta(project_path)
        modified_at = datetime.fromtimestamp(project_path.stat().st_mtime).isoformat()
        project_id = action if legacy else make_project_id(role, action)

        return {
            "id": project_id,
            "role": role,
            "action": action,
            "legacy": legacy,
            "name": meta.get("project_name", action) if meta else action,
            "path": str(project_path),
            "video_path": meta.get("video_path", "") if meta else "",
            "frame_interval": meta.get("frame_interval", 1) if meta else 1,
            "created_at": meta.get("timestamp", "") if meta else "",
            "modified_at": modified_at,
            "steps": self._get_step_status(project_path),
        }

    def get_projects(self) -> list[dict[str, Any]]:
        """Get list of all action projects with metadata."""
        projects = []

        if not self._projects_root.exists():
            return projects

        for first_level in sorted(self._projects_root.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if not first_level.is_dir():
                continue

            if is_project_dir(first_level):
                projects.append(self._project_to_dict(first_level, LEGACY_ROLE, first_level.name, True))
                continue

            for action_dir in sorted(first_level.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
                if action_dir.is_dir() and is_project_dir(action_dir):
                    projects.append(self._project_to_dict(action_dir, first_level.name, action_dir.name, False))

        return projects

    def get_roles(self) -> list[dict[str, Any]]:
        """Get role list with project counts for selectors."""
        role_counts: dict[str, int] = {}
        for project in self.get_projects():
            role = project.get("role") or UNKNOWN_ROLE
            role_counts[role] = role_counts.get(role, 0) + 1

        return [
            {"name": role, "projectCount": count}
            for role, count in sorted(role_counts.items(), key=lambda item: item[0].lower())
        ]

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        """Get single project by ID"""
        project_path = self._get_project_path(project_id)

        if not project_path.exists():
            return None

        role, action = split_project_id(project_id)
        legacy = role is None
        if legacy:
            action = action or project_id
            role = LEGACY_ROLE

        meta = self._load_project_meta(project_path)

        result = {
            "id": project_id,
            "role": role,
            "action": action,
            "legacy": legacy,
            "name": meta.get("project_name", action) if meta else action,
            "path": str(project_path),
            "video_path": meta.get("video_path", "") if meta else "",
            "frame_interval": meta.get("frame_interval", 1) if meta else 1,
            "created_at": meta.get("timestamp", "") if meta else "",
            "modified_at": datetime.fromtimestamp(project_path.stat().st_mtime).isoformat(),
            "output_path": str(project_path / "output"),
            "cache_path": str(project_path / "cache"),
            "steps": self._get_step_status(project_path),
        }

        return result

    def _get_step_status(self, project_path: Path) -> dict[str, Any]:
        """Get completion status for each step based on unified config"""
        steps = {
            "1": {"completed": False, "data_ready": False, "count": 0, "processed": False},
            "2": {"completed": False, "data_ready": False, "count": 0, "processed": False},
            "3": {"completed": False, "data_ready": False, "count": 0, "processed": False},
        }

        # Read from unified steps config
        config_path = project_path / "cache" / "steps_config.json"
        config = {}

        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    config = json.load(f)
            except Exception as e:
                print(f"Error reading steps config: {e}")

        has_unified_config = config_path.exists()

        # Check processed flag for each step (primary switch for navigation)
        for step_num in ["1", "2", "3"]:
            step_key = f"step{step_num}"
            if step_key in config and config[step_key].get("processed", False):
                steps[step_num]["processed"] = True
                steps[step_num]["completed"] = True

        # Step 1: Check cache/01_frames_cache and output/01_frames
        step1_cache = project_path / "cache" / "01_frames_cache"
        step1_output = project_path / "output" / "01_frames"
        cache_frames = list(step1_cache.glob("frame_*.png")) if step1_cache.exists() else []
        output_frames = list(step1_output.glob("frame_*.png")) if step1_output.exists() else []
        # New projects use the processed flag for navigation. File existence means
        # preview data is available, not that Step 1 has been accepted.
        if not has_unified_config and not steps["1"]["completed"]:
            steps["1"]["completed"] = len(output_frames) > 0
        steps["1"]["data_ready"] = len(cache_frames) > 0
        steps["1"]["count"] = len(output_frames) if len(output_frames) > 0 else len(cache_frames)

        # Step 2: Check output/02_no_bg
        step2_output = project_path / "output" / "02_no_bg"
        if step2_output.exists():
            frames = list(step2_output.glob("*.png"))
            if not steps["2"]["completed"]:
                steps["2"]["completed"] = len(frames) > 0
            steps["2"]["count"] = len(frames)

        # Step 3: Check output/03_hole_punched (new location)
        step3_output = project_path / "output" / "03_hole_punched"
        if step3_output.exists():
            frames = list(step3_output.glob("*.png"))
            if not steps["3"]["completed"]:
                steps["3"]["completed"] = len(frames) > 0
            steps["3"]["count"] = len(frames)

        return steps

    def create_project(self, role: str, action: str, video_path: str = "", frame_interval: int = 1) -> dict[str, Any]:
        """Create a new action project under a role."""
        # Backward compatibility with the old signature: (name, video_path, frame_interval)
        if isinstance(video_path, int):
            video_path = action
            action = role
            role = UNKNOWN_ROLE

        safe_role = sanitize_segment(role, UNKNOWN_ROLE)
        safe_action = self._sanitize_name(action)
        project_id = make_project_id(safe_role, safe_action)

        # Check for duplicate action in the same role (case-insensitive)
        existing_projects = self.get_projects()
        for project in existing_projects:
            if project.get("legacy"):
                continue
            if (
                project.get("role", "").lower() == safe_role.lower()
                and project.get("action", "").lower() == safe_action.lower()
            ):
                raise ValueError(f"角色 '{safe_role}' 下的动作 '{action}' 已存在，请使用其他名称")

        # Create directory structure
        project_path = self._get_project_path(project_id)
        (project_path / "cache").mkdir(parents=True)
        (project_path / "output" / "01_frames").mkdir(parents=True)
        (project_path / "output" / "02_no_bg").mkdir(parents=True)
        (project_path / "output" / "03_hole_punched").mkdir(parents=True)
        (project_path / "cache" / "01_frames_cache").mkdir(parents=True)

        # Determine actual last frame and fps for default step1 params
        end_frame = -1
        fps = 30  # Default fallback
        if video_path and Path(video_path).exists():
            from backend.core.video_utils import (
                validate_video,
            )

            try:
                vinfo = validate_video(str(video_path))
                if vinfo.get("frame_count"):
                    end_frame = int(vinfo["frame_count"]) - 1
                if vinfo.get("fps"):
                    # Round to integer as requested
                    fps = int(round(float(vinfo["fps"])))
            except Exception:
                pass

        # Save metadata
        meta = {
            "project_name": action,
            "role": safe_role,
            "action": safe_action,
            "video_path": video_path,
            "fps": fps,
            "frame_interval": 1,
            "timestamp": datetime.now().isoformat(),
        }

        with open(project_path / "cache" / "global_params.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        # Save unified steps config (new structure)
        steps_config = {
            "step1": {
                "frame_interval": 1,
                "start_frame": 0,
                "end_frame": end_frame,
                "fps": fps,
                "processed": False,
                "processing_time": 0,
            },
            "background_color": None,  # Will be set after step 1
            "step2": {
                # Step 2: Background removal only (rembg parameters)
                "alpha_matting": True,
                "alpha_matting_erode_size": 5,
                "alpha_matting_background_threshold": 120,
                "alpha_matting_foreground_threshold": 240,
                "edge_erode": 1,
                "fps": 10,  # Playback fps for preview
                "processed": False,
            },
            "step3": {
                # Step 3: Post-processing (hole punching + alignment)
                "enabled": True,  # Hole punching enabled
                "green_intensity": 3,
                "feather_radius": 3,
                "min_hole_size": 5,
                "align_enabled": False,  # Alignment disabled by default
                "align_h": False,  # Horizontal centering (default off)
                "align_v": False,  # Vertical bottom alignment (default off)
                "use_padding": True,  # Use bottom padding
                "padding_bottom": 10,  # Bottom padding pixels
                "fps": 10,  # Playback fps for preview
                "processed": False,
            },
        }
        with open(project_path / "cache" / "steps_config.json", "w", encoding="utf-8") as f:
            json.dump(steps_config, f, ensure_ascii=False, indent=2)

        # Extract frames to cache immediately - save ALL frames (frame_interval = 1)
        if video_path and Path(video_path).exists():
            from backend.core.video_utils import process_video_to_cache

            cache_dir = project_path / "cache" / "01_frames_cache"
            try:
                print(f"[DEBUG] Starting frame extraction for project: {project_id}")
                # Extract all frames (frame_interval = 1)
                result = process_video_to_cache(str(video_path), str(cache_dir), frame_interval=1)
                print(f"[DEBUG] Frame extraction completed: {result}")

                # After extraction, calculate background color from cache frames
                print("[DEBUG] Starting background color calculation...")
                bg_hsv = self._calculate_background_color_from_cache(str(cache_dir))
                if bg_hsv:
                    print(f"[DEBUG] Background color calculated: {bg_hsv}, updating config...")
                    update_result = self._update_background_color_in_config(str(project_path), bg_hsv)
                    print(f"[DEBUG] Background color update result: {update_result}")
                else:
                    print("[WARNING] Failed to calculate background color")
            except Exception as e:
                print(f"Error extracting frames during project creation: {e}")
                import traceback

                traceback.print_exc()

        return {
            "id": project_id,
            "role": safe_role,
            "action": safe_action,
            "legacy": False,
            "name": action,
            "path": str(project_path),
            "video_path": video_path,
            "frame_interval": 1,
            "created_at": meta["timestamp"],
            "steps": self._get_step_status(project_path),
        }

    def _sanitize_name(self, name: str) -> str:
        """Sanitize project name for filesystem"""
        # Remove invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, "_")
        # Strip whitespace
        name = name.strip()
        # Ensure not empty
        if not name:
            name = "untitled_project"
        return name

    def _calculate_background_color_from_cache(self, cache_dir: str, sample_count: int = 3) -> tuple | None:
        """
        Calculate background color by sampling from random frames in cache.
        Randomly selects `sample_count` frames and averages their corner colors.

        Args:
            cache_dir: Path to cache directory containing frames
            sample_count: Number of frames to sample (default 3)

        Returns:
            Tuple of (H, S, V) or None if calculation failed
        """
        import random
        from pathlib import Path

        import cv2
        import numpy as np

        print(f"[DEBUG] Calculating background color from cache: {cache_dir}")

        cache_path = Path(cache_dir)
        if not cache_path.exists():
            print(f"[DEBUG] Cache path does not exist: {cache_dir}")
            return None

        frames = sorted(cache_path.glob("frame_*.png"))
        print(f"[DEBUG] Found {len(frames)} frames in cache")

        if not frames:
            return None

        # Randomly sample frames.
        sampled_frames = frames if len(frames) <= sample_count else random.sample(list(frames), sample_count)

        print(f"[DEBUG] Sampled {len(sampled_frames)} frames for background calculation")

        all_corner_colors = []

        for frame_path in sampled_frames:
            try:
                # Read image
                img_array = np.fromfile(str(frame_path), dtype=np.uint8)
                img_bgr = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

                if img_bgr is None:
                    print(f"[DEBUG] Failed to read image: {frame_path}")
                    continue

                # Convert to HSV and sample corners
                hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
                h, w = img_bgr.shape[:2]

                # Sample from four corners
                corners = [
                    (5, 5),  # top-left
                    (5, w - 5),  # top-right
                    (h - 5, 5),  # bottom-left
                    (h - 5, w - 5),  # bottom-right
                ]

                for y, x in corners:
                    y = max(0, min(y, h - 1))
                    x = max(0, min(x, w - 1))
                    all_corner_colors.append(hsv[y, x])

                print(f"[DEBUG] Sampled corners from {frame_path.name}: {[hsv[y, x].tolist() for y, x in corners]}")

            except Exception as e:
                print(f"[Warning] Failed to sample from {frame_path}: {e}")
                continue

        if not all_corner_colors:
            print("[DEBUG] No corner colors collected")
            return None

        # Calculate average HSV
        avg_hsv = tuple(int(x) for x in np.mean(all_corner_colors, axis=0).astype(int))
        print(f"[DEBUG] Calculated average HSV: {avg_hsv} from {len(all_corner_colors)} corner samples")
        return avg_hsv

    def _update_background_color_in_config(self, project_path: str, bg_hsv: tuple) -> bool:
        """
        Update background color in steps_config.json

        Args:
            project_path: Path to project directory
            bg_hsv: Background color as (H, S, V) tuple

        Returns:
            True if successful, False otherwise
        """
        import cv2
        import numpy as np

        config_path = Path(project_path) / "cache" / "steps_config.json"
        print(f"[DEBUG] Updating background color in: {config_path}")
        print(f"[DEBUG] bg_hsv: {bg_hsv}")

        try:
            # Load existing config
            config = {}
            if config_path.exists():
                try:
                    with open(config_path, encoding="utf-8") as f:
                        config = json.load(f)
                    print(f"[DEBUG] Loaded existing config with keys: {list(config.keys())}")
                except Exception as e:
                    print(f"[Warning] Failed to read existing config: {e}")
                    # If read fails, we still have empty config
            else:
                print("[DEBUG] Config file does not exist, creating new one")

            # Ensure step configs exist
            for step_num in [1, 2, 3]:
                step_key = f"step{step_num}"
                if step_key not in config:
                    config[step_key] = (
                        {"frame_interval": 1, "start_frame": 0, "end_frame": -1, "fps": 30, "processed": False}
                        if step_num == 1
                        else {
                            "alpha_matting": True,
                            "alpha_matting_erode_size": 5,
                            "alpha_matting_background_threshold": 120,
                            "alpha_matting_foreground_threshold": 240,
                            "edge_erode": 1,
                            "fps": 10,
                            "processed": False,
                        }
                        if step_num == 2
                        else {
                            "enabled": True,
                            "green_intensity": 3,
                            "feather_radius": 3,
                            "min_hole_size": 5,
                            "align_enabled": False,
                            "align_h": False,
                            "align_v": False,
                            "use_padding": True,
                            "padding_bottom": 10,
                            "fps": 10,
                            "processed": False,
                        }
                    )

            # Convert HSV to RGB for display
            hsv_array = np.uint8([[list(bg_hsv)]])
            rgb_array = cv2.cvtColor(hsv_array, cv2.COLOR_HSV2RGB)[0][0]
            rgb = tuple(int(x) for x in rgb_array)

            # Update background color
            config["background_color"] = {
                "hsv": [int(x) for x in bg_hsv],
                "rgb": [int(x) for x in rgb],
                "sampled_from": "random_3_frames_corners",
            }
            print(f"[DEBUG] Updated config background_color: {config['background_color']}")

            # Save back
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            print("[DEBUG] Config saved successfully")

            return True
        except Exception as e:
            print(f"[Error] Failed to update background color: {e}")
            import traceback

            traceback.print_exc()
            return False

    def delete_project(self, project_id: str) -> bool:
        """Delete a project and all its data"""
        project_path = self._get_project_path(project_id)

        if not project_path.exists():
            return False

        try:
            shutil.rmtree(project_path)
            return True
        except Exception as e:
            print(f"Error deleting project: {e}")
            return False

    def delete_role(self, role: str) -> bool:
        """Delete a role and all action projects under it."""
        safe_role = sanitize_segment(role, UNKNOWN_ROLE)

        try:
            if safe_role == LEGACY_ROLE:
                deleted_any = False
                for project_dir in list(self._projects_root.iterdir()):
                    if project_dir.is_dir() and is_project_dir(project_dir):
                        shutil.rmtree(project_dir)
                        deleted_any = True
                return deleted_any

            role_path = self._projects_root / safe_role
            if not role_path.exists() or not role_path.is_dir():
                return False

            shutil.rmtree(role_path)
            return True
        except Exception as e:
            print(f"Error deleting role {role}: {e}")
            return False

    def update_project(self, project_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update project metadata"""
        project_path = self._get_project_path(project_id)

        if not project_path.exists():
            raise ValueError(f"Project {project_id} not found")

        meta_path = project_path / "cache" / "global_params.json"

        # Load existing meta
        meta = {}
        if meta_path.exists():
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)

        # Update fields
        if "name" in data:
            new_name = data["name"]
            # Check for duplicate name (excluding current project)
            existing_projects = self.get_projects()
            for project in existing_projects:
                if project["id"] != project_id and project["name"].lower() == new_name.lower():
                    raise ValueError(f"项目 '{new_name}' 已存在，请使用其他名称")
            meta["project_name"] = new_name
        if "fps" in data:
            meta["fps"] = data["fps"]

        # Save back
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        return self.get_project(project_id)

    def migrate_legacy_projects(self, migrations: Any = UNKNOWN_ROLE) -> dict[str, Any]:
        """Move legacy flat project directories into role/action targets.

        Backward compatibility: passing a string still migrates every legacy
        project under that one role. New callers should pass a list of
        {projectId, targetRole, targetAction} mappings.
        """
        legacy_dirs = (
            [path for path in self._projects_root.iterdir() if path.is_dir() and is_project_dir(path)]
            if self._projects_root.exists()
            else []
        )
        legacy_by_id = {path.name: path for path in legacy_dirs}

        if isinstance(migrations, str):
            safe_role = sanitize_segment(migrations, UNKNOWN_ROLE)
            migrations = [
                {
                    "projectId": legacy_dir.name,
                    "targetRole": safe_role,
                    "targetAction": legacy_dir.name,
                }
                for legacy_dir in legacy_dirs
                if legacy_dir.name != safe_role
            ]

        normalized = []
        conflicts = []
        seen_targets = set()

        for item in migrations or []:
            project_id = sanitize_segment(str(item.get("projectId", "")), "")
            source_path = legacy_by_id.get(project_id)
            safe_role = sanitize_segment(str(item.get("targetRole", "")), UNKNOWN_ROLE)
            safe_action = sanitize_segment(str(item.get("targetAction", project_id)), project_id or "untitled_project")
            target_root = self._projects_root / safe_role
            target_path = target_root / safe_action
            target_id = make_project_id(safe_role, safe_action)

            if not source_path:
                conflicts.append({"projectId": project_id, "targetPath": str(target_path), "reason": "旧项目不存在"})
                continue

            if target_root.exists() and is_project_dir(target_root):
                conflicts.append(
                    {"projectId": project_id, "targetPath": str(target_root), "reason": "目标角色名与旧项目目录冲突"}
                )
                continue

            if target_id in seen_targets:
                conflicts.append(
                    {"projectId": project_id, "targetPath": str(target_path), "reason": "多个旧项目指向同一目标"}
                )
                continue

            if target_path.exists():
                conflicts.append({"projectId": project_id, "targetPath": str(target_path), "reason": "目标目录已存在"})
                continue

            seen_targets.add(target_id)
            normalized.append(
                {
                    "projectId": project_id,
                    "sourcePath": source_path,
                    "targetRole": safe_role,
                    "targetAction": safe_action,
                    "targetPath": target_path,
                    "targetId": target_id,
                }
            )

        if conflicts:
            return {"success": False, "migrated": [], "conflicts": conflicts}

        migrated = []
        for item in normalized:
            target_path = item["targetPath"]
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(item["sourcePath"]), str(target_path))

            meta_path = target_path / "cache" / "global_params.json"
            meta = {}
            if meta_path.exists():
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f)
            meta["role"] = item["targetRole"]
            meta["action"] = item["targetAction"]
            meta["project_name"] = item["targetAction"]
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

            migrated.append({"from": item["projectId"], "to": item["targetId"], "path": str(target_path)})

        return {"success": True, "migrated": migrated, "conflicts": []}

    def _resolve_legacy_import_source(self, selected_root: Path) -> tuple[Path, list[Path]] | None:
        """Resolve the actual legacy project root from the user-selected directory.

        Checks the selected directory first, then its direct ``project/``
        subdirectory, without recursing any further. Returns the resolved
        root together with the frozen list of valid legacy projects, or None
        when no candidate contains valid legacy projects.
        """
        for candidate in (selected_root, selected_root / "project"):
            if not candidate.is_dir():
                continue
            projects = sorted(
                (path for path in candidate.iterdir() if path.is_dir() and is_legacy_import_project_dir(path)),
                key=lambda path: path.name.casefold(),
            )
            if projects:
                return candidate, projects
        return None

    def import_legacy_project_directory(self, source_directory: str) -> dict[str, Any]:
        """Copy valid projects from a user-selected legacy project directory."""
        selected_root = Path(source_directory).expanduser().resolve()
        if not selected_root.is_dir():
            raise ValueError("所选旧项目目录不存在")

        resolved = self._resolve_legacy_import_source(selected_root)
        if resolved is None:
            return {
                "success": False,
                "source": str(selected_root),
                "imported": [],
                "skipped": [],
                "failed": [{"projectId": "", "reason": "所选目录中没有有效的旧项目"}],
            }

        source_root, source_projects = resolved
        if source_root.resolve() == self._projects_root.resolve():
            raise ValueError("所选目录已经是当前项目目录")

        existing_names = {
            path.name.casefold()
            for path in self._projects_root.iterdir()
            if path.is_dir()
        }
        imported: list[dict[str, str]] = []
        skipped: list[dict[str, str]] = []
        failed: list[dict[str, str]] = []

        for source_project in source_projects:
            project_id = sanitize_segment(source_project.name, "")
            if not project_id:
                failed.append({"projectId": source_project.name, "reason": "项目目录名无效"})
                continue
            target = self._projects_root / project_id
            if project_id.casefold() in existing_names:
                skipped.append({"projectId": project_id, "reason": "同名项目已存在"})
                continue

            staging = Path(tempfile.mkdtemp(prefix=".gam-import-", dir=self._projects_root))
            try:
                shutil.copytree(source_project, staging, dirs_exist_ok=True)
                if not is_legacy_import_project_dir(staging):
                    raise ValueError("复制后的项目校验失败")
                staging.replace(target)
                existing_names.add(project_id.casefold())
                imported.append({"projectId": project_id, "path": str(target)})
            except Exception as error:
                failed.append({"projectId": project_id, "reason": str(error)})
            finally:
                if staging.exists():
                    shutil.rmtree(staging)

        return {
            "success": not failed,
            "source": str(source_root),
            "imported": imported,
            "skipped": skipped,
            "failed": failed,
        }
