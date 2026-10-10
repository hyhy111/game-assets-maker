"""Project selection and final export-directory receipts."""

from pathlib import Path
from typing import Any


def trim_projects(api, project_ids: list[str], mode: str) -> dict[str, Any]:
    if (
        not isinstance(project_ids, list)
        or not project_ids
        or not all(isinstance(item, str) and item for item in project_ids)
    ):
        raise ValueError("INPUT_INVALID")
    if len(set(project_ids)) != len(project_ids) or mode not in ("global", "individual"):
        raise ValueError("INPUT_INVALID")
    for project_id in project_ids:
        if not api.get_project(project_id):
            raise ValueError("PROJECT_NOT_FOUND")
    raw = api.execute_batch_trim({"projectIds": project_ids, "mode": mode})
    return normalize_trim_results(raw, project_ids, mode)


def normalize_trim_results(raw, project_ids, mode):
    results = []
    for item in raw:
        output = Path(item["outputPath"]).resolve() if item.get("outputPath") else None
        success = (
            item.get("status") == "success"
            and item.get("failedCount", 0) == 0
            and not item.get("audioErrors")
            and output is not None
            and output.is_dir()
        )
        results.append(
            {
                "project_id": item.get("projectId"),
                "status": "success" if success else "failed",
                "frame_count": item.get("successCount", 0),
                "failed_count": item.get("failedCount", 0),
                "total_frame_count": item.get("frameCount", 0),
                "failed_frames": item.get("failedFrames", []),
                "audio_errors": item.get("audioErrors", []),
                "final_frames_dir": str(output) if output and output.is_dir() else None,
                "batch_root": str(output.parent) if output and output.parent.is_dir() else None,
                "offset_data_path": str(output / "_frame_data.json")
                if output and (output / "_frame_data.json").is_file()
                else None,
                "audio_timeline_path": str(output / "_audio_timeline.json")
                if output and (output / "_audio_timeline.json").is_file()
                else None,
                "message": item.get("message"),
            }
        )
    return {
        "mode": mode,
        "final": bool(results) and all(item["status"] == "success" for item in results),
        "results": results,
        "raw_results": raw,
        "project_ids": project_ids,
        "persisted": any(item["final_frames_dir"] is not None for item in results),
    }
