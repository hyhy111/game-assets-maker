"""Process API - Processing task management"""

import datetime
import json
import os
import sys
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from backend.api.project_paths import resolve_project_path
from src.core.rembg_model import validate_model
from backend.core.model_preloader import ModelLoader, ModelPreloader, ModelStatus, RembgModelLoader
from backend.core.smart_remove_background import batch_remove_background

# Import core processing modules from backend
from backend.core.video_utils import (
    detect_background_color_from_frames,
    export_frames_step1,
)
from src.utils.data_paths import data_root, projects_root


def _write_debug_log(msg: str):
    """Write debug message to a log file for diagnosing packaged app issues"""
    try:
        if hasattr(sys, "_MEIPASS"):
            return
        log_dir = data_root() / "logs"
        log_dir.mkdir(exist_ok=True)
        log_path = log_dir / "debug_process.log"
        timestamp = datetime.datetime.now().isoformat()
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {msg}\n")
    except Exception:
        pass


class Task:
    """Represents a processing task"""

    def __init__(self, task_id: str, project_id: str, step: int, params: dict[str, Any]):
        self.task_id = task_id
        self.project_id = project_id
        self.step = step
        self.params = params
        self.status = "pending"  # pending, running, completed, failed, cancelled
        self.progress = 0
        self.total = 0
        self.current = 0
        self.error = None
        self.result = None
        self.cancelled = False
        self.start_time = None
        self.processing_time = 0.0


