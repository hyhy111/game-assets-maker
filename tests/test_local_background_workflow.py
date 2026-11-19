"""Exercise background replacement and the post-processing contract for older projects."""

import base64
import io
import json
import threading

import numpy as np
import pytest
from PIL import Image

from backend.api.batch_trim_api import BatchTrimAPI
from backend.api.frame_api import FrameAPI
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


def test_birefnet_result_without_saved_hole_choice_disables_hole_punch(process, project, monkeypatch):
    assert process.get_step_params(PROJECT_ID, 3)["enabled"] is True

    monkeypatch.setattr(
        "backend.core.birefnet.remove_background",
        lambda _: Image.new("RGBA", (16, 16), (255, 255, 0, 128)),
    )
    assert run(process, 2, {"model": "birefnet-comfy"}) == "completed"

    params = process.get_step_params(PROJECT_ID, 3)
    assert params["enabled"] is False
    assert params["green_intensity"] == 4

    assert process.save_step_params(PROJECT_ID, 2, {"model": "u2net"})
    assert process.get_step_params(PROJECT_ID, 3)["enabled"] is False


def test_u2net_result_without_saved_hole_choice_enables_hole_punch(process, project, monkeypatch):
    assert process.save_step_params(PROJECT_ID, 2, {"model": "birefnet-comfy"})
    assert process.get_step_params(PROJECT_ID, 3)["enabled"] is True
    monkeypatch.setattr(
        "backend.core.smart_remove_background.remove_background_single_rembg",
        lambda *_args, **_kwargs: (Image.new("RGBA", (16, 16), (255, 255, 0, 128)), None),
    )

    assert run(process, 2, {"model": "u2net"}) == "completed"

    assert process.get_step_params(PROJECT_ID, 3)["enabled"] is True


def test_new_project_birefnet_result_uses_unset_hole_choice(process, tmp_path, monkeypatch):
    ProjectAPI(projects_root=tmp_path).create_project("角色", "动作")
    frames = tmp_path / PROJECT_ID / "output" / "01_frames"
    Image.new("RGBA", (16, 16), (0, 255, 0, 255)).save(frames / FRAME)
    monkeypatch.setattr(
        "backend.core.birefnet.remove_background",
        lambda _: Image.new("RGBA", (16, 16), (255, 255, 0, 128)),
    )

    assert run(process, 2, {"model": "birefnet-comfy"}) == "completed"

    assert process.get_step_params(PROJECT_ID, 3)["enabled"] is False


def test_legacy_project_without_step3_config_keeps_model_default_unset(process, tmp_path, monkeypatch):
    project = tmp_path / PROJECT_ID
    cache = project / "cache"
    cache.mkdir(parents=True)
    (cache / "step2_params.json").write_text(json.dumps({"processed": True}), encoding="utf-8")
    frames = project / "output" / "01_frames"
    frames.mkdir(parents=True)
    Image.new("RGBA", (16, 16), (0, 255, 0, 255)).save(frames / FRAME)
    assert process.get_step_params(PROJECT_ID, 3)["enabled"] is True

    monkeypatch.setattr(
        "backend.core.birefnet.remove_background",
        lambda _: Image.new("RGBA", (16, 16), (255, 255, 0, 128)),
    )
    assert run(process, 2, {"model": "birefnet-comfy"}) == "completed"

    assert process.get_step_params(PROJECT_ID, 3)["enabled"] is False


@pytest.mark.parametrize(
    ("saved_choice", "model"),
    [(True, "birefnet-comfy"), (False, "u2net")],
)
def test_saved_hole_choice_survives_model_results_and_project_reopening(
    process, project, tmp_path, monkeypatch, saved_choice, model
):
    assert process.get_step_params(PROJECT_ID, 3)["green_intensity"] == 4
    assert process.save_step_params(PROJECT_ID, 3, {"enabled": saved_choice})
    if model == "birefnet-comfy":
        monkeypatch.setattr(
            "backend.core.birefnet.remove_background",
            lambda _: Image.new("RGBA", (16, 16), (255, 255, 0, 128)),
        )
    else:
        monkeypatch.setattr(
            "backend.core.smart_remove_background.remove_background_single_rembg",
            lambda *_args, **_kwargs: (Image.new("RGBA", (16, 16), (255, 255, 0, 128)), None),
        )

    assert run(process, 2, {"model": model}) == "completed"
    assert process.get_step_params(PROJECT_ID, 3)["enabled"] is saved_choice

    reopened = ProcessAPI(projects_root=tmp_path)
    try:
        params = reopened.get_step_params(PROJECT_ID, 3)
        assert params["enabled"] is saved_choice
        assert params["green_intensity"] == 4
        assert ProjectAPI(projects_root=tmp_path).get_project(PROJECT_ID)["steps"]["2"]["result_model"] == model
    finally:
        reopened.shutdown()


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


