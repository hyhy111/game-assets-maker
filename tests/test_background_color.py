"""Regression coverage shared by the three background-color comparison branches."""

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from backend.api.process_api import ProcessAPI, Task
from backend.core.background_color import (
    background_hsv_from_images,
    batch_punch_holes_color,
    color_distance,
    estimate_background,
    punch_color_mask,
    sample_edge_pixels,
    to_color_space,
)


def write_png(path, image):
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    encoded.tofile(path)


def scene(root, bgr=(30, 220, 35), noise=0, index=0):
    original = np.full((96, 96, 3), bgr, dtype=np.uint8)
    if noise:
        jitter = np.random.default_rng(index).integers(-noise, noise + 1, original.shape)
        original = np.clip(original.astype(int) + jitter, 0, 255).astype(np.uint8)
    original[16:80, 16:80] = (210, 60, 180)
    original[36:60, 36:60] = np.clip(np.array(bgr) + noise // 2, 0, 255)
    alpha = np.zeros((96, 96), dtype=np.uint8)
    alpha[16:80, 16:80] = 255
    rgba = np.dstack((original, alpha))
    # Simulate rembg changing the retained background RGB during alpha matting.
    rgba[36:60, 36:60, :3] = (90, 90, 90)
    filename = f"frame_{index:06d}.png"
    write_png(root / "01_frames" / filename, original)
    write_png(root / "02_no_bg" / filename, rgba)
    return original, rgba


@pytest.mark.parametrize(
    "bgr", [(30, 220, 35), (35, 35, 220), (220, 35, 35), (245, 245, 245), (120, 120, 120), (10, 10, 10)]
)
def test_removes_arbitrary_uneven_background_without_changing_subject_rgb(tmp_path, bgr):
    _, before = scene(tmp_path, bgr, noise=6)
    result = batch_punch_holes_color(
        str(tmp_path / "02_no_bg"),
        str(tmp_path / "03_hole_punched"),
        str(tmp_path / "01_frames"),
        {"feather_radius": 0},
    )
    after = cv2.imread(str(tmp_path / "03_hole_punched/frame_000000.png"), cv2.IMREAD_UNCHANGED)
    assert result == {"total": 1, "success": 1, "failed": 0}
    assert np.all(after[40:56, 40:56, 3] == 0)
    assert np.all(after[20:32, 20:32] == before[20:32, 20:32])
    assert np.all(after[:10, :, 3] == 0)
    assert after.shape == before.shape


def test_red_boundary_sampling_and_distance():
    hsv = np.full((96, 96, 3), (179, 230, 220), dtype=np.uint8)
    hsv[:, 48:, 0] = 1
    bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    h, _, _ = background_hsv_from_images([bgr])
    assert h <= 2 or h >= 178
    colors = to_color_space(bgr)
    assert float(color_distance(colors[0, 0], colors[0, -1])) < 10


def test_edge_patches_ignore_one_subject_covered_corner():
    image = np.full((128, 128, 3), (30, 220, 35), dtype=np.uint8)
    image[:12, :12] = (220, 20, 200)
    assert np.allclose(sample_edge_pixels(image).mean(axis=0), (30, 220, 35))


@pytest.mark.parametrize("size", [1, 2, 8])
def test_sampling_small_images(size):
    assert np.isfinite(sample_edge_pixels(np.full((size, size, 3), 80, dtype=np.uint8))).all()


def test_all_five_levels_expand_monotonically_with_bounded_variation(tmp_path):
    for index in range(3):
        scene(tmp_path, (30 + index, 220 - index, 35), noise=6, index=index)
    frames = sorted((tmp_path / "01_frames").glob("*.png"))
    estimates = [estimate_background(frames, intensity) for intensity in range(1, 6)]
    assert all(np.array_equal(estimates[0][0], entry[0]) for entry in estimates)
    assert all(estimates[index][1] < estimates[index + 1][1] for index in range(4))


def test_neutral_background_keeps_brightness_discrimination():
    colors = to_color_space(np.array([[[0, 0, 0], [128, 128, 128], [255, 255, 255]]], dtype=np.uint8))[0]
    assert color_distance(colors[0], colors[2]) > 50
    assert color_distance(colors[1], colors[2]) > 20


def test_area_filter_and_feather_preserve_existing_transparency():
    mask = np.full((32, 32), 255, dtype=np.uint8)
    mask[:2] = 0
    colors = np.zeros_like(mask, dtype=bool)
    colors[12:20, 12:20] = True
    colors[4, 4] = True
    result = punch_color_mask(mask, colors, feather_radius=3, min_hole_size=5)
    assert result[4, 4] == 255
    assert result[15, 15] == 0
    assert 0 < result[11, 15] < 255
    assert np.all(result[:2] == 0)


def test_missing_original_fails_before_deleting_previous_result(tmp_path):
    scene(tmp_path)
    (tmp_path / "01_frames/frame_000000.png").unlink()
    marker = tmp_path / "03_hole_punched/previous.png"
    write_png(marker, np.full((2, 2, 4), 255, dtype=np.uint8))
    with pytest.raises(ValueError, match="Original frames required"):
        batch_punch_holes_color(str(tmp_path / "02_no_bg"), str(marker.parent), str(tmp_path / "01_frames"), {})
    assert marker.exists()


def test_mismatched_dimensions_fail_instead_of_reporting_success(tmp_path):
    scene(tmp_path)
    write_png(tmp_path / "02_no_bg/frame_000000.png", np.full((12, 12, 4), 255, dtype=np.uint8))
    with pytest.raises(ValueError, match="dimensions"):
        batch_punch_holes_color(
            str(tmp_path / "02_no_bg"), str(tmp_path / "03_hole_punched"), str(tmp_path / "01_frames"), {}
        )


def test_cancellation_stops_before_writing_frames(tmp_path):
    scene(tmp_path)

    def cancelled(current, total):
        raise InterruptedError("cancelled")

    with pytest.raises(InterruptedError):
        batch_punch_holes_color(
            str(tmp_path / "02_no_bg"), str(tmp_path / "03_hole_punched"), str(tmp_path / "01_frames"), {}, cancelled
        )
    assert not list((tmp_path / "03_hole_punched").glob("*.png"))


def test_public_step3_uses_original_frames_and_legacy_saved_intensity(tmp_path):
    project = tmp_path / "hero/idle"
    (project / "cache").mkdir(parents=True)
    (project / "cache/global_params.json").write_text(json.dumps({"role": "hero", "action": "idle"}))
    scene(project / "output", (220, 35, 35))
    process = ProcessAPI(projects_root=tmp_path)
    try:
        saved = process.get_step_params("hero/idle", 3)
        saved.update(green_intensity=2, feather_radius=0)
        task = Task("comparison", "hero/idle", 3, saved)
        process._run_task(task)
        assert task.status == "completed", task.error
        after = cv2.imread(str(project / "output/03_hole_punched/frame_000000.png"), cv2.IMREAD_UNCHANGED)
        assert after[45, 45, 3] == 0
        assert process.get_step_params("hero/idle", 3)["green_intensity"] == 2
    finally:
        process.shutdown()


def test_disabled_punching_needs_no_original_frames(tmp_path):
    project = tmp_path / "hero/idle"
    (project / "cache").mkdir(parents=True)
    frame = project / "output/02_no_bg/frame_000000.png"
    rgba = np.full((12, 12, 4), 255, dtype=np.uint8)
    write_png(frame, rgba)
    process = ProcessAPI(projects_root=tmp_path)
    try:
        task = Task("disabled", "hero/idle", 3, {"enabled": False})
        process._run_task(task)
        assert task.status == "completed", task.error
        assert (project / "output/03_hole_punched/frame_000000.png").read_bytes() == frame.read_bytes()
    finally:
        process.shutdown()


@pytest.mark.parametrize(
    "params", [{"green_intensity": 6}, {"green_intensity": True}, {"feather_radius": -1}, {"min_hole_size": 501}]
)
def test_public_api_rejects_invalid_color_parameters_before_starting(tmp_path, params):
    process = ProcessAPI(projects_root=tmp_path)
    try:
        with pytest.raises(ValueError, match="Invalid step parameter"):
            process.start_processing("hero/idle", 3, params)
        assert not process.tasks
    finally:
        process.shutdown()


def test_ciede2000_matches_all_34_published_reference_pairs():
    data = np.loadtxt(Path(__file__).parent / "fixtures/ciede2000_reference.txt")
    measured = color_distance(data[:, :3], data[:, 3:6])
    reverse = color_distance(data[:, 3:6], data[:, :3])
    assert np.allclose(measured, data[:, 6], atol=5e-5, rtol=0)
    assert np.allclose(reverse, measured, atol=1e-12, rtol=0)


def test_creation_and_extraction_metadata_both_handle_red_boundary(tmp_path):
    from backend.api.project_api import ProjectAPI
    from backend.core.smart_remove_background import detect_background_color_from_frames as smart_detect
    from backend.core.video_utils import detect_background_color_from_frames as video_detect

    hsv = np.full((96, 96, 3), (179, 230, 220), dtype=np.uint8)
    hsv[:, 48:, 0] = 1
    frames = tmp_path / "frames"
    write_png(frames / "frame_000000.png", cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR))
    projects = ProjectAPI(projects_root=tmp_path / "projects")
    estimates = [
        projects._calculate_background_color_from_cache(str(frames)),
        smart_detect(str(frames)),
        video_detect(str(frames)),
    ]
    assert estimates[0] == estimates[1] == estimates[2]
    assert estimates[0][0] <= 2 or estimates[0][0] >= 178


