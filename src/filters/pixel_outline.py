"""
Pixel art outline application utilities.
"""

import os

import cv2
import numpy as np

from src.utils.logger import log_error, log_info


def hex_to_bgr(hex_color: str) -> tuple[int, int, int]:
    """Convert a hex color to BGR format."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (4, 2, 0))


def apply_pixel_outline(
    image_path: str,
    output_path: str,
    *,
    outline_color: str = "#000000",
    extra_thickness: int = 1,
    replace_inner_edge: bool = True,
) -> bool:
    """
    Apply an outline to a pixel-art image.

    Args:
        image_path: Input image path.
        output_path: Output image path.
        outline_color: outline color in HEX format, such as "#FF0000".
        extra_thickness: number of added outer outline layers; 0 disables outer outline.
        replace_inner_edge: whether to replace original outer edge pixels with outline color.

    Returns:
        True if successful, False otherwise
    """
    img = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None:
        log_error(f"无法读取图片: {image_path}")
        return False

    # Ensure an alpha channel exists.
    if img.shape[2] < 4:
        log_info("图片没有透明通道，正在自动添加...")
        b, g, r = cv2.split(img)
        alpha = np.ones_like(b) * 255
        img = cv2.merge([b, g, r, alpha])

    h, w = img.shape[:2]
    b, g, r, a = cv2.split(img)
    target_bgr = hex_to_bgr(outline_color)

    # Generate solid core mask.
    _, solid_mask = cv2.threshold(a, 0, 255, cv2.THRESH_BINARY)

    # Morphology kernel: 3x3 rectangle for 8-neighbor connectivity.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))

    # Feature A: replace original edge pixels for inner outline.
    if replace_inner_edge:
        eroded_mask = cv2.erode(solid_mask, kernel, iterations=1)
        inner_edge_mask = cv2.bitwise_xor(solid_mask, eroded_mask)

        b[inner_edge_mask == 255] = target_bgr[0]
        g[inner_edge_mask == 255] = target_bgr[1]
        r[inner_edge_mask == 255] = target_bgr[2]

    # Feature B: add outer outline.
    if extra_thickness > 0:
        dilated_mask = cv2.dilate(solid_mask, kernel, iterations=extra_thickness)
        outer_outline_mask = cv2.bitwise_xor(dilated_mask, solid_mask)

        b[outer_outline_mask == 255] = target_bgr[0]
        g[outer_outline_mask == 255] = target_bgr[1]
        r[outer_outline_mask == 255] = target_bgr[2]

        a[outer_outline_mask == 255] = 255

    # Merge and save.
    final_img = cv2.merge([b, g, r, a])

    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    is_success, encoded_img = cv2.imencode(".png", final_img)
    if is_success:
        encoded_img.tofile(output_path)
        log_info(f"处理完成: {os.path.basename(output_path)}")
        log_info(f"颜色: {outline_color}, 外扩: {extra_thickness}px, 替换内边: {replace_inner_edge}")
        return True

    return False


def batch_apply_outline(
    input_dir: str,
    output_dir: str,
    *,
    outline_color: str = "#000000",
    extra_thickness: int = 1,
    replace_inner_edge: bool = True,
) -> tuple[int, int]:
    """
    Apply outline processing in batch.

    Args:
        input_dir: input directory.
        output_dir: output directory.
        outline_color: outline color.
        extra_thickness: outer outline thickness.
        replace_inner_edge: whether to replace inner edge pixels.

    Returns:
        Tuple of (success_count, total_files)
    """
    os.makedirs(output_dir, exist_ok=True)

    files = [f for f in os.listdir(input_dir) if f.lower().endswith(".png")]
    total_files = len(files)

    if total_files == 0:
        log_info(f"在 {input_dir} 中未找到图片文件")
        return 0, 0

    log_info(f"开始为 {total_files} 张图片添加描边...")

    success_count = 0
    for f in files:
        in_path = os.path.join(input_dir, f)
        out_path = os.path.join(output_dir, f)

        if apply_pixel_outline(
            in_path,
            out_path,
            outline_color=outline_color,
            extra_thickness=extra_thickness,
            replace_inner_edge=replace_inner_edge,
        ):
            success_count += 1

    log_info(f"批量描边完成！成功: {success_count} / {total_files}")
    return success_count, total_files


if __name__ == "__main__":
    INPUT_DIR = r"E:\python\game_assets_maker\project\old_boss_rbg\output\03_pixelate"
    OUTPUT_DIR = r"E:\python\game_assets_maker\project\old_boss_rbg\output\04_outlined"

    TARGET_COLOR = "#000000"
    ADD_LAYERS = 1
    REPLACE_INNER = True

    if not os.path.exists(INPUT_DIR):
        log_error("输入目录不存在")
    else:
        batch_apply_outline(
            INPUT_DIR,
            OUTPUT_DIR,
            outline_color=TARGET_COLOR,
            extra_thickness=ADD_LAYERS,
            replace_inner_edge=REPLACE_INNER,
        )
