"""Shared validation and Base64 encoding for local images submitted to Ark APIs."""

from __future__ import annotations

import base64
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from pillow_heif import register_heif_opener

register_heif_opener()

ALLOWED_IMAGE_FORMATS = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "BMP": "image/bmp",
    "TIFF": "image/tiff",
    "GIF": "image/gif",
    "HEIC": "image/heic",
    "HEIF": "image/heif",
}
MAX_IMAGE_BYTES = 30 * 1024 * 1024


class ImageInputError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def file_size(path: Path) -> int:
    return path.stat().st_size


def read_image_metadata(path: Path) -> tuple[str, int, int]:
    """Return (format, width, height) after validating existence, size, and format."""
    if not path.is_file():
        raise ImageInputError("IMAGE_NOT_FOUND", "Image file does not exist")
    if file_size(path) >= MAX_IMAGE_BYTES:
        raise ImageInputError("IMAGE_TOO_LARGE", "Each image must be smaller than 30 MiB")
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image_format = image.format
            width, height = image.size
    except (OSError, UnidentifiedImageError) as error:
        raise ImageInputError("INVALID_IMAGE", "Image file cannot be opened") from error
    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise ImageInputError("UNSUPPORTED_IMAGE_FORMAT", "Unsupported image format")
    return image_format, width, height


def image_data_url(path: Path, image_format: str) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{ALLOWED_IMAGE_FORMATS[image_format]};base64,{encoded}"
