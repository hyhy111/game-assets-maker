"""Process API - Processing task management"""

import datetime
import json
import queue
import shutil
import sys
import tempfile
import threading
import time
import traceback
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from filelock import FileLock

from backend.api.project_paths import project_video_path, resolve_project_path
from backend.core.alpha_refine import validate_alpha_refine_params
from backend.core.background_color import batch_punch_holes_color, validate_color_params
from backend.core.edge_shrink import shrink_frame, validate_edge_shrink_params
from backend.core.frame_edit_history import (
    current_frame_edit_generation,
    new_frame_edit_generation,
    use_frame_edit_generation,
)
from backend.core.model_preloader import (
    BackgroundModelLoader,
    ModelLoader,
    ModelPreloader,
    ModelStatus,
    validate_background_model,
)
from backend.core.post_process_backup import clean_processing_backups, processing_backup
from backend.core.smart_remove_background import batch_remove_background

# Import core processing modules from backend
from backend.core.video_utils import (
    detect_background_color_from_frames,
    export_frames_step1,
    selected_frame_indices,
)
from src.utils.app_config import default_projects_root, load_app_config
from src.utils.background_models import background_models, is_birefnet
from src.utils.data_paths import data_root
from src.utils.file_operations import rename_path


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
        self.cancel_event = threading.Event()
        self.gpu_ready = False
        self.execution_device = "cpu"
        self.gpu_fallback = None
        self.committed = False
        self.future: Future | None = None
        self.start_time = None
        self.processing_time = 0.0


