"""AudioAPI 抽取源音轨的测试。

用 imageio-ffmpeg 自带的 ffmpeg 现生成带音轨的夹具视频，断言抽出非空、
时长/采样率正确的 wav；已存在则复用、不重复抽取；无音轨时返回清晰错误。
"""

from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path

import imageio_ffmpeg
import pytest

from backend.api.audio_api import AudioAPI


def _ffmpeg_exe() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def _write_video_with_audio(path: Path, *, fps: int = 10, duration: float = 1.0) -> None:
    """用 ffmpeg lavfi 源生成带音轨的测试视频。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            _ffmpeg_exe(), "-y",
            "-f", "lavfi", "-i", f"testsrc=duration={duration}:size=64x64:rate={fps}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
            "-c:v", "libx264", "-c:a", "aac", "-shortest",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )


def _write_video_no_audio(path: Path) -> None:
    """用 OpenCV 生成无音轨视频（同 conftest._write_video 模式）。"""
    import cv2
    import numpy as np

    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 6, (64, 64))
    assert writer.isOpened()
    for _ in range(8):
        writer.write(np.full((64, 64, 3), (30, 180, 40), dtype=np.uint8))
    writer.release()


def _create_project(workspace: Path, project_id: str, video_path: Path) -> Path:
    """在 isolated_workspace 下建项目目录与 global_params.json。"""
    from backend.api.project_paths import resolve_project_path

    projects_root = workspace / "project"
    project_path = resolve_project_path(projects_root, project_id)
    cache_dir = project_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "global_params.json").write_text(
        json.dumps(
            {
                "project_name": project_id.split("/")[-1],
                "video_path": str(video_path),
                "timestamp": "2026-01-01T00:00:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return project_path


# ---------------------------------------------------------------------------
# 抽取源音频
# ---------------------------------------------------------------------------


def test_extract_source_audio_generates_non_empty_wav(isolated_workspace, tmp_path):
    """带音轨视频 -> 抽出非空 wav，返回正确的 source_fps/total_frames/URL。"""
    video_path = tmp_path / "source.mp4"
    _write_video_with_audio(video_path, fps=10, duration=1.0)
    _create_project(isolated_workspace, "hero/attack", video_path)

    api = AudioAPI()
    result = api.extract_source_audio("hero/attack")

    assert result["success"] is True
    assert result["source_fps"] == pytest.approx(10.0, abs=0.5)
    assert result["total_frames"] >= 8
    assert result["source_wav"].startswith("http://")

    wav_path = isolated_workspace / "project" / "hero" / "attack" / "cache" / "01_audio" / "source.wav"
    assert wav_path.exists()
    assert wav_path.stat().st_size > 0

    with wave.open(str(wav_path), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getframerate() == 44100
        assert wf.getnframes() > 0


def test_extract_source_audio_reuses_cached_wav(isolated_workspace, tmp_path):
    """已存在的 wav 不重复抽取。"""
    video_path = tmp_path / "source.mp4"
    _write_video_with_audio(video_path, fps=10, duration=1.0)
    _create_project(isolated_workspace, "hero/attack", video_path)

    api = AudioAPI()
    api.extract_source_audio("hero/attack")

    wav_path = isolated_workspace / "project" / "hero" / "attack" / "cache" / "01_audio" / "source.wav"
    mtime_before = wav_path.stat().st_mtime

    # 删掉源视频，若复用缓存则不应报错
    video_path.unlink()
    result = api.extract_source_audio("hero/attack")

    assert result["success"] is True
    assert wav_path.stat().st_mtime == mtime_before


def test_extract_source_audio_no_audio_track_returns_error(isolated_workspace, tmp_path):
    """无音轨视频 -> 返回清晰的错误状态，应用不崩溃。"""
    video_path = tmp_path / "source.mp4"
    _write_video_no_audio(video_path)
    _create_project(isolated_workspace, "hero/attack", video_path)

    api = AudioAPI()
    result = api.extract_source_audio("hero/attack")

    assert result["success"] is False
    assert "error" in result
    assert result["source_wav"] == ""


def test_extract_source_audio_missing_project(isolated_workspace):
    """项目不存在 -> 返回错误。"""
    api = AudioAPI()
    result = api.extract_source_audio("nope/missing")
    assert result["success"] is False
    assert result["source_wav"] == ""


# ---------------------------------------------------------------------------
# audio_timeline.json 读写（票 02）
# ---------------------------------------------------------------------------

_SAMPLE_CLIPS = [
    {"name": "step", "srcStartFrame": 0, "srcEndFrame": 3, "placementFrame": 0},
    {"name": "hit", "srcStartFrame": 5, "srcEndFrame": 8, "placementFrame": 12},
]


def test_load_timeline_returns_empty_default_when_unsaved(isolated_workspace, tmp_path):
    """未保存时间线 -> 返回空默认（clips 为空数组，字段齐全）。"""
    _create_project(isolated_workspace, "hero/attack", tmp_path / "source.mp4")
    api = AudioAPI()
    result = api.load_timeline("hero/attack")

    assert result["clips"] == []
    assert "source_fps" in result
    assert "total_frames" in result
    assert "source_wav" in result


def test_save_then_load_timeline_round_trips_clips(isolated_workspace, tmp_path):
    """写 clips 读回相等（往返一致）。"""
    video_path = tmp_path / "source.mp4"
    _write_video_with_audio(video_path, fps=10, duration=1.0)
    _create_project(isolated_workspace, "hero/attack", video_path)
    api = AudioAPI()
    api.extract_source_audio("hero/attack")  # 确保 source_meta.json + wav 存在

    timeline = {
        "source_fps": 10.0,
        "total_frames": 10,
        "source_wav": "http://localhost:8080/cache/01_audio/source.wav?t=1",
        "clips": _SAMPLE_CLIPS,
    }
    save_result = api.save_timeline("hero/attack", timeline)
    assert save_result["success"] is True

    loaded = api.load_timeline("hero/attack")
    assert loaded["clips"] == _SAMPLE_CLIPS
    assert loaded["source_fps"] == pytest.approx(10.0, abs=0.5)
    assert loaded["total_frames"] == 10


def test_timeline_persists_relative_wav_path_and_returns_runtime_url(isolated_workspace, tmp_path):
    video_path = tmp_path / "source.mp4"
    _write_video_with_audio(video_path, fps=10, duration=1.0)
    project_path = _create_project(isolated_workspace, "hero/attack", video_path)
    api = AudioAPI(assets_base_url="http://127.0.0.1:54321")
    extracted = api.extract_source_audio("hero/attack")

    save_result = api.save_timeline("hero/attack", {
        "source_fps": extracted["source_fps"],
        "total_frames": extracted["total_frames"],
        "source_wav": extracted["source_wav"],
        "clips": _SAMPLE_CLIPS,
    })

    assert save_result["success"] is True
    persisted = json.loads((project_path / "cache" / "audio_timeline.json").read_text(encoding="utf-8"))
    assert persisted["source_wav"] == "cache/01_audio/source.wav"
    assert api.load_timeline("hero/attack")["source_wav"].startswith("http://127.0.0.1:54321/")


def test_save_timeline_fills_metadata_from_source_meta(isolated_workspace, tmp_path):
    """首次保存时若 source_fps/total_frames/source_wav 缺失，从 source_meta.json 填充。"""
    video_path = tmp_path / "source.mp4"
    _write_video_with_audio(video_path, fps=10, duration=1.0)
    _create_project(isolated_workspace, "hero/attack", video_path)
    api = AudioAPI()
    api.extract_source_audio("hero/attack")

    # 保存时只带 clips，缺失 source_fps/total_frames/source_wav
    save_result = api.save_timeline(
        "hero/attack",
        {"clips": [{"name": "c", "srcStartFrame": 1, "srcEndFrame": 2, "placementFrame": 1}]},
    )
    assert save_result["success"] is True

    loaded = api.load_timeline("hero/attack")
    assert loaded["source_fps"] == pytest.approx(10.0, abs=0.5)
    assert loaded["total_frames"] >= 8
    assert loaded["source_wav"].startswith("http://")
    assert len(loaded["clips"]) == 1
    assert loaded["clips"][0]["name"] == "c"


def test_load_timeline_missing_project_returns_empty(isolated_workspace):
    """项目不存在 -> 返回空默认，不抛异常。"""
    api = AudioAPI()
    result = api.load_timeline("nope/missing")
    assert result["clips"] == []


def test_api_class_delegates_load_save_timeline(isolated_workspace, tmp_path):
    """API 类委托 load_timeline / save_timeline。"""
    from backend.main import API

    video_path = tmp_path / "source.mp4"
    _write_video_with_audio(video_path, fps=10, duration=1.0)
    _create_project(isolated_workspace, "hero/attack", video_path)
    api = API()
    api.extract_source_audio("hero/attack")

    loaded = api.load_timeline("hero/attack")
    assert loaded["clips"] == []

    save_result = api.save_timeline(
        "hero/attack",
        {"clips": [{"name": "c", "srcStartFrame": 0, "srcEndFrame": 1, "placementFrame": 0}]},
    )
    assert save_result["success"] is True

    loaded_again = api.load_timeline("hero/attack")
    assert len(loaded_again["clips"]) == 1
