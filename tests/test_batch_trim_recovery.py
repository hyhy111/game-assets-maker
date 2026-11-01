from pathlib import Path

import pytest
from PIL import Image

from backend.api import batch_trim_api
from backend.api.batch_trim_api import BatchTrimAPI


def make_frame(root: Path, action: str, filename: str, bounds: tuple[int, int, int, int]) -> None:
    target = root / "hero" / action / "output" / "03_hole_punched" / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (32, 32))
    image.paste((255, 0, 0, 255), bounds)
    image.save(target)


def test_retry_only_failed_animation_preserves_shared_crop_and_previous_outputs(tmp_path, monkeypatch):
    make_frame(tmp_path, "idle", "1.png", (2, 2, 30, 30))
    make_frame(tmp_path, "walk", "1.png", (10, 10, 20, 20))
    make_frame(tmp_path, "walk", "2.png", (10, 10, 20, 20))
    writer = batch_trim_api._imwrite_unicode

    def fail_second_walk_frame(path, image):
        if path.parent.name == "walk" and path.name.endswith("002.png"):
            raise OSError("Simulated disk write failure")
        return writer(path, image)

    monkeypatch.setattr(batch_trim_api, "_imwrite_unicode", fail_second_walk_frame)
    api = BatchTrimAPI(tmp_path)
    initial = api.execute_trim({"projectIds": ["hero/idle", "hero/walk"], "mode": "global"})
    assert [result["status"] for result in initial] == ["success", "partial"]
    assert initial[1]["failedFrames"][0]["reason"] == "Simulated disk write failure"
    assert initial[0]["globalCropBox"] == [2, 2, 30, 30]
    original_output = Path(initial[0]["outputPath"]) / "idle_trim_001.png"
    original_bytes = original_output.read_bytes()

    monkeypatch.setattr(batch_trim_api, "_imwrite_unicode", writer)
    retry = api.execute_trim(
        {"projectIds": ["hero/walk"], "mode": "global", "globalCropBox": initial[0]["globalCropBox"]}
    )
    assert len(retry) == 1 and retry[0]["status"] == "success"
    assert retry[0]["outputPath"] != initial[1]["outputPath"]
    assert original_output.read_bytes() == original_bytes
    with Image.open(Path(retry[0]["outputPath"]) / "walk_trim_001.png") as frame:
        assert frame.size == (28, 28)
    assert not (Path(retry[0]["outputPath"]).parent / "idle").exists()


@pytest.mark.parametrize(
    "bounds", [[0, 0, 0, 0], [0, 0, 2], [0, 0, 1.5, 2], [False, 0, 2, 2], [-1, 0, 2, 2], "invalid"]
)
def test_retry_bounds_are_validated_before_creating_output_directories(tmp_path, bounds):
    with pytest.raises(ValueError, match="Invalid global crop bounds"):
        BatchTrimAPI(tmp_path).execute_trim({"projectIds": ["hero/walk"], "globalCropBox": bounds})
    assert list(tmp_path.iterdir()) == []


def test_legacy_individual_request_needs_no_retry_metadata(tmp_path):
    make_frame(tmp_path, "walk", "1.png", (10, 10, 20, 20))
    result = BatchTrimAPI(tmp_path).execute_trim({"projectIds": ["hero/walk"], "mode": "individual"})[0]
    assert result["status"] == "success"
    assert "globalCropBox" not in result
    with Image.open(Path(result["outputPath"]) / "walk_001.png") as frame:
        assert frame.size == (10, 10)
