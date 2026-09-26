"""
Video frame extraction and processing utilities.
"""

import io
import os
import shutil
from collections.abc import Callable

import cv2
import numpy as np
from PIL import Image

from src.core import naming_utils
from src.utils.logger import log_error, log_info

# Type alias for progress callback
ProgressCallback = Callable[[int, str], None] | None


def load_frames_from_dir(dir_path: str) -> list[np.ndarray]:
    """
    Load all images from a directory into a list of numpy arrays (OpenCV images).

    Args:
        dir_path: Path to directory containing images

    Returns:
        List of numpy arrays representing images
    """
    frames: list[np.ndarray] = []
    if os.path.exists(dir_path) and os.listdir(dir_path):
        files = sorted([f for f in os.listdir(dir_path) if f.lower().endswith((".png", ".jpg", ".jpeg", ".bmp"))])
        if not files:
            return []

        for f in files:
            fpath = os.path.join(dir_path, f)
            img = cv2.imdecode(np.fromfile(fpath, dtype=np.uint8), cv2.IMREAD_UNCHANGED)

            if img is not None and len(img.shape) == 3 and img.shape[2] == 3:
                try:
                    with open(fpath, "rb") as file:
                        img_bytes = file.read()
                    pil_img = Image.open(io.BytesIO(img_bytes))
                    has_alpha = False
                    if pil_img.mode in ("RGBA", "LA") or pil_img.mode == "P" and "transparency" in pil_img.info:
                        has_alpha = True

                    if has_alpha:
                        pil_img = pil_img.convert("RGBA")
                        img_rgba = np.array(pil_img)
                        img = cv2.cvtColor(img_rgba, cv2.COLOR_RGBA2BGRA)
                except OSError as e:
                    log_error(f"Failed to read image with PIL: {fpath}", e)

            if img is not None:
                frames.append(img)
    return frames


class VideoError(Exception):
    """Base exception for video processing errors."""

    pass


class VideoNotFoundError(VideoError):
    """Raised when video file is not found."""

    pass


class VideoValidationError(VideoError):
    """Raised when video exceeds validation constraints."""

    pass


