"""Use saved step parameters with validated explicit overrides."""

from pathlib import Path
from typing import Any

FIELDS = {
    1: {"frame_interval": (1, None), "start_frame": (0, None), "end_frame": (-1, None)},
    2: {
        "alpha_matting": bool,
        "alpha_matting_erode_size": (0, 20),
        "alpha_matting_foreground_threshold": (100, 250),
        "alpha_matting_background_threshold": (0, 255),
    },
    3: {
        "enabled": bool,
        "green_intensity": (1, 5),
        "feather_radius": (0, 10),
        "min_hole_size": (0, 500),
        "align_enabled": bool,
        "align_h": bool,
        "align_v": bool,
    },
}


def merge_params(saved: dict[str, Any], step: int, patch: dict[str, Any]) -> dict[str, Any]:
    if type(step) is not int or step not in FIELDS or not isinstance(patch, dict):
        raise ValueError("INPUT_INVALID")
    if set(patch) - (FIELDS[step].keys() | {"fps"}):
        raise ValueError("Unsupported step parameter")
    merged = {**saved, **patch}
    if "fps" in patch and (type(patch["fps"]) is not int or not 1 <= patch["fps"] <= 60):
        raise ValueError("fps must be between 1 and 60")
    for name, rule in FIELDS[step].items():
        value = merged.get(name)
        if rule is bool:
            valid = type(value) is bool
        else:
            low, high = rule
            valid = type(value) is int and value >= low and (high is None or value <= high)
        if not valid:
            raise ValueError(f"Invalid step parameter: {name}")
    if step == 1 and merged["end_frame"] != -1 and merged["end_frame"] < merged["start_frame"]:
        raise ValueError("end_frame must not precede start_frame")
    if step == 2 and merged["alpha_matting_background_threshold"] >= merged["alpha_matting_foreground_threshold"]:
        raise ValueError("background threshold must be smaller than foreground threshold")
    return merged


class StepControl:
    """Wrap the existing project and processing APIs, without another processor."""

    def __init__(self, project_api, process_api):
        self.projects = project_api
        self.process = process_api

    def apply(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        if operation == "step.status":
            status = self.process.get_task_status(payload.get("task_id", ""))
            if not status.get("success"):
                raise ValueError("TASK_NOT_FOUND")
            task = self.process.tasks.get(payload.get("task_id", ""))
            if task is not None:
                status.update(
                    project_id=task.project_id,
                    params_used=dict(task.params),
                    output_dir=str(
                        self.process._get_project_path(task.project_id)
                        / "output"
                        / {1: "01_frames", 2: "02_no_bg", 3: "03_hole_punched"}[task.step]
                    ),
                )
            return status
        project_id, step = payload.get("project_id"), payload.get("step")
        if not isinstance(project_id, str) or type(step) is not int or step not in FIELDS:
            raise ValueError("INPUT_INVALID")
        project = self.projects.get_project(project_id)
        if not project:
            raise ValueError("PROJECT_NOT_FOUND")
        with self.process.parameter_transaction(project_id):
            return self._apply_to_project(operation, payload, project_id, step, project)

    def _apply_to_project(self, operation, payload, project_id, step, project):
        saved = self.process.get_step_params(project_id, step)
        params = merge_params(saved, step, payload.get("patch", {}))
        data = {
            "project_id": project_id,
            "step": step,
            "params_used": params,
            "output_dir": str(
                Path(project["path"]) / "output" / {1: "01_frames", 2: "02_no_bg", 3: "03_hole_punched"}[step]
            ),
        }
        if operation == "step.get":
            return data
        if self.process.has_active_writes():
            raise ValueError("PROCESSING_ACTIVE")
        if operation == "step.run":
            if step > 1 and not project.get("steps", {}).get(str(step - 1), {}).get("completed"):
                raise ValueError("STEP_INPUT_MISSING")
            if step == 2 and self.process.get_model_status(params.get("model", "u2net"))["phase"] != "ready":
                raise ValueError("MODEL_NOT_READY")
            if not self.process.save_step_params(project_id, step, params):
                raise ValueError("SAVE_FAILED")
            execution = {**params, "processed": True}
            if step == 1:
                execution["video_path"] = project.get("video_path")
            data["task_id"] = self.process.start_processing(project_id, step, execution)
            data["status"] = "pending"
        elif operation == "step.set":
            if not self.process.save_step_params(project_id, step, params):
                raise ValueError("SAVE_FAILED")
        else:
            raise ValueError("INPUT_INVALID")
        data["persisted"] = True
        return data
