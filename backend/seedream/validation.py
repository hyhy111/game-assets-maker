from pathlib import Path
from typing import Any

from backend.image_input import ImageInputError, image_data_url, read_image_metadata
from backend.platform.sources import PLATFORM_SOURCE
from backend.seedream.models import MODEL_CAPABILITIES, SeedreamRequest, platform_model_id

_ALLOWED_RATIOS = ("1:1", "16:9", "9:16", "4:3", "3:4")


class ValidationError(ValueError):
    def __init__(self, field: str, code: str, message: str):
        super().__init__(message)
        self.field = field
        self.code = code


def validate_request(request: SeedreamRequest, *, draft: bool = False) -> None:
    _validate_common(request, draft=draft)
    if request.reference_image:
        _reference_image_format(Path(request.reference_image))


def _validate_common(request: SeedreamRequest, *, draft: bool = False) -> None:
    # Platform model IDs are validated by the server; local tables describe API-key models.
    if request.source != PLATFORM_SOURCE:
        if request.model not in MODEL_CAPABILITIES:
            raise ValidationError("model", "UNSUPPORTED_MODEL", "Unsupported Seedream model")
        if request.resolution not in MODEL_CAPABILITIES[request.model]["resolutions"]:
            raise ValidationError("resolution", "UNSUPPORTED_RESOLUTION", "Resolution is unsupported for this model")
    if request.ratio not in _ALLOWED_RATIOS:
        raise ValidationError("ratio", "UNSUPPORTED_RATIO", "Unsupported aspect ratio")
    if not isinstance(request.count, int) or request.count < 1 or request.count > 4:
        raise ValidationError("count", "INVALID_COUNT", "Image count must be between 1 and 4")
    if not draft and not request.prompt.strip():
        raise ValidationError("prompt", "PROMPT_REQUIRED", "Prompt must not be empty")


# 上游**图片**接口对输入图的约束（Seedream 参考图）——与视频那套不同，别混用。
# 见火山《图片生成教程》"不同场景对输入图的约束"表。
_IMAGE_MIN_PX = 15
_IMAGE_MAX_PX = 6000
_IMAGE_MAX_TOTAL_PX = 36_000_000
_IMAGE_MIN_RATIO = 1.0 / 16
_IMAGE_MAX_RATIO = 16.0


def _reference_image_format(path: Path) -> str:
    """校验参考图并返回其格式。

    此前这里只取格式、丢弃宽高——直连模式下超大或超宽比的参考图会一路走到上游才失败，
    错误文案还是上游给的，不友好。现在按**图片接口**的约束在本地拦（注意不是视频那套：
    视频要求 300~6000px / 比例 [0.4,2.5]，比图片严得多）。
    """
    try:
        image_format, width, height = read_image_metadata(path)
    except ImageInputError as error:
        raise ValidationError("reference_image", error.code, error.message) from error

    if width < _IMAGE_MIN_PX or width > _IMAGE_MAX_PX or height < _IMAGE_MIN_PX or height > _IMAGE_MAX_PX:
        raise ValidationError(
            "reference_image",
            "INVALID_IMAGE_DIMENSIONS",
            f"参考图宽高须大于 14 且不超过 6000 像素（当前 {width}×{height}）",
        )
    if width * height > _IMAGE_MAX_TOTAL_PX:
        raise ValidationError(
            "reference_image",
            "INVALID_IMAGE_DIMENSIONS",
            f"参考图总像素不能超过 3600 万（当前 {width * height}）",
        )
    ratio = width / height
    if not _IMAGE_MIN_RATIO <= ratio <= _IMAGE_MAX_RATIO:
        raise ValidationError(
            "reference_image",
            "INVALID_IMAGE_ASPECT_RATIO",
            f"参考图宽高比须在 1/16~16 之间（当前 {ratio:.2f}）",
        )
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
        "model": platform_model_id(request.model),
        "prompt": _build_prompt_with_ratio(request.prompt, request.ratio),
        "size": request.resolution,
        "response_format": "url",
        "watermark": False,
    }
    if image_entries is not None:
        payload["image"] = image_entries
    return payload
