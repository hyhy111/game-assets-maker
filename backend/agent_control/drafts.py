"""Validate incomplete creation forms without submitting a generation."""

from dataclasses import fields
from typing import Any

from backend.seedance.models import SeedanceRequest
from backend.seedance.validation import ValidationError
from backend.seedance.validation import validate_request as validate_video
from backend.seedream.models import SeedreamRequest
from backend.seedream.validation import validate_request as validate_image

CLI_VIDEO_DURATIONS = (4, 5, 6)


def validate_video_duration(duration: Any) -> None:
    """Keep Agent video drafts and submissions within the GUI duration choices."""
    if type(duration) is not int or duration not in CLI_VIDEO_DURATIONS:
        raise ValidationError("duration", "INVALID_DURATION", "CLI video duration must be 4, 5 or 6 seconds")


def validate_draft(kind: str, values: dict[str, Any]) -> None:
    if kind not in ("image", "video") or not isinstance(values, dict):
        raise ValueError("INPUT_INVALID")
    model = SeedanceRequest if kind == "video" else SeedreamRequest
    allowed = {field.name for field in fields(model)}
    if kind == "video":
        allowed -= {"priority", "execution_expires_after"}
    if set(values) - allowed:
        raise ValueError("Unknown draft field")
    if kind == "video":
        validate_video_duration(values.get("duration", 5))
    for key, value in values.items():
        if key in {"duration", "count"}:
            valid = type(value) is int
        elif key in {"generate_audio", "return_last_frame"}:
            valid = type(value) is bool
        elif key in {"last_frame", "reference_image"}:
            valid = value is None or isinstance(value, str)
        else:
            valid = isinstance(value, str)
        if not valid:
            raise ValueError(f"Invalid field type: {key}")
    request = model.from_dict(values)
    (validate_video if kind == "video" else validate_image)(request, draft=True)


def restore_draft(api, kind: str, local_id: str) -> dict[str, Any]:
    from pathlib import Path

    from backend.agent_control.artifacts import LocalArtifacts

    if (
        kind not in ("image", "video")
        or not isinstance(local_id, str)
        or not local_id
        or any(c in local_id for c in "/\\")
        or local_id in (".", "..")
    ):
        raise ValueError("INPUT_INVALID")
    locations = api.storage_locations
    root = locations.ai_pic_cache_root if kind == "image" else locations.ai_video_cache_root
    metadata = (
        root
        / ("batches" if kind == "image" else "tasks")
        / local_id
        / ("batch.json" if kind == "image" else "task.json")
    )
    original = LocalArtifacts(locations).read(str(metadata))["content"]
    restore = api.seedream_get_regeneration_draft if kind == "image" else api.seedance_get_regeneration_draft
    result = restore(local_id)
    if not result.get("success"):
        raise ValueError("ASSET_MISSING")
    request = result["data"]["request"]
    if kind == "image":
        if original.get("request", {}).get("reference_image") and not request.get("reference_image"):
            raise ValueError("ASSET_MISSING")
        request["reference_image"] = request.get("reference_image") or ""
    else:
        if original.get("input_paths", {}).get("last_frame") and not request.get("last_frame"):
            raise ValueError("ASSET_MISSING")
        request = {key: value for key, value in request.items() if key not in {"priority", "execution_expires_after"}}
    for field in ("reference_image", "first_frame", "last_frame"):
        if request.get(field) and not Path(request[field]).is_file():
            raise ValueError("ASSET_MISSING")
    validate_draft(kind, request)
    return {"patch": request, "provenance": {"kind": kind, "local_id": local_id, "metadata_path": str(metadata)}}