def process_video_to_cache(
    video_path: str, cache_dir: str, progress_callback: ProgressCallback = None
) -> tuple[list[np.ndarray], str]:
    """
    Reads video, saves frames to cache.

    Args:
        video_path: Path to video file
        cache_dir: Root cache directory
        progress_callback: function(percentage, message)

    Returns:
        Tuple of (frames list, video name)

    Raises:
        VideoNotFoundError: If video path does not exist
        VideoValidationError: If video exceeds size/duration limits
        VideoError: On other video processing errors
    """
    if not os.path.exists(video_path):
        raise VideoNotFoundError(f"Video path does not exist: {video_path}")

    video_name = os.path.splitext(os.path.basename(video_path))[0]
    video_cache_path = os.path.join(cache_dir, naming_utils.get_cache_dir_name(video_name, "frames"))

    # Try loading existing cache first
    frames = load_frames_from_dir(video_cache_path)
    if frames:
        if progress_callback:
            progress_callback(100, f"已加载缓存: {video_name}")
        return frames, video_name

    # If not in cache, process video
    os.makedirs(video_cache_path, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise VideoError("无法打开视频文件")

    try:
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0

        if width > 2160 or height > 2160:
            log_info("分辨率过高，抠像处理可能会偏慢")

        # Validation
        if duration > 60 or total_frames > 1000:
            if duration > 60:
                raise VideoValidationError(f"视频超出限制: {width}x{height}, {duration:.1f}秒。\n限制: 60秒")
            if total_frames > 1000:
                raise VideoValidationError(f"视频超出限制: {total_frames}帧。\n限制: 1000帧")

        count = 0
        frames: list[np.ndarray] = []
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frames.append(frame)
            fname = os.path.join(video_cache_path, naming_utils.get_frame_filename("raw", count))
            is_success, im_buf = cv2.imencode(".png", frame, [cv2.IMWRITE_PNG_COMPRESSION, 1])
            if is_success:
                im_buf.tofile(fname)

            count += 1
            if progress_callback and count % 10 == 0:
                pct = int(count / (total_frames or 1) * 100)
                progress_callback(pct, f"正在切帧: {pct}%")

        if not frames:
            raise VideoError("No frames extracted from video")

        return frames, video_name

    finally:
        cap.release()


def export_frames_step1(
    frames: list[np.ndarray],
    output_dir: str,
    video_name: str,
    start: int,
    end: int,
    step: int,
    progress_callback: ProgressCallback = None,
) -> tuple[int, str]:
    """
    Export selected frames to output directory.

    Args:
        frames: List of frames to export
        output_dir: Output directory path
        video_name: Name of the video
        start: Start frame index
        end: End frame index
        step: Step size for frame selection
        progress_callback: Optional progress callback

    Returns:
        Tuple of (saved_count, target_directory)
    """
    dir_name = naming_utils.get_output_dir_name(video_name, "frames")
    target_dir = os.path.join(output_dir, dir_name)

    if os.path.exists(target_dir):
        shutil.rmtree(target_dir)
    os.makedirs(target_dir)

    saved_count = 0
    total_to_check = end - start + 1
    if total_to_check <= 0:
        return 0, target_dir

    for i, idx in enumerate(range(start, end + 1)):
        if (idx - start) % step == 0 and idx < len(frames):
            frame = frames[idx]
            fname = os.path.join(target_dir, naming_utils.get_frame_filename("raw", saved_count))
            is_success, im_buf = cv2.imencode(".png", frame, [cv2.IMWRITE_PNG_COMPRESSION, 3])
            if is_success:
                im_buf.tofile(fname)
                saved_count += 1

        if progress_callback and i % 5 == 0:
            pct = int((i / total_to_check) * 100)
            progress_callback(pct, f"导出中... {pct}% ({saved_count} 帧)")

    return saved_count, target_dir


def validate_sequence_dir(dir_path: str) -> tuple[bool, str]:
    """
    Validates if a directory contains a sequence of PNG images with incrementing numbers.

    Args:
        dir_path: Path to directory to validate

    Returns:
        Tuple of (is_valid, message)
    """
    if not os.path.exists(dir_path) or not os.path.isdir(dir_path):
        return False, "Directory does not exist"

    files = sorted([f for f in os.listdir(dir_path) if f.lower().endswith(".png")])
    if not files:
        return False, "No PNG files found"

    import re

    numbers: list[int] = []
    for f in files:
        nums = re.findall(r"\d+", f)
        if nums:
            numbers.append(int(nums[-1]))

    if not numbers:
        return False, "No numbers found in filenames"

    if len(numbers) != len(files):
        return False, "Some PNG files do not contain numbers"

    # Check for incrementing sequence
    start_num = numbers[0]
    for i, num in enumerate(numbers):
        if num != start_num + i:
            return False, f"Sequence break: expected {start_num + i}, found {num}"

    return True, f"Found {len(files)} sequential frames"


def export_frames_to_dir(
    frames: list[np.ndarray],
    target_dir: str,
    start: int,
    end: int,
    step: int,
    prefix: str = "raw",
    progress_callback: ProgressCallback = None,
) -> int:
    """
    Export selected frames to a specific target directory.

    Args:
        frames: List of frames to export
        target_dir: Target directory path
        start: Start frame index
        end: End frame index
        step: Step size
        prefix: Filename prefix
        progress_callback: Optional progress callback

    Returns:
        Number of frames saved
    """
    log_info(f"export_frames_to_dir: start={start}, end={end}, step={step}")

    if os.path.exists(target_dir):
        shutil.rmtree(target_dir)
    os.makedirs(target_dir)

    saved_count = 0
    total_to_check = end - start + 1
    if total_to_check <= 0:
        return 0

    selected_indices: list[int] = []

    for i, idx in enumerate(range(start, end + 1)):
        if (idx - start) % step == 0 and idx < len(frames):
            selected_indices.append(idx)
            frame = frames[idx]
            fname = os.path.join(target_dir, f"{prefix}_{saved_count:04d}.png")
            is_success, im_buf = cv2.imencode(".png", frame, [cv2.IMWRITE_PNG_COMPRESSION, 3])
            if is_success:
                im_buf.tofile(fname)
                saved_count += 1

        if progress_callback and i % 5 == 0:
            pct = int((i / total_to_check) * 100)
            progress_callback(pct, f"正在导出... {pct}%")

    log_info(f"Selected indices: {selected_indices[:10]}{'...' if len(selected_indices) > 10 else ''}")
    log_info(f"Total frames saved: {saved_count}")

    return saved_count
