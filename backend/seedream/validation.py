from pathlib import Path
from typing import Any

from backend.image_input import ImageInputError, image_data_url, read_image_metadata
from backend.seedream.models import MODEL_CAPABILITIES, SeedreamRequest

_ALLOWED_RATIOS = ("1:1", "16:9", "9:16", "4:3", "3:4")


class ValidationError(ValueError):
    def __init__(self, field: str, code: str, message: str):
        super().__init__(message)
        self.field = field
        self.code = code


def validate_request(request: SeedreamRequest) -> None:
    _validate_common(request)
    if request.reference_image:
        _reference_image_format(Path(request.reference_image))


def _validate_common(request: SeedreamRequest) -> None:
    if request.model not in MODEL_CAPABILITIES:
        raise ValidationError("model", "UNSUPPORTED_MODEL", "Unsupported Seedream model")
    if request.resolution not in MODEL_CAPABILITIES[request.model]["resolutions"]:
        raise ValidationError("resolution", "UNSUPPORTED_RESOLUTION", "Resolution is unsupported for this model")
    if request.ratio not in _ALLOWED_RATIOS:
        raise ValidationError("ratio", "UNSUPPORTED_RATIO", "Unsupported aspect ratio")
    if not isinstance(request.count, int) or request.count < 1 or request.count > 4:
        raise ValidationError("count", "INVALID_COUNT", "Image count must be between 1 and 4")
    if not request.prompt.strip():
        raise ValidationError("prompt", "PROMPT_REQUIRED", "Prompt must not be empty")


def _reference_image_format(path: Path) -> str:
    try:
        image_format, _, _ = read_image_metadata(path)
    except ImageInputError as error:
        raise ValidationError("reference_image", error.code, error.message) from error
    return image_format


def _build_prompt_with_ratio(prompt: str, ratio: str) -> str:
    trimmed = prompt.strip()
    if not trimmed:
        return trimmed
    return f"图片比例 {ratio}，{trimmed}"


def build_api_payload(request: SeedreamRequest) -> dict[str, Any]:
    _validate_common(request)
    image_entries: list[str] | None = None
    if request.reference_image:
        path = Path(request.reference_image)
        image_entries = [image_data_url(path, _reference_image_format(path))]
    payload: dict[str, Any] = {
        "model": MODEL_CAPABILITIES[request.model]["id"],
        "prompt": _build_prompt_with_ratio(request.prompt, request.ratio),
        "size": request.resolution,
        "response_format": "url",
        "watermark": False,
    }
    if image_entries is not None:
        payload["image"] = image_entries
    return payload