def test_edge_shrink_accumulates_across_batches_and_preserves_step2(process, project):
    output = project / "output"
    source = output / "02_no_bg" / FRAME
    original = source.read_bytes()
    final = output / "03_hole_punched" / FRAME
    final.unlink()
    params = {"enabled": False, "edge_shrink_enabled": True, "edge_shrink_px": 1}
    for inset in (1, 2, 3):
        assert run(process, 3, params) == "completed"
        with Image.open(final) as result:
            assert result.size == (16, 16)
            assert result.getpixel((inset - 1, 4)) == (255, 0, 0, 0)
            assert result.getpixel((inset, 4)) == (255, 0, 0, 255)
    assert source.read_bytes() == original


def erase_pixel(api, frame, position):
    opened = api.get_editable_frame(PROJECT_ID, frame.name)
    with Image.open(frame) as image, io.BytesIO() as stream:
        image.putpixel(position, (0, 0, 0, 0))
        image.save(stream, format="PNG")
        data_url = "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode("ascii")
    api.save_frame_edit(PROJECT_ID, frame.name, data_url, opened["revision"])


def test_batch_versions_include_all_saved_edits_and_advance_the_frame_restore_point(
    process, project, tmp_path, monkeypatch
):
    output = project / "output"
    raw = Image.new("RGB", (16, 16), "lime")
    raw.paste("red", (3, 3, 13, 13))
    raw.paste("lime", (7, 7, 9, 9))
    step2 = Image.new("RGBA", raw.size)
    step2.paste("red", (3, 3, 13, 13))
    raw.save(output / "01_frames" / FRAME)
    source = output / "02_no_bg" / FRAME
    step2.save(source)
    untouched = "frame_000002.png"
    raw.save(output / "01_frames" / untouched)
    step2.save(output / "02_no_bg" / untouched)
    final = output / "03_hole_punched" / FRAME
    final.unlink()

    api = FrameAPI(projects_root=tmp_path)
    erase_pixel(api, source, (4, 4))

    assert run(process, 3, {"enabled": True, "min_hole_size": 2, "feather_radius": 0}) == "completed"
    with Image.open(final) as result, Image.open(final.with_name(untouched)) as unedited:
        assert result.getpixel((4, 4))[3] == 0
        assert result.getpixel((7, 7))[3] == 0
        assert unedited.getpixel((4, 4))[3] == 255

    first_batch = final.read_bytes()
    other = final.with_name(untouched)
    erase_pixel(api, final, (11, 4))
    erase_pixel(api, other, (4, 4))
    erase_pixel(api, final, (11, 11))
    opened = api.get_editable_frame(PROJECT_ID, FRAME)
    assert base64.b64decode(opened["initial_image_data_url"].split(",", 1)[1]) == first_batch
    api.save_frame_edit(PROJECT_ID, FRAME, opened["initial_image_data_url"], opened["revision"])
    with Image.open(other) as unchanged:
        assert unchanged.getpixel((4, 4))[3] == 0
    erase_pixel(api, final, (11, 4))
    edited = final.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(process, "_save_steps_config", lambda *_: False)
        assert run(process, 3, {"enabled": False}) == "failed"
    assert final.read_bytes() == edited
    assert base64.b64decode(api.get_editable_frame(PROJECT_ID, FRAME)["initial_image_data_url"].split(",", 1)[1]) == (
        first_batch
    )

    assert run(process, 3, {"enabled": False}) == "completed"
    with Image.open(final) as result, Image.open(source) as original, Image.open(other) as other_result:
        assert result.getpixel((4, 4))[3] == 0
        assert result.getpixel((7, 7))[3] == 0
        assert result.getpixel((11, 4))[3] == 0
        assert result.getpixel((11, 11))[3] == 255
        assert other_result.getpixel((4, 4))[3] == 0
        assert original.getpixel((4, 4))[3] == 255
    assert base64.b64decode(api.get_editable_frame(PROJECT_ID, FRAME)["initial_image_data_url"].split(",", 1)[1]) == (
        edited
    )


