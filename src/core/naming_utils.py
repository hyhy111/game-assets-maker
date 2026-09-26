"""
File and directory naming utilities for video to sprite sheet conversion.
"""


def get_output_dir_name(video_name: str, stage_function: str) -> str:
    """
    Generate output directory name: output_[video_name]_[function].

    Examples:
        output_knight_attack_frames, output_knight_attack_no_bg
    """
    return f"output_{video_name}_{stage_function}"


def get_cache_dir_name(video_name: str, stage_function: str) -> str:
    """
    Generate cache directory name: cache_[video_name]_[function].

    Examples:
        cache_knight_attack_frames, cache_knight_attack_pixelart
    """
    return f"cache_{video_name}_{stage_function}"


def get_pixelart_cache_subdir_name(size: str | int, pixel_style: bool = True) -> str:
    """
    Generate pixel art cache subdirectory name.

    Args:
        size: Target size, such as 64, 128, 256, 512, or "origin".
        pixel_style: True=pixel style, False=smooth style

    Examples:
        "64px_pixel", "originpx_smooth"
    """
    suffix = "_pixel" if pixel_style else "_smooth"
    return f"{size}px{suffix}"


def get_frame_filename(function_shortcode: str, sequence_number: int) -> str:
    """
    Generate frame filename: [function_shortcode]_[sequence].png.

    Examples:
        raw_0001.png, mask_0002.png, px_0003.png

    Args:
        function_shortcode: Function shortcode, such as raw, mask, or px.
        sequence_number: Sequence number starting from 0.

    Returns:
        Formatted filename.
    """
    return f"{function_shortcode}_{sequence_number:04d}.png"


def extract_video_name_from_output_dir(dir_name: str) -> str:
    """
    Extract video name from output directory name.

    Pattern: output_[video_name]_[function]
    """
    parts = dir_name.split("_")
    if len(parts) >= 3 and parts[0] == "output":
        return "_".join(parts[1:-1])
    return dir_name


def extract_video_name_from_cache_dir(dir_name: str) -> str:
    """
    Extract video name from cache directory name.

    Pattern: cache_[video_name]_[function]
    """
    parts = dir_name.split("_")
    if len(parts) >= 3 and parts[0] == "cache":
        return "_".join(parts[1:-1])
    return dir_name