@pytest.mark.full
def test_real_rembg_output_reaches_automatic_color_cleanup(tmp_path):
    import time

    from backend.core.smart_remove_background import check_model_available

    if not check_model_available("u2net"):
        pytest.skip("A local U2Net model is required; this test never downloads models")
    project = tmp_path / "hero/idle"
    (project / "cache").mkdir(parents=True)
    scene(project / "output", (35, 35, 220), noise=4)
    process = ProcessAPI(projects_root=tmp_path)
    try:
        process.preload_model("u2net")
        deadline = time.monotonic() + 60
        while process.get_model_status("u2net")["phase"] == "initializing" and time.monotonic() < deadline:
            time.sleep(0.05)
        assert process.get_model_status("u2net")["phase"] == "ready"
        step2 = Task("real-rembg", "hero/idle", 2, {"alpha_matting": False, "edge_erode": 0})
        process._run_task(step2)
        assert step2.status == "completed", step2.error
        before = cv2.imread(str(project / "output/02_no_bg/frame_000000.png"), cv2.IMREAD_UNCHANGED)
        step3 = Task("color-cleanup", "hero/idle", 3, {"feather_radius": 1})
        process._run_task(step3)
        assert step3.status == "completed", step3.error
        after = cv2.imread(str(project / "output/03_hole_punched/frame_000000.png"), cv2.IMREAD_UNCHANGED)
        assert after.shape == before.shape
        assert np.all(after[:, :, 3] <= before[:, :, 3])
        assert np.all(after[40:56, 40:56, 3] == 0)
        assert np.any(after[:, :, 3] > 0)
    finally:
        process.shutdown()


def test_matching_across_row_blocks(tmp_path):
    source = np.full((320, 320, 3), (35, 35, 220), dtype=np.uint8)
    source[20:300, 20:300] = (210, 60, 180)
    source[100:180, 100:180] = (35, 35, 220)
    rgba = np.dstack((source, np.full((320, 320), 255, dtype=np.uint8)))
    write_png(tmp_path / "01_frames/frame_000000.png", source)
    write_png(tmp_path / "02_no_bg/frame_000000.png", rgba)
    batch_punch_holes_color(
        str(tmp_path / "02_no_bg"),
        str(tmp_path / "03_hole_punched"),
        str(tmp_path / "01_frames"),
        {"feather_radius": 0},
    )
    after = cv2.imread(str(tmp_path / "03_hole_punched/frame_000000.png"), cv2.IMREAD_UNCHANGED)
    assert np.all(after[100:180, 100:180, 3] == 0)
    assert np.all(after[200:280, 100:180, 3] == 255)
