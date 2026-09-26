"""
Edge cleaning utilities for pixel art - removes edge artifacts and noise.
"""

import math
import os
import sys
from typing import Any

from PIL import Image

# Enable Windows terminal color support
if os.name == "nt":
    os.system("")

# Type definitions
RGBA = tuple[int, int, int, int]
ColorGroup = dict[str, Any]


class EdgeCleaner:
    """Clean edge artifacts from pixel art images."""

    def __init__(self, image_path: str, tolerance: int = 30) -> None:
        """
        Initialize the edge cleaner.

        Args:
            image_path: Path to the image file
            tolerance: Color distance tolerance for grouping similar colors
        """
        self.image_path = image_path
        with Image.open(image_path) as img:
            self.img = img.convert("RGBA")
        self.width, self.height = self.img.size
        self.pixels = self.img.load()
        self.tolerance = tolerance
        self.edge_raw_counts: dict[RGBA, int] = {}
        self.color_groups: list[ColorGroup] = []

    def _is_edge_pixel(self, x: int, y: int) -> bool:
        """Return whether a pixel is on an edge touching transparency."""
        if self.pixels[x, y][3] == 0:
            return False

        directions = [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]
        for nx, ny in directions:
            if 0 <= nx < self.width and 0 <= ny < self.height:
                if self.pixels[nx, ny][3] == 0:
                    return True
            else:
                return True
        return False

    def analyze(self) -> None:
        """Run scanning and clustering.。"""
        print(f"[*] 正在分析图片边缘: {os.path.basename(self.image_path)} ...")
        self.scan_image()
        self.cluster_colors()

    def scan_image(self) -> None:
        """Scan edge pixels.。"""
        for y in range(self.height):
            for x in range(self.width):
                if self._is_edge_pixel(x, y):
                    c = self.pixels[x, y]
                    self.edge_raw_counts[c] = self.edge_raw_counts.get(c, 0) + 1

    def cluster_colors(self) -> None:
        """Cluster similar colors into groups.。"""
        sorted_colors = sorted(self.edge_raw_counts.items(), key=lambda item: item[1], reverse=True)

        self.color_groups = []
        for color, count in sorted_colors:
            added_to_group = False
            for group in self.color_groups:
                dist = self._color_distance(color, group["main"])
                if dist < self.tolerance:
                    group["members"].append(color)
                    group["count"] += count
                    added_to_group = True
                    break

            if not added_to_group:
                self.color_groups.append({"main": color, "members": [color], "count": count})

    def _color_distance(self, c1: RGBA, c2: RGBA) -> float:
        """Compute RGBA Euclidean distance.。"""
        return math.sqrt((c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2 + (c1[2] - c2[2]) ** 2 + (c1[3] - c2[3]) ** 2)

    def _get_ansi_color_block(self, r: int, g: int, b: int, a: int) -> str:
        """Generate a true-color terminal preview block.。"""
        if a == 0:
            return "[TRAN]"
        return f"\033[48;2;{r};{g};{b}m      \033[0m"

    def print_menu(self) -> None:
        """Print menu with color previews.。"""
        print("\n" + "=" * 80)
        print(f"{'ID':<4} | {'预览':<8} | {'样本RGBA值':<20} | {'像素数':<8} | {'推测说明'}")
        print("-" * 80)

        total_pixels = self.width * self.height

        for i, group in enumerate(self.color_groups):
            r, g, b, a = group["main"]
            preview = self._get_ansi_color_block(r, g, b, a)
            rgba_str = f"{r},{g},{b},{a}"

            notes: list[str] = []
            if a < 255:
                notes.append("半透明")

            ratio = group["count"] / total_pixels
            if ratio > 0.1:
                notes.append("主体")
            elif group["count"] < 20:
                notes.append("噪点")

            note_str = ", ".join(notes)

            print(f"{i:<4} | {preview:<8} | {rgba_str:<20} | {group['count']:<8} | {note_str}")
        print("=" * 80)

    def get_sorted_groups(self) -> list[ColorGroup]:
        """Return color groups sorted by pixel count ascending.。"""
        return sorted(self.color_groups, key=lambda g: g["count"])

    def process_cleaning(
        self, group_ids: list[int] | None = None, target_colors: set[RGBA] | None = None, max_loops: int = 5
    ) -> int:
        """
        Run edge cleanup.

        Args:
            group_ids: color group ids to remove.
            target_colors: exact color values to remove.
            max_loops: maximum iteration count.

        Returns:
            Total number of removed pixels.
        """
        final_target_colors: set[RGBA] = set()

        if target_colors:
            final_target_colors.update(target_colors)

        if group_ids:
            for gid in group_ids:
                if 0 <= gid < len(self.color_groups):
                    final_target_colors.update(self.color_groups[gid]["members"])

        if not final_target_colors:
            return 0

        total_removed = 0

        for _loop in range(max_loops):
            pixels_to_remove: list[tuple[int, int]] = []

            for y in range(self.height):
                for x in range(self.width):
                    if self._is_edge_pixel(x, y) and self.pixels[x, y] in final_target_colors:
                        pixels_to_remove.append((x, y))

            if not pixels_to_remove:
                break

            for x, y in pixels_to_remove:
                self.pixels[x, y] = (0, 0, 0, 0)

            count = len(pixels_to_remove)
            total_removed += count

        return total_removed

    def save_image(self, output_path: str) -> None:
        """Save the processed image."""
        self.img.save(output_path)
        print(f"[√] 结果已保存至: {output_path}")


if __name__ == "__main__":
    INPUT_PATH = r"E:\\python\\game_assets_maker\\project\\witch\\output\\03_pixelate\\px_0000.png"
    OUTPUT_PATH = r"witch_fixed.png"
    TOLERANCE = 30

    if not os.path.exists(INPUT_PATH):
        print(f"错误: 找不到文件 {INPUT_PATH}")
        print(">>> 生成测试图片 demo.png 以供测试...")
        img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        for x in range(30, 70):
            for y in range(30, 70):
                img.putpixel((x, y), (50, 50, 50, 255))
        for x in range(29, 71):
            img.putpixel((x, 29), (200, 200, 200, 100))
            img.putpixel((x, 70), (200, 200, 200, 100))
        img.save("demo.png")
        INPUT_PATH = "demo.png"
        OUTPUT_PATH = "demo_fixed.png"

    cleaner = EdgeCleaner(INPUT_PATH, tolerance=TOLERANCE)
    cleaner.analyze()

    if not cleaner.color_groups:
        print("未检测到任何边缘颜色。")
        sys.exit()

    cleaner.print_menu()

    print("\n请输入要删除的色系 ID (例如: 1, 3)：")
    user_input = input(">> ").strip()

    if user_input:
        try:
            selected_ids = [int(x.strip()) for x in user_input.replace("，", ",").split(",") if x.strip().isdigit()]

            cleaner.process_cleaning(selected_ids, max_loops=5)
            cleaner.save_image(OUTPUT_PATH)

        except ValueError as e:
            print(f"输入格式错误: {e}")
    else:
        print("取消操作。")
