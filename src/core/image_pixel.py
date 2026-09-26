"""
K-Means color quantization for pixel art processing.
"""

import os

import cv2
import numpy as np

from src.utils.logger import log_error, log_info


def clean_pixel_art_kmeans_v2(image_path: str, output_path: str, *, k: int = 16, green_threshold: int = 60) -> bool:
    """
    Process one image with K-Means color quantization.

    Args:
        image_path: Path to input image
        output_path: Path to save output image
        k: Number of color clusters
        green_threshold: Distance threshold for green detection

    Returns:
        True if successful, False otherwise
    """
    img_array = np.fromfile(image_path, dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    if img is None:
        log_error(f"无法读取图片: {image_path}")
        return False

    data = img.reshape((-1, 3)).astype(np.float32)

    # K-Means clustering.
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.2)
    _, label, center = cv2.kmeans(data, k, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)

    center = np.uint8(center)

    # Detect the background color index.
    bg_indices: list[int] = []
    target_green = np.array([0, 255, 0])

    for i, color in enumerate(center):
        dist = np.linalg.norm(color - target_green)

        b, g, r = int(color[0]), int(color[1]), int(color[2])
        is_green_dominant = g > (r + 20) and g > (b + 20)

        if dist < green_threshold or is_green_dominant:
            bg_indices.append(i)

    # Rebuild the image with the alpha channel.
    labels_flat = label.flatten()
    alpha_channel = np.ones(labels_flat.shape, dtype=np.uint8) * 255

    mask = np.isin(labels_flat, bg_indices)
    alpha_channel[mask] = 0

    result_rgb = center[labels_flat].reshape(img.shape)

    b, g, r = cv2.split(result_rgb)
    alpha_reshaped = alpha_channel.reshape((img.shape[0], img.shape[1]))

    final_img = cv2.merge([b, g, r, alpha_reshaped])

    is_success, encoded_img = cv2.imencode(".png", final_img)
    if is_success:
        encoded_img.tofile(output_path)
    return True


def batch_process_images(input_dir: str, output_dir: str, *, k: int = 16, green_threshold: int = 60) -> tuple[int, int]:
    """
    Batch process images.

    Args:
        input_dir: Input directory path
        output_dir: Output directory path
        k: Number of color clusters
        green_threshold: Green detection threshold

    Returns:
        Tuple of (success_count, total_files)
    """
    os.makedirs(output_dir, exist_ok=True)
    log_info(f"创建输出目录: {output_dir}")

    valid_extensions = (".png", ".jpg", ".jpeg", ".bmp", ".tga")
    files = [f for f in os.listdir(input_dir) if f.lower().endswith(valid_extensions)]

    total_files = len(files)
    if total_files == 0:
        log_info(f"在 {input_dir} 中未找到图片文件")
        return 0, 0

    log_info(f"开始批量处理，共 {total_files} 张图片")
    log_info(f"参数: K={k}, Threshold={green_threshold}")

    success_count = 0
    for index, filename in enumerate(files):
        input_path = os.path.join(input_dir, filename)
        output_path = os.path.join(output_dir, filename)

        log_info(f"[{index + 1}/{total_files}] 处理中: {filename}")

        try:
            if clean_pixel_art_kmeans_v2(input_path, output_path, k=k, green_threshold=green_threshold):
                success_count += 1
        except OSError as e:
            log_error(f"处理 {filename} 时发生错误", e)

    log_info(f"批量处理完成！成功: {success_count} / {total_files}")
    log_info(f"结果保存在: {output_dir}")

    return success_count, total_files


if __name__ == "__main__":
    INPUT_FOLDER = r"E:\python\game_assets_maker\output\test_step1"
    OUTPUT_FOLDER = r"processed_images\test_step1"
    K_VALUE = 16
    GREEN_THRESHOLD = 130

    if not os.path.exists(INPUT_FOLDER):
        log_error(f"输入文件夹 '{INPUT_FOLDER}' 不存在")
    else:
        batch_process_images(INPUT_FOLDER, OUTPUT_FOLDER, k=K_VALUE, green_threshold=GREEN_THRESHOLD)
