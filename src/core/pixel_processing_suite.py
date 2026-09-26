"""
Pixel art processing pipeline for sprite sheet generation.
"""

import io
import os
from typing import Optional

import cv2
import numpy as np
from PIL import Image

from src.core import naming_utils
from src.utils.logger import log_error, log_info

# Type alias for size values
SizeValue = str | int


def filter_by_density(alpha_mask: np.ndarray, min_neighbors: int = 6) -> np.ndarray:
    """
    Neighborhood density filter: remove isolated or spike pixels with too few neighbors.

    Args:
        alpha_mask: Alpha channel mask (grayscale)
        min_neighbors: Minimum number of neighboring pixels required

    Returns:
        Refined mask with isolated pixels removed
    """
    binary = (alpha_mask > 0).astype(np.uint8)

    kernel = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], dtype=np.uint8)

    counts = cv2.filter2D(binary, -1, kernel, borderType=cv2.BORDER_CONSTANT)

    refined_mask = np.where((binary == 1) & (counts >= min_neighbors), 255, 0)
    return refined_mask.astype(np.uint8)


def remove_isolated_islands(alpha_mask: np.ndarray, min_island_size: int = 15) -> np.ndarray:
    """
    Connected-component filter: remove disconnected pixel islands below the area threshold.

    Args:
        alpha_mask: Alpha channel mask (grayscale)
        min_island_size: Minimum size for connected components

    Returns:
        Cleaned mask with small islands removed
    """
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(alpha_mask, connectivity=8)
    clean_mask = np.zeros_like(alpha_mask)

    for i in range(1, num_labels):
        if stats[i, cv2.CC_STAT_AREA] >= min_island_size:
            clean_mask[labels == i] = 255
    return clean_mask


def pixel_engine_processor(
    image_path: str,
    output_folder: str,
    target_sizes: list[SizeValue],
    *,
    do_crop: bool = True,
    alpha_threshold: int = 160,
    min_neighbors: int = 6,
    min_island_size: int = 15,
    frame_num: int = 0,
    pixel_style: bool = True,
) -> None:
    """
    Core processing engine combining resize and multi-stage cleanup.

    Args:
        image_path: Path to input image
        output_folder: Output directory
        target_sizes: List of target sizes (e.g., [64, 128, 256, 512, "origin"])
        do_crop: Whether to crop to 1:1 aspect ratio
        alpha_threshold: Alpha threshold for removing semi-transparent noise
        min_neighbors: Minimum neighbor count for density filtering
        min_island_size: Minimum size for connected component retention
        frame_num: Frame number for naming
        pixel_style: True uses pixel style (NEAREST); False uses smooth interpolation
    """
    if not os.path.exists(image_path):
        log_error(f"Image file not found: {image_path}")
        return

    try:
        with open(image_path, "rb") as f:
            img_bytes = f.read()
        with Image.open(io.BytesIO(img_bytes)).convert("RGBA") as img:
            orig_w, orig_h = img.size

            for size in target_sizes:
                processed_img = _resize_image(img, orig_w, orig_h, size, do_crop, pixel_style)
                processed_img = _clean_alpha_channel(processed_img, alpha_threshold, min_neighbors, min_island_size)
                _save_pixel_image(processed_img, output_folder, size, frame_num, pixel_style)

    except OSError as e:
        log_error(f"Failed to process image: {image_path}", e)


def _resize_image(
    img: Image.Image, orig_w: int, orig_h: int, size: SizeValue, do_crop: bool, pixel_style: bool = True
) -> Image.Image:
    """Resize image based on crop settings."""
    if size == "origin":
        return img.copy()

    # Choose interpolation algorithm.
    resample = Image.NEAREST if pixel_style else Image.LANCZOS

    if do_crop:
        side = min(orig_w, orig_h)
        left = (orig_w - side) // 2
        top = (orig_h - side) // 2
        cropped = img.crop((left, top, left + side, top + side))
        return cropped.resize((int(size), int(size)), resample=resample)

    # Maintain aspect ratio
    target_size = int(size)
    if orig_w > orig_h:
        new_w = target_size
        new_h = int(orig_h * (target_size / orig_w))
    else:
        new_h = target_size
        new_w = int(orig_w * (target_size / orig_h))
    return img.resize((new_w, new_h), resample=resample)


