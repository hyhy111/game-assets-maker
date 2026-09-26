"""Core package initialization"""

from .pixel_processing_suite import (
    apply_outline,
    pixel_engine_processor,
    process_single_frame,
    remove_isolated_pixels,
)
from .smart_remove_background import (
    HOLE_INTENSITY_MAP,
    batch_punch_holes,
    batch_remove_background,
    punch_holes_in_frame,
    remove_background_single,
    remove_background_single_rembg,
)
from .video_utils import (
    detect_background_color_from_frames,
    export_frames_step1,
    load_frames_from_dir,
    process_video_to_cache,
    validate_video,
)

__all__ = [
    "process_video_to_cache",
    "export_frames_step1",
    "load_frames_from_dir",
    "validate_video",
    "detect_background_color_from_frames",
    "remove_background_single",
    "remove_background_single_rembg",
    "batch_remove_background",
    "punch_holes_in_frame",
    "batch_punch_holes",
    "HOLE_INTENSITY_MAP",
    "pixel_engine_processor",
    "process_single_frame",
    "apply_outline",
    "remove_isolated_pixels",
]
