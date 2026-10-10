import json
from pathlib import Path
from typing import Any

from backend.image_input import (
    ImageInputError,
    image_data_url,
    read_image_metadata,
)
from backend.seedance.models import MODEL_CAPABILITIES, SeedanceRequest

_ALLOWED_RATIOS = {"adaptive", "16:9", "1:1", "4:3"}
_MAX_PAYLOAD_BYTES = 64 * 1024 * 1024


class ValidationError(ValueError):
    def __init__(self, field: str, code: str, message: str):
        super().__init__(message)
        self.field = field
        self.code = code


def _serialized_payload_bytes(payload: dict[str, Any]) -> int:
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _trimmed_prompt(request: SeedanceRequest) -> str:
    return request.prompt.strip()


def _image_metadata(path: Path, field: str) -> tuple[str, int, int]:
    try:
        image_format, width, height = read_image_metadata(path)
    except ImageInputError as error:
        raise ValidationError(field, error.code, error.message) from error
    if not 300 <= width <= 6000 or not 300 <= height <= 6000:
        raise ValidationError(field, "INVALID_IMAGE_DIMENSIONS", "Image dimensions must be between 300 and 6000 pixels")
    aspect_ratio = width / height
    if not 0.4 <= aspect_ratio <= 2.5:
        raise ValidationError(field, "INVALID_IMAGE_ASPECT_RATIO", "Image aspect ratio must be between 0.4 and 2.5")
    return image_format, width, height


def _validate_integer(value: int, field: str, minimum: int, maximum: int, code: str) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValidationError(field, code, f"{field} must be between {minimum} and {maximum}")


def validate_request(request: SeedanceRequest, *, draft: bool = False) -> None:
    if request.model not in MODEL_CAPABILITIES:
        raise ValidationError("model", "UNSUPPORTED_MODEL", "Unsupported Seedance model")
    if request.resolution not in MODEL_CAPABILITIES[request.model]["resolutions"]:
        raise ValidationError("resolution", "UNSUPPORTED_RESOLUTION", "Resolution is unsupported for this model")
    if request.ratio not in _ALLOWED_RATIOS:
        raise ValidationError("ratio", "UNSUPPORTED_RATIO", "Unsupported aspect ratio")
    if type(request.duration) is not int or (request.duration != -1 and not 4 <= request.duration <= 15):
        raise ValidationError("duration", "INVALID_DURATION", "duration must be -1 or between 4 and 15")
    _validate_integer(request.priority, "priority", 0, 9, "INVALID_PRIORITY")
    _validate_integer(request.execution_expires_after, "execution_expires_after", 3600, 259200, "INVALID_EXPIRY")
    if not draft or str(request.first_frame) not in ("", "."):
        _image_metadata(request.first_frame, "first_frame")
    if request.last_frame is not None:
        _image_metadata(request.last_frame, "last_frame")


def _image_content(path: Path, role: str) -> dict[str, Any]:
    image_format, _, _ = _image_metadata(path, role)
    return {
        "type": "image_url",
        "image_url": {"url": image_data_url(path, image_format)},
        "role": role,
    }


def _build_payload(request: SeedanceRequest) -> dict[str, Any]:
    prompt = _trimmed_prompt(request)
    content: list[dict[str, Any]] = []
    if prompt:
        content.append({"type": "text", "text": prompt})
    content.append(_image_content(request.first_frame, "first_frame"))
    if request.last_frame is not None:
        content.append(_image_content(request.last_frame, "last_frame"))
    return {
        "model": MODEL_CAPABILITIES[request.model]["id"],
        "content": content,
        "resolution": request.resolution,
        "ratio": request.ratio,
        "duration": request.duration,
        "generate_audio": request.generate_audio,
        "return_last_frame": request.return_last_frame,
        "priority": request.priority,
        "execution_expires_after": request.execution_expires_after,
        "watermark": False,
    }


def estimate_payload_bytes(request: SeedanceRequest) -> int:
    validate_request(request)
    return _serialized_payload_bytes(_build_payload(request))


def build_api_payload(request: SeedanceRequest) -> dict[str, Any]:
    validate_request(request)
    payload = _build_payload(request)
    if _serialized_payload_bytes(payload) >= _MAX_PAYLOAD_BYTES:
        raise ValidationError("payload", "PAYLOAD_TOO_LARGE", "The request body must be smaller than 64 MiB")
    return payload
