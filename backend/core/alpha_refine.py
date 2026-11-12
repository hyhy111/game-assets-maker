"""Alpha-mask refinement and edge defringe for transparent frames (debug/tuning)."""

import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

DEFAULTS = {
    "alpha_contrast": 1.0,
    "alpha_threshold": 0,
    "defringe_enabled": False,
    "defringe_px": 2,
    "defringe_amount": 0.5,
    "min_foreground_area": 0,
    "fill_holes_max_size": 0,
}

# name -> (min, max, must_be_int)
_RANGES = {
    "alpha_contrast": (0.5, 3.0, False),
    "alpha_threshold": (0, 254, True),
    "defringe_px": (0, 20, True),
    "defringe_amount": (0.0, 1.0, False),
    "min_foreground_area": (0, 1_000_000, True),
    "fill_holes_max_size": (0, 1_000_000, True),
}


def validate_alpha_refine_params(params: dict) -> dict:
    """Return refinement settings with defaults filled and ranges enforced."""
    settings = dict(DEFAULTS)
    for name, (low, high, integer) in _RANGES.items():
        value = params.get(name, DEFAULTS[name])
        valid_type = type(value) is int if integer else type(value) in (int, float)
        if not valid_type or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"Invalid {name}. Expected a number from {low} to {high}.")
        settings[name] = value
    enabled = params.get("defringe_enabled", DEFAULTS["defringe_enabled"])
    if type(enabled) is not bool:
        raise ValueError("Invalid defringe_enabled. Expected a boolean.")
    settings["defringe_enabled"] = enabled
    return settings


def needs_refinement(settings: dict) -> bool:
    """Whether the settings change the frame at all (all-neutral means skip the pass)."""
    return bool(
        settings["alpha_contrast"] != 1.0
        or settings["alpha_threshold"]
        or settings["min_foreground_area"]
        or settings["fill_holes_max_size"]
        or (settings["defringe_enabled"] and settings["defringe_px"] and settings["defringe_amount"] > 0)
    )


def _fill_holes(alpha: np.ndarray, max_size: int) -> np.ndarray:
    """Fill interior zero-alpha holes no larger than max_size; border background stays untouched."""
    if not max_size:
        return alpha
    background = (alpha == 0).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(background, connectivity=4)
    filled = alpha.copy()
    for label in range(1, count):
        touches_border = (
            np.any(labels[0, :] == label)
            or np.any(labels[-1, :] == label)
            or np.any(labels[:, 0] == label)
            or np.any(labels[:, -1] == label)
        )
        if not touches_border and stats[label, cv2.CC_STAT_AREA] <= max_size:
            filled[labels == label] = 255
    return filled


def _remove_small_blobs(alpha: np.ndarray, min_area: int) -> np.ndarray:
    """Delete isolated foreground blobs smaller than min_area (mask noise cleanup)."""
    if not min_area:
        return alpha
    foreground = (alpha > 0).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(foreground, connectivity=8)
    result = alpha.copy()
    for label in range(1, count):
        if stats[label, cv2.CC_STAT_AREA] < min_area:
            result[labels == label] = 0
    return result


def _contrast_alpha(alpha: np.ndarray, contrast: float) -> np.ndarray:
    """Stretch alpha around the 0.5 midpoint; >1 hardens edges, <1 softens them."""
    if contrast == 1:
        return alpha
    adjusted = (alpha.astype(np.float32) / 255.0 - 0.5) * contrast + 0.5
    return np.clip(np.floor(adjusted * 255.0 + 0.5), 0, 255).astype(np.uint8)


def _threshold_alpha(alpha: np.ndarray, threshold: int) -> np.ndarray:
    """Cut semi-transparent residue below the threshold; 0 disables the cut."""
    if not threshold:
        return alpha
    return np.where(alpha < threshold, 0, alpha).astype(np.uint8)


def refine_alpha(alpha: np.ndarray, settings: dict | None = None, **overrides) -> np.ndarray:
    """Run the enabled alpha refinements in a fixed order: fill, prune, contrast, threshold."""
    merged = validate_alpha_refine_params({**(settings or {}), **overrides})
    result = _fill_holes(alpha, int(merged["fill_holes_max_size"]))
    result = _remove_small_blobs(result, int(merged["min_foreground_area"]))
    result = _contrast_alpha(result, merged["alpha_contrast"])
    result = _threshold_alpha(result, int(merged["alpha_threshold"]))
    return result


def defringe_rgba(rgba: np.ndarray, px: int, amount: float) -> np.ndarray:
    """Pull edge-band colors toward the estimated opaque interior color.

    BiRefNet-style cutouts show the visible fringe mostly in *opaque* halo pixels
    (alpha = 255 within a few px of the edge), where the RGB still holds background
    color. The band is therefore defined by distance to the nearest transparent
    pixel, not by alpha: opaque rim pixels are corrected most aggressively,
    semi-transparent pixels are blended by their background fraction, and the
    interior (farther than px from any edge) is never touched.
    """
    if not px or not amount:
        return rgba
    alpha = rgba[..., 3]
    solid = (alpha >= 250).astype(np.uint8)
    if not (alpha > 0).any() or not solid.any():
        return rgba
    rgb = rgba[..., :3]
    # Distance of each pixel to the nearest transparent region; semi/transparent
    # pixels sit on the source mask boundary, so their distance is 0 and any
    # positive-alpha pixel within px of an edge lands in the band.
    distance = cv2.distanceTransform(solid, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    interior = solid.astype(bool) & (distance > px)
    targets = (alpha > 0) & (distance <= px)
    if not targets.any():
        return rgba
    # Estimate the true foreground color under edge pixels by inpainting from
    # definitely-interior pixels only.
    mask = np.where(interior, 0, 255).astype(np.uint8)
    estimated_fg = cv2.inpaint(rgb, mask, max(int(px), 1), cv2.INPAINT_TELEA)
    weights = np.zeros(alpha.shape, dtype=np.float32)
    band = targets & solid.astype(bool)
    weights[band] = amount * (1.0 - distance[band] / (px + 1))
    semi = targets & ~solid.astype(bool)
    weights[semi] = amount * (1.0 - alpha[semi].astype(np.float32) / 255.0)
    weight = weights[targets][:, None]
    blended = np.rint(rgb[targets] * (1.0 - weight) + estimated_fg[targets] * weight)
    rgba[..., :3][targets] = blended.astype(np.uint8)
    return rgba


def refine_frame(path: Path, settings: dict | None = None, **overrides) -> None:
    """Apply alpha refinement and (if enabled) defringe to a transparent frame in place."""
    merged = validate_alpha_refine_params({**(settings or {}), **overrides})
    with Image.open(path) as source:
        rgba = np.asarray(source.convert("RGBA")).copy()
    rgba[..., 3] = refine_alpha(rgba[..., 3], merged)
    if merged["defringe_enabled"]:
        rgba = defringe_rgba(rgba, int(merged["defringe_px"]), float(merged["defringe_amount"]))
    Image.fromarray(rgba, "RGBA").save(path)
