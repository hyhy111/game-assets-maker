import os
import re
import shutil

from src.core import naming_utils, pixel_processing_suite, video_utils

try:
    from src.core.image_pixel import clean_pixel_art_kmeans_v2
except ImportError:
    clean_pixel_art_kmeans_v2 = None

try:
    from src.core.image_aligning import align_sprites
except ImportError:
    align_sprites = None


class BatchProcessor:
    def __init__(self, output_base_dir="./output", cache_base_dir="./cache"):
        self.output_base_dir = output_base_dir
        self.cache_base_dir = cache_base_dir
        os.makedirs(self.output_base_dir, exist_ok=True)
        os.makedirs(self.cache_base_dir, exist_ok=True)

    def _get_video_name(self, video_path):
        return os.path.splitext(os.path.basename(video_path))[0]

    def process_video_to_frames(self, video_path):
        video_name = self._get_video_name(video_path)

        # Cache directory for raw frames
        raw_frames_cache_dir = os.path.join(self.cache_base_dir, naming_utils.get_cache_dir_name(video_name, "frames"))
        os.makedirs(raw_frames_cache_dir, exist_ok=True)

        # Output directory for raw frames
        raw_frames_output_dir = os.path.join(
            self.output_base_dir, naming_utils.get_output_dir_name(video_name, "frames")
        )
        os.makedirs(raw_frames_output_dir, exist_ok=True)

        print(f"Processing video {video_name} to frames...")
        frames, _ = video_utils.process_video_to_cache(
            video_path, self.cache_base_dir, progress_callback=lambda p, m: print(f"[Video2Frames] {m}")
        )

        # Export selected frames to the new output directory
        # For batch processing, we export all frames from cache to output
        saved_count, final_output_dir = video_utils.export_frames_step1(
            frames,
            self.output_base_dir,
            video_name,
            0,
            len(frames) - 1,
            1,
            progress_callback=lambda p, m: print(f"[ExportFrames] {m}"),
        )
        print(f"Exported {saved_count} raw frames to {final_output_dir}")
        return final_output_dir

    def remove_background(self, input_dir, k_val, threshold, enable_align, padding):
        input_name = os.path.basename(os.path.normpath(input_dir))
        video_name = naming_utils.extract_video_name_from_output_dir(input_name)
        if not video_name:
            video_name = "default_video"

        output_dir = os.path.join(self.output_base_dir, naming_utils.get_output_dir_name(video_name, "no_bg"))
        os.makedirs(output_dir, exist_ok=True)

        print(f"Removing background for frames in {input_dir}...")
        files = sorted([f for f in os.listdir(input_dir) if f.lower().endswith((".png", ".jpg", ".jpeg"))])
        total = len(files)

        for i, filename in enumerate(files):
            in_path = os.path.join(input_dir, filename)
            num_match = re.search(r"(\d+)", filename)
            frame_num = int(num_match.group(1)) if num_match else i + 1

            out_filename = naming_utils.get_frame_filename("mask", frame_num)
            out_path = os.path.join(output_dir, out_filename)

            print(f"[RemoveBG] Processing [{i + 1}/{total}]: {filename}")
            if clean_pixel_art_kmeans_v2:
                res = clean_pixel_art_kmeans_v2(in_path, out_path, k_val, threshold)
                if res and enable_align and align_sprites:
                    try:
                        align_sprites(out_path, out_path, rows=1, cols=1, padding_bottom=padding)
                    except Exception as err:
                        print(f"Align error: {err}")
            else:
                print("Warning: clean_pixel_art_kmeans_v2 not available. Skipping background removal.")
                shutil.copy2(in_path, out_path)  # Copy if no processing
        print(f"Background removal complete. Output in {output_dir}")
        return output_dir

    def process_pixel_art(self, input_dir, target_sizes, do_crop, do_clean):
        input_name = os.path.basename(os.path.normpath(input_dir))
        video_name = naming_utils.extract_video_name_from_output_dir(input_name)
        if not video_name:
            video_name = "default_video"

        # Cache directory for pixel art
        pixel_art_cache_root = os.path.join(
            self.cache_base_dir, naming_utils.get_cache_dir_name(video_name, "pixelart")
        )
        os.makedirs(pixel_art_cache_root, exist_ok=True)

        # Output directory for final pixel art
        final_pixel_art_output_dir = os.path.join(
            self.output_base_dir, naming_utils.get_output_dir_name(video_name, "pixelart")
        )
        os.makedirs(final_pixel_art_output_dir, exist_ok=True)

        print(f"Processing pixel art for frames in {input_dir}...")
        files = sorted([f for f in os.listdir(input_dir) if f.lower().endswith((".png", ".jpg", ".jpeg"))])
        total = len(files)

        if do_clean:
            alpha_thresh = 160
            min_neighbors = 6
            min_island = 15
        else:
            alpha_thresh = 1  # Keep almost everything
            min_neighbors = 0
            min_island = 0

        for i, filename in enumerate(files):
            in_path = os.path.join(input_dir, filename)
            num_match = re.search(r"(\d+)", filename)
            frame_num = int(num_match.group(1)) if num_match else i + 1

            print(f"[PixelArt] Processing [{i + 1}/{total}]: {filename}")
            pixel_processing_suite.pixel_engine_processor(
                in_path,
                pixel_art_cache_root,
                target_sizes,
                do_crop=do_crop,
                alpha_threshold=alpha_thresh,
                min_neighbors=min_neighbors,
                min_island_size=min_island,
                frame_num=frame_num,
            )
        print(f"Pixel art processing complete. Cached in {pixel_art_cache_root}")

        # Copy from cache to final output, renaming files
        for size in target_sizes:
            cache_subdir = os.path.join(pixel_art_cache_root, naming_utils.get_pixelart_cache_subdir_name(size))
            if os.path.exists(cache_subdir):
                output_subdir = os.path.join(
                    final_pixel_art_output_dir, naming_utils.get_pixelart_cache_subdir_name(size)
                )
                os.makedirs(output_subdir, exist_ok=True)

                px_files = sorted(os.listdir(cache_subdir))
                for i, px_file in enumerate(px_files):
                    src_path = os.path.join(cache_subdir, px_file)
                    num_match = re.search(r"(\d+)", px_file)
                    frame_num = int(num_match.group(1)) if num_match else i + 1
                    dst_filename = naming_utils.get_frame_filename("px", frame_num)
                    dst_path = os.path.join(output_subdir, dst_filename)
                    shutil.copy2(src_path, dst_path)
                print(f"Copied {len(px_files)} pixel art frames to {output_subdir}")

        return final_pixel_art_output_dir

    def run_full_pipeline(self, video_path, config):
        print(f"Starting full pipeline for video: {video_path}")
        video_name = self._get_video_name(video_path)

        # Step 1: Video to Frames
        step1_output_dir = self.process_video_to_frames(video_path)

        # Step 2: Background Removal
        step2_output_dir = self.remove_background(
            step1_output_dir,
            config.get("s2_k_val", 16),
            config.get("s2_threshold", 100),
            config.get("s2_enable_align", False),
            config.get("s2_padding", 10),
        )

        # Step 3: Pixel Art Processing
        step3_output_dir = self.process_pixel_art(
            step2_output_dir,
            config.get("s3_target_sizes", [64, 128, 256, 512]),
            config.get("s3_do_crop", False),
            config.get("s3_do_clean", True),
        )

        print(f"Full pipeline completed for {video_name}. Final output in {step3_output_dir}")
        return step3_output_dir


def main():
    """Batch processor entry point."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: batch-processor <video_file> [output_dir] [cache_dir]")
        print("Example: batch-processor input/test.mp4 ./output ./cache")
        sys.exit(1)

    video_file = sys.argv[1]
    output_base = sys.argv[2] if len(sys.argv) > 2 else "./output_processed"
    cache_base = sys.argv[3] if len(sys.argv) > 3 else "./cache_processed"

    if not os.path.exists(video_file):
        print(f"Error: Video file not found: {video_file}")
        sys.exit(1)

    # Configuration for each step
    pipeline_config = {
        "s2_k_val": 16,
        "s2_threshold": 100,
        "s2_enable_align": True,
        "s2_padding": 10,
        "s3_target_sizes": [64, 128, 256, 512],
        "s3_do_crop": False,
        "s3_do_clean": True,
    }

    processor = BatchProcessor(output_base_dir=output_base, cache_base_dir=cache_base)
    final_output = processor.run_full_pipeline(video_file, pipeline_config)
    print(f"Batch processing finished. Check {final_output} for results.")


if __name__ == "__main__":
    main()
