"""
Sprite alignment utilities for pixel art sheets.
"""

import cv2
import numpy as np

from src.utils.logger import log_error, log_info


def align_sprites(
    image_path: str,
    output_path: str,
    *,
    rows: int = 2,
    cols: int = 2,
    align_h: bool = True,
    align_v: bool = True,
    use_padding: bool = True,
    padding_bottom: int = 10,
) -> bool:
    """
    Align each sprite sheet cell so character feet line up.

    Args:
        image_path: Path to input sprite sheet (must have alpha channel)
        output_path: Path to save aligned output
        rows: Number of rows in sprite sheet
        cols: Number of columns in sprite sheet
        padding_bottom: Padding at bottom for foot position

    Returns:
        True if successful, False otherwise
    """
    img_array = np.fromfile(image_path, dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_UNCHANGED)
    if img is None:
        log_error(f"找不到图片: {image_path}")
        return False

    h_total, w_total = img.shape[:2]

    cell_w = w_total // cols
    cell_h = h_total // rows

    log_info(f"全图尺寸: {w_total}x{h_total} | 单格尺寸: {cell_w}x{cell_h}")

    # Create a transparent output canvas.
    final_canvas = np.zeros((h_total, w_total, 4), dtype=np.uint8)

    for r in range(rows):
        for c in range(cols):
            x_start = c * cell_w
            y_start = r * cell_h
            cell_img = img[y_start : y_start + cell_h, x_start : x_start + cell_w]

            alpha = cell_img[:, :, 3]
            points = cv2.findNonZero(alpha)

            if points is not None:
                x, y, w, h = cv2.boundingRect(points)

                current_feet_x = x + w // 2
                current_feet_y = y + h

                target_feet_x = cell_w // 2
                target_feet_y = cell_h - (padding_bottom if use_padding else 0)

                shift_x = target_feet_x - current_feet_x if align_h else 0
                shift_y = target_feet_y - current_feet_y if align_v else 0

                transform = np.float32([[1, 0, shift_x], [0, 1, shift_y]])

                aligned_cell = cv2.warpAffine(
                    cell_img, transform, (cell_w, cell_h), borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0)
                )

                log_info(f"格子[{r},{c}]: 偏移 X={shift_x}, Y={shift_y}")
            else:
                aligned_cell = cell_img
                log_info(f"格子[{r},{c}]: 空白")

            final_canvas[y_start : y_start + cell_h, x_start : x_start + cell_w] = aligned_cell

    is_success, encoded_img = cv2.imencode(".png", final_canvas)
    if is_success:
        encoded_img.tofile(output_path)
        log_info(f"对齐完成，已保存至: {output_path}")
        return True

    return False


if __name__ == "__main__":
    align_sprites(
        r"image_pixel\output\knight_km_fixed_attack_v2.png",
        r"image_pixel\output_aligned\knight_aligned.png",
        rows=2,
        cols=2,
    )
