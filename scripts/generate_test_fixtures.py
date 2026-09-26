#!/usr/bin/env python3
"""Generate pytest fixtures from videos under tests/fixtures/videos."""

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import cv2

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.core.smart_remove_background import check_model_available  # noqa: E402
from backend.main import API  # noqa: E402

VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


@dataclass(frozen=True, slots=True)
class CompactVideo:
    role: str
    action: str
    source_path: Path
    output_path: Path
    frame_count: int


def generate_compact_videos(
    source_root: Path,
    output_root: Path,
    *,
    max_frames: int,
    max_dimension: int = 256,
) -> list[CompactVideo]:
    """Create small role/action videos from private source media."""
    if max_frames < 1:
        raise ValueError("max_frames must be at least 1")
    if max_dimension < 2:
        raise ValueError("max_dimension must be at least 2")

    generated: list[CompactVideo] = []
    for role_dir in sorted(source_root.iterdir()):
        if not role_dir.is_dir():
            continue
        for source_path in sorted(role_dir.iterdir()):
            if source_path.suffix.lower() not in VIDEO_SUFFIXES:
                continue

            capture = cv2.VideoCapture(str(source_path))
            if not capture.isOpened():
                raise ValueError(f"Cannot read source video: {source_path}")
            writer = None
            try:
                width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = capture.get(cv2.CAP_PROP_FPS) or 12.0
                scale = min(1.0, max_dimension / max(width, height))
                output_width = max(2, int(width * scale)) // 2 * 2
                output_height = max(2, int(height * scale)) // 2 * 2
                output_path = output_root / role_dir.name / f"{source_path.stem}.mp4"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                writer = cv2.VideoWriter(
                    str(output_path),
                    cv2.VideoWriter_fourcc(*"mp4v"),
                    fps,
                    (output_width, output_height),
                )
                if not writer.isOpened():
                    raise RuntimeError(f"Cannot create compact video: {output_path}")

                frame_count = 0
                while frame_count < max_frames:
                    ok, frame = capture.read()
                    if not ok:
                        break
                    if frame.shape[1] != output_width or frame.shape[0] != output_height:
                        frame = cv2.resize(frame, (output_width, output_height), interpolation=cv2.INTER_AREA)
                    writer.write(frame)
                    frame_count += 1
                if frame_count == 0:
                    raise ValueError(f"Source video contains no readable frames: {source_path}")
            finally:
                capture.release()
                if writer is not None:
                    writer.release()

            generated.append(
                CompactVideo(role_dir.name, source_path.stem, source_path, output_path, frame_count)
            )
    return generated


def wait_for_task(api: API, task_id: str, timeout: float):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = api.get_task_status(task_id)
        if status.get("status") in {"completed", "failed", "cancelled"}:
            return status
        time.sleep(0.2)
    raise TimeoutError(f"Task {task_id} timed out")


def wait_for_local_model(api: API, model: str, timeout: float = 60.0) -> None:
    """Initialize an already-installed model without entering the download path."""
    status = api.get_model_status(model)
    if status["phase"] == "needs_download":
        raise RuntimeError(
            f"{model} is not installed; prepare it explicitly with "
            f"`uv run python scripts/download_models.py {model}`"
        )
    status = api.preload_model(model)
    deadline = time.time() + timeout
    while status["phase"] not in {"ready", "failed"} and time.time() < deadline:
        time.sleep(0.2)
        status = api.get_model_status(model)
    if status["phase"] != "ready":
        raise RuntimeError(f"Could not initialize local {model} model: {status}")


def copy_pngs(source: Path, target: Path, limit: int):
    target.mkdir(parents=True, exist_ok=True)
    for old_file in target.glob("*.png"):
        old_file.unlink()

    copied = 0
    for idx, image_path in enumerate(sorted(source.glob("*.png"))[:limit]):
        shutil.copy2(image_path, target / f"frame_{idx:06d}.png")
        copied += 1
    return copied


def discover_videos(videos_root: Path):
    for role_dir in sorted(videos_root.iterdir()):
        if not role_dir.is_dir():
            continue
        for video_path in sorted(role_dir.glob("*.mp4")):
            yield role_dir.name, video_path.stem, video_path


