"""
Video utilities - Frame extraction from video files
Wraps src/core/video_utils.py for the new backend API
"""

from collections.abc import Callable
from pathlib import Path

import cv2
from PIL import Image


def process_video_to_cache(
    video_path: str,
    cache_dir: str,
    fps: int = 12,
    frame_interval: int = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict:
    """
    Extract frames from video to cache directory

    Args:
        video_path: Path to video file
        cache_dir: Directory to save cached frames
        fps: Target frame rate for extraction (legacy, used if frame_interval is None)
        frame_interval: Frame interval for extraction (1 = every frame, 2 = every 2nd frame, etc.)
        progress_callback: Called with (current, total) progress

    Returns:
        Dictionary with extraction results
    """
    import os

    os.makedirs(cache_dir, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    video_fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / video_fps if video_fps > 0 else 0

    # Calculate frame interval
    if frame_interval is not None:
        # Use explicit frame_interval
        frame_interval = max(1, frame_interval)
        target_frames = total_frames // frame_interval
    elif fps >= video_fps:
        frame_interval = 1
        target_frames = total_frames
    else:
        frame_interval = int(video_fps / fps)
        target_frames = total_frames // frame_interval

    frame_count = 0
    saved_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_count % frame_interval == 0:
            # Convert BGR to RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)

            # Save frame
            frame_filename = f"frame_{saved_count:06d}.png"
            frame_path = Path(cache_dir) / frame_filename
            img.save(frame_path, "PNG")

            saved_count += 1

            if progress_callback:
                progress_callback(saved_count, target_frames)

        frame_count += 1

    cap.release()

    return {"total_frames": saved_count, "video_fps": video_fps, "target_fps": fps, "duration": duration}


def export_frames_step1(
    cache_dir: str,
    output_dir: str,
    start: int = 0,
    end: int = -1,
    step: int = 1,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list:
    """
    Export frames from cache to output directory (Step 1)
    Copies selected frames from cache to output/01_frames with optional range and step

    Args:
        cache_dir: Source cache directory
        output_dir: Target output directory
        start: Start frame index (0-based)
        end: End frame index (-1 means last frame)
        step: Frame interval (1 = every frame, 2 = every 2nd frame, etc.)
        progress_callback: Called with (current, total) progress

    Returns:
        List of exported frame paths
    """
    import shutil
    from pathlib import Path

    cache_path = Path(cache_dir)
    output_path = Path(output_dir)

    # Clear output directory if exists, then recreate
    if output_path.exists():
        shutil.rmtree(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    # Get all frame files sorted
    all_frames = sorted(cache_path.glob("frame_*.png"))

    if not all_frames:
        return []

    # Determine end index
    if end < 0 or end >= len(all_frames):
        end = len(all_frames) - 1

    # Clamp start to valid range
    start = max(0, min(start, len(all_frames) - 1))

    # Ensure start <= end
    if start > end:
        start = end

    exported = []
    output_index = 0
    total_to_export = len(range(start, end + 1, step))

    for output_index, i in enumerate(range(start, end + 1, step)):
        if i >= len(all_frames):
            break

        frame_file = all_frames[i]
        # Use sequential naming for output
        dest = output_path / f"frame_{output_index:06d}.png"
        shutil.copy2(frame_file, dest)
        exported.append(str(dest))

        if progress_callback:
            progress_callback(output_index + 1, total_to_export)

    return exported


def load_frames_from_dir(directory: str) -> list:
    """
    Load all frames from a directory

    Args:
        directory: Directory containing frame images

    Returns:
        List of frame file paths
    """
    from pathlib import Path

    path = Path(directory)
    if not path.exists():
        return []

    frames = sorted(path.glob("*.png"))
    return [str(f) for f in frames]


def validate_video(video_path: str) -> dict:
    """
    Validate video file for processing

    Args:
        video_path: Path to video file

    Returns:
        Dictionary with validation results
    """
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        return {"valid": False, "error": "Cannot open video file"}

    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = frame_count / fps if fps > 0 else 0

    cap.release()

    errors = []
    warnings = []

    # Warn for very large videos, but do not block processing.
    if width > 2160 or height > 2160:
        warnings.append("Resolution is high; background removal may be slow")

    # Check duration (max 60 seconds)
    if duration > 60:
        errors.append(f"Video too long: {duration:.1f}s (max 60s)")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "fps": fps,
        "frame_count": frame_count,
        "width": width,
        "height": height,
        "duration": duration,
    }


def detect_background_color_from_frames(input_dir: str, sample_count: int = 5) -> tuple[int, int, int] | None:
    """Estimate background metadata from original-frame edge patches."""
    from backend.core.background_color import detect_background_hsv

    return detect_background_hsv(input_dir, sample_count)
