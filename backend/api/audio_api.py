"""Audio API - 从源视频抽取音轨并提供 wav 服务。

按需用 imageio-ffmpeg 自带的 ffmpeg 把源视频整条音轨抽成 wav 存入
``cache/01_audio/source.wav``，已存在则复用、不重复抽取。
"""

import json
import subprocess
from pathlib import Path
from typing import Any

import cv2
import imageio_ffmpeg

from backend.api.project_paths import resolve_project_path
from src.utils.data_paths import data_root, projects_root

# wav 采样率与声道数（前端 Web Audio 解码用）
_WAV_SAMPLE_RATE = 44100
_WAV_CHANNELS = 1


class AudioAPI:
    """API for source audio extraction and serving."""

    def __init__(self, assets_base_url: str = "http://localhost:8080"):
        self._projects_root = projects_root()
        self._project_root = data_root()
        self.assets_base_url = assets_base_url.rstrip("/")

    def set_assets_base_url(self, assets_base_url: str) -> None:
        self.assets_base_url = assets_base_url.rstrip("/")

    def extract_source_audio(self, project_id: str) -> dict[str, Any]:
        """确保项目源 wav 存在（缺失则抽取），返回 wav URL + source_fps + total_frames。

        已存在则复用、不重复抽取。无音轨或不可读时返回清晰错误状态。
        """
        project_path = resolve_project_path(self._projects_root, project_id)
        if not project_path.exists():
            return {"success": False, "error": "项目不存在", "source_wav": "", "source_fps": 0, "total_frames": 0}

        meta = self._load_project_meta(project_path)
        video_path = meta.get("video_path", "") if meta else ""
        if not video_path:
            return {"success": False, "error": "项目缺少源视频路径", "source_wav": "", "source_fps": 0, "total_frames": 0}

        audio_dir = project_path / "cache" / "01_audio"
        wav_path = audio_dir / "source.wav"
        meta_path = audio_dir / "source_meta.json"

        if not wav_path.exists():
            video_file = Path(video_path)
            if not video_file.exists():
                return {"success": False, "error": "源视频文件不存在", "source_wav": "", "source_fps": 0, "total_frames": 0}
            audio_dir.mkdir(parents=True, exist_ok=True)
            ok = self._extract_wav(video_file, wav_path)
            if not ok:
                return {
                    "success": False,
                    "error": "源视频无音轨或音轨不可读",
                    "source_wav": "",
                    "source_fps": 0,
                    "total_frames": 0,
                }
            # 首次抽取时把 fps/帧数缓存到 meta，后续复用不再依赖源视频
            source_fps, total_frames = self._probe_video(video_file)
            self._write_meta(meta_path, source_fps, total_frames)
        else:
            source_fps, total_frames = self._read_meta(meta_path)
            if source_fps == 0.0:
                # meta 缺失时回退到探测源视频（若仍可访问）
                video_file = Path(video_path)
                if video_file.exists():
                    source_fps, total_frames = self._probe_video(video_file)

        return {
            "success": True,
            "source_wav": self._wav_url(wav_path),
            "source_fps": source_fps,
            "total_frames": total_frames,
        }

    def load_timeline(self, project_id: str) -> dict[str, Any]:
        """读取 ``cache/audio_timeline.json``，返回 ``AudioTimeline`` 对象。

        未保存时返回空默认（``clips`` 为空数组）。若已保存但
        ``source_fps``/``total_frames``/``source_wav`` 缺失，从
        ``source_meta.json`` 与 wav 路径回填。
        """
        project_path = resolve_project_path(self._projects_root, project_id)
        if not project_path.exists():
            return self._empty_timeline()

        timeline_path = project_path / "cache" / "audio_timeline.json"
        if not timeline_path.exists():
            return self._empty_timeline()

        try:
            with open(timeline_path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return self._empty_timeline()

        if not isinstance(data, dict):
            return self._empty_timeline()

        data.setdefault("clips", [])
        self._fill_timeline_metadata(data, project_path)
        wav_path = project_path / "cache" / "01_audio" / "source.wav"
        if wav_path.exists():
            data["source_wav"] = self._wav_url(wav_path)
        return data

    def save_timeline(self, project_id: str, timeline: dict[str, Any]) -> dict[str, Any]:
        """写入 ``cache/audio_timeline.json``。

        缺失的 ``source_fps``/``total_frames`` 从 ``source_meta.json`` 回填；
        ``source_wav`` 持久化为项目相对路径，加载时再生成当前运行时 URL。
        """
        project_path = resolve_project_path(self._projects_root, project_id)
        if not project_path.exists():
            return {"success": False, "error": "项目不存在"}

        cache_dir = project_path / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        timeline_path = cache_dir / "audio_timeline.json"

        # 规范化入参：拷贝一份，避免改调用方对象；确保 clips 为列表
        data = dict(timeline) if isinstance(timeline, dict) else {}
        data["clips"] = list(data.get("clips", []) or [])
        self._fill_timeline_metadata(data, project_path)
        wav_path = project_path / "cache" / "01_audio" / "source.wav"
        data["source_wav"] = (
            wav_path.relative_to(project_path).as_posix() if wav_path.exists() else ""
        )

        timeline_path.write_text(
            json.dumps(data, ensure_ascii=False),
            encoding="utf-8",
        )
        return {"success": True}

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _empty_timeline(self) -> dict[str, Any]:
        """空默认时间线（字段齐全，clips 为空数组）。"""
        return {"source_fps": 0.0, "total_frames": 0, "source_wav": "", "clips": []}

    def _fill_timeline_metadata(self, data: dict[str, Any], project_path: Path) -> None:
        """若 source_fps/total_frames 缺失或为零，从 source_meta.json 回填。"""
        meta_path = project_path / "cache" / "01_audio" / "source_meta.json"
        source_fps, total_frames = self._read_meta(meta_path)

        if not data.get("source_fps"):
            data["source_fps"] = source_fps
        if not data.get("total_frames"):
            data["total_frames"] = total_frames
    def _load_project_meta(self, project_path: Path) -> dict[str, Any] | None:
        meta_path = project_path / "cache" / "global_params.json"
        if meta_path.exists():
            with open(meta_path, encoding="utf-8") as f:
                return json.load(f)
        return None

    def _extract_wav(self, video_path: Path, wav_path: Path) -> bool:
        """用 imageio-ffmpeg 的 ffmpeg 抽取整条音轨为 mono wav。成功返回 True。"""
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        try:
            result = subprocess.run(
                [
                    ffmpeg_exe, "-y",
                    "-i", str(video_path),
                    "-vn",
                    "-acodec", "pcm_s16le",
                    "-ar", str(_WAV_SAMPLE_RATE),
                    "-ac", str(_WAV_CHANNELS),
                    str(wav_path),
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            print(f"音频抽取异常: {e}")
            return False

        if result.returncode != 0 or not wav_path.exists() or wav_path.stat().st_size < 44:
            # 抽取失败或 wav 过小（仅含头）-> 清理残留
            wav_path.unlink(missing_ok=True)
            return False
        return True

    def _probe_video(self, video_path: Path) -> tuple[float, int]:
        """用 OpenCV 读取源视频 fps 与帧数（与 VideoAPI 一致）。"""
        cap = cv2.VideoCapture(str(video_path))
        try:
            if not cap.isOpened():
                return 0.0, 0
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            return fps, frame_count
        finally:
            cap.release()

    def _write_meta(self, meta_path: Path, source_fps: float, total_frames: int) -> None:
        meta_path.write_text(
            json.dumps({"source_fps": source_fps, "total_frames": total_frames}, ensure_ascii=False),
            encoding="utf-8",
        )

    def _read_meta(self, meta_path: Path) -> tuple[float, int]:
        if not meta_path.exists():
            return 0.0, 0
        try:
            with open(meta_path, encoding="utf-8") as f:
                data = json.load(f)
            return float(data.get("source_fps", 0.0)), int(data.get("total_frames", 0))
        except (json.JSONDecodeError, OSError, ValueError):
            return 0.0, 0

    def _wav_url(self, wav_path: Path) -> str:
        """把 wav 本地路径转为 assets server 的 HTTP URL（与 FrameAPI 同模式）。"""
        try:
            relative = wav_path.relative_to(self._project_root)
            mtime = int(wav_path.stat().st_mtime) if wav_path.exists() else 0
            return f"{self.assets_base_url}/{relative.as_posix()}?t={mtime}"
        except ValueError:
            return str(wav_path)