def main():
    parser = argparse.ArgumentParser(description="Generate tests/fixtures assets from fixture videos.")
    parser.add_argument("--max-frames", type=int, default=3, help="number of output frames to keep per action")
    parser.add_argument(
        "--skip-rembg",
        action="store_true",
        help="only run Step 1 and use opaque frames as trim sources",
    )
    parser.add_argument(
        "--source",
        type=Path,
        help="private role/action media root; originals are read only and never copied verbatim",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="compact video output root (default: tests/fixtures/videos)",
    )
    parser.add_argument("--max-dimension", type=int, default=256, help="largest compact video dimension")
    args = parser.parse_args()

    fixtures_root = REPO_ROOT / "tests" / "fixtures"
    videos_root = (args.output or fixtures_root / "videos").resolve()
    trim_root = fixtures_root / "trim_sources"
    legacy_root = fixtures_root / "legacy_projects"

    if args.source:
        generated = generate_compact_videos(
            args.source.resolve(),
            videos_root,
            max_frames=args.max_frames,
            max_dimension=args.max_dimension,
        )
        print(f"Generated {len(generated)} compact videos in {videos_root}")

    if not videos_root.exists():
        raise SystemExit(f"No fixture videos found at {videos_root}")

    videos = list(discover_videos(videos_root))
    if not videos:
        raise SystemExit(f"No .mp4 files found under {videos_root}")

    run_rembg = not args.skip_rembg and check_model_available("u2net")
    print(f"Found {len(videos)} videos")
    print(f"rembg full pipeline: {'enabled' if run_rembg else 'disabled'}")

    first_generated_project = None
    with tempfile.TemporaryDirectory(prefix="gam-fixtures-") as tmp:
        tmp_path = Path(tmp)
        previous_cwd = Path.cwd()
        os.chdir(tmp_path)
        try:
            api = API()
            if run_rembg:
                wait_for_local_model(api, "u2net")
            for role, action, video_path in videos:
                print(f"[{role}/{action}] creating project")
                project = api.create_project(role, action, str(video_path), 1)

                step1 = api.start_processing(
                    project["id"],
                    1,
                    {
                        "video_path": str(video_path),
                        "frame_interval": 1,
                        "start_frame": 0,
                        "end_frame": args.max_frames - 1,
                        "fps": 12,
                    },
                )
                status = wait_for_task(api, step1, 60)
                if status["status"] != "completed":
                    raise RuntimeError(f"Step 1 failed for {project['id']}: {status}")

                source_dir = Path(project["path"]) / "output" / "01_frames"

                if run_rembg:
                    step2 = api.start_processing(
                        project["id"],
                        2,
                        {
                            "model": "u2net",
                            "alpha_matting": False,
                            "edge_erode": 0,
                            "fps": 12,
                        },
                    )
                    status = wait_for_task(api, step2, 180)
                    if status["status"] != "completed":
                        raise RuntimeError(f"Step 2 failed for {project['id']}: {status}")
                    source_dir = Path(project["path"]) / "output" / "02_no_bg"

                    step3 = api.start_processing(
                        project["id"],
                        3,
                        {
                            "enabled": True,
                            "green_intensity": 3,
                            "feather_radius": 1,
                            "min_hole_size": 0,
                            "align_enabled": False,
                            "fps": 12,
                        },
                    )
                    status = wait_for_task(api, step3, 60)
                    if status["status"] != "completed":
                        raise RuntimeError(f"Step 3 failed for {project['id']}: {status}")
                    source_dir = Path(project["path"]) / "output" / "03_hole_punched"

                copied = copy_pngs(source_dir, trim_root / role / action, args.max_frames)
                print(f"[{role}/{action}] copied {copied} frames")

                if first_generated_project is None:
                    first_generated_project = Path(project["path"])

            if first_generated_project:
                legacy_target = legacy_root / "legacy_from_video"
                if legacy_target.exists():
                    shutil.rmtree(legacy_target)
                (legacy_target / "cache").mkdir(parents=True, exist_ok=True)
                (legacy_target / "output" / "02_no_bg").mkdir(parents=True, exist_ok=True)

                source_meta = first_generated_project / "cache" / "global_params.json"
                meta = json.loads(source_meta.read_text(encoding="utf-8")) if source_meta.exists() else {}
                meta["project_name"] = "legacy_from_video"
                meta.pop("role", None)
                meta.pop("action", None)
                meta_path = legacy_target / "cache" / "global_params.json"
                meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

                source_output = first_generated_project / "output" / "02_no_bg"
                if not any(source_output.glob("*.png")):
                    source_output = first_generated_project / "output" / "01_frames"
                copy_pngs(source_output, legacy_target / "output" / "02_no_bg", args.max_frames)
                print(f"legacy fixture written to {legacy_target}")
        finally:
            if api._process_api_instance is not None:
                api._process_api.shutdown()
            os.chdir(previous_cwd)


if __name__ == "__main__":
    main()
