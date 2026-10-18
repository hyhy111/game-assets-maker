"""平台源的模型标识必须原样透传（task 4.3 / design D5）。

平台源下 model 是能力清单下发的**上游 ID**，不是客户端的本地短键
（standard/fast/mini、pro/flash/lite）。若客户端仍拿本地表拦截，运营上新模型时
用户会在客户端就被拒掉——而后端本该是权威校验方。这里锁住三件事：
本地表放行未知 ID、下游收到的就是该 ID、直连模式的白名单不受影响。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from backend.platform.sources import PLATFORM_SOURCE
from backend.seedance.models import SeedanceRequest
from backend.seedance.models import platform_model_id as video_model_id
from backend.seedance.validation import ValidationError, build_api_payload
from backend.seedance.validation import validate_request as validate_video
from backend.seedream.models import SeedreamRequest
from backend.seedream.models import platform_model_id as image_model_id
from backend.seedream.validation import ValidationError as SeedreamValidationError
from backend.seedream.validation import validate_request as validate_image

UNKNOWN_VIDEO = "doubao-seedance-9-9-brandnew"
UNKNOWN_IMAGE = "doubao-seedream-9-9-brandnew"


@pytest.fixture
def frame(tmp_path: Path) -> Path:
    path = tmp_path / "first.png"
    Image.new("RGB", (320, 320), (20, 160, 60)).save(path, format="PNG")
    return path


def _video_request(frame: Path, **overrides) -> SeedanceRequest:
    values = {
        "first_frame": frame,
        "prompt": "a scene",
        "model": UNKNOWN_VIDEO,
        "resolution": "720p",
        "ratio": "16:9",
        "duration": 5,
        "source": PLATFORM_SOURCE,
    }
    values.update(overrides)
    return SeedanceRequest(**values)


# ---- 模型标识归一 ----

def test_known_short_key_maps_to_upstream_id():
    assert video_model_id("standard") == "doubao-seedance-2-0-260128"
    assert video_model_id("mini") == "doubao-seedance-2-0-mini-260615"
    assert image_model_id("pro") == "doubao-seedream-5-0-pro-260628"


def test_unknown_id_passes_through_untouched():
    assert video_model_id(UNKNOWN_VIDEO) == UNKNOWN_VIDEO
    assert image_model_id(UNKNOWN_IMAGE) == UNKNOWN_IMAGE


# ---- 平台源：本地白名单不拦截 ----

def test_platform_source_accepts_a_model_the_local_table_does_not_know(frame):
    # 不抛异常即通过：合法域交给后端（parseVideo + 查价）
    validate_video(_video_request(frame))
    # 且该 ID 原样下发（build_api_payload 是直连路径的构造器，平台不经过它）
    assert video_model_id(UNKNOWN_VIDEO) == UNKNOWN_VIDEO


def test_platform_source_accepts_unpriced_resolution_locally(frame):
    # 平台侧会按定价行拒绝，客户端不该抢先拦（否则错误文案会变成客户端通用错误）
    validate_video(_video_request(frame, model="mini", resolution="1080p"))


def test_image_platform_source_accepts_unknown_model():
    validate_image(SeedreamRequest(prompt="x", model=UNKNOWN_IMAGE, resolution="2K", source=PLATFORM_SOURCE))


# ---- 直连源：白名单照旧 ----

def test_direct_source_still_rejects_an_unknown_model(frame):
    with pytest.raises(ValidationError):
        build_api_payload(_video_request(frame, source="api-key"))


def test_direct_source_still_rejects_a_resolution_the_model_lacks(frame):
    with pytest.raises(ValidationError):
        build_api_payload(_video_request(frame, model="mini", resolution="1080p", source="api-key"))


def test_image_direct_source_still_rejects_an_unknown_size():
    with pytest.raises(SeedreamValidationError):
        validate_image(SeedreamRequest(prompt="x", model="pro", resolution="8K", source="api-key"))
