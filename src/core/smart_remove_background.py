"""
Smart background removal using flood-fill algorithm.
"""

import cv2
import numpy as np

from src.utils.logger import log_info

# Algorithm switch: 'legacy' uses flood-fill, 'rembg' uses rembg+u2net.
USE_REM_BG_ALGORITHM = "rembg"  # Options: 'legacy' or 'rembg'.


def smart_remove_background(
    image_path: str,
    output_path: str,
    *,
    min_hole_size: int = 1000,
    diff_h_bg: int = 20,
    diff_sv_bg: int = 100,
    diff_h_hole: int = 10,
    diff_sv_hole: int = 40,
    erode_size: int = 1,
    enabled: bool = True,
) -> bool:
    """
    Stepwise background removal algorithm:
    1. External background: use loose thresholds plus FloodFill for clean edges.
    2. Internal holes: use strict thresholds to avoid damaging similar subject colors.

    Args:
        image_path: Path to input image
        output_path: Path to save output image
        min_hole_size: Minimum hole size to remove
        diff_h_bg: Hue tolerance for background (loose)
        diff_sv_bg: SV tolerance for background (loose)
        diff_h_hole: Hue tolerance for holes (strict)
        diff_sv_hole: SV tolerance for holes (strict)
        erode_size: Erosion iterations for edge optimization
        enabled: Whether to process the image

    Returns:
        True if successful, False otherwise
    """
    if not enabled:
        return False

    # 1. Read image.
    img_array = np.fromfile(image_path, dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    if img is None:
        return False

    h, w = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # -------------------------------------------------
    # Step A: compute background reference color from corner samples.
    # -------------------------------------------------
    corners = [(5, 5), (5, w - 5), (h - 5, 5), (h - 5, w - 5)]
    bg_colors = []
    for y, x in corners:
        y = max(0, min(y, h - 1))
        x = max(0, min(x, w - 1))
        bg_colors.append(hsv[y, x])

    bg_mean = np.mean(bg_colors, axis=0)
    bg_h, bg_s, bg_v = bg_mean

    # -------------------------------------------------
    # Step B: process external background with loose thresholds.
    # -------------------------------------------------
    lower_bg = np.array([max(0, bg_h - diff_h_bg), max(0, bg_s - diff_sv_bg), max(0, bg_v - diff_sv_bg)])
    upper_bg = np.array([min(180, bg_h + diff_h_bg), min(255, bg_s + diff_sv_bg), min(255, bg_v + diff_sv_bg)])
    mask_bg_loose = cv2.inRange(hsv, lower_bg, upper_bg)

    # Use FloodFill to identify the external area.
    h_mask, w_mask = h + 2, w + 2
    mask_flood = np.zeros((h_mask, w_mask), np.uint8)

    flood_input = mask_bg_loose.copy()

    flood_points = [(0, 0), (0, w - 1), (h - 1, 0), (h - 1, w - 1)]
    for y, x in flood_points:
        if flood_input[y, x] == 255:
            cv2.floodFill(flood_input, mask_flood, (x, y), 0, flags=4 | cv2.FLOODFILL_FIXED_RANGE | (255 << 8))

    is_body = mask_flood[1:-1, 1:-1] == 0

    # -------------------------------------------------
    # Step C: process internal holes with strict thresholds limited to the subject.
    # -------------------------------------------------
    lower_hole = np.array([max(0, bg_h - diff_h_hole), max(0, bg_s - diff_sv_hole), max(0, bg_v - diff_sv_hole)])
    upper_hole = np.array([min(180, bg_h + diff_h_hole), min(255, bg_s + diff_sv_hole), min(255, bg_v + diff_sv_hole)])
    mask_hole_strict = cv2.inRange(hsv, lower_hole, upper_hole)

    potential_holes = (mask_hole_strict == 255) & is_body

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(potential_holes.astype(np.uint8), connectivity=8)

    # -------------------------------------------------
    # Step D: merge results.
    # -------------------------------------------------
    final_alpha = np.zeros((h, w), dtype=np.uint8)
    final_alpha[is_body] = 255

    hole_count = 0
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if area > min_hole_size:
            final_alpha[labels == i] = 0
            hole_count += 1

    log_info(f"挖孔统计: 发现 {hole_count} 个孔洞 (阈值: H±{diff_h_hole})")

    # -------------------------------------------------
    # Step E: edge cleanup.
    # -------------------------------------------------
    if erode_size > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
        final_alpha = cv2.erode(final_alpha, kernel, iterations=erode_size)

    # Save output.
    b, g, r = cv2.split(img)
    # Clear RGB in transparent areas to avoid interpolation artifacts.
    b[final_alpha == 0] = 0
    g[final_alpha == 0] = 0
    r[final_alpha == 0] = 0
    final_img = cv2.merge([b, g, r, final_alpha])
    cv2.imencode(".png", final_img)[1].tofile(output_path)
    return True


def smart_remove_background_rembg(
    image_path: str,
    output_path: str,
    *,
    min_hole_size: int = 1000,
    diff_h_bg: int = 20,
    diff_sv_bg: int = 100,
    diff_h_hole: int = 10,
    diff_sv_hole: int = 40,
    erode_size: int = 1,
    enabled: bool = True,
    core_threshold: int = 230,
    hole_edge_margin: int = 5,
) -> bool:
    """
    Use the rembg u2net model for background removal plus internal hole punching.

    Algorithm flow:
    1. Generate the subject mask with rembg u2net.
    2. Sample background color from the original image corners.
    3. Punch holes inside the subject core area (mask >= core_threshold).
    4. Preserve feathered edges where mask < core_threshold.

    Args:
        image_path: Path to input image
        output_path: Path to save output image
        min_hole_size: Minimum hole size to remove
        diff_h_bg: Not used for rembg (kept for API compatibility)
        diff_sv_bg: Not used for rembg (kept for API compatibility)
        diff_h_hole: Hue tolerance for holes (strict)
        diff_sv_hole: SV tolerance for holes (strict)
        erode_size: Erosion iterations for edge optimization
        enabled: Whether to process the image
        core_threshold: Mask threshold for core area (default 200)
        hole_edge_margin: Edge margin to protect from hole punching (default 5)

    Returns:
        True if successful, False otherwise
    """
    if not enabled:
        return False

    try:
        from rembg import remove
        from backend.core.smart_remove_background import get_rembg_session
    except ImportError:
        log_info("rembg not installed, falling back to legacy algorithm")
        return False

    # 1. Read image.
    img_array = np.fromfile(image_path, dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    if img is None:
        return False

    h, w = img.shape[:2]

    # 2. Generate mask with rembg u2net.
    try:
        session = get_rembg_session("u2net")
        # rembg expects a PIL image, so convert OpenCV BGR to RGB.
        from PIL import Image as PILImage

        pil_img = PILImage.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        # Generate image with alpha channel.
        output_pil = remove(pil_img, session=session)
        # Convert back to OpenCV RGBA format.
        output_rgba = cv2.cvtColor(np.array(output_pil), cv2.COLOR_RGBA2BGRA)
        # Extract mask.
        mask = output_rgba[:, :, 3]
    except Exception as e:
        log_info(f"rembg processing failed: {e}")
        return False

    # 3. Compute background reference color from corner samples.
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    corners = [(5, 5), (5, w - 5), (h - 5, 5), (h - 5, w - 5)]
    bg_colors = []
    for y, x in corners:
        y = max(0, min(y, h - 1))
        x = max(0, min(x, w - 1))
        bg_colors.append(hsv[y, x])

    bg_mean = np.mean(bg_colors, axis=0)
    bg_h, bg_s, bg_v = bg_mean

    # 4. Determine subject core area (mask >= core_threshold).
    core_mask = (mask >= core_threshold).astype(np.uint8) * 255

    # 5. Edge protection: erode the subject core to avoid punching edge pixels.
    if hole_edge_margin > 0:
        kernel = np.ones((hole_edge_margin, hole_edge_margin), np.uint8)
        core_mask_eroded = cv2.erode(core_mask, kernel, iterations=1)
    else:
        core_mask_eroded = core_mask

    # 6. Find background-like pixels inside the subject core for hole punching.
    lower_hole = np.array([max(0, bg_h - diff_h_hole), max(0, bg_s - diff_sv_hole), max(0, bg_v - diff_sv_hole)])
    upper_hole = np.array([min(180, bg_h + diff_h_hole), min(255, bg_s + diff_sv_hole), min(255, bg_v + diff_sv_hole)])
    mask_hole_strict = cv2.inRange(hsv, lower_hole, upper_hole)

    # Keep only holes inside the core area.
    potential_holes = (mask_hole_strict == 255) & (core_mask_eroded == 255)

    # 7. Run connected-component analysis and keep holes larger than min_hole_size.
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(potential_holes.astype(np.uint8), connectivity=8)

    # 8. Merge rembg mask with punched holes.
    final_alpha = mask.copy()

    hole_count = 0
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if area > min_hole_size:
            final_alpha[labels == i] = 0
            hole_count += 1

    log_info(f"rembg挖孔统计: 发现 {hole_count} 个孔洞 (阈值: H±{diff_h_hole}, SV±{diff_sv_hole})")

    # 9. Edge cleanup.
    if erode_size > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
        final_alpha = cv2.erode(final_alpha, kernel, iterations=erode_size)

    # 10. Use rembg RGBA output and apply the final alpha.
    b, g, r, rembg_alpha = cv2.split(output_rgba)

    # 11. Clear RGB in transparent areas.
    b[final_alpha == 0] = 0
    g[final_alpha == 0] = 0
    r[final_alpha == 0] = 0

    # Compose final BGRA output.
    final_img = cv2.merge([b, g, r, final_alpha])
    cv2.imencode(".png", final_img)[1].tofile(output_path)
    return True
