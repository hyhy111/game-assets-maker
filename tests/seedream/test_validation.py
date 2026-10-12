from __future__ import annotations

import base64
from pathlib import Path

import pytest
from PIL import Image

from backend.seedream.models import SeedreamRequest
from backend.seedream.validation import ValidationError, build_api_payload, validate_request


def _reference_png(tmp_path: Path) -> Path:
    path = tmp_path / "reference.png"
    Image.new("RGB", (64, 64), "#3156d9").save(path, format="PNG")
    return path


def test_pro_supports_1k_1_5k_2k():
    for resolution in ("1K", "1.5K", "2K"):
        validate_request(SeedreamRequest(prompt="hero", model="pro", resolution=resolution, ratio="16:9"))


def test_flash_supports_1k_1_5k_2k():
    for resolution in ("1K", "1.5K", "2K"):
        validate_request(SeedreamRequest(prompt="hero", model="flash", resolution=resolution, ratio="16:9"))


@pytest.mark.parametrize(
    "model", ("v45", "v40", "lite", "doubao-seedream-5-0-lite-260128", "doubao-seedream-5-0-260128")
)
def test_removed_models_are_rejected(model):
    with pytest.raises(ValidationError) as exc:
        validate_request(SeedreamRequest(prompt="hero", model=model, resolution="2K", ratio="16:9"))
    assert exc.value.code == "UNSUPPORTED_MODEL"


def test_4k_rejected_for_all_models():
    for model in ("pro", "flash"):
        with pytest.raises(ValidationError) as exc:
            validate_request(SeedreamRequest(prompt="hero", model=model, resolution="4K", ratio="16:9"))
        assert exc.value.code == "UNSUPPORTED_RESOLUTION"


def test_unsupported_model_rejected():
    with pytest.raises(ValidationError, match="model"):
        validate_request(SeedreamRequest(prompt="hero", model="mega", resolution="2K", ratio="16:9"))


def test_allowed_ratios():
    for ratio in ("1:1", "16:9", "9:16", "4:3", "3:4"):
        validate_request(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio=ratio))


def test_custom_ratio_rejected():
    with pytest.raises(ValidationError, match="ratio"):
        validate_request(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="21:9"))


def test_empty_prompt_rejected():
    with pytest.raises(ValidationError) as exc:
        validate_request(SeedreamRequest(prompt="  ", model="pro", resolution="1K", ratio="16:9"))
    assert exc.value.code == "PROMPT_REQUIRED"


def test_long_prompt_still_valid():
    validate_request(SeedreamRequest(prompt="x" * 1000, model="pro", resolution="1K", ratio="16:9"))


def test_build_api_payload_single_image_non_streaming_url_no_watermark():
    payload = build_api_payload(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9"))
    assert payload["model"] == "doubao-seedream-5-0-pro-260628"
    assert payload["prompt"] == "图片比例 16:9，hero"
    assert payload["size"] == "1K"
    assert payload["response_format"] == "url"
    assert payload["watermark"] is False
    assert "sequential_image_generation" not in payload


def test_build_api_payload_rejects_retired_lite():
    with pytest.raises(ValidationError) as exc:
        build_api_payload(SeedreamRequest(prompt="hero", model="lite", resolution="2K", ratio="1:1"))
    assert exc.value.code == "UNSUPPORTED_MODEL"


def test_build_api_payload_flash_model_id():
    payload = build_api_payload(SeedreamRequest(prompt="hero", model="flash", resolution="1.5K", ratio="1:1"))
    assert payload["model"] == "doubao-seedream-5-0-flash-260915"
    assert payload["size"] == "1.5K"


def test_build_api_payload_strips_prompt():
    payload = build_api_payload(SeedreamRequest(prompt="  hero  ", model="pro", resolution="1K", ratio="16:9"))
    assert payload["prompt"] == "图片比例 16:9，hero"


def test_image_request_defaults():
    request = SeedreamRequest(prompt="hero")
    assert (request.model, request.resolution, request.ratio, request.count) == ("pro", "2K", "16:9", 1)
    validate_request(request)


def test_count_valid_range_one_to_four():
    for count in (1, 2, 3, 4):
        validate_request(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=count))


def test_count_zero_rejected():
    with pytest.raises(ValidationError) as exc:
        validate_request(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=0))
    assert exc.value.code == "INVALID_COUNT"
    assert exc.value.field == "count"


def test_count_five_rejected():
    with pytest.raises(ValidationError) as exc:
        validate_request(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=5))
    assert exc.value.code == "INVALID_COUNT"


