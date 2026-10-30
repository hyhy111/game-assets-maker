"""Automatically sample a solid background and clean rembg's remaining color regions."""

from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np

ALGORITHM = "CIELAB CIEDE2000"
BASE_TOLERANCES = (3.0, 5.0, 7.0, 10.0, 14.0)
MAX_VARIATION = 7.0
MAX_TOLERANCE = 21.0


def to_color_space(bgr: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(bgr.astype(np.float32) / 255.0, cv2.COLOR_BGR2Lab)


def color_distance(colors: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """CIEDE2000 with unit parametric factors, vectorized over the last Lab axis.

    Equations and verification data: Sharma, Wu, Dalal (2005), DOI:10.1002/col.20070.
    https://hajim.rochester.edu/ece/sites/gsharma/ciede2000/
    """
    colors, reference = np.broadcast_arrays(
        np.asarray(colors, dtype=np.float64), np.asarray(reference, dtype=np.float64)
    )
    light1, a1, b1 = np.moveaxis(colors, -1, 0)
    light2, a2, b2 = np.moveaxis(reference, -1, 0)
    chroma_mean = (np.hypot(a1, b1) + np.hypot(a2, b2)) / 2
    g = 0.5 * (1 - np.sqrt(chroma_mean**7 / (chroma_mean**7 + 25.0**7)))
    a1p, a2p = a1 * (1 + g), a2 * (1 + g)
    c1, c2 = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1 = np.mod(np.degrees(np.arctan2(b1, a1p)), 360)
    h2 = np.mod(np.degrees(np.arctan2(b2, a2p)), 360)
    h1, h2 = np.where(c1 == 0, 0, h1), np.where(c2 == 0, 0, h2)
    zero_chroma = c1 * c2 == 0
    delta_h = h2 - h1
    delta_h = np.where(delta_h > 180, delta_h - 360, delta_h)
    delta_h = np.where(delta_h < -180, delta_h + 360, delta_h)
    delta_h = np.where(zero_chroma, 0, delta_h)
    delta_h_term = 2 * np.sqrt(c1 * c2) * np.sin(np.radians(delta_h / 2))
    mean_l, mean_c = (light1 + light2) / 2, (c1 + c2) / 2
    mean_h = np.where(
        np.abs(h1 - h2) <= 180, (h1 + h2) / 2, np.where(h1 + h2 < 360, (h1 + h2 + 360) / 2, (h1 + h2 - 360) / 2)
    )
    mean_h = np.where(zero_chroma, h1 + h2, mean_h)
    t = (
        1
        - 0.17 * np.cos(np.radians(mean_h - 30))
        + 0.24 * np.cos(np.radians(2 * mean_h))
        + 0.32 * np.cos(np.radians(3 * mean_h + 6))
        - 0.20 * np.cos(np.radians(4 * mean_h - 63))
    )
    sl = 1 + 0.015 * (mean_l - 50) ** 2 / np.sqrt(20 + (mean_l - 50) ** 2)
    sc, sh = 1 + 0.045 * mean_c, 1 + 0.015 * mean_c * t
    rotation = (
        -2 * np.sqrt(mean_c**7 / (mean_c**7 + 25.0**7)) * np.sin(np.radians(60 * np.exp(-(((mean_h - 275) / 25) ** 2))))
    )
    dl, dc, dh = (light2 - light1) / sl, (c2 - c1) / sc, delta_h_term / sh
    return np.sqrt(np.maximum(0, dl**2 + dc**2 + dh**2 + rotation * dc * dh))


def read_bgr(path: Path) -> np.ndarray:
    image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Cannot read source frame: {path.name}")
    return image


def sample_edge_pixels(image: np.ndarray) -> np.ndarray:
    """Average multiple small edge patches, rejecting isolated subject-covered patches."""
    height, width = image.shape[:2]
    size = max(1, min(16, min(height, width) // 32))
    ys = (0, (height - size) // 2, height - size)
    xs = (0, (width - size) // 2, width - size)
    patches = [
        image[y : y + size, x : x + size].reshape(-1, 3)
        for y in ys
        for x in xs
        if y in (ys[0], ys[-1]) or x in (xs[0], xs[-1])
    ]
    means = np.array([patch.mean(axis=0) for patch in patches])
    distances = np.linalg.norm(means - np.median(means, axis=0), axis=1)
    keep = distances <= max(20.0, float(np.median(distances)) * 2.5)
    return np.concatenate([patch for patch, accepted in zip(patches, keep, strict=True) if accepted])


def background_hsv_from_images(images: list[np.ndarray]) -> tuple[int, int, int]:
    """Keep legacy HSV metadata, averaging BGR samples before converting the result."""
    samples = np.concatenate([sample_edge_pixels(image) for image in images])
    mean = np.rint(samples.mean(axis=0)).astype(np.uint8).reshape(1, 1, 3)
    return tuple(int(value) for value in cv2.cvtColor(mean, cv2.COLOR_BGR2HSV)[0, 0])


def detect_background_hsv(input_dir: str, sample_count: int = 5) -> tuple[int, int, int] | None:
    frames = sorted(Path(input_dir).glob("*.png"))
    if not frames or sample_count < 1:
        return None
    indices = np.linspace(0, len(frames) - 1, min(sample_count, len(frames)), dtype=int)
    return background_hsv_from_images([read_bgr(frames[index]) for index in indices])


def validate_color_params(params: dict) -> None:
    # Retain the saved field name for existing projects and CLI callers.
    for name, low, high, default in (
        ("green_intensity", 1, 5, 3),
        ("feather_radius", 0, 10, 3),
        ("min_hole_size", 0, 500, 5),
    ):
        value = params.get(name, default)
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"Invalid step parameter: {name}")


def estimate_background(frames: list[Path], intensity: int) -> tuple[np.ndarray, float]:
    """Use one reference across the sequence to avoid frame-by-frame threshold flicker."""
    indices = np.linspace(0, len(frames) - 1, min(5, len(frames)), dtype=int)
    samples = np.concatenate([sample_edge_pixels(read_bgr(frames[index])) for index in indices])
    mean_bgr = samples.mean(axis=0).astype(np.float32).reshape(1, 1, 3)
    reference = to_color_space(mean_bgr)[0, 0]
    colors = to_color_space(samples.astype(np.float32).reshape(-1, 1, 3))[:, 0]
    variation = float(np.percentile(color_distance(colors, reference), 95))
    # Bound automatic expansion so a contaminated edge cannot create an unlimited color range.
    tolerance = min(MAX_TOLERANCE, BASE_TOLERANCES[intensity - 1] + min(variation, MAX_VARIATION))
    return reference, tolerance


def punch_color_mask(mask: np.ndarray, color_mask: np.ndarray, feather_radius: int, min_hole_size: int) -> np.ndarray:
    candidates = ((mask > 100) & color_mask).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(candidates, connectivity=8)
    keep = stats[:, cv2.CC_STAT_AREA] >= min_hole_size
    keep[0] = False
    holes = keep[labels]
    if count == 1 or not holes.any():
        return mask.copy()
    result = mask.copy()
    result[holes] = 0
    if feather_radius:
        distance = cv2.distanceTransform((~holes).astype(np.uint8), cv2.DIST_L2, 5)
        result = (result * np.clip(distance / feather_radius, 0, 1)).astype(np.uint8)
    return result


def batch_punch_holes_color(
    input_dir: str,
    output_dir: str,
    source_dir: str,
    params: dict,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict:
    """Match original-frame colors and apply the resulting holes to rembg RGBA frames."""
    import shutil

    validate_color_params(params)
    frames = sorted(Path(input_dir).glob("*.png"))
    if not frames:
        raise ValueError("Step 2 frames not found")
    sources = [Path(source_dir) / frame.name for frame in frames]
    if any(not source.is_file() for source in sources):
        raise ValueError("Original frames required for background detection. Please run Step 1 and Step 2 again.")
    reference, tolerance = estimate_background(sources, params.get("green_intensity", 3))
    output = Path(output_dir)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    for index, (frame, source) in enumerate(zip(frames, sources, strict=True)):
        if progress_callback:
            progress_callback(index, len(frames))
        rgba = cv2.imdecode(np.fromfile(frame, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        original = read_bgr(source)
        if rgba is None or rgba.ndim != 3 or rgba.shape[2] != 4 or rgba.shape[:2] != original.shape[:2]:
            raise ValueError(f"Source and RGBA frame dimensions must match: {frame.name}")
        # Bound metric intermediates on large frames, especially CIEDE2000's float64 arrays.
        matches = np.empty(original.shape[:2], dtype=bool)
        for row in range(0, original.shape[0], 128):
            colors = to_color_space(original[row : row + 128])
            matches[row : row + 128] = color_distance(colors, reference) <= tolerance
        rgba[:, :, 3] = punch_color_mask(
            rgba[:, :, 3], matches, params.get("feather_radius", 3), params.get("min_hole_size", 5)
        )
        rgba[rgba[:, :, 3] == 0, :3] = 0
        success, encoded = cv2.imencode(".png", rgba)
        if not success:
            raise OSError(f"Cannot encode output frame: {frame.name}")
        encoded.tofile(output / frame.name)
        if progress_callback:
            progress_callback(index + 1, len(frames))
    return {"total": len(frames), "success": len(frames), "failed": 0}
