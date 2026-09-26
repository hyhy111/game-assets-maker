"""Batch trim API for transparent margin cropping."""

import json
import math
import os
import wave
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from backend.api.frame_visibility import get_hidden_frame_names
from backend.api.project_paths import (
    LEGACY_ROLE,
    UNKNOWN_ROLE,
    resolve_project_path,
    sanitize_segment,
    split_project_id,
)
from src.utils.data_paths import projects_root


def _imread_unicode(path: Path) -> Any:
    """Unicode-safe image read for Windows"""
    img_array = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(img_array, cv2.IMREAD_UNCHANGED)


def _imwrite_unicode(path: Path, image: Any) -> bool:
    """Unicode-safe image write for Windows"""
    ext = Path(path).suffix.lower()
    params = [cv2.IMWRITE_JPEG_QUALITY, 95] if ext in [".jpg", ".jpeg"] else [cv2.IMWRITE_PNG_COMPRESSION, 6]
    success, encoded = cv2.imencode(ext, image, params)
    if success:
        encoded.tofile(str(path))
        return True
    return False


class BatchTrimAPI:
    """Batch trimming API."""

    def __init__(self):
        self._projects_root = projects_root()
        self._output_root = self._projects_root / "global-output"

    def _get_project_info(self, project_id: str) -> tuple[str, str, Path]:
        role, action = split_project_id(project_id)
        if not role:
            role = LEGACY_ROLE if (self._projects_root / action).exists() else UNKNOWN_ROLE
        action = action or project_id
        return role, action, resolve_project_path(self._projects_root, project_id)

    def _get_project_output_dirs(self, project_id: str) -> tuple[Path | None, Path | None]:
        """Return project output directories as (hole_punched_dir, no_bg_dir)."""
        _, _, project_dir = self._get_project_info(project_id)
        hole_punched = project_dir / "output" / "03_hole_punched"
        no_bg = project_dir / "output" / "02_no_bg"
        return hole_punched if hole_punched.exists() else None, no_bg if no_bg.exists() else None

    def _get_visible_image_files(self, project_id: str, dir_path: Path | None) -> list[str]:
        if not dir_path or not dir_path.exists():
            return []
        _, _, project_path = self._get_project_info(project_id)
        hidden_frames = set(get_hidden_frame_names(project_path))
        return sorted(
            filename
            for filename in os.listdir(dir_path)
            if filename.lower().endswith((".png", ".jpg", ".jpeg")) and filename not in hidden_frames
        )

    def _check_dir_has_images(self, project_id: str, dir_path: Path | None) -> int:
        """Return the number of image files in a directory."""
        return len(self._get_visible_image_files(project_id, dir_path))

    def _get_alpha_bbox(self, image: Any) -> tuple[int, int, int, int]:
        """Return the bounding box for non-transparent image content."""
        if image.shape[2] == 4:
            alpha = image[:, :, 3]
        else:
            # Treat images without alpha as fully opaque.
            return 0, 0, image.shape[1], image.shape[0]

        non_zero = cv2.findNonZero(alpha)
        if non_zero is None:
            return 0, 0, image.shape[1], image.shape[0]

        x, y, w, h = cv2.boundingRect(non_zero)
        return x, y, x + w, y + h

    def check_projects(self, project_ids: list[str]) -> list[dict[str, Any]]:
        """Check whether multiple projects can be processed."""
        results = []
        for project_id in project_ids:
            hole_punched, no_bg = self._get_project_output_dirs(project_id)

            hole_count = self._check_dir_has_images(project_id, hole_punched)
            no_bg_count = self._check_dir_has_images(project_id, no_bg)

            if hole_count > 0:
                status = "available"
            elif no_bg_count > 0:
                status = "fallback"
            else:
                status = "unavailable"

            results.append(
                {
                    "projectId": project_id,
                    "status": status,
                    "hasHolePunched": hole_count > 0,
                    "hasNoBg": no_bg_count > 0,
                    "frameCount": hole_count if hole_count > 0 else no_bg_count,
                }
            )

        return results

    def _get_source_dir(self, project_id: str) -> Path | None:
        """Return the project source image directory, preferring 03_hole_punched over 02_no_bg."""
        hole_punched, no_bg = self._get_project_output_dirs(project_id)

        if hole_punched and self._check_dir_has_images(project_id, hole_punched) > 0:
            return hole_punched
        elif no_bg and self._check_dir_has_images(project_id, no_bg) > 0:
            return no_bg
        return None

    def _analyze_project_frames(self, project_id: str, source_dir: Path) -> list[dict]:
        """Analyze all project frames and return per-frame bounds."""
        frames = []
        image_files = self._get_visible_image_files(project_id, source_dir)

        for filename in image_files:
            filepath = source_dir / filename
            img = _imread_unicode(filepath)
            if img is not None:
                left, top, right, bottom = self._get_alpha_bbox(img)
                frames.append({"projectId": project_id, "filename": filename, "bbox": (left, top, right, bottom)})

        return frames

    def _compute_global_bbox(self, frames_data: list[dict]) -> tuple[int, int, int, int]:
        """Compute the unified global crop bounds."""
        if not frames_data:
            return 0, 0, 0, 0

        min_left = min(f["bbox"][0] for f in frames_data)
        min_top = min(f["bbox"][1] for f in frames_data)
        max_right = max(f["bbox"][2] for f in frames_data)
        max_bottom = max(f["bbox"][3] for f in frames_data)
        return min_left, min_top, max_right, max_bottom

    def _export_audio_clips(
        self,
        project_id: str,
        source_dir: Path,
        output_dir: Path,
        exported_source_files: list[str],
    ) -> dict[str, Any]:
        """Export timeline Audio Clips as WAV files beside the animation frames."""
        _, action, project_path = self._get_project_info(project_id)
        timeline_path = project_path / "cache" / "audio_timeline.json"
        source_wav = project_path / "cache" / "01_audio" / "source.wav"
        if not timeline_path.exists() or not source_wav.exists():
            return {"count": 0, "skipped": 0, "errors": []}

        try:
            timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
            clips = timeline.get("clips", [])
            source_fps = float(timeline.get("source_fps", 0))
            if not clips or source_fps <= 0:
                return {"count": 0, "skipped": len(clips), "errors": []}

            config_path = project_path / "cache" / "steps_config.json"
            config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
            step1 = config.get("step1", {})
            start_frame = int(step1.get("start_frame", 0))
            frame_interval = max(1, int(step1.get("frame_interval", 1)))

            all_source_files = sorted(
                filename
                for filename in os.listdir(source_dir)
                if filename.lower().endswith((".png", ".jpg", ".jpeg"))
            )
            source_slots = {filename: index for index, filename in enumerate(all_source_files)}
            exported_slots = [source_slots[name] for name in exported_source_files if name in source_slots]

            safe_action = sanitize_segment(action, "action")
            manifest_clips = []
            errors = []
            skipped = 0

            with wave.open(str(source_wav), "rb") as source_audio:
                sample_rate = source_audio.getframerate()
                total_samples = source_audio.getnframes()
                channels = source_audio.getnchannels()
                sample_width = source_audio.getsampwidth()
                compression = source_audio.getcomptype()
                compression_name = source_audio.getcompname()

                for clip_index, clip in enumerate(clips, start=1):
                    source_placement = int(clip.get("placementFrame", 0))
                    trigger_slot = math.ceil((source_placement - start_frame) / frame_interval)
                    placement_frame = next(
                        (index for index, slot in enumerate(exported_slots) if slot >= trigger_slot),
                        None,
                    )
                    if placement_frame is None:
                        skipped += 1
                        continue

                    start_source_frame = int(clip.get("srcStartFrame", 0))
                    end_source_frame = int(clip.get("srcEndFrame", start_source_frame))
                    start_sample = max(0, min(total_samples, round(start_source_frame / source_fps * sample_rate)))
                    end_sample = max(start_sample, min(total_samples, round(end_source_frame / source_fps * sample_rate)))
                    if end_sample <= start_sample:
                        errors.append(f"{clip.get('name', clip_index)}: 音频区间为空")
                        continue

                    audio_filename = f"{safe_action}_audio_{clip_index:03d}.wav"
                    try:
                        source_audio.setpos(start_sample)
                        audio_frames = source_audio.readframes(end_sample - start_sample)
                        with wave.open(str(output_dir / audio_filename), "wb") as output_audio:
                            output_audio.setnchannels(channels)
                            output_audio.setsampwidth(sample_width)
                            output_audio.setframerate(sample_rate)
                            output_audio.setcomptype(compression, compression_name)
                            output_audio.writeframes(audio_frames)
                    except Exception as exc:
                        errors.append(f"{clip.get('name', clip_index)}: {exc}")
                        continue

                    manifest_clips.append(
                        {
                            "name": clip.get("name", f"Audio Clip {clip_index}"),
                            "file": audio_filename,
                            "placement_frame": placement_frame,
                            "source_placement_frame": source_placement,
                            "source_region": {
                                "start_frame": start_source_frame,
                                "end_frame": end_source_frame,
                            },
                        }
                    )

            if manifest_clips:
                manifest = {
                    "version": 1,
                    "project_id": project_id,
                    "source_fps": source_fps,
                    "animation_fps": step1.get("fps"),
                    "frame_interval": frame_interval,
                    "clips": manifest_clips,
                }
                (output_dir / "_audio_timeline.json").write_text(
                    json.dumps(manifest, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )

            return {"count": len(manifest_clips), "skipped": skipped, "errors": errors}
        except Exception as exc:
            return {"count": 0, "skipped": 0, "errors": [str(exc)]}

    def _add_audio_export_result(self, result: dict[str, Any], audio: dict[str, Any]) -> None:
        result["audioClipCount"] = audio["count"]
        result["audioSkippedCount"] = audio["skipped"]
        if audio["count"]:
            result["message"] += f"，已导出 {audio['count']} 个音效"
        if audio["errors"]:
            result["audioErrors"] = audio["errors"]
            result["message"] += f"，{len(audio['errors'])} 个音效导出失败"
            if result["status"] == "success":
                result["status"] = "partial"

    def _process_project_global(
        self, project_id: str, source_dir: Path, output_dir: Path, crop_box: tuple[int, int, int, int]
    ) -> dict[str, Any]:
        """Process one project with global bounds and track failed frames."""
        try:
            _, action, _ = self._get_project_info(project_id)
            safe_action = sanitize_segment(action, "action")
            output_dir.mkdir(parents=True, exist_ok=True)
            left, top, right, bottom = crop_box

            image_files = self._get_visible_image_files(project_id, source_dir)

            success_count = 0
            failed_frames = []
            exported_source_files = []

            for idx, filename in enumerate(image_files, start=1):
                input_path = source_dir / filename
                output_filename = f"{safe_action}_trim_{idx:03d}.png"
                output_path = output_dir / output_filename

                try:
                    img = _imread_unicode(input_path)
                    if img is None:
                        failed_frames.append({"filename": filename, "reason": "无法读取图片"})
                        continue

                    # Clamp to image bounds.
                    h, w = img.shape[:2]
                    crop_left = max(0, left)
                    crop_top = max(0, top)
                    crop_right = min(w, right)
                    crop_bottom = min(h, bottom)

                    cropped = img[crop_top:crop_bottom, crop_left:crop_right]
                    _imwrite_unicode(output_path, cropped)
                    success_count += 1
                    exported_source_files.append(filename)
                except Exception as e:
                    failed_frames.append({"filename": filename, "reason": str(e)})

            # Classify status as complete, partial, or failed.
            if success_count == len(image_files):
                status = "success"
                message = f"已处理 {success_count} 帧"
            elif success_count > 0:
                status = "partial"
                message = f"已处理 {success_count}/{len(image_files)} 帧，{len(failed_frames)} 帧失败"
            else:
                status = "error"
                message = f"全部失败：{len(failed_frames)} 帧无法处理"

            result = {
                "projectId": project_id,
                "projectName": action,
                "status": status,
                "message": message,
                "outputPath": str(output_dir),
                "frameCount": len(image_files),
                "successCount": success_count,
                "failedCount": len(failed_frames),
            }

            if failed_frames:
                result["failedFrames"] = failed_frames

            audio = self._export_audio_clips(project_id, source_dir, output_dir, exported_source_files)
            self._add_audio_export_result(result, audio)

            return result
        except Exception as e:
            return {
                "projectId": project_id,
                "projectName": self._get_project_info(project_id)[1],
                "status": "error",
                "message": f"处理异常：{str(e)}",
                "failedCount": 0,
                "failedFrames": [{"filename": "N/A", "reason": str(e)}],
            }

    def _process_project_individual(self, project_id: str, source_dir: Path, output_dir: Path) -> dict[str, Any]:
        """Process one project with per-frame cropping."""
        try:
            _, action, _ = self._get_project_info(project_id)
            safe_action = sanitize_segment(action, "action")
            output_dir.mkdir(parents=True, exist_ok=True)

            image_files = self._get_visible_image_files(project_id, source_dir)
            frame_data = []
            original_size = None

            # Detect anchor point from the first frame bottom center.
            first_frame_path = source_dir / image_files[0]
            first_frame = _imread_unicode(first_frame_path)
            if first_frame is not None:
                h, w = first_frame.shape[:2]
                anchor_point = (w / 2, h)
            else:
                anchor_point = (0, 0)

            failed_frames = []
            exported_source_files = []

            for idx, filename in enumerate(image_files, start=1):
                input_path = source_dir / filename
                output_filename = f"{safe_action}_{idx:03d}.png"
                output_path = output_dir / output_filename

                try:
                    img = _imread_unicode(input_path)
                    if img is None:
                        failed_frames.append({"filename": filename, "reason": "无法读取图片"})
                        continue

                    if original_size is None:
                        original_size = (img.shape[1], img.shape[0])

                    left, top, right, bottom = self._get_alpha_bbox(img)
                    cropped = img[top:bottom, left:right]
                    _imwrite_unicode(output_path, cropped)

                    # Compute offset.
                    crop_center_x = left + (right - left) / 2
                    crop_center_y = top + (bottom - top) / 2
                    offset_x = anchor_point[0] - crop_center_x
                    offset_y = anchor_point[1] - crop_center_y

                    frame_data.append(
                        {
                            "filename": filename,
                            "output_name": output_filename,
                            "frame_index": idx - 1,
                            "original_size": {"width": original_size[0], "height": original_size[1]},
                            "crop_region": {
                                "left": int(left),
                                "top": int(top),
                                "right": int(right),
                                "bottom": int(bottom),
                                "width": int(right - left),
                                "height": int(bottom - top),
                            },
                            "offset": {"x": round(offset_x, 2), "y": round(offset_y, 2)},
                        }
                    )
                    exported_source_files.append(filename)
                except Exception as e:
                    failed_frames.append({"filename": filename, "reason": str(e)})

            # Save JSON data.
            if frame_data:
                json_path = output_dir / "_frame_data.json"
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "project_id": project_id,
                            "role": self._get_project_info(project_id)[0],
                            "action": action,
                            "original_size": {"width": original_size[0], "height": original_size[1]},
                            "anchor_point": {"x": int(anchor_point[0]), "y": int(anchor_point[1])},
                            "frames": frame_data,
                        },
                        f,
                        indent=2,
                        ensure_ascii=False,
                    )

            success_count = len(frame_data)
            total_count = len(image_files)

            # Classify status.
            if success_count == total_count:
                status = "success"
                message = f"已处理 {success_count} 帧（独立裁剪）"
            elif success_count > 0:
                status = "partial"
                message = f"已处理 {success_count}/{total_count} 帧，{len(failed_frames)} 帧失败"
            else:
                status = "error"
                message = f"全部失败：{len(failed_frames)} 帧无法处理"

            result = {
                "projectId": project_id,
                "projectName": action,
                "status": status,
                "message": message,
                "outputPath": str(output_dir),
                "frameCount": total_count,
                "successCount": success_count,
                "failedCount": len(failed_frames),
            }

            if failed_frames:
                result["failedFrames"] = failed_frames

            audio = self._export_audio_clips(project_id, source_dir, output_dir, exported_source_files)
            self._add_audio_export_result(result, audio)

            return result
        except Exception as e:
            return {
                "projectId": project_id,
                "projectName": self._get_project_info(project_id)[1],
                "status": "error",
                "message": str(e),
                "failedCount": 0,
                "failedFrames": [{"filename": "N/A", "reason": str(e)}],
            }

    def _get_unique_output_dir(self, base_dir: Path, base_name: str) -> Path:
        """Return a unique output directory, adding an incrementing suffix if needed."""
        output_dir = base_dir / base_name
        if not output_dir.exists():
            return output_dir

        # Add incrementing suffixes when the path already exists.
        counter = 1
        while True:
            output_dir = base_dir / f"{base_name}-{counter}"
            if not output_dir.exists():
                return output_dir
            counter += 1

    def _get_role_output_roots(self, project_ids: list[str]) -> dict[str, Path]:
        roots: dict[str, Path] = {}
        roles = sorted({self._get_project_info(project_id)[0] for project_id in project_ids})
        for role in roles:
            role_dir = self._projects_root / role
            role_dir.mkdir(parents=True, exist_ok=True)
            roots[role] = self._get_unique_output_dir(role_dir, "batch-trim")
        return roots

    def execute_trim(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Execute batch trimming."""
        project_ids = params.get("projectIds", [])
        mode = params.get("mode", "global")
        role_output_roots = self._get_role_output_roots(project_ids)

        results = []

        if mode == "global":
            # Global mode: analyze all projects to find global bounds.
            all_frames_data = []
            for project_id in project_ids:
                source_dir = self._get_source_dir(project_id)
                if source_dir:
                    frames = self._analyze_project_frames(project_id, source_dir)
                    all_frames_data.extend(frames)

            # Compute global bounds.
            global_bbox = self._compute_global_bbox(all_frames_data)

            # Crop all projects.
            for project_id in project_ids:
                source_dir = self._get_source_dir(project_id)
                if source_dir:
                    role, action, _ = self._get_project_info(project_id)
                    result = self._process_project_global(
                        project_id, source_dir, role_output_roots[role] / action, global_bbox
                    )
                    results.append(result)
                else:
                    role, action, _ = self._get_project_info(project_id)
                    results.append(
                        {
                            "projectId": project_id,
                            "projectName": action,
                            "status": "error",
                            "message": "未找到可用图片（请先完成步骤 2 或步骤 3）",
                            "outputPath": str(
                                role_output_roots.get(role, self._projects_root / role / "batch-trim") / action
                            ),
                            "frameCount": 0,
                            "successCount": 0,
                            "failedCount": 0,
                        }
                    )
        else:
            # Individual mode: crop each frame independently.
            for project_id in project_ids:
                source_dir = self._get_source_dir(project_id)
                if source_dir:
                    role, action, _ = self._get_project_info(project_id)
                    result = self._process_project_individual(project_id, source_dir, role_output_roots[role] / action)
                    results.append(result)
                else:
                    role, action, _ = self._get_project_info(project_id)
                    results.append(
                        {
                            "projectId": project_id,
                            "projectName": action,
                            "status": "error",
                            "message": "未找到可用图片（请先完成步骤 2 或步骤 3）",
                            "outputPath": str(
                                role_output_roots.get(role, self._projects_root / role / "batch-trim") / action
                            ),
                            "frameCount": 0,
                            "successCount": 0,
                            "failedCount": 0,
                        }
                    )

        return results
