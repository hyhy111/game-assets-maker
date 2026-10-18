"""
Smart background removal using rembg - Remove background from frames
Uses rembg u2net model with alpha matting for high-quality edge smoothing

Step 2: Background removal only (rembg, no hole punching)
Step 3: Hole punching (based on background color saved from Step 1)
"""

import datetime
import io
import os
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from src.utils.data_paths import data_root, models_root


def _write_debug_log(msg: str):
    """Write debug message to a log file for diagnosing packaged app issues"""
    try:
        if hasattr(sys, "_MEIPASS"):
            return
        log_dir = data_root() / "logs"
        log_dir.mkdir(exist_ok=True)
        log_path = log_dir / "debug_rembg.log"
        timestamp = datetime.datetime.now().isoformat()
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {msg}\n")
    except Exception:
        pass


# Set the rembg model directory through the shared data-path boundary (before
# importing rembg). Source runs keep the repository models/ directory;
# installed builds use the per-user GAM User Data root so models survive app updates and the
# install directory can stay read-only.
_MODELS_DIR = models_root()

_MODELS_DIR.mkdir(parents=True, exist_ok=True)
os.environ["U2NET_HOME"] = str(_MODELS_DIR)

_write_debug_log(f"U2NET_HOME set to: {os.environ['U2NET_HOME']}")
_model_contents = [f.name for f in _MODELS_DIR.glob("*")] if _MODELS_DIR.exists() else "N/A"
_write_debug_log(f"Model dir exists: {_MODELS_DIR.exists()}, contents: {_model_contents}")

# Import rembg lazily inside functions to speed up startup
# try:
#     from rembg import remove, new_session
#     _write_debug_log("rembg imported successfully")
# except ImportError as _e:
#     _write_debug_log(f"rembg import failed: {_e}")
#     raise ImportError("rembg not installed. Please install: pip install rembg[cpu]")


# Hole intensity mapping for step 3 hole punching
HOLE_INTENSITY_MAP = {
    1: {"diff_h": 5, "diff_sv": 20, "description": "弱 - 保守挖孔"},
    3: {"diff_h": 10, "diff_sv": 40, "description": "标准"},
    5: {"diff_h": 15, "diff_sv": 60, "description": "强 - 激进挖孔"},
    7: {"diff_h": 20, "diff_sv": 80, "description": "极强"},
}

# Global session cache and lock for rembg
_session_cache: dict[str, Any] = {}
_session_lock = threading.Lock()

# Available rembg models (bundled with the application)
AVAILABLE_MODELS = [
    "u2net",  # Default, general purpose (~176MB)
]


def _get_model_path(model: str) -> Path:
    """Get the expected path for a model file"""
    return _MODELS_DIR / f"{model}.onnx"


def check_model_available(model: str) -> bool:
    """Check if a model file exists locally"""
    from pooch import file_hash

    from src.core.rembg_model import U2NET_HASH

    path = _get_model_path(model)
    return model == "u2net" and path.is_file() and file_hash(str(path), alg="md5") == U2NET_HASH.split(":", 1)[1]


def get_model_file_size(model: str) -> int | None:
    """Return the local model size when the completed file is available."""
    path = _get_model_path(model)
    return path.stat().st_size if path.is_file() else None


def get_available_local_models() -> list:
    """Get list of models available locally"""
    return [model for model in AVAILABLE_MODELS if _get_model_path(model).is_file()]


def get_rembg_session(model: str = "u2net") -> Any:
    """Get or create rembg session (cached) with thread safety"""
    from src.core.rembg_model import validate_model

    validate_model(model)
    with _session_lock:
        if model not in _session_cache:
            model_path = _get_model_path(model)
            _write_debug_log(f"get_rembg_session: model={model}, path={model_path}, exists={model_path.exists()}")

            if not check_model_available(model):
                raise RuntimeError("MODEL_DOWNLOAD_REQUIRED")

            try:
                from rembg import new_session

                _write_debug_log(f"Initializing rembg session for {model}...")
                # This is the time-consuming part
                _session_cache[model] = new_session(model)
                _write_debug_log(f"new_session({model}) created successfully")
            except Exception as e:
                _write_debug_log(f"new_session({model}) failed: {e}")
                raise
        return _session_cache[model]


