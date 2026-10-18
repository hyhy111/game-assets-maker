import json
import shutil
import time
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def pytest_collection_modifyitems(config, items):
    if config.option.markexpr:
        return

    skip_full = pytest.mark.skip(reason="full tests are skipped by default; run with -m full")
    for item in items:
        if "full" in item.keywords:
            item.add_marker(skip_full)


@pytest.fixture
def isolated_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GAM_CONFIG", str(tmp_path / "runtime-config.json"))
    (tmp_path / "project").mkdir()
    return tmp_path


def _write_video(path: Path, color: tuple[int, int, int]):
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        6,
        (64, 64),
    )
    assert writer.isOpened(), f"Cannot create test video: {path}"

    for i in range(8):
        frame = np.full((64, 64, 3), (30, 180, 40), dtype=np.uint8)
        x = 10 + i
        y = 16
        frame[y : y + 28, x : x + 24] = color
        writer.write(frame)

    writer.release()


def _write_trim_frames(output_dir: Path, color: tuple[int, int, int, int]):
    output_dir.mkdir(parents=True, exist_ok=True)
    for idx in range(3):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle((12 + idx, 18, 40 + idx, 50), fill=color)
        img.save(output_dir / f"frame_{idx:06d}.png")


def _copy_if_exists(src: Path, dst: Path):
    if src.exists():
        shutil.copytree(src, dst, dirs_exist_ok=True)


@pytest.fixture
def test_assets(tmp_path, repo_root):
    """Materialize real fixtures when present, otherwise generate compact assets."""
    source_root = repo_root / "tests" / "fixtures"
    assets_root = tmp_path / "fixtures"
    _copy_if_exists(source_root / "videos", assets_root / "videos")
    _copy_if_exists(source_root / "trim_sources", assets_root / "trim_sources")
    _copy_if_exists(source_root / "legacy_projects", assets_root / "legacy_projects")

    required = {}
    existing_roles = (
        {
            role_dir.name: sorted(video_path.stem for video_path in role_dir.glob("*.mp4"))
            for role_dir in (assets_root / "videos").iterdir()
            if role_dir.is_dir()
        }
        if (assets_root / "videos").exists()
        else {}
    )

    if len(existing_roles) < 2 or any(len(actions) < 2 for actions in existing_roles.values()):
        required = {
            "mage": {"walk": (40, 40, 230), "attack": (40, 80, 230)},
            "robot": {"idle": (220, 80, 40), "jump": (220, 120, 40)},
        }

    for role, actions in required.items():
        for action, bgr in actions.items():
            video_path = assets_root / "videos" / role / f"{action}.mp4"
            if not video_path.exists():
                _write_video(video_path, bgr)

            trim_dir = assets_root / "trim_sources" / role / action
            if not any(trim_dir.glob("*.png")):
                rgba = (bgr[2], bgr[1], bgr[0], 255)
                _write_trim_frames(trim_dir, rgba)

    for role_dir in (assets_root / "videos").iterdir():
        if not role_dir.is_dir():
            continue
        for video_path in role_dir.glob("*.mp4"):
            trim_dir = assets_root / "trim_sources" / role_dir.name / video_path.stem
            if not any(trim_dir.glob("*.png")):
                seed = sum(ord(ch) for ch in f"{role_dir.name}/{video_path.stem}")
                rgba = (80 + seed % 140, 60 + (seed // 3) % 140, 70 + (seed // 7) % 140, 255)
                _write_trim_frames(trim_dir, rgba)

    legacy_root = assets_root / "legacy_projects" / "legacy_walk"
    if not legacy_root.exists():
        (legacy_root / "cache").mkdir(parents=True, exist_ok=True)
        (legacy_root / "output" / "02_no_bg").mkdir(parents=True, exist_ok=True)
        (legacy_root / "cache" / "global_params.json").write_text(
            json.dumps(
                {"project_name": "legacy_walk", "video_path": "", "timestamp": "2026-01-01T00:00:00"},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        _write_trim_frames(legacy_root / "output" / "02_no_bg", (255, 0, 0, 255))

    return assets_root


@pytest.fixture
def asset_catalog(test_assets):
    roles = []
    videos_root = test_assets / "videos"
    for role_dir in sorted(videos_root.iterdir()):
        if not role_dir.is_dir():
            continue
        actions = sorted(video_path.stem for video_path in role_dir.glob("*.mp4"))
        if actions:
            roles.append({"role": role_dir.name, "actions": actions})

    usable_roles = [role for role in roles if len(role["actions"]) >= 2]
    assert len(usable_roles) >= 2, "Need at least two roles with two actions each"
    return usable_roles


@pytest.fixture
def api(isolated_workspace):
    from backend.main import API

    api_instance = API()
    yield api_instance
    if api_instance._process_api_instance is not None:
        api_instance._process_api.shutdown()
    if api_instance._seedance_api_instance is not None:
        api_instance._seedance_api_instance.shutdown()


def wait_for_task(api, task_id: str, timeout: float = 20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = api.get_task_status(task_id)
        if status.get("status") in {"completed", "failed", "cancelled"}:
            return status
        time.sleep(0.1)
    pytest.fail(f"Task {task_id} did not finish within {timeout}s")
