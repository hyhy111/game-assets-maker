"""Draft validation never creates remote tasks."""

from pathlib import Path

import pytest
from PIL import Image

from backend.main import API


def test_partial_draft_accepts_empty_inputs_and_valid_local_image(tmp_path):
    api = API()
    image = tmp_path / "image.png"
    Image.new("RGB", (300, 300), "green").save(image)
    assert api.agent_validate_draft("video", {"prompt": "", "first_frame": "", "last_frame": None})["success"]
    assert api.agent_validate_draft("image", {"prompt": "", "reference_image": str(image)})["success"]


def test_draft_validation_rejects_unknown_fields_and_invalid_mixed_update(tmp_path):
    api = API()
    for kind, value in [
        ("video", {"duration": True}),
        ("image", {"count": True}),
        ("image", {"prompt": "walk", "reference_image": str(tmp_path / "missing.png")}),
        ("video", {"api_key": "not-a-field"}),
    ]:
        assert api.agent_validate_draft(kind, value)["success"] is False


@pytest.mark.parametrize(
    ("model_id", "short_key"),
    [
        ("doubao-seedream-5-0-pro-260628", "pro"),
        ("doubao-seedream-5-0-flash-260915", "flash"),
    ],
)
def test_image_draft_normalizes_equivalent_api_key_model_ids(model_id, short_key):
    values = {"prompt": "updated", "model": model_id, "resolution": "1.5K", "count": 3}
    result = API().agent_validate_draft("image", values)
    assert result["success"] is True
    assert result["draft"] == {**values, "model": short_key}
    assert values["model"] == model_id


def test_image_draft_preserves_platform_model_ids():
    values = {"prompt": "updated", "model": "new-platform-model", "source": "forfuner-ai"}
    result = API().agent_validate_draft("image", values)
    assert result["success"] is True
    assert result["draft"] == values


def test_image_draft_validation_does_not_insert_a_default_model():
    values = {"prompt": "updated"}
    result = API().agent_validate_draft("image", values)
    assert result["success"] is True
    assert result["draft"] == values


@pytest.mark.parametrize("model", ["lite", "doubao-seedream-5-0-lite-260128", "unknown-model"])
def test_image_draft_rejects_non_equivalent_api_key_models(model):
    assert API().agent_validate_draft("image", {"prompt": "updated", "model": model})["success"] is False


def test_image_draft_still_validates_resolution_after_model_normalization():
    result = API().agent_validate_draft("image", {"model": "doubao-seedream-5-0-pro-260628", "resolution": "4K"})
    assert result == {"success": False, "error": "Resolution is unsupported for this model"}


def test_history_restore_rejects_missing_reference_without_submission(tmp_path, monkeypatch):
    from backend.agent_control.drafts import restore_draft
    from backend.seedream.models import SeedreamRequest
    from backend.seedream.repository import BatchRepository

    monkeypatch.setenv("GAM_CONFIG", str(tmp_path / "config.json"))
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    api = API()
    image = tmp_path / "reference.png"
    Image.new("RGB", (300, 300), "green").save(image)
    repository = BatchRepository(api.storage_locations.ai_pic_cache_root)
    batch = repository.create_batch(SeedreamRequest(prompt="original", reference_image=str(image)))
    restored = restore_draft(api, "image", batch.local_id)
    assert restored["patch"]["prompt"] == "original"
    stored = Path(restored["patch"]["reference_image"])
    stored.unlink()
    import pytest

    with pytest.raises(ValueError, match="ASSET_MISSING"):
        restore_draft(api, "image", batch.local_id)


@pytest.mark.parametrize("duration", [4, 5, 6])
def test_agent_video_draft_accepts_gui_duration_choices(duration):
    from backend.agent_control.drafts import validate_draft

    validate_draft("video", {"first_frame": "", "duration": duration})


@pytest.mark.parametrize("duration", [-1, 3, 7, 15, 4.0, True])
def test_agent_video_draft_rejects_other_durations(duration):
    from backend.agent_control.drafts import validate_draft
    from backend.seedance.validation import ValidationError

    with pytest.raises(ValidationError) as caught:
        validate_draft("video", {"first_frame": "", "duration": duration})
    assert caught.value.code == "INVALID_DURATION"