def _clean_alpha_channel(
    processed_img: Image.Image, alpha_threshold: int, min_neighbors: int, min_island_size: int
) -> Image.Image:
    """Clean alpha channel using multiple filtering passes."""
    cv_img = cv2.cvtColor(np.array(processed_img), cv2.COLOR_RGBA2BGRA)
    alpha = cv_img[:, :, 3]

    # A. Color thresholding
    _, alpha_bin = cv2.threshold(alpha, alpha_threshold, 255, cv2.THRESH_BINARY)

    # B. Density filtering
    alpha_bin = filter_by_density(alpha_bin, min_neighbors)

    # C. Connected component cleaning
    alpha_bin = remove_isolated_islands(alpha_bin, min_island_size)

    cv_img[:, :, 3] = alpha_bin

    # D. Clear RGB in transparent areas to prevent color leakage during resizing.
    transparent_mask = alpha_bin == 0
    cv_img[transparent_mask, 0] = 0  # B
    cv_img[transparent_mask, 1] = 0  # G
    cv_img[transparent_mask, 2] = 0  # R

    return Image.fromarray(cv2.cvtColor(cv_img, cv2.COLOR_BGRA2RGBA))


def _save_pixel_image(
    final_img: Image.Image, output_folder: str, size: SizeValue, frame_num: int, pixel_style: bool = True
) -> None:
    """Save processed pixel image to output directory."""
    size_dir = os.path.join(output_folder, naming_utils.get_pixelart_cache_subdir_name(size, pixel_style))
    os.makedirs(size_dir, exist_ok=True)

    output_path = os.path.join(size_dir, naming_utils.get_frame_filename("px", frame_num))

    img_byte_arr = io.BytesIO()
    final_img.save(img_byte_arr, format="PNG")
    with open(output_path, "wb") as f:
        f.write(img_byte_arr.getvalue())


def clean_image_file(
    image_path: str, output_path: str, alpha_threshold: int = 160, min_neighbors: int = 6, min_island_size: int = 15
) -> bool:
    """
    Clean isolated alpha pixels in one image and save it.

    Args:
        image_path: Input image path.
        output_path: Output image path.
        alpha_threshold: Alpha threshold; pixels below this value are cleared.
        min_neighbors: Minimum neighbor count for density filtering.
        min_island_size: Minimum component area for connected-component filtering.

    Returns:
        True if successful, False otherwise
    """
    try:
        with open(image_path, "rb") as f:
            img_bytes = f.read()
        with Image.open(io.BytesIO(img_bytes)).convert("RGBA") as img:
            cleaned = _clean_alpha_channel(img, alpha_threshold, min_neighbors, min_island_size)
        img_byte_arr = io.BytesIO()
        cleaned.save(img_byte_arr, format="PNG")
        with open(output_path, "wb") as f:
            f.write(img_byte_arr.getvalue())
        return True
    except OSError as e:
        log_error(f"Failed to clean image: {image_path}", e)
        return False


def batch_pixel_pipeline(input_dir: str, output_root: str, target_sizes: list[SizeValue], **kwargs: Optional) -> None:
    """
    Batch pipeline that iterates over the input directory.

    Args:
        input_dir: Input directory containing images
        output_root: Root output directory
        target_sizes: List of target sizes
        **kwargs: Additional arguments passed to processor
    """
    os.makedirs(output_root, exist_ok=True)

    files = [f for f in os.listdir(input_dir) if f.lower().endswith((".png", ".jpg", ".jpeg"))]
    log_info(f"找到 {len(files)} 张图片，开始处理流水线...")

    for filename in files:
        input_path = os.path.join(input_dir, filename)
        pixel_engine_processor(input_path, output_root, target_sizes, **kwargs)
        log_info(f"已完成: {filename}")


if __name__ == "__main__":
    # Configuration parameters.
    config = {
        "input_dir": "frames_no_green",
        "output_root": "pixel_assets_final",
        "target_sizes": [512, 256, 64],
        "do_crop": False,
        "alpha_threshold": 160,
        "min_neighbors": 6,
        "min_island_size": 10,
    }

    batch_pixel_pipeline(**config)
