"""Shrink and feather a transparent frame's visible contour."""

import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def validate_edge_shrink_params(params: dict) -> tuple[int, float]:
    shrink = params.get("edge_shrink_px", 0)
    feather = params.get("edge_feather_px", 0)
    if type(shrink) is not int or not 0 <= shrink <= 100:
        raise ValueError("Invalid edge shrink amount. Expected a whole number from 0 to 100.")
    if type(feather) not in (int, float) or not math.isfinite(feather) or not 0 <= feather <= 100:
        raise ValueError("Invalid edge feather amount. Expected a number from 0 to 100.")
    return shrink, feather


def shrink_alpha(alpha: np.ndarray, shrink: int, feather: float) -> np.ndarray:
    if not (shrink or feather):
        return alpha.copy()
    foreground = np.pad((alpha > 0).astype(np.uint8), 1)
    distance = cv2.distanceTransform(foreground, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)[1:-1, 1:-1]
    remaining = distance - shrink
    if not feather:
        return np.where(remaining > 0, alpha, 0).astype(np.uint8)
    return np.floor(alpha * np.clip(remaining / feather, 0, 1) + 0.5).astype(np.uint8)


def shrink_frame(path: Path, shrink: int, feather: float) -> None:
    with Image.open(path) as source:
        frame = source.convert("RGBA")
    alpha = np.asarray(frame.getchannel("A"))
    frame.putalpha(Image.fromarray(shrink_alpha(alpha, shrink, feather)))
    frame.save(path)
