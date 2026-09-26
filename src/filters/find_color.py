import os
from collections import Counter

from PIL import Image


def scan_edge_colors(folder_path):
    all_edge_colors = Counter()

    files = [f for f in os.listdir(folder_path) if f.lower().endswith(".png")]
    for filename in files:
        img = Image.open(os.path.join(folder_path, filename)).convert("RGBA")
        pixels = img.load()
        w, h = img.size
        img_edge_colors = []

        for y in range(h):
            for x in range(w):
                r, g, b, a = pixels[x, y]
                if a > 0:  # Found an opaque pixel.
                    # Check whether any neighbor is transparent.
                    for nx, ny in [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]:
                        if 0 <= nx < w and 0 <= ny < h and pixels[nx, ny][3] == 0:
                            hex_val = f"#{r:02x}{g:02x}{b:02x}"
                            img_edge_colors.append(hex_val)
                            break

        counts = Counter(img_edge_colors).most_common(3)
        print(f"图片 [{filename}] 的边缘主要颜色是: {counts}")
        all_edge_colors.update(img_edge_colors)

    print("-" * 30)
    print("所有图片汇总，出现频率最高的边缘颜色：", all_edge_colors.most_common(10))


# Run scan.
scan_edge_colors(r"E:\python\game_assets_maker\output\output_pixelart\output_witch_no_pixelart")