def preload_model(model: str = "u2net") -> bool:
    """Explicitly preload a model into memory in a background thread"""
    try:
        _write_debug_log(f"Preloading model: {model}")
        get_rembg_session(model)
        return True
    except Exception as e:
        _write_debug_log(f"Preload failed: {e}")
        return False


def sample_background_color_from_corners(img: np.ndarray) -> tuple[int, int, int] | None:
    """
    Sample background color from image corners (original image background still present)

    Args:
        img: BGR original image
    Returns:
        (H, S, V) background color HSV average value
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, w = img.shape[:2]

    # Sample from four corners (usually background area)
    corners = [
        (5, 5),  # top-left
        (5, w - 5),  # top-right
        (h - 5, 5),  # bottom-left
        (h - 5, w - 5),  # bottom-right
    ]

    bg_colors = []
    for y, x in corners:
        y = max(0, min(y, h - 1))
        x = max(0, min(x, w - 1))
        bg_colors.append(hsv[y, x])

    if not bg_colors:
        return None

    return tuple(np.mean(bg_colors, axis=0).astype(int))


def detect_background_color_from_frames(input_dir: str, sample_count: int = 5) -> tuple[int, int, int] | None:
    """
    Detect background color by sampling from multiple frames in the input directory.
    This is called during Step 1 completion.

    Args:
        input_dir: Directory containing extracted frames
        sample_count: Number of frames to sample (default 5)

    Returns:
        (H, S, V) background color HSV tuple, or None if detection failed
    """
    input_path = Path(input_dir)
    if not input_path.exists():
        return None

    frames = sorted(input_path.glob("*.png"))
    if not frames:
        return None

    # Sample frames evenly
    step = max(1, len(frames) // sample_count)
    sampled_colors = []

    for i in range(0, len(frames), step):
        if len(sampled_colors) >= sample_count:
            break

        try:
            # Read original frame
            img_array = np.fromfile(str(frames[i]), dtype=np.uint8)
            img_bgr = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

            if img_bgr is not None:
                bg_hsv = sample_background_color_from_corners(img_bgr)
                if bg_hsv is not None:
                    sampled_colors.append(bg_hsv)
        except Exception as e:
            print(f"[Warning] Failed to sample background from {frames[i]}: {e}")
            continue

    if not sampled_colors:
        return None

    # Average all sampled colors
    return tuple(np.mean(sampled_colors, axis=0).astype(int))


def remove_background_single_rembg(
    image_path: str, params: dict[str, Any] | None = None
) -> tuple[Image.Image | None, tuple[int, int, int] | None]:
    """
    Step 2: Remove background from a single image using rembg (NO hole punching)

    Args:
        image_path: Path to input image
        params: Processing parameters including:
            - model: 'u2net' (the only supported model)
            - post_process_mask: Apply mask post-processing for smoother edges (bool)
            - alpha_matting: Enable alpha matting (bool, default True)
            - alpha_matting_erode_size: Alpha matting erosion size (0-20, default 5)
            - alpha_matting_background_threshold: Background threshold (0-255, default 12)
            - alpha_matting_foreground_threshold: Foreground threshold (100-250, default 240)
            - edge_erode: Edge erosion iterations after rembg (0-5, default 1)

    Returns:
        Tuple of (PIL Image with background removed, background color HSV)
        or (None, None) if failed
    """
    if params is None:
        params = {}

    # Default parameters - only rembg related
    model = params.get("model", "u2net")
    post_process_mask = params.get("post_process_mask", False)
    alpha_matting = params.get("alpha_matting", True)
    alpha_matting_erode_size = params.get("alpha_matting_erode_size", 5)
    alpha_matting_background_threshold = params.get("alpha_matting_background_threshold", 12)
    alpha_matting_foreground_threshold = params.get("alpha_matting_foreground_threshold", 240)
    edge_erode = params.get("edge_erode", 1)

    try:
        _write_debug_log(f"remove_background_single_rembg: processing {image_path}, model={model}")

        # 1. Read original image (background still present, for background color sampling)
        img_array = np.fromfile(image_path, dtype=np.uint8)
        img_bgr_original = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if img_bgr_original is None:
            print(f"[Error] Cannot read image: {image_path}")
            _write_debug_log(f"Cannot read image: {image_path}")
            return None, None

        # 2. Sample background color from corners (for return value - used in Step 3)
        bg_hsv = sample_background_color_from_corners(img_bgr_original)

        # 3. Use rembg to generate color-corrected RGBA image (fixes edge green issues)
        with open(image_path, "rb") as f:
            img_data = f.read()

        # Get or create rembg session with specified model
        from rembg import remove

        session = get_rembg_session(model)

        # Use background threshold directly (0-255 range)
        ab_threshold = alpha_matting_background_threshold

        # Get full RGBA image (rembg does color correction, removes edge green)
        _write_debug_log(f"Calling rembg.remove for {image_path}")
        rgba_data = remove(
            img_data,
            session=session,
            only_mask=False,  # Get full image
            alpha_matting=alpha_matting,  # Enable alpha matting
            alpha_matting_erode_size=alpha_matting_erode_size,
            alpha_matting_background_threshold=ab_threshold,
            alpha_matting_foreground_threshold=alpha_matting_foreground_threshold,
            post_process_mask=post_process_mask,  # Apply mask post-processing
        )
        rgba_pil = Image.open(io.BytesIO(rgba_data))
        rgba = np.array(rgba_pil)

        # Separate RGB and Alpha (rembg already did color correction)
        if rgba.shape[2] == 4:
            rgb_clean = rgba[:, :, :3]  # Clean RGB (no green at edges)
            mask = rgba[:, :, 3]  # Alpha as mask
        else:
            # fallback
            rgba_pil = rgba_pil.convert("RGBA")
            rgba = np.array(rgba_pil)
            rgb_clean = rgba[:, :, :3]
            mask = rgba[:, :, 3]

        # 4. Edge optimization (erosion) - minimal, no hole punching here
        if edge_erode > 0:
            kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
            mask = cv2.erode(mask, kernel, iterations=edge_erode)

        # 5. Compose final image (using rembg color-corrected clean RGB)
        # Convert RGB to BGR for OpenCV
        img_bgr_clean = cv2.cvtColor(rgb_clean, cv2.COLOR_RGB2BGR)
        b, g, r = cv2.split(img_bgr_clean)

        # Pre-multiply Alpha: clear RGB in transparent areas
        b[mask == 0] = 0
        g[mask == 0] = 0
        r[mask == 0] = 0

        result = cv2.merge([b, g, r, mask])

        # Convert to PIL Image
        result_rgb = cv2.cvtColor(result, cv2.COLOR_BGRA2RGBA)
        _write_debug_log(f"Successfully processed {image_path}")
        return Image.fromarray(result_rgb, "RGBA"), bg_hsv

    except Exception as e:
        print(f"[Error] Failed to process {image_path}: {e}")
        import traceback

        tb = traceback.format_exc()
        _write_debug_log(f"Failed to process {image_path}: {e}\n{tb}")
        return None, None


def batch_remove_background(
    input_dir: str,
    output_dir: str,
    params: dict[str, Any] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict:
    """
    Step 2: Remove background from all frames in a directory using rembg (NO hole punching)

    Args:
        input_dir: Directory containing input frames
        output_dir: Directory to save processed frames
        params: Processing parameters (see remove_background_single_rembg for details)
        progress_callback: Called with (current, total) progress

    Returns:
        Dictionary with processing results including 'background_color' HSV
    """
    import shutil
    from pathlib import Path

    input_path = Path(input_dir)
    output_path = Path(output_dir)

    # Clear output directory if exists to ensure fresh processing
    if output_path.exists():
        shutil.rmtree(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    frames = sorted(input_path.glob("*.png"))
    total = len(frames)

    results = {
        "total": total,
        "success": 0,
        "failed": 0,
        "output_files": [],
        "background_color": None,  # Will store the first frame's bg color
    }

    # Process each frame
    for i, frame_path in enumerate(frames):
        try:
            result, bg_hsv = remove_background_single_rembg(str(frame_path), params=params)

            if result:
                output_file = output_path / frame_path.name
                result.save(output_file, "PNG")
                results["success"] += 1
                results["output_files"].append(str(output_file))

                # Store background color from first frame
                if i == 0 and bg_hsv is not None:
                    results["background_color"] = bg_hsv
            else:
                results["failed"] += 1

        except Exception as e:
            print(f"Error processing {frame_path}: {e}")
            results["failed"] += 1

        if progress_callback:
            progress_callback(i + 1, total)

    return results


def punch_holes(
    img: np.ndarray,
    mask: np.ndarray,
    bg_hsv: tuple[int, int, int],
    diff_h: int,
    diff_sv: int,
    min_hole_size: int,
    edge_margin: int = 5,
    core_threshold: int = 200,
) -> tuple[np.ndarray, int]:
    """
    Punch holes inside the subject (preserve feathered edges)

    Args:
        img: BGR original image (for color analysis)
        mask: grayscale mask (0-255, contains feathered edges)
        bg_hsv: Background color HSV value
        diff_h: Hue tolerance
        diff_sv: Saturation/value tolerance
        min_hole_size: Minimum hole area in pixels
        edge_margin: Edge protection margin in pixels
        core_threshold: Subject core threshold
    Returns:
        (processed mask, number of holes punched)
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, w = img.shape[:2]

    bg_h, bg_s, bg_v = bg_hsv

    # Define hole color range (strict threshold) - normal background color
    lower_hole = np.array([max(0, bg_h - diff_h), max(0, bg_s - diff_sv), max(0, bg_v - diff_sv)])
    upper_hole = np.array([min(180, bg_h + diff_h), min(255, bg_s + diff_sv), min(255, bg_v + diff_sv)])

    # Detect potential hole areas (on original image)
    mask_hole_normal = cv2.inRange(hsv, lower_hole, upper_hole)

    # Additional detection: dark green areas (background residue darkened by alpha matting)
    lower_dark_green = np.array(
        [
            max(0, bg_h - diff_h),
            50,  # Minimum saturation 50 to avoid detecting gray
            0,  # Minimum value 0 to detect all dark colors
        ]
    )
    upper_dark_green = np.array(
        [
            min(180, bg_h + diff_h),
            255,
            max(0, bg_v - diff_sv - 20),  # 20 lower than normal background tolerance
        ]
    )

    mask_hole_dark = cv2.inRange(hsv, lower_dark_green, upper_dark_green)

    # Merge both detection results
    mask_hole_strict = cv2.bitwise_or(mask_hole_normal, mask_hole_dark)

    # Create subject core area (for edge protection)
    mask_core = (mask >= core_threshold).astype(np.uint8) * 255

    # Create inner protected area (distance from core edge)
    if edge_margin > 0:
        kernel = np.ones((3, 3), np.uint8)
        mask_inner = cv2.erode(mask_core, kernel, iterations=edge_margin)
    else:
        mask_inner = mask_core

    # Hole detection strategy:
    # 1. Is background color on original image (mask_hole_strict == 255)
    # 2. Inside subject contour (subject_mask == 255)
    # 3. Distance from edge (mask_inner == 255)
    potential_holes = (mask_hole_strict == 255) & (mask_inner == 255)

    # Connected component analysis
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(potential_holes.astype(np.uint8), connectivity=8)

    # Copy original mask
    result_mask = mask.copy().astype(np.uint8)

    hole_count = 0
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if area >= min_hole_size:
            # Punch hole here (set to transparent)
            result_mask[labels == i] = 0
            hole_count += 1

    return result_mask, hole_count


