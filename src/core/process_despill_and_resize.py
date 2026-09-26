import os

import cv2
import numpy as np


def pixel_art_resize_fix(image_path, output_path, erode_output_path=None, target_width=512, erode_size=1):
    """
    Pixel-art pipeline: strong despill, edge erosion, optional intermediate output, nearest-neighbor resize.
    :param erode_output_path: if not None, save the despilled and eroded unscaled image here.
    """
    # 1. Read image while preserving alpha.
    img = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None:
        return False

    # Check channels.
    if img.shape[2] < 4:
        print(f"⚠️ 跳过无透明通道图片: {image_path}")
        return False

    b, g, r, a = cv2.split(img)

    # Step 1: strong despill.
    # Reduce green wherever the green channel exceeds red or blue.
    bg_limit = np.maximum(b, r)
    new_g = np.minimum(g, bg_limit)

    # Merge channels while preserving size; green halos become neutral halos.
    img_despilled = cv2.merge([b, new_g, r, a])

    # Step 2: edge erosion.
    # Remove the outermost opaque pixel layer.
    if erode_size > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
        a_eroded = cv2.erode(a, kernel, iterations=erode_size)
        img_despilled[:, :, 3] = a_eroded

    # Optional intermediate output before resizing.
    if erode_output_path:
        # Ensure the directory exists so the function can run independently.
        os.makedirs(os.path.dirname(erode_output_path), exist_ok=True)
        is_success, buffer = cv2.imencode(".png", img_despilled)
        if is_success:
            buffer.tofile(erode_output_path)

    # Step 3: nearest-neighbor resize.
    # Compute height.
    h, w = img.shape[:2]
    scale = target_width / w
    new_h = int(h * scale)

    # Use cv2.INTER_NEAREST.
    resized_img = cv2.resize(img_despilled, (target_width, new_h), interpolation=cv2.INTER_NEAREST)

    # Save final output.
    cv2.imencode(".png", resized_img)[1].tofile(output_path)
    return True


# Batch execution.
def batch_run(input_dir, output_dir, intermediate_dir):
    # Create required directories.
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    if not os.path.exists(intermediate_dir):
        os.makedirs(intermediate_dir)

    files = [f for f in os.listdir(input_dir) if f.lower().endswith(".png")]

    print("🚀 开始像素完美处理 (及保存中间文件)...")
    print(f"📂 中间结果(无缩放): {intermediate_dir}")
    print(f"📂 最终结果(已缩放): {output_dir}")

    for f in files:
        in_p = os.path.join(input_dir, f)
        out_p = os.path.join(output_dir, f)
        erode_p = os.path.join(intermediate_dir, f)  # Intermediate file path.

        try:
            # erode_size=1 removes the dirtiest outer edge layer.
            pixel_art_resize_fix(
                image_path=in_p,
                output_path=out_p,
                erode_output_path=erode_p,  # Pass intermediate path.
                target_width=512,
                erode_size=1,
            )
            print(f"处理: {f}", end="\r")
        except Exception as e:
            print(f"错误: {e}")

    print("\n✅ 完成！请检查两个输出目录。")


if __name__ == "__main__":
    # Input directory from the previous hole-punch background-removal step.
    INPUT = r"E:\python\game_assets_maker\project\test\output\02_no_bg"

    # Output 1: despill and erode only, preserving original size.
    OUTPUT_ERODE = r"E:\python\game_assets_maker\project\test\output\02_5_eroded_no_resize"

    # Output 2: final resized result.
    OUTPUT_FINAL = r"E:\python\game_assets_maker\project\test\output\03_pixel_perfect"

    batch_run(INPUT, OUTPUT_FINAL, OUTPUT_ERODE)