class ProcessAPI:
    """API for processing tasks"""

    def __init__(self, window=None, *, model_loader: ModelLoader | None = None):
        self.tasks: dict[str, Task] = {}
        self.executor = ThreadPoolExecutor(max_workers=2)
        self._projects_root = projects_root()
        self._window = window  # PyWebView window instance
        self._model_preloader = ModelPreloader(model_loader or RembgModelLoader(), self._emit_model_status)

    def _emit_progress(self, task_id: str, progress: int, current: int, total: int, status: str = "running"):
        """Emit progress to frontend via evaluate_js"""
        if self._window:
            js_code = f"""
                window.dispatchEvent(new CustomEvent('task-progress', {{
                    detail: {{
                        taskId: '{task_id}',
                        progress: {progress},
                        current: {current},
                        total: {total},
                        status: '{status}'
                    }}
                }}));
            """
            try:
                self._window.evaluate_js(js_code)
            except Exception as e:
                print(f"Failed to emit progress: {e}")

    def _emit_complete(self, task_id: str, success: bool = True, error: str = None, processing_time: float = 0):
        """Emit task completion to frontend via evaluate_js"""
        if self._window:
            error_str = f"'{error}'" if error else "null"
            time_str = f"{processing_time}" if processing_time > 0 else "null"
            js_code = f"""
                window.dispatchEvent(new CustomEvent('task-complete', {{
                    detail: {{
                        taskId: '{task_id}',
                        success: {str(success).lower()},
                        error: {error_str},
                        processing_time: {time_str}
                    }}
                }}));
            """
            try:
                self._window.evaluate_js(js_code)
            except Exception as e:
                print(f"Failed to emit completion: {e}")

    def start_processing(self, project_id: str, step: int, params: dict[str, Any]) -> str:
        """Start a processing task"""
        if step == 2:
            model = params.get("model", "u2net")
            if self.get_model_status(model)["phase"] != "ready":
                raise RuntimeError("MODEL_NOT_READY")

        task_id = str(uuid.uuid4())
        task = Task(task_id, project_id, step, params)
        self.tasks[task_id] = task

        # Submit to thread pool
        future = self.executor.submit(self._run_task, task)
        task.future = future

        return task_id

    def _get_project_path(self, project_id: str) -> Path:
        return resolve_project_path(self._projects_root, project_id)

    def _run_task(self, task: Task):
        """Run the processing task"""
        task.start_time = time.time()
        try:
            task.status = "running"
            self._emit_progress(task.task_id, 0, 0, 100, "running")

            if task.step == 1:
                self._run_step1(task)
            elif task.step == 2:
                self._run_step2(task)
            elif task.step == 3:
                self._run_step3(task)

            if not task.cancelled:
                task.processing_time = time.time() - task.start_time
                task.status = "completed"
                task.progress = 100
                self._emit_progress(task.task_id, 100, task.current, task.total, "completed")
                # Save params (without processing_time)
                self.save_step_params(task.project_id, task.step, task.params)
                self._emit_complete(task.task_id, success=True, processing_time=task.processing_time)

        except InterruptedError:
            task.status = "cancelled"
            self._emit_complete(task.task_id, success=False, error="Task cancelled")
        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            tb = traceback.format_exc()
            print(f"Task {task.task_id} failed: {e}")
            _write_debug_log(f"Task {task.task_id} failed: {e}\n{tb}")
            self._emit_complete(task.task_id, success=False, error=str(e))

    def _run_step1(self, task: Task):
        """Run Step 1: Frame extraction and background color detection"""
        project_path = self._get_project_path(task.project_id)
        video_path = task.params.get("video_path")
        frame_interval = task.params.get("frame_interval", 1)
        start_frame = task.params.get("start_frame", 0)
        end_frame = task.params.get("end_frame", -1)

        if not video_path:
            # Try to get from project metadata
            meta_path = project_path / "cache" / "global_params.json"
            if meta_path.exists():
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f)
                    video_path = meta.get("video_path")

        if not video_path or not Path(video_path).exists():
            raise ValueError("Video file not found")

        cache_dir = project_path / "cache" / "01_frames_cache"
        output_dir = project_path / "output" / "01_frames"

        # Cache should already be populated during project creation
        # Just export frames with the specified range and interval

        def progress_callback(current, total):
            if task.cancelled:
                raise InterruptedError("Task cancelled")
            task.current = current
            task.total = total
            # Map to 50-99% range
            task.progress = 50 + int((current / max(total, 1)) * 49)
            self._emit_progress(task.task_id, task.progress, current, total, "running")

        # Send initial progress
        self._emit_progress(task.task_id, 0, 0, 100, "running")

        # Export frames with range and interval
        export_frames_step1(
            str(cache_dir),
            str(output_dir),
            start=start_frame,
            end=end_frame,
            step=frame_interval,
            progress_callback=progress_callback,
        )

        # Detect and save background color from exported frames
        self._emit_progress(task.task_id, 95, 95, 100, "running")
        print(f"[DEBUG] Step 1: Detecting background color from {output_dir}")
        bg_hsv = detect_background_color_from_frames(str(output_dir))
        if bg_hsv:
            print(f"[DEBUG] Step 1: Background color detected: {bg_hsv}, saving...")
            self._save_background_color(task.project_id, bg_hsv)
            print(f"[Step 1] Detected background color HSV: {bg_hsv}")
        else:
            print("[Step 1] Warning: Could not detect background color")

        # Send final progress
        task.progress = 100
        self._emit_progress(task.task_id, 100, 100, 100, "running")

        # Save params
        print(f"[DEBUG] Step 1: Saving params: {task.params}")
        save_result = self.save_step_params(task.project_id, 1, task.params)
        print(f"[DEBUG] Step 1: Params save result: {save_result}")

        # 重新抽取后，下游步骤的输出已失效：清空 02/03 输出并重置 processed=False。
        # 否则 _get_step_status 会因旧输出文件存在而仍标记 completed，导致 Step 2/3 加载到旧帧。
        import shutil
        for sub, step_num in [("02_no_bg", 2), ("03_hole_punched", 3)]:
            stale_dir = project_path / "output" / sub
            if stale_dir.exists():
                shutil.rmtree(stale_dir)
            self.save_step_params(task.project_id, step_num, {"processed": False})

    def _run_step2(self, task: Task):
        """Run Step 2: Background removal using rembg (NO hole punching)"""
        project_path = self._get_project_path(task.project_id)
        input_dir = project_path / "output" / "01_frames"
        output_dir = project_path / "output" / "02_no_bg"

        if not input_dir.exists():
            raise ValueError("Step 1 frames not found. Please run Step 1 first.")

        _write_debug_log(f"[_run_step2] Starting step 2 for project {task.project_id}")
        _write_debug_log(f"[_run_step2] Input dir: {input_dir}, Output dir: {output_dir}")
        _write_debug_log(f"[_run_step2] CWD: {os.getcwd()}, MEIPASS: {getattr(sys, '_MEIPASS', 'N/A')}")

        # Get rembg parameters (no hole punching params)
        params = {
            "model": "u2net",
            "post_process_mask": task.params.get("post_process_mask", False),
            "alpha_matting": task.params.get("alpha_matting", True),
            "alpha_matting_erode_size": task.params.get("alpha_matting_erode_size", 5),
            "alpha_matting_background_threshold": task.params.get("alpha_matting_background_threshold", 120),
            "alpha_matting_foreground_threshold": task.params.get("alpha_matting_foreground_threshold", 240),
            "edge_erode": task.params.get("edge_erode", 1),
        }
        _write_debug_log(f"[_run_step2] rembg params: {params}")

        def progress_callback(current, total):
            if task.cancelled:
                raise InterruptedError("Task cancelled")
            task.current = current
            task.total = total
            task.progress = int((current / total) * 100)
            # Push progress to frontend via evaluate_js
            self._emit_progress(task.task_id, task.progress, current, total, "running")

        result = batch_remove_background(
            str(input_dir), str(output_dir), params=params, progress_callback=progress_callback
        )

        _write_debug_log(f"[_run_step2] batch_remove_background result: {result}")

        if result["total"] > 0 and result["success"] == 0:
            raise RuntimeError(
                f"背景移除失败：所有 {result['total']} 帧都处理失败。请查看 logs/debug_process.log 了解详细原因。"
            )

        # Save the background color detected during step 2 if not already saved
        if result.get("background_color"):
            self._save_background_color(task.project_id, result["background_color"])

        # Save params
        self.save_step_params(task.project_id, 2, task.params)

    def _run_step3(self, task: Task):
        """Run Step 3: Post-processing (hole punching + alignment)"""
        import shutil

        project_path = self._get_project_path(task.project_id)
        input_dir = project_path / "output" / "02_no_bg"
        output_dir = project_path / "output" / "03_hole_punched"

        if not input_dir.exists():
            raise ValueError("Step 2 output not found. Please run Step 2 first.")

        # Clear output directory if exists
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Check if hole punching is enabled
        enabled = task.params.get("enabled", True)

        def progress_callback(current, total):
            if task.cancelled:
                raise InterruptedError("Task cancelled")
            task.current = current
            task.total = total
            task.progress = int((current / total) * 100)
            # Push progress to frontend via evaluate_js
            self._emit_progress(task.task_id, task.progress, current, total, "running")

        if enabled:
            # Get green detection parameters
            params = {
                "green_intensity": task.params.get("green_intensity", 3),
                "feather_radius": task.params.get("feather_radius", 3),
                "min_hole_size": task.params.get("min_hole_size", 5),
            }

            # Import here to avoid circular dependency
            from backend.core.smart_remove_background import batch_punch_holes_green

            batch_punch_holes_green(str(input_dir), str(output_dir), params=params, progress_callback=progress_callback)
        else:
            # Hole punching disabled, just copy files
            frames = sorted(input_dir.glob("*.png"))
            total = len(frames)
            for i, frame_path in enumerate(frames):
                output_file = output_dir / frame_path.name
                shutil.copy2(str(frame_path), str(output_file))
                if progress_callback:
                    progress_callback(i + 1, total)

        # Check if alignment is enabled
        align_enabled = task.params.get("align_enabled", False)
        if align_enabled:
            # Get alignment parameters
            align_params = {
                "align_h": task.params.get("align_h", True),
                "align_v": task.params.get("align_v", True),
                "use_padding": task.params.get("use_padding", True),
                "padding_bottom": task.params.get("padding_bottom", 10),
            }

            # Process each frame with alignment
            from src.core.image_aligning import align_sprites

            frames = sorted(output_dir.glob("*.png"))
            total = len(frames)

            for i, frame_path in enumerate(frames):
                if task.cancelled:
                    raise InterruptedError("Task cancelled")

                # Create a temporary file for the aligned output
                temp_output = output_dir / f"aligned_{frame_path.name}"

                # Align the sprite (rows=1, cols=1 for single frame)
                align_sprites(
                    str(frame_path),
                    str(temp_output),
                    rows=1,
                    cols=1,
                    align_h=align_params["align_h"],
                    align_v=align_params["align_v"],
                    use_padding=align_params["use_padding"],
                    padding_bottom=align_params["padding_bottom"],
                )

                # Replace original with aligned version
                if temp_output.exists():
                    shutil.move(str(temp_output), str(frame_path))

                # Update progress (50-100% for alignment phase)
                if progress_callback:
                    progress_callback(50 + int((i + 1) / total * 50), 100)

        # Save params
        self.save_step_params(task.project_id, 3, task.params)

    def _get_background_color(self, project_id: str) -> tuple | None:
        """Get background color from steps_config.json"""
        config_path = self._get_project_path(project_id) / "cache" / "steps_config.json"
        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    config = json.load(f)
                bg_color = config.get("background_color", {})
                hsv = bg_color.get("hsv")
                if hsv and len(hsv) == 3:
                    return tuple(hsv)
            except Exception as e:
                print(f"Error reading background color: {e}")
        return None

    def _save_background_color(self, project_id: str, bg_hsv: tuple):
        """Save background color to steps_config.json"""
        config_path = self._get_project_path(project_id) / "cache" / "steps_config.json"
        print(f"[DEBUG] _save_background_color called with HSV: {bg_hsv}")
        print(f"[DEBUG] Config path: {config_path}")

        config = {}
        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    config = json.load(f)
                print(f"[DEBUG] Loaded existing config, keys: {list(config.keys())}")
            except Exception as e:
                print(f"[Error] Error reading config: {e}")
        else:
            print("[WARNING] Config file does not exist!")

        # Convert HSV to RGB for display
        hsv_array = np.uint8([[list(bg_hsv)]])
        rgb_array = cv2.cvtColor(hsv_array, cv2.COLOR_HSV2RGB)[0][0]
        rgb = tuple(int(x) for x in rgb_array)

        config["background_color"] = {
            "hsv": [int(x) for x in bg_hsv],
            "rgb": [int(x) for x in rgb],
            "sampled_from": "corners",
        }
        print(f"[DEBUG] Updated background_color in config: {config['background_color']}")

        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            print("[DEBUG] Background color saved successfully")
        except Exception as e:
            print(f"[Error] Error saving background color: {e}")
            import traceback

            traceback.print_exc()

    def get_task_status(self, task_id: str) -> dict[str, Any]:
        """Get task status and progress"""
        task = self.tasks.get(task_id)
        if not task:
            return {"success": False, "error": "Task not found"}

        result = {
            "success": True,
            "task_id": task_id,
            "status": task.status,
            "progress": task.progress,
            "current": task.current,
            "total": task.total,
            "step": task.step,
            "error": task.error,
        }

        # Include processing time if task is completed
        if task.status == "completed" and task.processing_time > 0:
            result["processing_time"] = round(task.processing_time, 2)

        return result

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task"""
        task = self.tasks.get(task_id)
        if not task:
            return False

        task.cancelled = True
        task.status = "cancelled"

        if hasattr(task, "future"):
            task.future.cancel()

        return True

    def shutdown(self):
        """Shutdown the process API - cancel all tasks and stop executor"""
        # Cancel all running tasks
        for task in self.tasks.values():
            if task.status == "running":
                task.cancelled = True
                task.status = "cancelled"
                if hasattr(task, "future"):
                    task.future.cancel()

        self._model_preloader.shutdown()

        # Shutdown executor
        self.executor.shutdown(wait=False)

    # Default parameters for each step
    DEFAULT_STEP_PARAMS = {
        1: {"frame_interval": 1, "start_frame": 0, "end_frame": -1, "fps": 30, "processed": False},
        2: {
            # Step 2: Background removal only (rembg parameters)
            "model": "u2net",  # rembg model selection
            "post_process_mask": False,  # apply mask post-processing
            "alpha_matting": True,
            "alpha_matting_erode_size": 5,
            "alpha_matting_background_threshold": 120,
            "alpha_matting_foreground_threshold": 240,
            "edge_erode": 1,
            "fps": 10,  # Playback fps for preview
            "processed": False,
        },
        3: {
            # Step 3: Post-processing (hole punching + alignment)
            "enabled": True,  # Hole punching enabled
            "green_intensity": 3,
            "feather_radius": 3,  # 0-10 pixels
            "min_hole_size": 5,  # Minimum hole area in pixels
            "align_enabled": False,  # Alignment disabled by default
            "align_h": False,  # Horizontal centering (default off)
            "align_v": False,  # Vertical bottom alignment (default off)
            "use_padding": True,  # Use bottom padding
            "padding_bottom": 10,  # Bottom padding pixels
            "fps": 10,  # Playback fps for preview
            "processed": False,
        },
    }

    def _get_steps_config_path(self, project_id: str) -> Path:
        """Get path to unified steps config file"""
        return self._get_project_path(project_id) / "cache" / "steps_config.json"

    def _migrate_legacy_params(self, project_path: Path) -> dict[str, Any]:
        """Migrate legacy separate step params to unified config"""
        config = {}
        cache_path = project_path / "cache"

        for step_num in [1, 2, 3]:
            step_key = f"step{step_num}"
            legacy_path = cache_path / f"step{step_num}_params.json"

            if legacy_path.exists():
                try:
                    with open(legacy_path, encoding="utf-8") as f:
                        config[step_key] = json.load(f)
                    # Optionally remove legacy file after migration
                    # legacy_path.unlink()
                except Exception as e:
                    print(f"Error migrating legacy params for step {step_num}: {e}")
                    config[step_key] = self.DEFAULT_STEP_PARAMS[step_num].copy()
            else:
                config[step_key] = self.DEFAULT_STEP_PARAMS[step_num].copy()

        return config

    def get_step_params(self, project_id: str, step: int) -> dict[str, Any]:
        """Get saved parameters for a step from unified config"""
        project_path = self._get_project_path(project_id)
        config_path = self._get_steps_config_path(project_id)

        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    config = json.load(f)
                step_key = f"step{step}"
                if step_key in config:
                    return config[step_key]
            except Exception as e:
                print(f"Error reading steps config: {e}")

        # Try to migrate from legacy files
        config = self._migrate_legacy_params(project_path)
        if config:
            # Save migrated config
            self._save_steps_config(project_id, config)
            step_key = f"step{step}"
            return config.get(step_key, self.DEFAULT_STEP_PARAMS.get(step, {}).copy())

        # Return defaults
        return self.DEFAULT_STEP_PARAMS.get(step, {}).copy()

    def save_step_params(self, project_id: str, step: int, params: dict[str, Any]) -> bool:
        """Save parameters for a step to unified config"""
        config_path = self._get_steps_config_path(project_id)

        # Load existing config or create new
        config = {}
        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    config = json.load(f)
            except Exception as e:
                print(f"Error reading existing config: {e}")

        # Ensure all steps exist in config
        for step_num in [1, 2, 3]:
            step_key = f"step{step_num}"
            if step_key not in config:
                config[step_key] = self.DEFAULT_STEP_PARAMS[step_num].copy()

        # Update the specific step
        step_key = f"step{step}"
        print(f"[DEBUG] Saving step {step} params: {params}")  # Debug log
        config[step_key].update(params)
        print(f"[DEBUG] Updated config for step {step}: {config[step_key]}")  # Debug log

        result = self._save_steps_config(project_id, config)
        print(f"[DEBUG] Save result: {result}")  # Debug log
        return result

    def _save_steps_config(self, project_id: str, config: dict[str, Any]) -> bool:
        """Save the entire steps config"""
        config_path = self._get_steps_config_path(project_id)

        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"Error saving steps config: {e}")
            return False

    def get_all_steps_params(self, project_id: str) -> dict[str, Any]:
        """Get all steps parameters from unified config"""
        config_path = self._get_steps_config_path(project_id)

        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error reading steps config: {e}")

        # Try to migrate from legacy files
        project_path = self._get_project_path(project_id)
        return self._migrate_legacy_params(project_path)

    def get_background_color(self, project_id: str) -> dict[str, Any]:
        """Get background color for a project"""
        config_path = self._get_steps_config_path(project_id)

        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    config = json.load(f)
                return config.get("background_color", {})
            except Exception as e:
                print(f"Error reading steps config: {e}")

        return {}

    def get_model_status(self, model: str = "u2net") -> ModelStatus:
        validate_model(model)
        return self._model_preloader.get_status(model)

    def preload_model(self, model: str = "u2net", source: str | None = None) -> ModelStatus:
        """Start model preparation once and return its current observable state."""
        validate_model(model)
        return self._model_preloader.preload(model, source=source)

    def retry_model(self, model: str = "u2net", source: str | None = None) -> ModelStatus:
        validate_model(model)
        return self._model_preloader.retry(model, source=source)

    def _emit_model_status(self, status: ModelStatus) -> None:
        if self._window is None:
            return
        js_code = (
            "window.dispatchEvent(new CustomEvent('model-status', { detail: "
            + json.dumps(status, ensure_ascii=False)
            + " }));"
        )
        try:
            self._window.evaluate_js(js_code)
        except Exception as error:
            print(f"Failed to emit model status: {error}")
