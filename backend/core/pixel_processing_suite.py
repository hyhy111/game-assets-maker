"""
Pixel processing suite - Pixelization and outline processing
Wraps src/core/pixel_processing_suite.py for the new backend API
"""

from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def pixel_engine_processor(
    input_dir: str,
    project_path: str,
    target_sizes: list[int] = None,
    outline_thickness: int = 1,
    enable_inner_outline: bool = False,
    inner_outline_thickness: int = 1,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict:
    """
    Process frames through pixelization pipeline

    Args:
        input_dir: Directory containing input frames (Step 2 output)
        project_path: Root project path
        target_sizes: List of target pixelization sizes (e.g., [64, 128, 256])
        outline_thickness: Outline thickness in pixels
        enable_inner_outline: Whether to add inner outline
        inner_outline_thickness: Inner outline thickness
        progress_callback: Called with (current, total) progress

    Returns:
        Dictionary with processing results
    """
    if target_sizes is None:
        target_sizes = [64, 128, 256]

    input_path = Path(input_dir)
    project_path = Path(project_path)
    output_dir = project_path / "output" / "03_hole_punched"
    cache_root = project_path / "cache" / "03_pixelate_cache"

    output_dir.mkdir(parents=True, exist_ok=True)
    cache_root.mkdir(parents=True, exist_ok=True)

    frames = sorted(input_path.glob("*.png"))
    total_frames = len(frames)

    results = {"total_frames": total_frames, "target_sizes": target_sizes, "output_files": [], "cache_dirs": []}

    processed_count = 0

    for frame_path in frames:
        try:
            # Process for each target size
            for size in target_sizes:
                result = process_single_frame(
                    str(frame_path),
                    target_size=size,
                    outline_thickness=outline_thickness,
                    enable_inner_outline=enable_inner_outline,
                    inner_outline_thickness=inner_outline_thickness,
                )

                if result:
                    # Save to cache
                    cache_dir = cache_root / f"{size}px"
                    cache_dir.mkdir(exist_ok=True)

                    cache_file = cache_dir / frame_path.name
                    result.save(cache_file, "PNG")

                    # Copy first size to main output
                    if size == target_sizes[0]:
                        output_file = output_dir / frame_path.name
                        result.save(output_file, "PNG")
                        results["output_files"].append(str(output_file))

            processed_count += 1

            if progress_callback:
                progress_callback(processed_count, total_frames)

        except Exception as e:
            print(f"Error processing {frame_path}: {e}")

    results["processed_count"] = processed_count
    return results


def process_single_frame(
    image_path: str,
    target_size: int = 128,
    outline_thickness: int = 1,
    enable_inner_outline: bool = False,
    inner_outline_thickness: int = 1,
) -> Image.Image | None:
    """
    Process a single frame through pixelization

    Args:
        image_path: Path to input image
        target_size: Target size for pixelization
        outline_thickness: Outline thickness
        enable_inner_outline: Whether to add inner outline
        inner_outline_thickness: Inner outline thickness

    Returns:
        Processed PIL Image or None if failed
    """
    try:
        # Load image
        img = Image.open(image_path).convert("RGBA")
        original_size = img.size

        # Pixelization step - use NEAREST for pixel art style
        img_small = img.resize((target_size, target_size), Image.NEAREST)
        img_pixelized = img_small.resize(original_size, Image.NEAREST)

        # Apply outline if requested
        if outline_thickness > 0:
            img_pixelized = apply_outline(
                img_pixelized,
                thickness=outline_thickness,
                inner=enable_inner_outline,
                inner_thickness=inner_outline_thickness,
            )

        return img_pixelized

    except Exception as e:
        print(f"Error processing frame {image_path}: {e}")
        return None


def apply_outline(
    img: Image.Image,
    thickness: int = 1,
    color: tuple[int, int, int, int] = (0, 0, 0, 255),
    inner: bool = False,
    inner_thickness: int = 1,
) -> Image.Image:
    """
    Apply outline to image

    Args:
        img: Input PIL Image
        thickness: Outline thickness
        color: Outline color (RGBA)
        inner: Whether to add inner outline
        inner_thickness: Inner outline thickness

    Returns:
        Image with outline applied
    """
    np_img = np.array(img)
    alpha = np_img[:, :, 3]

    # Create outline mask
    kernel = np.ones((thickness * 2 + 1, thickness * 2 + 1), np.uint8)
    dilated = cv2.dilate(alpha, kernel, iterations=1)
    outline_mask = dilated - alpha

    # Apply outline
    result = np_img.copy()
    for c in range(4):
        if c < 3:
            result[:, :, c] = np.where(outline_mask > 0, color[c], result[:, :, c])
        else:
            result[:, :, c] = np.maximum(alpha, outline_mask)

    # Inner outline if requested
    if inner and inner_thickness > 0:
        inner_kernel = np.ones((inner_thickness * 2 + 1, inner_thickness * 2 + 1), np.uint8)
        eroded = cv2.erode(alpha, inner_kernel, iterations=1)
        inner_mask = alpha - eroded

        inner_color = (0, 0, 0, 255)  # Black inner outline
        for c in range(4):
            if c < 3:
                result[:, :, c] = np.where(inner_mask > 0, inner_color[c], result[:, :, c])

    return Image.fromarray(result, "RGBA")


def remove_isolated_pixels(img: Image.Image, min_size: int = 5) -> Image.Image:
    """
    Remove isolated pixels and small noise

    Args:
        img: Input PIL Image
        min_size: Minimum connected component size to keep

    Returns:
        Cleaned image
    """
    np_img = np.array(img)
    alpha = np_img[:, :, 3]

    # Find connected components
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(alpha, connectivity=8)

    # Create mask for components to keep
    mask = np.zeros_like(alpha)
    for i in range(1, num_labels):
        if stats[i, cv2.CC_STAT_AREA] >= min_size:
            mask[labels == i] = 255

    # Apply mask
    result = np_img.copy()
    result[:, :, 3] = mask

    return Image.fromarray(result, "RGBA")