class ProcessAPI:
    """API for processing tasks"""

    def __init__(self, window=None, *, model_loader: ModelLoader | None = None, projects_root: Path | None = None):
        self.tasks: dict[str, Task] = {}
        self._control_lock = threading.RLock()
        self._parameter_locks: dict[str, FileLock] = {}
        self._parameter_lock_guard = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=2)
        self._projects_root = projects_root if projects_root is not None else default_projects_root()
        self._window = window  # PyWebView window instance
        self._model_preloader = ModelPreloader(model_loader or BackgroundModelLoader(), self._emit_model_status)
        self._gpu_prepare_cancel = threading.Event()
        self._gpu_prepare_future = None
        # JS events are dispatched by one daemon thread: Cocoa's evaluate_js
        # blocks on a semaphore until the main run loop services it, which
        # never happens once the window is destroyed. Executor workers must
        # never call it directly, or they hang and the interpreter join of
        # executor threads keeps the dead process alive forever.
        self._js_events: queue.SimpleQueue[str | None] = queue.SimpleQueue()
        self._js_dispatcher = threading.Thread(
            target=self._js_dispatch_loop,
            name="process-api-event-dispatcher",
            daemon=True,
        )
        self._js_dispatcher.start()

    def _queue_js_event(self, js_code: str) -> None:
        self._js_events.put(js_code)

    def _js_dispatch_loop(self) -> None:
        while True:
            js_code = self._js_events.get()
            if js_code is None:
                return
            window = self._window
            if window is None:
                continue
            try:
                window.evaluate_js(js_code)
            except Exception as error:
                print(f"Failed to emit JS event: {error}")

    def _emit_progress(self, task_id: str, progress: int, current: int, total: int, status: str = "running"):
        """Emit progress to frontend via evaluate_js"""
        task = self.tasks.get(task_id)
        js_code = f"""
            window.dispatchEvent(new CustomEvent('task-progress', {{
                detail: {{
                    taskId: '{task_id}',
                    progress: {progress},
                    current: {current},
                    total: {total},
                    status: '{status}',
                    execution_device: {json.dumps(task.execution_device if task else None)},
                    gpu_fallback: {json.dumps(task.gpu_fallback if task else None)}
                }}
            }}));
        """
        self._queue_js_event(js_code)

    def _emit_complete(self, task_id: str, success: bool = True, error: str = None, processing_time: float = 0):
        """Emit task completion to frontend via evaluate_js"""
        error_str = json.dumps(error)
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
        self._queue_js_event(js_code)

    def start_processing(self, project_id: str, step: int, params: dict[str, Any]) -> str:
        """Start a processing task"""
        with self._control_lock:
            return self._start_processing(project_id, step, params)

    def _start_processing(self, project_id: str, step: int, params: dict[str, Any]) -> str:
        if any(task.project_id == project_id and task.status in ("pending", "running") for task in self.tasks.values()):
            raise ValueError("PROCESSING_ACTIVE")
        if step == 2:
            model = params.get("model", "u2net")
            if self.get_model_status(model)["phase"] != "ready":
                raise RuntimeError("MODEL_NOT_READY")
            validate_alpha_refine_params(params)
            params = {**params, "model": model}

        if step == 3:
            if params.get("enabled", True):
                validate_color_params(params)
            if params.get("edge_shrink_enabled", False):
                validate_edge_shrink_params(params)

        task_id = str(uuid.uuid4())
        task = Task(task_id, project_id, step, params)
        gpu_status = self.get_gpu_runtime_status() if step == 2 and params.get("model", "").endswith("-onnx") else {}
        task.gpu_ready = (
            step == 2
            and sys.platform == "win32"
            and params.get("model", "").endswith("-onnx")
            and gpu_status.get("gpu_ready", gpu_status.get("phase") == "ready")
        )
        task.execution_device = "gpu" if task.gpu_ready else "cpu"
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

            if task.cancelled:
                raise InterruptedError("Task cancelled")
            task.processing_time = time.time() - task.start_time
            task.status = "completed"
            task.progress = 100
            task.current = task.total
            self._emit_progress(task.task_id, 100, task.current, task.total, "completed")
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
                    video_path = project_video_path(project_path, meta)

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
            frame_overrides=task.params.get("frame_overrides"),
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
        for sub, step_num in [("02_no_bg", 2), ("03_hole_punched", 3)]:
            stale_dir = project_path / "output" / sub
            if stale_dir.exists():
                shutil.rmtree(stale_dir)
            reset = {"processed": False}
            if step_num == 3:
                reset["result_aligned"] = False
            self.save_step_params(task.project_id, step_num, reset)
        with self.parameter_transaction(task.project_id):
            config = self._load_processing_config(task.project_id)
            undo = config.pop("step3_undo", None)
            legacy = config.pop("step3_history", None)
            if (undo or legacy) and not self._save_steps_config(task.project_id, config):
                raise OSError("Could not invalidate the Step 3 backup")
            clean_processing_backups(project_path)

    def _progress(self, task: Task, current: int, total: int, phase: int = 0, phases: int = 1) -> None:
        if task.cancelled:
            raise InterruptedError("Task cancelled")
        task.current = current
        task.total = total
        task.progress = int((phase + current / max(total, 1)) * 99 / phases)
        self._emit_progress(task.task_id, task.progress, current, total, "running")

    def _run_step2(self, task: Task):
        """Process all extracted frames before replacing the published sequence."""
        project = self._get_project_path(task.project_id)
        input_dir = project / "output" / "01_frames"
        if not input_dir.is_dir():
            raise ValueError("Step 1 frames not found. Please run Step 1 first.")

        def fallback(error):
            task.execution_device = "cpu"
            task.gpu_fallback = error
            self._emit_progress(task.task_id, task.progress, task.current, task.total)

        params = {**self.DEFAULT_STEP_PARAMS[2], **task.params}
        with tempfile.TemporaryDirectory(dir=input_dir.parent, prefix=".step2-") as staging:
            result = batch_remove_background(
                str(input_dir),
                staging,
                params=params,
                progress_callback=lambda current, total: self._progress(task, current, total),
                use_gpu=task.gpu_ready,
                cancel_event=task.cancel_event,
                fallback_callback=fallback,
            )
            if not result["total"] or result["success"] != result["total"]:
                raise RuntimeError(f"Background removal failed ({result['success']}/{result['total']} frames).")
            self._publish_processed_frames(task, Path(staging), result.get("background_color"))

    def _run_step3(self, task: Task):
        """Apply enabled operations to the current result, keeping Step 2 intact."""
        from src.core.image_aligning import align_sprites

        project = self._get_project_path(task.project_id)
        input_dir = project / "output" / "02_no_bg"
        frames = sorted(input_dir.glob("*.png"))
        if not frames:
            raise ValueError("Step 2 output not found. Please run Step 2 first.")

        params = task.params
        with self.parameter_transaction(task.project_id):
            previous = self._read_step_params(task.project_id, 3, migrate=False)
        current_dir = input_dir.with_name("03_hole_punched")
        if current_dir.resolve() != project.resolve() / "output" / current_dir.name:
            raise ValueError("Invalid Step 3 output path")
        current_frames = {
            frame.name: frame for frame in current_dir.glob("*.png") if frame.is_file() and not frame.is_symlink()
        }
        previously_aligned = bool(
            current_frames and previous.get("result_aligned", previous.get("align_enabled", False))
        )
        shrink, feather = validate_edge_shrink_params(params) if params.get("edge_shrink_enabled") else (0, 0)
        align = params.get("align_enabled", False)
        phases = 1 + bool(shrink or feather) + bool(align)
        total = len(frames)
        with tempfile.TemporaryDirectory(dir=input_dir.parent, prefix=".step3-") as staging:
            output = Path(staging)
            if params.get("enabled", True):
                batch_punch_holes_color(
                    str(input_dir),
                    staging,
                    str(input_dir.with_name("01_frames")),
                    params=params,
                    progress_callback=lambda current, total: self._progress(task, current, total, phases=phases),
                    frame_overrides=current_frames,
                    overrides_aligned=previously_aligned,
                )
            else:
                for index, frame in enumerate(frames, 1):
                    self._progress(task, index - 1, total, phases=phases)
                    shutil.copy2(current_frames.get(frame.name, frame), output / frame.name)

            if shrink or feather:
                for index, frame in enumerate(frames, 1):
                    self._progress(task, index - 1, total, phase=1, phases=phases)
                    shrink_frame(output / frame.name, shrink, feather)

            if align:
                for index, frame in enumerate(frames, 1):
                    self._progress(task, index - 1, total, phase=phases - 1, phases=phases)
                    path = output / frame.name
                    aligned = output / f"aligned_{frame.name}"
                    align_sprites(
                        str(path),
                        str(aligned),
                        rows=1,
                        cols=1,
                        align_h=params.get("align_h", True),
                        align_v=params.get("align_v", True),
                        use_padding=params.get("use_padding", True),
                        padding_bottom=params.get("padding_bottom", 10),
                    )
                    rename_path(aligned, path, replace=True)

            self._publish_processed_frames(task, output, result_aligned=previously_aligned or bool(align))

    def _publish_processed_frames(
        self,
        task: Task,
        staged: Path,
        background_color=None,
        *,
        result_aligned: bool = False,
    ) -> None:
        """Replace the active result, restoring the old files if publishing fails."""
        project = self._get_project_path(task.project_id)
        step2 = task.step == 2
        output = project / "output" / ("02_no_bg" if step2 else "03_hole_punched")
        replaced = [output, output.with_name("03_hole_punched")] if step2 else [output]
        backup_id = None
        previous_output = None
        with self.parameter_transaction(task.project_id):
            if task.cancelled:
                raise InterruptedError("Task cancelled")

            config = self._load_processing_config(task.project_id)
            config.pop("step3_history", None)
            if step2:
                config["step2"].update(task.params, processed=True)
                config["step2"]["result_model"] = task.params.get("model", "u2net")
                config.setdefault("step3", {}).update(processed=False, result_aligned=False)
                config.pop("step3_undo", None)
                if background_color:
                    config["background_color"] = self._background_color_entry(background_color)
            else:
                frame_count = sum(frame.is_file() and not frame.is_symlink() for frame in output.glob("*.png"))
                previous = config["step3"]
                if frame_count:
                    backup_id = uuid.uuid4().hex
                    previous_output = processing_backup(project, backup_id)
                    previous_output.parent.mkdir(parents=True, exist_ok=True)
                config["step3_undo"] = {
                    "backup": backup_id,
                    "frame_count": frame_count,
                    "generation": current_frame_edit_generation(project, 3) if frame_count else None,
                    "result_aligned": bool(
                        frame_count and previous.get("result_aligned", previous.get("align_enabled"))
                    ),
                }
                previous.update(task.params, processed=True, result_aligned=result_aligned)
            self._publish_replacement(task.project_id, task.step, replaced, staged, config, keep=previous_output)
            task.committed = True
            clean_processing_backups(project, backup_id)

    def _publish_replacement(
        self,
        project_id: str,
        step: int,
        replaced: list[Path],
        staged: Path | None,
        config: dict,
        *,
        keep: Path | None = None,
        undo: dict | None = None,
    ) -> None:
        """Publish frames and settings together while holding the parameter transaction."""
        project = self._get_project_path(project_id)
        output = replaced[0]
        backups = []
        published = False
        generation = (
            new_frame_edit_generation(project, step)
            if undo is None
            else use_frame_edit_generation(project, step, undo["generation"])
        )
        try:
            with generation:
                for old in replaced:
                    if old.exists():
                        backup = (
                            keep
                            if old == output and keep is not None
                            else (old.with_name(f".{old.name}-backup-{uuid.uuid4().hex}"))
                        )
                        rename_path(old, backup)
                        backups.append((old, backup))
                if staged is not None:
                    rename_path(staged, output)
                    published = True
                if not self._save_steps_config(project_id, config):
                    raise OSError("Could not save processing settings")
        except BaseException:
            if published:
                rename_path(output, staged)
            for old, backup in reversed(backups):
                rename_path(backup, old)
            raise
        for _, backup in backups:
            if backup != keep:
                shutil.rmtree(backup, ignore_errors=True)

    def undo_post_processing(self, project_id: str) -> bool:
        """Restore the sequence and editing baseline from before the last Step 3 batch."""
        with self.parameter_transaction(project_id):
            project, output = self._step3_restore_path(project_id)
            config = self._load_processing_config(project_id)
            undo = config.pop("step3_undo", None)
            if not undo:
                raise ValueError("No Step 3 batch to undo")
            backup = processing_backup(project, undo["backup"]) if undo["backup"] is not None else None
            if backup is not None:
                frame_count = sum(frame.is_file() and not frame.is_symlink() for frame in backup.glob("*.png"))
                if not frame_count or frame_count != undo["frame_count"]:
                    raise ValueError("Incomplete Step 3 backup")
            config.pop("step3_history", None)
            config["step3"].update(
                processed=backup is not None, processing_time=0, result_aligned=undo["result_aligned"]
            )
            self._publish_replacement(project_id, 3, [output], backup, config, undo=undo)
            clean_processing_backups(project)
        return True

    def reset_post_processing(self, project_id: str) -> bool:
        """Remove the current Step 3 result so the editor falls back to Step 2."""
        with self.parameter_transaction(project_id):
            project, output = self._step3_restore_path(project_id)
            config = self._load_processing_config(project_id)
            config.pop("step3_undo", None)
            config.pop("step3_history", None)
            config["step3"].update(processed=False, processing_time=0, result_aligned=False)
            self._publish_replacement(project_id, 3, [output], None, config)
            clean_processing_backups(project)
        return True

    def _step3_restore_path(self, project_id: str) -> tuple[Path, Path]:
        if self.has_active_writes():
            raise ValueError("PROCESSING_ACTIVE")
        project = self._get_project_path(project_id).resolve()
        output = project / "output" / "03_hole_punched"
        if output.resolve() != output or (output.exists() and not output.is_dir()):
            raise ValueError("Invalid Step 3 output path")
        if not any(output.with_name("02_no_bg").glob("*.png")):
            raise ValueError("Step 2 output not found. Please run Step 2 first.")
        return project, output

    def _load_processing_config(self, project_id: str) -> dict[str, Any]:
        config = self._migrate_legacy_params(self._get_project_path(project_id))
        config_path = self._get_steps_config_path(project_id)
        if config_path.is_file():
            with config_path.open(encoding="utf-8") as stream:
                config.update(json.load(stream))
        return config

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
        with self.parameter_transaction(project_id):
            return self._write_background_color(project_id, bg_hsv)

    def _write_background_color(self, project_id: str, bg_hsv: tuple):
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

        config["background_color"] = self._background_color_entry(bg_hsv)
        self._save_steps_config(project_id, config)

    @staticmethod
    def _background_color_entry(bg_hsv: tuple) -> dict[str, Any]:
        hsv_array = np.uint8([[list(bg_hsv)]])
        rgb_array = cv2.cvtColor(hsv_array, cv2.COLOR_HSV2RGB)[0][0]
        return {
            "hsv": [int(x) for x in bg_hsv],
            "rgb": [int(x) for x in rgb_array],
            "sampled_from": "edge_patches",
        }

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
            "execution_device": task.execution_device,
            "gpu_fallback": task.gpu_fallback,
        }

        # Include processing time if task is completed
        if task.status == "completed" and task.processing_time > 0:
            result["processing_time"] = round(task.processing_time, 2)

        return result

    def has_active_writes(self) -> bool:
        """True while any processing task may still write project data."""
        return any(task.status in ("pending", "running") for task in self.tasks.values())

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task"""
        with self._control_lock:
            task = self.tasks.get(task_id)
            if not task or task.committed or task.status not in ("pending", "running"):
                return False
            task.cancelled = True
            task.cancel_event.set()
            if task.future is None or task.future.cancel():
                task.status = "cancelled"
                self._emit_complete(task.task_id, success=False, error="Task cancelled")
            return True

    def shutdown(self):
        """Shutdown the process API - cancel all tasks and stop executor"""
        for task_id in list(self.tasks):
            self.cancel_task(task_id)

        self._model_preloader.shutdown()
        self._gpu_prepare_cancel.set()
        from backend.core.gpu_runtime import close_cancelled_workers

        close_cancelled_workers({self._gpu_prepare_cancel, *(task.cancel_event for task in self.tasks.values())})

        # Shutdown executor
        self.executor.shutdown(wait=False)

        # Drop events still queued for the dead window and stop the dispatcher.
        self._window = None
        self._js_events.put(None)

    # Default parameters for each step
    DEFAULT_STEP_PARAMS = {
        1: {
            "frame_interval": 1,
            "start_frame": 0,
            "end_frame": -1,
            "fps": 30,
            "processed": False,
            "frame_overrides": {},
        },
        2: {
            # Step 2: Background removal
            "post_process_mask": False,  # apply mask post-processing
            "alpha_matting": True,
            "alpha_matting_erode_size": 5,
            "alpha_matting_background_threshold": 120,
            "alpha_matting_foreground_threshold": 240,
            "edge_erode": 1,
            "alpha_contrast": 1.0,
            "alpha_threshold": 0,
            "defringe_enabled": False,
            "defringe_px": 2,
            "defringe_amount": 0.5,
            "min_foreground_area": 0,
            "fill_holes_max_size": 0,
            "fps": 10,  # Playback fps for preview
            "processed": False,
        },
        3: {
            # Step 3: Post-processing
            "green_intensity": 3,
            "feather_radius": 3,  # 0-10 pixels
            "min_hole_size": 5,  # Minimum hole area in pixels
            "edge_shrink_enabled": False,
            "edge_shrink_px": 0,
            "edge_feather_px": 0,
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

    @contextmanager
    def parameter_transaction(self, project_id: str):
        """Serialize read/merge/write with GUI saves and other local processes."""
        config_path = self._get_steps_config_path(project_id)
        if not config_path.parent.is_dir():
            raise FileNotFoundError("Project cache not found")
        with self._parameter_lock_guard:
            lock = self._parameter_locks.setdefault(str(config_path), FileLock(str(config_path) + ".lock", timeout=10))
        with self._control_lock, lock:
            yield

    def get_step_params(self, project_id: str, step: int) -> dict[str, Any]:
        with self.parameter_transaction(project_id):
            return self._read_step_params(project_id, step)

    def _merge_step_params(self, step: int, config: dict[str, Any]) -> dict[str, Any]:
        saved = config.get(f"step{step}", {})
        params = {**self.DEFAULT_STEP_PARAMS.get(step, {}), **saved}
        if step == 2 and params.get("model") not in background_models():
            params["model"] = load_app_config()["processing"]["background_model"]
        if step == 3 and "enabled" not in saved:
            # Absence means no explicit choice; keep the resolved default out of persisted config.
            result_model = config.get("step2", {}).get("result_model", "u2net")
            params["enabled"] = not is_birefnet(result_model)
        return params

    def _read_step_params(self, project_id: str, step: int, *, migrate: bool = True) -> dict[str, Any]:
        """Get saved parameters for a step from unified config"""
        project_path = self._get_project_path(project_id)
        config_path = self._get_steps_config_path(project_id)

        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    config = json.load(f)
                step_key = f"step{step}"
                if step_key in config:
                    return self._merge_step_params(step, config)
            except Exception as e:
                print(f"Error reading steps config: {e}")

        # Try to migrate from legacy files
        config = self._migrate_legacy_params(project_path)
        if config:
            if migrate:
                self._save_steps_config(project_id, config)
            return self._merge_step_params(step, config)

        # Return defaults
        return self.DEFAULT_STEP_PARAMS.get(step, {}).copy()

    def save_step_params(self, project_id: str, step: int, params: dict[str, Any]) -> bool:
        with self.parameter_transaction(project_id):
            return self._write_step_params(project_id, step, params)

    def _write_step_params(self, project_id: str, step: int, params: dict[str, Any]) -> bool:
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
        if step == 1:
            params = dict(params)
            saved = config[step_key]
            if "frame_overrides" not in params and any(
                name in params and params[name] != saved.get(name)
                for name in ("start_frame", "end_frame", "frame_interval")
            ):
                params["frame_overrides"] = {}
            merged = {**saved, **params}
            cache_dir = self._get_project_path(project_id) / "cache" / "01_frames_cache"
            selected_frame_indices(
                len(list(cache_dir.glob("frame_*.png"))),
                merged.get("start_frame", 0),
                merged.get("end_frame", -1),
                merged.get("frame_interval", 1),
                merged.get("frame_overrides"),
            )
        print(f"[DEBUG] Saving step {step} params: {params}")  # Debug log
        config[step_key].update(params)
        print(f"[DEBUG] Updated config for step {step}: {config[step_key]}")  # Debug log

        result = self._save_steps_config(project_id, config)
        print(f"[DEBUG] Save result: {result}")  # Debug log
        return result

    def _save_steps_config(self, project_id: str, config: dict[str, Any]) -> bool:
        """Save the entire steps config"""
        config_path = self._get_steps_config_path(project_id)

        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=config_path.parent, prefix=".steps-", mode="w", encoding="utf-8", delete=False
            ) as stream:
                temporary = Path(stream.name)
                json.dump(config, stream, ensure_ascii=False, indent=2)
            rename_path(temporary, config_path, replace=True)
            return True
        except Exception as e:
            print(f"Error saving steps config: {e}")
            return False
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

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

    def get_gpu_runtime_status(self) -> dict:
        from backend.core.gpu_runtime import runtime_status

        return runtime_status()

    def prepare_gpu_runtime(self, model: str = "birefnet-lite-onnx", source: str | None = None) -> dict:
        from backend.core.gpu_runtime import _status, activate_runtime, prepare_runtime

        validate_background_model(model)
        if sys.platform != "win32" or not model.endswith("-onnx"):
            raise ValueError("NVIDIA components are only supported by Windows ONNX models")
        if source == "tuna":
            source = "aliyun"
        if source is not None and source not in {"aliyun", "pypi"}:
            raise ValueError("Unknown GPU component source")
        with self._control_lock:
            if self._gpu_prepare_future is None or self._gpu_prepare_future.done():
                self._gpu_prepare_cancel.clear()
                _status("initializing" if source is None else "downloading")
                self._gpu_prepare_future = self.executor.submit(
                    activate_runtime if source is None else prepare_runtime,
                    **({} if source is None else {"source": source}),
                    model=None if model == "birefnet-lite-onnx" else model,
                    cancel_event=self._gpu_prepare_cancel,
                )
        return self.get_gpu_runtime_status()

    def cancel_gpu_runtime_prepare(self) -> dict:
        self._gpu_prepare_cancel.set()
        return self.get_gpu_runtime_status()

    def get_model_status(self, model: str = "u2net") -> ModelStatus:
        validate_background_model(model)
        return self._model_preloader.get_status(model)

    def preload_model(self, model: str = "u2net", source: str | None = None) -> ModelStatus:
        """Start model preparation once and return its current observable state."""
        validate_background_model(model)
        return self._model_preloader.preload(model, source=source)

    def retry_model(self, model: str = "u2net", source: str | None = None) -> ModelStatus:
        validate_background_model(model)
        return self._model_preloader.retry(model, source=source)

    def cancel_model_download(self, model: str = "u2net") -> ModelStatus:
        """Interrupt a model download; Windows ONNX resources retain resumable progress."""
        validate_background_model(model)
        return self._model_preloader.cancel(model)

    def _emit_model_status(self, status: ModelStatus) -> None:
        js_code = (
            "window.dispatchEvent(new CustomEvent('model-status', { detail: "
            + json.dumps(status, ensure_ascii=False)
            + " }));"
        )
        self._queue_js_event(js_code)
