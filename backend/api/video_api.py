"""Video API - Video file operations"""

from typing import Any

import cv2


class VideoAPI:
    """API for video file operations"""

    def get_video_info(self, video_path: str) -> dict[str, Any]:
        """Get video file information"""
        try:
            cap = cv2.VideoCapture(video_path)

            if not cap.isOpened():
                return {"success": False, "error": "无法打开视频文件"}

            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = frame_count / fps if fps > 0 else 0

            cap.release()

            return {
                "success": True,
                "fps": fps,
                "frame_count": frame_count,
                "width": width,
                "height": height,
                "duration": duration,
                "duration_formatted": self._format_duration(duration),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def validate_video(self, video_path: str) -> dict[str, Any]:
        """Validate video for processing"""
        info = self.get_video_info(video_path)

        if not info["success"]:
            return info

        errors = []
        warnings = []

        # Warn for very large videos, but do not block processing.
        if info["width"] > 2160 or info["height"] > 2160:
            warnings.append("分辨率过高，抠像处理可能会偏慢")

        # Check duration (max 60 seconds)
        if info["duration"] > 60:
            errors.append(f"视频过长: {info['duration_formatted']} (最大支持 60 秒)")

        # Check FPS
        if info["fps"] < 1:
            errors.append("无效的帧率")

        return {
            "success": len(errors) == 0,
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "info": info,
        }

    def _format_duration(self, seconds: float) -> str:
        """Format duration as MM:SS"""
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"
