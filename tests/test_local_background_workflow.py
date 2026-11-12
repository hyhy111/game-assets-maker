"""Exercise background replacement and the post-processing contract for older projects."""

import json
import threading

import numpy as np
import pytest
from PIL import Image

from backend.api.batch_trim_api import BatchTrimAPI
from backend.api.process_api import ProcessAPI
from backend.api.project_api import ProjectAPI
from backend.core.edge_shrink import shrink_alpha

PROJECT_ID = "角色/动作"
FRAME = "frame_000001.png"


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    directory = tmp_path / PROJECT_ID
    cache = directory / "cache"
    cache.mkdir(parents=True)
    (cache / "step2_params.json").write_text(json.dumps({"processed": True, "alpha_matting": False}), encoding="utf-8")
    (cache / "step3_params.json").write_text(json.dumps({"processed": True, "green_intensity": 4}), encoding="utf-8")
    for stage, pixel in [
        ("01_frames", (0, 255, 0, 255)),
        ("02_no_bg", (255, 0, 0, 255)),
        ("03_hole_punched", (0, 0, 255, 255)),
    ]:
        path = directory / "output" / stage
        path.mkdir(parents=True)
        Image.new("RGBA", (16, 16), pixel).save(path / FRAME)
    return directory


@pytest.fixture
def process(tmp_path, monkeypatch):
    api = ProcessAPI(projects_root=tmp_path)
    monkeypatch.setattr(api, "get_model_status", lambda _: {"phase": "ready"})
    yield api
    api.shutdown()


def run(process, step, params):
    task = process.start_processing(PROJECT_ID, step, params)
    process.tasks[task].future.result(timeout=5)
    return process.get_task_status(task)["status"]


def test_successful_model_switch_publishes_only_the_new_sequence(process, project, tmp_path, monkeypatch):
    output = project / "output"
    assert process.get_step_params(PROJECT_ID, 2)["model"] == "u2net"
    previous = process.get_step_params(PROJECT_ID, 3)
    assert previous["green_intensity"] == 4
    assert previous["edge_shrink_enabled"] is False

    def fake_birefnet(frame):
        assert frame == output / "01_frames" / FRAME
        return Image.new("RGBA", (16, 16), (255, 255, 0, 128))

    monkeypatch.setattr("backend.core.birefnet.remove_background", fake_birefnet)
    assert run(process, 2, {"model": "birefnet-comfy"}) == "completed"
    with Image.open(output / "02_no_bg" / FRAME) as result:
        assert result.getpixel((0, 0)) == (255, 255, 0, 128)
    assert not (output / "03_hole_punched").exists()
    assert process.get_step_params(PROJECT_ID, 3)["processed"] is False
    assert process.get_step_params(PROJECT_ID, 3)["green_intensity"] == 4
    steps = ProjectAPI(projects_root=tmp_path)._get_step_status(project)
    assert steps["2"]["result_model"] == "birefnet-comfy"
    assert not steps["3"]["completed"]
    assert BatchTrimAPI(projects_root=tmp_path)._get_source_dir(PROJECT_ID) == output / "02_no_bg"


@pytest.mark.parametrize("failure", ["partial", "cancelled", "publish"])
def test_failed_or_cancelled_replacement_keeps_outputs_and_settings(process, project, failure, monkeypatch):
    output = project / "output"
    if failure == "partial":
        Image.new("RGB", (16, 16), "green").save(output / "01_frames" / "frame_000002.png")
    process.get_step_params(PROJECT_ID, 2)
    config = project / "cache" / "steps_config.json"
    original = config.read_bytes()
    started, resume = threading.Event(), threading.Event()

    def infer(frame):
        if failure == "cancelled":
            started.set()
            assert resume.wait(timeout=5)
        if failure == "partial" and frame.name != FRAME:
            raise ValueError("test failed frame")
        return Image.new("RGBA", (16, 16), (255, 255, 0, 128))

    monkeypatch.setattr("backend.core.birefnet.remove_background", infer)
    if failure == "publish":
        monkeypatch.setattr(process, "_save_steps_config", lambda *_: False)

    task = process.start_processing(PROJECT_ID, 2, {"model": "birefnet-comfy"})
    if failure == "cancelled":
        try:
            assert started.wait(timeout=5)
            assert process.cancel_task(task)
            assert process.has_active_writes()
        finally:
            resume.set()
    process.tasks[task].future.result(timeout=5)

    assert process.get_task_status(task)["status"] == ("cancelled" if failure == "cancelled" else "failed")
    assert config.read_bytes() == original
    with (
        Image.open(output / "02_no_bg" / FRAME) as old_step2,
        Image.open(output / "03_hole_punched" / FRAME) as old_step3,
    ):
        assert old_step2.getpixel((0, 0)) == (255, 0, 0, 255)
        assert old_step3.getpixel((0, 0)) == (0, 0, 255, 255)


def test_edge_shrink_uses_published_step2_and_preserves_its_pixels(process, project):
    output = project / "output"
    source = output / "02_no_bg" / FRAME
    original = source.read_bytes()
    assert run(process, 3, {"enabled": False, "edge_shrink_enabled": True, "edge_shrink_px": 1}) == "completed"
    with Image.open(output / "03_hole_punched" / FRAME) as result:
        assert result.size == (16, 16)
        assert result.getpixel((0, 4)) == (255, 0, 0, 0)
        assert result.getpixel((1, 4)) == (255, 0, 0, 255)
    assert source.read_bytes() == original


def test_edge_shrink_respects_transparent_holes_and_original_alpha():
    alpha = np.full((9, 9), 200, dtype=np.uint8)
    alpha[4, 4] = 0
    refined = shrink_alpha(alpha, 1, 2)
    assert refined[4, 3] == 0
    assert refined[3, 3] == 41
    assert refined[2, 4] == 100
    assert refined[2, 2] == 183
    assert not (refined > alpha).any()