def punch_holes_in_frame(
    image_path: str, bg_hsv: tuple[int, int, int], hole_intensity: int, min_hole_size: int
) -> Image.Image | None:
    """
    Step 3: Punch holes in a single frame that has already been background-removed

    Args:
        image_path: Path to input image (must be RGBA with alpha from rembg)
        bg_hsv: Background color HSV tuple (from step 1)
        hole_intensity: Hole punching intensity (1-7, default 3)
        min_hole_size: Minimum hole area (0-5000, default 500)
        edge_erode: Edge erosion iterations (0-5, default 1)
        hole_edge_margin: Hole edge protection margin (0-20, default 5)
        core_threshold: Subject core threshold (100-255, default 200)
        alpha_normalize: Normalize alpha to binary (0 or 255) (default False)

    Returns:
        PIL Image with holes punched and alpha normalized, or None if failed
    """
    try:
        # Read the background-removed image (RGBA)
        img_array = np.fromfile(image_path, dtype=np.uint8)
        img_rgba = cv2.imdecode(img_array, cv2.IMREAD_UNCHANGED)

        if img_rgba is None:
            print(f"[Error] Cannot read image: {image_path}")
            return None

        # Must have alpha channel
        if len(img_rgba.shape) < 3 or img_rgba.shape[2] != 4:
            print(f"[Error] Image does not have alpha channel: {image_path}")
            return None

        # Split RGB and Alpha
        bgr = img_rgba[:, :, :3]
        mask = img_rgba[:, :, 3]

        # Punch holes
        # Get hole intensity parameters
        hole_params = HOLE_INTENSITY_MAP.get(hole_intensity, HOLE_INTENSITY_MAP[3])

        # Punch holes (with fixed default values for removed parameters)
        final_mask, hole_count = punch_holes(
            bgr,
            mask,
            bg_hsv,
            hole_params["diff_h"],
            hole_params["diff_sv"],
            min_hole_size,
            edge_margin=0,
            core_threshold=255,
        )

        # Recompose image with new mask
        b, g, r = cv2.split(bgr)
        b[final_mask == 0] = 0
        g[final_mask == 0] = 0
        r[final_mask == 0] = 0

        result = cv2.merge([b, g, r, final_mask])

        # Convert to PIL Image
        result_rgb = cv2.cvtColor(result, cv2.COLOR_BGRA2RGBA)
        return Image.fromarray(result_rgb, "RGBA")

    except Exception as e:
        print(f"[Error] Failed to punch holes in {image_path}: {e}")
        import traceback

        traceback.print_exc()
        return None


