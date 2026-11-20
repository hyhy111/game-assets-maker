"""Tests for alpha refinement and defringe parameters (Step 3 debug tuning)."""

import json

import numpy as np
import pytest
from PIL import Image

from backend.core.alpha_refine import (
    defringe_rgba,
    needs_refinement,
    refine_alpha,
    refine_frame,
    validate_alpha_refine_params,
)


def test_validate_fills_defaults():
    settings = validate_alpha_refine_params({})
    assert settings["alpha_contrast"] == 1.0
    assert settings["alpha_threshold"] == 0
    assert settings["defringe_enabled"] is False
    assert settings["defringe_px"] == 2
    assert settings["defringe_amount"] == 0.5
    assert settings["min_foreground_area"] == 0
    assert settings["fill_holes_max_size"] == 0


@pytest.mark.parametrize(
    "params",
    [
        {"alpha_contrast": 0.4},
        {"alpha_contrast": 3.1},
        {"alpha_contrast": "1.5"},
        {"alpha_threshold": -1},
        {"alpha_threshold": 255},
        {"alpha_threshold": 1.5},
        {"defringe_enabled": "yes"},
        {"defringe_px": 21},
        {"defringe_amount": 1.5},
        {"min_foreground_area": -1},
        {"fill_holes_max_size": 1_000_001},
    ],
)
def test_validate_rejects_out_of_range(params):
    with pytest.raises(ValueError):
        validate_alpha_refine_params(params)


def test_neutral_settings_need_no_refinement():
    assert needs_refinement(validate_alpha_refine_params({})) is False
    assert needs_refinement(validate_alpha_refine_params({"defringe_enabled": True, "defringe_amount": 0})) is False


def test_non_default_settings_trigger_refinement():
    assert needs_refinement(validate_alpha_refine_params({"alpha_contrast": 1.5})) is True
    assert needs_refinement(validate_alpha_refine_params({"alpha_threshold": 100})) is True
    assert needs_refinement(validate_alpha_refine_params({"defringe_enabled": True})) is True


def test_contrast_identity_at_one():
    alpha = np.arange(256, dtype=np.uint8).reshape(16, 16)
    assert np.array_equal(refine_alpha(alpha, alpha_contrast=1.0), alpha)


def test_contrast_stretches_midtones():
    alpha = np.full((4, 4), 150, dtype=np.uint8)
    hardened = refine_alpha(alpha, alpha_contrast=2.0)
    assert hardened[0, 0] > 150
    softened = refine_alpha(alpha, alpha_contrast=0.5)
    assert softened[0, 0] < 150
    assert hardened.dtype == np.uint8


def test_threshold_cuts_weak_alpha():
    alpha = np.array([[10, 100, 200, 255]], dtype=np.uint8)
    result = refine_alpha(alpha, alpha_threshold=100)
    assert result.tolist() == [[0, 100, 200, 255]]


def test_fill_holes_interior_only():
    alpha = np.zeros((12, 12), dtype=np.uint8)
    alpha[2:10, 2:10] = 255
    alpha[5, 5] = 0  # small interior hole
    alpha[3:7, 3:7] = 0  # 4x4 = 16px interior hole
    result = refine_alpha(alpha, fill_holes_max_size=16)
    assert result[5, 5] == 255
    assert result[3, 5] == 255
    # Border background must stay transparent.
    assert result[0, 0] == 0


def test_fill_holes_keeps_oversized_hole():
    alpha = np.zeros((16, 16), dtype=np.uint8)
    alpha[1:15, 1:15] = 255
    alpha[4:10, 4:10] = 0  # 36 px interior hole
    result = refine_alpha(alpha, fill_holes_max_size=16)
    assert result[6, 6] == 0


def test_remove_small_blobs():
    alpha = np.zeros((16, 16), dtype=np.uint8)
    alpha[1:9, 1:9] = 255  # 64 px main blob
    alpha[12, 12] = 200  # 1 px noise blob
    result = refine_alpha(alpha, min_foreground_area=10)
    assert result[4, 4] == 255
    assert result[12, 12] == 0


def test_defringe_pulls_edge_toward_interior_color():
    rgba = np.zeros((10, 10, 4), dtype=np.uint8)
    rgba[1:9, 1:9] = (200, 30, 30, 255)  # opaque red block
    rgba[0, :] = (227, 142, 142, 128)  # semi edge contaminated toward white
    before = rgba[0, 5].copy()
    result = defringe_rgba(rgba.copy(), px=3, amount=1.0)
    after = result[0, 5]
    # Color moves toward the interior red; alpha stays untouched.
    assert after[3] == before[3]
    fg = np.array((200, 30, 30))
    before_dist = np.abs(before[:3].astype(int) - fg).sum()
    after_dist = np.abs(after[:3].astype(int) - fg).sum()
    assert after_dist < before_dist