def test_hole_punch_matches_color_in_the_aligned_manual_frame(process, project, tmp_path):
    output = project / "output"
    raw = Image.new("RGB", (16, 16), "lime")
    raw.paste("red", (2, 4, 10, 12))
    raw.paste("lime", (4, 7, 6, 9))
    current = Image.new("RGBA", raw.size)
    current.paste(raw.crop((2, 4, 10, 12)), (2, 4))
    raw.save(output / "01_frames" / FRAME)
    current.save(output / "02_no_bg" / FRAME)
    final = output / "03_hole_punched" / FRAME
    final.unlink()

    assert run(process, 3, {"enabled": False, "align_enabled": True, "align_h": True, "align_v": False}) == "completed"
    api = FrameAPI(projects_root=tmp_path)
    erase_pixel(api, final, (9, 5))
    assert run(process, 3, {"enabled": False}) == "completed"
    erase_pixel(api, final, (10, 5))
    assert run(process, 3, {"enabled": True, "min_hole_size": 2, "feather_radius": 0}) == "completed"
    with Image.open(final) as result:
        assert result.getpixel((4, 7)) == (255, 0, 0, 255)
        assert result.getpixel((6, 7))[3] == 0
        assert result.getpixel((9, 5))[3] == 0
        assert result.getpixel((10, 5))[3] == 0


def test_processing_retains_new_manual_edits_on_legacy_frames_without_a_known_initial_version(
    process, project, tmp_path
):
    final = project / "output" / "03_hole_punched" / FRAME
    legacy = project / "cache" / "frame_edits" / ("0" * 64)
    legacy.mkdir(parents=True)
    (legacy / FRAME).write_bytes(final.read_bytes())
    api = FrameAPI(projects_root=tmp_path)
    assert api.get_editable_frame(PROJECT_ID, FRAME)["initial_image_data_url"] is None
    erase_pixel(api, final, (4, 4))

    assert run(process, 3, {"enabled": False}) == "completed"
    with Image.open(final) as result:
        assert result.getpixel((4, 4))[3] == 0


def test_reset_post_processing_restores_step2_and_keeps_prior_result_on_failure(
    process, project, tmp_path, monkeypatch
):
    output = project / "output"
    step2 = output / "02_no_bg" / FRAME
    original = step2.read_bytes()
    final = output / "03_hole_punched" / FRAME
    api = FrameAPI(projects_root=tmp_path)
    erase_pixel(api, final, (4, 4))
    before_reset = api.get_editable_frame(PROJECT_ID, FRAME)
    # Flush legacy settings so both rollback files can be compared.
    process.get_step_params(PROJECT_ID, 3)
    config = project / "cache/steps_config.json"
    config_before = config.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(process, "_save_steps_config", lambda *_: False)
        with pytest.raises(OSError, match="Could not save"):
            process.reset_post_processing(PROJECT_ID)
    assert config.read_bytes() == config_before
    assert api.get_editable_frame(PROJECT_ID, FRAME) == before_reset

    assert process.reset_post_processing(PROJECT_ID)
    assert process.reset_post_processing(PROJECT_ID)
    assert step2.read_bytes() == original
    assert not final.parent.exists()
    assert not list(output.glob(".step3-reset-*"))
    assert not ProjectAPI(projects_root=tmp_path)._get_step_status(project)["3"]["completed"]
    params = process.get_step_params(PROJECT_ID, 3)
    assert params["processed"] is False
    assert params["green_intensity"] == 4
    assert BatchTrimAPI(projects_root=tmp_path)._get_source_dir(PROJECT_ID) == step2.parent
    restored = api.get_editable_frame(PROJECT_ID, FRAME)
    assert restored["image_data_url"] == restored["initial_image_data_url"]
    assert base64.b64decode(restored["image_data_url"].split(",", 1)[1]) == original


def test_cancelled_batch_keeps_the_current_edits_and_latest_restore_point(process, project, tmp_path, monkeypatch):
    assert run(process, 3, {"enabled": False}) == "completed"
    frame = project / "output" / "03_hole_punched" / FRAME
    api = FrameAPI(projects_root=tmp_path)
    erase_pixel(api, frame, (4, 4))
    edited = api.get_editable_frame(PROJECT_ID, FRAME)
    config = project / "cache/steps_config.json"
    previous_config = config.read_bytes()
    entered, resume = threading.Event(), threading.Event()

    def wait_in_shrink(*_):
        entered.set()
        assert resume.wait(timeout=5)

    monkeypatch.setattr("backend.api.process_api.shrink_frame", wait_in_shrink)
    task = process.start_processing(PROJECT_ID, 3, {"enabled": False, "edge_shrink_enabled": True, "edge_shrink_px": 1})
    try:
        assert entered.wait(timeout=5)
        assert process.cancel_task(task)
    finally:
        resume.set()
    process.tasks[task].future.result(timeout=5)
    assert process.get_task_status(task)["status"] == "cancelled"
    assert api.get_editable_frame(PROJECT_ID, FRAME) == edited
    assert config.read_bytes() == previous_config