def batch_punch_holes(
    input_dir: str,
    output_dir: str,
    bg_hsv: tuple[int, int, int],
    params: dict[str, Any] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict:
    """
    Step 3: Batch punch holes in all frames in a directory

    Args:
        input_dir: Directory containing input frames (RGBA from rembg)
        output_dir: Directory to save processed frames
        bg_hsv: Background color HSV tuple (from step 1)
        params: Processing parameters:
            - hole_intensity: Hole punching intensity (1-7, default 3)
            - min_hole_size: Minimum hole area (0-5000, default 500)
        progress_callback: Called with (current, total) progress

    Returns:
        Dictionary with processing results
    """
    import shutil
    from pathlib import Path

    if params is None:
        params = {}

    input_path = Path(input_dir)
    output_path = Path(output_dir)

    # Clear output directory if exists to ensure fresh processing
    if output_path.exists():
        shutil.rmtree(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    frames = sorted(input_path.glob("*.png"))
    total = len(frames)

    results = {"total": total, "success": 0, "failed": 0, "output_files": [], "total_holes_punched": 0}

    # Process each frame
    for i, frame_path in enumerate(frames):
        try:
            result = punch_holes_in_frame(
                str(frame_path),
                bg_hsv,
                hole_intensity=params.get("hole_intensity", 3),
                min_hole_size=params.get("min_hole_size", 500),
            )

            if result:
                output_file = output_path / frame_path.name
                result.save(output_file, "PNG")
                results["success"] += 1
                results["output_files"].append(str(output_file))
            else:
                results["failed"] += 1

        except Exception as e:
            print(f"Error processing {frame_path}: {e}")
            results["failed"] += 1

        if progress_callback:
            progress_callback(i + 1, total)

    return results


# Green intensity presets (1-5): 1=bright green, 5=dark/muted green
GREEN_INTENSITY_PRESETS = {
    1: {  # Vivid green - standard green screen.
        "hue_min": 40,
        "hue_max": 80,
        "sat_min": 120,
        "val_min": 150,
        "description": "鲜艳翠绿 - 仅标准绿幕",
    },
    2: {  # Bright green.
        "hue_min": 35,
        "hue_max": 85,
        "sat_min": 100,
        "val_min": 120,
        "description": "明亮绿色",
    },
    3: {  # Standard green - recommended.
        "hue_min": 30,
        "hue_max": 90,
        "sat_min": 80,
        "val_min": 100,
        "description": "标准绿色 - 推荐",
    },
    4: {  # Muted green.
        "hue_min": 25,
        "hue_max": 95,
        "sat_min": 50,
        "val_min": 70,
        "description": "暗沉绿色",
    },
    5: {  # Very dark green.
        "hue_min": 20,
        "hue_max": 100,
        "sat_min": 30,
        "val_min": 40,
        "description": "极暗绿色 - 包含灰暗绿色",
    },
}

# Fixed parameters
ALPHA_THRESHOLD = 100  # Only process pixels inside subject (alpha > threshold)
DEFAULT_FEATHER_RADIUS = 3  # 3px feather for smooth edges
DEFAULT_MIN_HOLE_SIZE = 5  # Minimum hole area in pixels


def punch_holes_green(
    img: np.ndarray,
    mask: np.ndarray,
    green_intensity: int,
    feather_radius: int = DEFAULT_FEATHER_RADIUS,
    min_hole_size: int = DEFAULT_MIN_HOLE_SIZE,
) -> tuple[np.ndarray, int]:
    """
    Punch holes based on green color detection with feathered edges.

    Args:
        img: BGR image
        mask: grayscale alpha mask (0-255)
        green_intensity: Intensity level 1-5 (1=bright green, 5=dark green)
        feather_radius: Feather radius in pixels (0-10), default 3
        min_hole_size: Minimum hole area in pixels, default 5

    Returns:
        Tuple of (processed mask, number of holes punched)
    """
    # Get preset parameters for the intensity level
    preset = GREEN_INTENSITY_PRESETS.get(green_intensity, GREEN_INTENSITY_PRESETS[3])

    # Convert to HSV
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Detect green areas based on preset
    lower_green = np.array([preset["hue_min"], preset["sat_min"], preset["val_min"]])
    upper_green = np.array([preset["hue_max"], 255, 255])
    green_mask = cv2.inRange(hsv, lower_green, upper_green)

    # High alpha mask - only process pixels inside the subject
    high_alpha_mask = (mask > ALPHA_THRESHOLD).astype(np.uint8) * 255

    # Green areas that are inside the subject (potential holes)
    potential_holes = cv2.bitwise_and(green_mask, high_alpha_mask)

    # Connected component analysis to filter small areas
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(potential_holes, connectivity=8)

    # Create hole mask (only holes larger than min_hole_size)
    hole_mask = np.zeros_like(mask)
    hole_count = 0

    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if area >= min_hole_size:
            hole_mask[labels == i] = 255
            hole_count += 1

    # Apply feathering
    if hole_count > 0:
        # Distance transform from hole edge (inverted hole mask)
        hole_mask_inv = cv2.bitwise_not(hole_mask)
        dist_transform = cv2.distanceTransform(hole_mask_inv, cv2.DIST_L2, 5)

        # Normalize distance to create feather weights (0-1 range)
        feather_weights = np.clip(dist_transform / max(1, feather_radius), 0, 1)

        # Apply feathering: reduce alpha inside holes, keep original at edge
        result_mask = mask.copy()
        result_mask = (result_mask * feather_weights).astype(np.uint8)
    else:
        # No holes found - return original mask
        result_mask = mask.copy()

    return result_mask, hole_count


def punch_holes_green_in_frame(image_path: str, params: dict[str, Any]) -> Image.Image | None:
    """
    Process a single frame with green detection hole punching.

    Args:
        image_path: Path to input image (must be RGBA)
        params: Processing parameters including:
            - green_intensity: Intensity level 1-5 (1=bright, 5=dark)

    Returns:
        PIL Image with holes punched, or None if failed
    """
    try:
        # Read the background-removed image (RGBA)
        img_array = np.fromfile(image_path, dtype=np.uint8)
        img_rgba = cv2.imdecode(img_array, cv2.IMREAD_UNCHANGED)

        if img_rgba is None:
            print(f"[Error] Cannot read image: {image_path}")
            return None

        # Must have alpha channel
        if len(img_rgba.shape) < 3 or img_rgba.shape[2] != 4:
            print(f"[Error] Image does not have alpha channel: {image_path}")
            return None

        # Split RGB and Alpha
        bgr = img_rgba[:, :, :3]
        mask = img_rgba[:, :, 3]

        # Get parameters
        green_intensity = params.get("green_intensity", 3)
        feather_radius = params.get("feather_radius", DEFAULT_FEATHER_RADIUS)
        min_hole_size = params.get("min_hole_size", DEFAULT_MIN_HOLE_SIZE)

        # Punch holes based on green detection
        final_mask, hole_count = punch_holes_green(bgr, mask, green_intensity, feather_radius, min_hole_size)

        # Recompose image with new mask
        b, g, r = cv2.split(bgr)
        b[final_mask == 0] = 0
        g[final_mask == 0] = 0
        r[final_mask == 0] = 0

        result = cv2.merge([b, g, r, final_mask])

        # Convert to PIL Image
        result_rgb = cv2.cvtColor(result, cv2.COLOR_BGRA2RGBA)
        return Image.fromarray(result_rgb, "RGBA")

    except Exception as e:
        print(f"[Error] Failed to punch holes in {image_path}: {e}")
        import traceback

        traceback.print_exc()
        return None


def batch_punch_holes_green(
    input_dir: str,
    output_dir: str,
    params: dict[str, Any] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict:
    """
    Step 3: Batch punch holes using green detection.

    Args:
        input_dir: Directory containing input frames (RGBA from rembg)
        output_dir: Directory to save processed frames
        params: Processing parameters:
            - green_intensity: Intensity level 1-5 (1=bright green, 5=dark green), default 3
            - feather_radius: Feather radius in pixels (0-10), default 3
            - min_hole_size: Minimum hole area in pixels (0-500), default 5
        progress_callback: Called with (current, total) progress

    Returns:
        Dictionary with processing results
    """
    import shutil
    from pathlib import Path

    if params is None:
        params = {}

    input_path = Path(input_dir)
    output_path = Path(output_dir)

    # Clear output directory if exists to ensure fresh processing
    if output_path.exists():
        shutil.rmtree(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    frames = sorted(input_path.glob("*.png"))
    total = len(frames)

    results = {"total": total, "success": 0, "failed": 0, "output_files": [], "total_holes_punched": 0}

    # Process each frame
    for i, frame_path in enumerate(frames):
        try:
            result = punch_holes_green_in_frame(str(frame_path), params=params)

            if result:
                output_file = output_path / frame_path.name
                result.save(output_file, "PNG")
                results["success"] += 1
                results["output_files"].append(str(output_file))
            else:
                results["failed"] += 1

        except Exception as e:
            print(f"Error processing {frame_path}: {e}")
            results["failed"] += 1

        if progress_callback:
            progress_callback(i + 1, total)

    return results


# Legacy compatibility function (for old API compatibility)
def remove_background_single(
    image_path: str, intensity: int = 5, hole_intensity: int = 3, enable_erosion: bool = False, erosion_value: int = 1
) -> Image.Image | None:
    """
    Legacy single image background removal function
    Maps old parameters to new rembg parameters
    """
    # Map legacy parameters to new parameters
    params = {
        "alpha_matting": True,
        "alpha_matting_erode_size": 5,
        "alpha_matting_background_threshold": 120,
        "alpha_matting_foreground_threshold": 245,
    }
    result, _ = remove_background_single_rembg(image_path, params)
    return result