def test_defringe_corrects_opaque_halo_band():
    """The visible BiRefNet fringe is opaque (alpha 255) — the band must include it."""
    rgba = np.zeros((20, 20, 4), dtype=np.uint8)
    rgba[5:15, 5:15] = (200, 30, 30, 255)  # interior block
    rgba[3:5, 3:15] = (250, 250, 250, 255)  # 2px opaque white halo ring, alpha 255
    rgba[3:5, 3:15, 3] = 255
    rgba[15:17, 5:15] = (250, 250, 250, 255)
    result = defringe_rgba(rgba.copy(), px=3, amount=1.0)
    # Opaque halo pixels are pulled strongly toward the interior red.
    assert result[3, 9, 0] < 250
    assert result[3, 9, 0] > result[3, 9, 1]  # red now dominates green/blue
    assert result[3, 9, 3] == 255  # alpha untouched
    # Deep interior is untouched.
    assert np.array_equal(result[8, 8], (200, 30, 30, 255))
    # Transparent surroundings stay transparent.
    assert result[0, 0, 3] == 0


def test_refine_frame_end_to_end(tmp_path):
    frame = np.zeros((12, 12, 4), dtype=np.uint8)
    frame[2:10, 2:10] = (200, 30, 30, 255)
    frame[5, 5] = (0, 0, 0, 0)  # interior hole
    path = tmp_path / "frame.png"
    Image.fromarray(frame, "RGBA").save(path)
    refine_frame(
        path,
        fill_holes_max_size=10,
        alpha_threshold=100,
        defringe_enabled=True,
        defringe_px=2,
        defringe_amount=0.5,
    )
    with Image.open(path) as source:
        result = np.asarray(source.convert("RGBA"))
    assert result[5, 5, 3] == 255  # hole filled
    assert result[2, 2, 3] == 255  # opaque interior untouched by threshold


def test_step2_applies_refinement_after_model_cutout(tmp_path, monkeypatch):
    """Refinement runs inside Step 2, right after the local model produces each frame."""
    from backend.api.process_api import ProcessAPI

    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    project = tmp_path / "角色/动作"
    (project / "cache").mkdir(parents=True)
    frames = project / "output" / "01_frames"
    frames.mkdir(parents=True)
    Image.new("RGBA", (8, 8), (0, 0, 0, 0)).save(frames / "frame_000001.png")

    def fake_birefnet(frame):
        assert frame == frames / "frame_000001.png"
        weak = np.zeros((8, 8, 4), dtype=np.uint8)
        weak[..., 3] = 120  # weak semi-transparent residue
        return Image.fromarray(weak, "RGBA")

    monkeypatch.setattr("backend.core.birefnet.remove_background", fake_birefnet)
    api = ProcessAPI(projects_root=tmp_path)
    monkeypatch.setattr(api, "get_model_status", lambda _: {"phase": "ready"})
    task = api.start_processing(
        "角色/动作",
        2,
        {"model": "birefnet-comfy", "alpha_threshold": 200, "processed": True},
    )
    api.tasks[task].future.result(timeout=10)
    status = api.get_task_status(task)
    assert status["status"] == "completed", status.get("error")
    with Image.open(project / "output" / "02_no_bg" / "frame_000001.png") as source:
        assert np.asarray(source.convert("RGBA"))[..., 3].max() == 0
    api.shutdown()


def test_step2_rejects_invalid_refine_params(tmp_path, monkeypatch):
    from backend.api.process_api import ProcessAPI

    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    api = ProcessAPI(projects_root=tmp_path)
    monkeypatch.setattr(api, "get_model_status", lambda _: {"phase": "ready"})
    with pytest.raises(ValueError):
        api.start_processing("角色/动作", 2, {"model": "birefnet-comfy", "alpha_contrast": 9})
    api.shutdown()


def test_agent_merge_accepts_and_validates_refine_fields():
    from backend.agent_control.steps import merge_params

    saved = {
        "alpha_matting": True,
        "alpha_matting_erode_size": 5,
        "alpha_matting_background_threshold": 120,
        "alpha_matting_foreground_threshold": 240,
    }
    merged = merge_params(saved, 2, {"alpha_contrast": 1.5, "defringe_enabled": True})
    assert merged["alpha_contrast"] == 1.5
    assert merged["fill_holes_max_size"] == 0
    with pytest.raises(ValueError):
        merge_params(saved, 2, {"alpha_threshold": 300})
    with pytest.raises(ValueError):
        merge_params(saved, 2, {"unknown_field": 1})


def test_step_params_defaults_include_refine_fields(tmp_path, monkeypatch):
    """Legacy saved step 2 params (missing the new fields) get safe defaults."""
    from backend.api.process_api import ProcessAPI

    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    project = tmp_path / "角色/动作"
    cache = project / "cache"
    cache.mkdir(parents=True)
    (cache / "steps_config.json").write_text(
        json.dumps({"step2": {"processed": True, "model": "u2net"}}), encoding="utf-8"
    )
    api = ProcessAPI(projects_root=tmp_path)
    params = api.get_step_params("角色/动作", 2)
    assert params["alpha_contrast"] == 1.0
    assert params["defringe_enabled"] is False
    api.shutdown()