def test_count_non_integer_rejected():
    with pytest.raises(ValidationError) as exc:
        validate_request(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count="two"))  # type: ignore[arg-type]
    assert exc.value.code == "INVALID_COUNT"


def test_reference_image_is_sent_as_a_single_image_array_entry(tmp_path):
    path = _reference_png(tmp_path)
    payload = build_api_payload(SeedreamRequest(prompt="keep the pose", reference_image=str(path)))
    expected = "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
    assert payload["image"] == [expected]


def test_payload_without_reference_image_has_no_image_key():
    payload = build_api_payload(SeedreamRequest(prompt="hero"))
    assert "image" not in payload


def test_empty_reference_image_is_treated_as_absent():
    payload = build_api_payload(SeedreamRequest(prompt="hero", reference_image=""))
    assert "image" not in payload


def test_reference_image_must_exist(tmp_path):
    with pytest.raises(ValidationError) as exc:
        build_api_payload(SeedreamRequest(prompt="hero", reference_image=str(tmp_path / "missing.png")))
    assert exc.value.field == "reference_image"
    assert exc.value.code == "IMAGE_NOT_FOUND"


def test_reference_image_must_be_openable(tmp_path):
    path = tmp_path / "not-an-image.png"
    path.write_bytes(b"definitely not an image")
    with pytest.raises(ValidationError) as exc:
        build_api_payload(SeedreamRequest(prompt="hero", reference_image=str(path)))
    assert exc.value.field == "reference_image"
    assert exc.value.code == "INVALID_IMAGE"


def test_reference_image_must_use_a_supported_format(tmp_path):
    path = tmp_path / "reference.ico"
    Image.new("RGBA", (64, 64)).save(path, format="ICO")
    with pytest.raises(ValidationError) as exc:
        build_api_payload(SeedreamRequest(prompt="hero", reference_image=str(path)))
    assert exc.value.field == "reference_image"
    assert exc.value.code == "UNSUPPORTED_IMAGE_FORMAT"


def test_reference_image_must_be_under_30_mib(tmp_path, monkeypatch: pytest.MonkeyPatch):
    path = _reference_png(tmp_path)
    monkeypatch.setattr("backend.image_input.file_size", lambda _: 30 * 1024 * 1024)
    with pytest.raises(ValidationError) as exc:
        build_api_payload(SeedreamRequest(prompt="hero", reference_image=str(path)))
    assert exc.value.field == "reference_image"
    assert exc.value.code == "IMAGE_TOO_LARGE"


def test_reference_image_is_optional_in_validate_request(tmp_path):
    validate_request(SeedreamRequest(prompt="hero", reference_image=str(_reference_png(tmp_path))))
    validate_request(SeedreamRequest(prompt="hero", reference_image=None))
    validate_request(SeedreamRequest(prompt="hero"))


# --------------------------------------------------------------------------
# 参考图校验（gen-asset-local-delivery：补齐尺寸缺口 + 与视频接口区分）
# --------------------------------------------------------------------------

def _png(path, size):
    from PIL import Image

    Image.new("RGB", size).save(path)
    return path


@pytest.fixture
def ref(tmp_path):
    return tmp_path / "ref.png"


def test_reference_image_accepts_sizes_the_video_interface_rejects(ref):
    """图片接口比视频接口宽松：200×200 / 比例 0.2 这类图，视频拒、图片收。

    此前 _reference_image_format 只取格式、丢弃宽高，这些图会一路走到上游才失败。
    """
    from backend.seedream.validation import _reference_image_format

    for size in ((200, 200), (100, 500), (500, 100)):
        assert _reference_image_format(_png(ref, size)) == "PNG", size


def test_reference_image_rejects_what_both_interfaces_reject(ref):
    from backend.seedream.validation import ValidationError, _reference_image_format

    with pytest.raises(ValidationError):
        _reference_image_format(_png(ref, (7000, 7000)))  # 超出 6000px
    with pytest.raises(ValidationError):
        _reference_image_format(_png(ref, (100, 4000)))  # 比例 0.025 < 1/16


def test_reference_image_total_pixel_cap(ref):
    from backend.seedream.validation import ValidationError, _reference_image_format

    # 6000×6000 = 3600 万是上限；6000×7000 会被 6000px 先拦，这里用一个两者都在界内
    # 但总像素超标的组合不成立，故只断言上限本身可被触达：6000×6000 通过。
    assert _reference_image_format(_png(ref, (6000, 6000))) == "PNG"
    with pytest.raises(ValidationError):
        _reference_image_format(_png(ref, (6000, 6001)))