def test_undo_last_batch_restores_saved_prebatch_edits_and_their_baseline(process, project, tmp_path, monkeypatch):
    final = project / "output" / "03_hole_punched" / FRAME
    final.unlink()
    params = {"enabled": False, "edge_shrink_enabled": True, "edge_shrink_px": 1}
    assert run(process, 3, params) == "completed"
    api = FrameAPI(projects_root=tmp_path)
    erase_pixel(api, final, (5, 5))
    before_batch = api.get_editable_frame(PROJECT_ID, FRAME)
    assert before_batch["initial_image_data_url"] != before_batch["image_data_url"]

    assert run(process, 3, params) == "completed"
    backups = project / "cache/step3_versions"
    assert len(list(backups.iterdir())) == 1
    erase_pixel(api, final, (9, 9))
    current = api.get_editable_frame(PROJECT_ID, FRAME)
    with monkeypatch.context() as patch:
        patch.setattr(process, "_save_steps_config", lambda *_: False)
        with pytest.raises(OSError, match="Could not save"):
            process.undo_post_processing(PROJECT_ID)
    assert api.get_editable_frame(PROJECT_ID, FRAME) == current
    assert len(list(backups.iterdir())) == 1

    assert process.undo_post_processing(PROJECT_ID)
    assert api.get_editable_frame(PROJECT_ID, FRAME) == before_batch
    assert not list(backups.iterdir())
    step3 = ProjectAPI(projects_root=tmp_path)._get_step_status(project)["3"]
    assert step3["completed"] and not step3.get("can_undo_processing")
    with pytest.raises(ValueError, match="No Step 3 batch to undo"):
        process.undo_post_processing(PROJECT_ID)


def test_undo_first_batch_falls_back_to_step2_without_copying_it(process, project, tmp_path):
    final = project / "output" / "03_hole_punched" / FRAME
    final.unlink()
    step2 = project / "output" / "02_no_bg" / FRAME
    original = step2.read_bytes()
    assert run(process, 3, {"enabled": False}) == "completed"
    api = ProjectAPI(projects_root=tmp_path)
    assert api._get_step_status(project)["3"]["can_undo_processing"]
    assert not list((project / "cache/step3_versions").glob("*"))
    assert process.undo_post_processing(PROJECT_ID)
    assert not final.exists()
    assert step2.read_bytes() == original
    assert not api._get_step_status(project)["3"]["completed"]


def test_only_the_previous_batch_input_is_retained_and_reset_clears_it(process, project, monkeypatch):
    backups = project / "cache/step3_versions"
    legacy = backups / ("a" * 32)
    legacy.mkdir(parents=True)
    (legacy / FRAME).write_bytes(b"legacy snapshot")
    config = project / "cache/steps_config.json"
    process.get_step_params(PROJECT_ID, 3)
    data = json.loads(config.read_text(encoding="utf-8"))
    data["step3_history"] = {"versions": [{"id": legacy.name}]}
    config.write_text(json.dumps(data), encoding="utf-8")

    with monkeypatch.context() as patch:
        patch.setattr(process, "_save_steps_config", lambda *_: False)
        assert run(process, 3, {"enabled": False}) == "failed"
    assert list(backups.iterdir()) == [legacy]

    assert run(process, 3, {"enabled": False}) == "completed"
    first = set(backups.iterdir())
    assert len(first) == 1 and legacy not in first
    assert run(process, 3, {"enabled": False}) == "completed"
    second = set(backups.iterdir())
    assert len(second) == 1 and first.isdisjoint(second)
    assert process.reset_post_processing(PROJECT_ID)
    assert not list(backups.iterdir())
    with pytest.raises(ValueError, match="No Step 3 batch to undo"):
        process.undo_post_processing(PROJECT_ID)


def test_replacing_step2_invalidates_the_step3_backup(process, project, monkeypatch):
    assert run(process, 3, {"enabled": False}) == "completed"
    backups = project / "cache/step3_versions"
    assert len(list(backups.iterdir())) == 1
    monkeypatch.setattr(
        "backend.core.birefnet.remove_background",
        lambda _: Image.new("RGBA", (16, 16), (255, 255, 0, 128)),
    )
    assert run(process, 2, {"model": "birefnet-comfy"}) == "completed"
    assert not list(backups.iterdir())
    with pytest.raises(ValueError, match="No Step 3 batch to undo"):
        process.undo_post_processing(PROJECT_ID)


def test_edge_shrink_respects_transparent_holes_and_original_alpha():
    alpha = np.full((9, 9), 200, dtype=np.uint8)
    alpha[4, 4] = 0
    refined = shrink_alpha(alpha, 1, 2)
    assert refined[4, 3] == 0
    assert refined[3, 3] == 41
    assert refined[2, 4] == 100
    assert refined[2, 2] == 183
    assert not (refined > alpha).any()


@pytest.fixture(autouse=True)
def macos_background_model_compatibility(monkeypatch):
    """These legacy Comfy workflow cases exercise the retained macOS backend."""
    monkeypatch.setattr("sys.platform", "darwin")
