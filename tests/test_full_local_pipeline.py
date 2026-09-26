from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import pytest
from PIL import Image

from backend.core.smart_remove_background import check_model_available
from tests.conftest import wait_for_task

MODEL_PREPARATION = "uv run python scripts/download_models.py u2net"


def _wait_for_model(api, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    status = api.get_model_status("u2net")
    if status["phase"] == "needs_download":
        pytest.skip(f"u2net rembg model is not installed; prepare it explicitly with `{MODEL_PREPARATION}`")
    status = api.preload_model("u2net")
    while status["phase"] not in {"ready", "failed"} and time.time() < deadline:
        time.sleep(0.1)
        status = api.get_model_status("u2net")
    assert status["phase"] == "ready", f"Step 2 model preparation failed: {status}"


def _run_step(api, project_id: str, step: int, params: dict, timeout: float) -> None:
    task_id = api.start_processing(project_id, step, params)
    status = wait_for_task(api, task_id, timeout=timeout)
    assert status["status"] == "completed", f"Step {step} failed: {status}"


@pytest.mark.full
def test_real_local_media_reaches_preview_and_both_batch_trim_modes(api, test_assets, asset_catalog) -> None:
    if not check_model_available("u2net"):
        pytest.skip(f"u2net rembg model is not installed; prepare it explicitly with `{MODEL_PREPARATION}`")

    sample = asset_catalog[0]
    source_video = test_assets / "videos" / sample["role"] / f"{sample['actions'][0]}.mp4"
    validation = api.validate_video(str(source_video))
    assert validation["valid"] is True

    project = api.create_project("full-local", sample["actions"][0], str(source_video), 1)
    _run_step(
        api,
        project["id"],
        1,
        {
            "video_path": str(source_video),
            "frame_interval": 1,
            "start_frame": 0,
            "end_frame": 2,
            "fps": 6,
        },
        timeout=30,
    )
    step1_frames = api.get_frames(project["id"], 1, page=1, page_size=10, use_cache=False)
    assert 1 <= step1_frames["total"] <= 3
    expected_frame_count = step1_frames["total"]
    with Image.open(step1_frames["frames"][0]["path"]) as image:
        expected_size = image.size

    _wait_for_model(api)
    assert api.get_model_status("u2net")["phase"] == "ready"
    _run_step(
        api,
        project["id"],
        2,
        {"model": "u2net", "alpha_matting": False, "edge_erode": 0, "fps": 6},
        timeout=180,
    )
    _run_step(
        api,
        project["id"],
        3,
        {
            "enabled": True,
            "green_intensity": 3,
            "feather_radius": 1,
            "min_hole_size": 0,
            "align_enabled": True,
            "align_h": True,
            "align_v": True,
            "use_padding": True,
            "padding_bottom": 2,
            "fps": 6,
        },
        timeout=60,
    )

    preview = api.get_frames(project["id"], 3, page=1, page_size=10)
    assert preview["total"] == expected_frame_count
    first_frame = preview["frames"][0]
    assert first_frame["url"].startswith("http://localhost:8080/project/")
    assert base64.b64decode(api.get_frame_image(first_frame["path"])).startswith(b"\x89PNG")
    assert base64.b64decode(api.get_frame_thumbnail(first_frame["path"], 32)).startswith(b"\x89PNG")

    with Image.open(first_frame["path"]) as image:
        rgba = image.convert("RGBA")
        alpha = rgba.getchannel("A")
        assert rgba.size == expected_size
        assert alpha.getbbox() is not None
        assert alpha.getextrema()[0] < 255

    availability = api.check_projects_for_trim([project["id"]])
    assert availability == [
        {
            "projectId": project["id"],
            "status": "available",
            "hasHolePunched": True,
            "hasNoBg": True,
            "frameCount": expected_frame_count,
        }
    ]

    global_result = api.execute_batch_trim(
        {"projectIds": [project["id"]], "mode": "global", "outputDir": ""}
    )[0]
    assert global_result["status"] == "success"
    assert len(list(Path(global_result["outputPath"]).glob("*.png"))) == expected_frame_count

    individual_result = api.execute_batch_trim(
        {"projectIds": [project["id"]], "mode": "individual", "outputDir": ""}
    )[0]
    assert individual_result["status"] == "success"
    metadata = json.loads(
        (Path(individual_result["outputPath"]) / "_frame_data.json").read_text(encoding="utf-8")
    )
    assert metadata["project_id"] == project["id"]
    assert len(metadata["frames"]) == expected_frame_count
    assert all(set(frame["offset"]) == {"x", "y"} for frame in metadata["frames"])
