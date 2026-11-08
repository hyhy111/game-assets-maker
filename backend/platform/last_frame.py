"""Extract the final frame of a local video with OpenCV.

Platform tasks now return the upstream last frame, so continuation normally
uses that artifact directly (see ``SeedanceManager._continuation_frame_source``).
This local extraction remains the fallback for tasks whose frame was missing,
expired, or not downloaded. OpenCV is the codebase's established video
dependency (the Seedance downloader validates videos with it); no new
dependency is needed.
"""

from __future__ import annotations

from pathlib import Path

import cv2


def extract_last_frame(video_path: Path, output_path: Path) -> Path:
    """Write the video's final frame as PNG; raises ValueError on failure."""
    capture = cv2.VideoCapture(str(video_path))
    try:
        if not capture.isOpened():
            raise ValueError("Video is not readable for last-frame extraction")
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if frame_count <= 0:
            raise ValueError("Video has no frames to extract")
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_count - 1)
        ok, frame = capture.read()
        if not ok or frame is None:
            # Fall back to sequential read for codecs that ignore seeking.
            capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            last = None
            while True:
                ok, candidate = capture.read()
                if not ok:
                    break
                last = candidate
            if last is None:
                raise ValueError("Video has no frames to extract")
            frame = last
    finally:
        capture.release()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), frame):
        raise ValueError("Failed to write the extracted last frame")
    return output_path
