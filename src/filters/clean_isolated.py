import math
import os
import sys

from PIL import Image

# Try to enable color support in Windows terminals.
if os.name == "nt":
    os.system("")


class EdgeCleaner:
    def __init__(self, image_path, tolerance=30):
        self.image_path = image_path
        with Image.open(image_path) as img:
            self.img = img.convert("RGBA")
        self.width, self.height = self.img.size
        self.pixels = self.img.load()
        self.tolerance = tolerance
        self.edge_raw_counts = {}  # {(r,g,b,a): count}
        self.color_groups = []  # Clustered results.

    def _is_edge_pixel(self, x, y):
        """Return whether a pixel is on an edge touching transparency."""
        # Fully transparent pixels do not need processing.
        if self.pixels[x, y][3] == 0:
            return False

        # Check the four orthogonal neighbors.
        # A transparent neighbor or canvas boundary makes this an edge pixel.
        directions = [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]
        for nx, ny in directions:
            if 0 <= nx < self.width and 0 <= ny < self.height:
                if self.pixels[nx, ny][3] == 0:  # Transparent neighbor found.
                    return True
            else:
                return True  # Canvas boundary.
        return False

    def analyze(self):
        """Run scanning and clustering."""
        print(f"[*] 正在分析图片边缘: {os.path.basename(self.image_path)} ...")
        self.scan_image()
        self.cluster_colors()

    def scan_image(self):
        """Scan edge pixels."""
        # 1. Scan edge pixels.
        for y in range(self.height):
            for x in range(self.width):
                if self._is_edge_pixel(x, y):
                    c = self.pixels[x, y]
                    self.edge_raw_counts[c] = self.edge_raw_counts.get(c, 0) + 1

    def cluster_colors(self):
        """Cluster similar colors into groups."""
        # 2. Cluster similar colors into groups.
        # Sort by frequency and keep dominant colors first.
        sorted_colors = sorted(self.edge_raw_counts.items(), key=lambda item: item[1], reverse=True)

        self.color_groups = []
        for color, count in sorted_colors:
            added_to_group = False
            for group in self.color_groups:
                # Compute distance to the group representative color.
                dist = self._color_distance(color, group["main"])
                if dist < self.tolerance:
                    group["members"].append(color)
                    group["count"] += count
                    added_to_group = True
                    break

            if not added_to_group:
                self.color_groups.append(
                    {
                        "main": color,  # Representative color.
                        "members": [color],  # Member colors.
                        "count": count,
                    }
                )

    def _color_distance(self, c1, c2):
        """Compute RGBA Euclidean distance."""
        return math.sqrt((c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2 + (c1[2] - c2[2]) ** 2 + (c1[3] - c2[3]) ** 2)

    def _get_ansi_color_block(self, r, g, b, a):
        """Generate a true-color terminal preview block."""
        # Show a marker for fully transparent colors.
        if a == 0:
            return "[TRAN]"
        # ANSI background color sequence: \033[48;2;R;G;Bm
        return f"\033[48;2;{r};{g};{b}m      \033[0m"

    def print_menu(self):
        """Print menu with color previews."""
        print("\n" + "=" * 80)
        print(f"{'ID':<4} | {'预览':<8} | {'样本RGBA值':<20} | {'像素数':<8} | {'推测说明'}")
        print("-" * 80)

        total_pixels = self.width * self.height

        for i, group in enumerate(self.color_groups):
            r, g, b, a = group["main"]
            preview = self._get_ansi_color_block(r, g, b, a)
            rgba_str = f"{r},{g},{b},{a}"

            # Infer likely meaning.
            notes = []
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

    def get_sorted_groups(self):
        """Return color groups sorted by pixel count ascending."""
        return sorted(self.color_groups, key=lambda g: g["count"])

    def process_cleaning(self, group_ids=None, target_colors=None, max_loops=5):
        """Run cleanup."""
        # Collect exact color values to remove.
        final_target_colors = set()

        if target_colors:
            final_target_colors.update(target_colors)

        if group_ids:
            for gid in group_ids:
                if 0 <= gid < len(self.color_groups):
                    final_target_colors.update(self.color_groups[gid]["members"])

        if not final_target_colors:
            # print("[!] No valid color group selected, skipping.")
            return 0

        # print(f"[*] Starting cleanup for {len(final_target_colors)} color variants, max {max_loops} loops...")

        total_removed = 0

        # Iteratively remove newly exposed edge pixels.
        for _loop in range(max_loops):
            pixels_to_remove = []

            # Rescan because edge state changes after each removal.
            for y in range(self.height):
                for x in range(self.width):
                    # Remove only edge pixels in the selected color set.
                    if self._is_edge_pixel(x, y) and self.pixels[x, y] in final_target_colors:
                        pixels_to_remove.append((x, y))

            if not pixels_to_remove:
                break

            # Apply removals.
            for x, y in pixels_to_remove:
                self.pixels[x, y] = (0, 0, 0, 0)

            count = len(pixels_to_remove)
            total_removed += count
            # print(f"    - Loop {loop + 1}: removed {count} pixels")

        # print(f"[√] Cleanup finished, removed {total_removed} pixels.")
        return total_removed

    def save_image(self, output_path):
        self.img.save(output_path)
        print(f"[√] 结果已保存至: {output_path}")


# Automated cleanup API.
def auto_clean_edges(image_path, output_path, tolerance=30):
    """
    Automatically clean edge noise without user interaction.
    Identify and remove edge noise based on color frequency.

    Cleanup strategy:
    1. Analyze all edge color variants.
    2. Sort by pixel count ascending.
    3. Treat small pixel groups (<20 pixels) as noise.
    4. Remove the smallest color group if no obvious noise group exists.
    5. Run iterative cleanup for up to 3 loops to handle newly exposed edges.

    :param image_path: Input image path.
    :param output_path: Output image path.
    :param tolerance: color clustering tolerance, default 30.
    :return: number of cleaned pixels; 0 means no cleanup needed.
    """
    try:
        cleaner = EdgeCleaner(image_path, tolerance=tolerance)
        cleaner.analyze()

        if not cleaner.color_groups:
            print(f"⚠️ 无边缘像素: {os.path.basename(image_path)}")
            # Save the original image even when cleanup is unnecessary.
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            cleaner.img.save(output_path)
            return 0

        # Select color groups to clean based on frequency and size.
        groups_to_remove = []

        # Get sorted color groups.
        sorted_groups = cleaner.get_sorted_groups()

        # Strategy: remove small pixel groups that are likely noise.
        for group in sorted_groups:
            # Small color groups are likely noise.
            if group["count"] < 20:  # Fewer than 20 pixels.
                group_id = cleaner.color_groups.index(group)
                groups_to_remove.append(group_id)

        # If no small groups exist, remove the smallest medium-sized group.
        if not groups_to_remove and len(sorted_groups) > 1:
            # Keep the largest group, usually the subject, and remove the smallest.
            groups_to_remove.append(0)  # Remove the first and smallest group.

        if groups_to_remove:
            removed_count = cleaner.process_cleaning(group_ids=groups_to_remove, max_loops=3)
            cleaner.save_image(output_path)
            return removed_count
        else:
            print(f"✨ 无需清理: {os.path.basename(image_path)}")
            # Save original image even when cleanup is unnecessary.
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            cleaner.img.save(output_path)
            return 0

    except Exception as e:
        print(f"❌ 清理失败 {os.path.basename(image_path)}: {str(e)}")
        # Try copying the original file on failure.
        try:
            import shutil

            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            shutil.copy2(image_path, output_path)
        except Exception:
            pass
        return 0


# Manual entry point.
if __name__ == "__main__":
    # Configuration.
    # Replace with your image path.
    INPUT_PATH = r"E:\\python\\game_assets_maker\\project\\witch\\output\\03_pixelate\\px_0000.png"
    OUTPUT_PATH = r"witch_fixed.png"
    TOLERANCE = 30  # Color grouping tolerance; smaller values create finer groups.

    # 1. Check file.
    if not os.path.exists(INPUT_PATH):
        print(f"错误: 找不到文件 {INPUT_PATH}")
        # Generate a demo image for demonstration.
        print(">>> 生成测试图片 demo.png 以供测试...")
        img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        for x in range(30, 70):
            for y in range(30, 70):
                img.putpixel((x, y), (50, 50, 50, 255))  # Dark gray subject.
        # Add a light fringe around it.
        for x in range(29, 71):
            img.putpixel((x, 29), (200, 200, 200, 100))
            img.putpixel((x, 70), (200, 200, 200, 100))
        img.save("demo.png")
        INPUT_PATH = "demo.png"
        OUTPUT_PATH = "demo_fixed.png"

    # 2. Initialize and analyze.
    cleaner = EdgeCleaner(INPUT_PATH, tolerance=TOLERANCE)
    cleaner.analyze()

    # 3. User interaction.
    if not cleaner.color_groups:
        print("未检测到任何边缘颜色。")
        sys.exit()

    cleaner.print_menu()

    print("\n请输入要删除的色系 ID (例如: 1, 3)：")
    user_input = input(">> ").strip()

    if user_input:
        try:
            # Parse input like "1, 2" into [1, 2].
            selected_ids = [int(x.strip()) for x in user_input.replace("，", ",").split(",") if x.strip().isdigit()]

            # 4. Run cleanup.
            cleaner.process_cleaning(selected_ids, max_loops=5)

            # 5. Save.
            cleaner.save_image(OUTPUT_PATH)

        except Exception as e:
            print(f"发生错误: {e}")
    else:
        print("取消操作。")
