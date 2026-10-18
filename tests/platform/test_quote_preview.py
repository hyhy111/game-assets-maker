"""SeedanceAPI.quote_video: live quote from the create page (task 5.2).

The quote drives the create-page credit estimate, so it must work from the
pricing parameters alone — before the user has picked a first frame.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from platform_test_helpers import FakeTransport, ajax_error, ajax_ok

from backend.api.seedance_api import SeedanceAPI
from backend.platform.config import PlatformConfig


class StubManager:
    """Quote never touches the manager; any call here is a bug."""

    def __getattr__(self, name):
        raise AssertionError(f"quote_video must not touch the task manager: {name}")


class MissingResolver:
    def resolve(self, local_id: str, kind: str):
        return None


def _quote_response(quote: int = 700) -> Any:
    return ajax_ok({
        "quote": quote,
        "baseCredits": 560,
        "multiplier": 1.25,
        "maxQueue": 3,
        "tierSource": "subscription",
        "priceDetail": "{}",
    })


@pytest.fixture
def transport() -> FakeTransport:
    return FakeTransport(lambda m, u, h, b: _quote_response())


@pytest.fixture
def api(transport: FakeTransport) -> SeedanceAPI:
    config = PlatformConfig(transport=transport)
    config.set("http://platform.test", "token-1")
    return SeedanceAPI(StubManager(), media_resolver=MissingResolver(), platform_config=config)


def test_quote_works_without_first_frame(api, transport):
    """The create page quotes as soon as model/duration/resolution are chosen."""
    result = api.quote_video({
        "model": "standard",
        "resolution": "720p",
        "ratio": "16:9",
        "duration": 5,
        "generate_audio": False,
    })

    assert result["success"] is True
    assert result["data"]["quote"] == 700
    body = json.loads(transport.last[3].decode("utf-8"))
    assert body["model"] == "doubao-seedance-2-0-260128"
    assert body["duration"] == 5
    assert body["resolution"] == "720p"
    # Pricing dimensions are model/duration/resolution — the image is never sent.
    assert body["content"] == [{"type": "text", "text": "quote"}]


def test_quote_requires_login(transport):
    api = SeedanceAPI(
        StubManager(), media_resolver=MissingResolver(), platform_config=PlatformConfig(transport=transport)
    )
    result = api.quote_video({"model": "standard", "duration": 5, "resolution": "720p"})
    assert result["success"] is False
    assert result["error"]["code"] == "PLATFORM_NOT_CONFIGURED"
    assert transport.requests == []


def test_quote_rejects_platform_unsupported_params(api, transport):
    for payload in (
        {"model": "standard", "resolution": "4k", "ratio": "adaptive", "duration": 5},
        {"model": "standard", "resolution": "720p", "ratio": "9:16", "duration": 5},
        {"model": "standard", "resolution": "720p", "ratio": "adaptive", "duration": 3},
        {"model": "standard", "resolution": "720p", "ratio": "adaptive", "duration": -1},
    ):
        result = api.quote_video(payload)
        assert result["success"] is False, payload
    # Rejected locally: no platform call was made.
    assert transport.requests == []


def test_video_quote_passes_an_upstream_model_id_through(api, transport):
    api.quote_video({"model": "doubao-seedance-9-9-brandnew", "resolution": "720p",
                     "ratio": "adaptive", "duration": 5})
    body = json.loads(transport.last[3].decode("utf-8"))
    assert body["model"] == "doubao-seedance-9-9-brandnew"


def test_unpriced_combination_surfaces_backend_message(transport):
    """e.g. an image model with no price row — the raw msg must reach the UI."""
    transport._handler = lambda m, u, h, b: ajax_error(500, "该参数组合暂未定价")
    config = PlatformConfig(transport=transport)
    config.set("http://platform.test", "token-1")
    api = SeedanceAPI(StubManager(), media_resolver=MissingResolver(), platform_config=config)

    result = api.quote_video({"model": "standard", "resolution": "720p", "ratio": "adaptive", "duration": 5})
    assert result["success"] is False
    assert result["error"]["message"] == "该参数组合暂未定价"


# --------------------------------------------------------------------------
# 图片报价（seedream）
# --------------------------------------------------------------------------

class StubBatchManager:
    """Image quote never touches the batch manager."""

    def __getattr__(self, name):
        raise AssertionError(f"quote_image must not touch the batch manager: {name}")


def _image_api(transport: FakeTransport) -> Any:
    from backend.api.seedream_api import SeedreamAPI

    config = PlatformConfig(transport=transport)
    config.set("http://platform.test", "token-1")
    return SeedreamAPI(StubBatchManager(), media_resolver=MissingResolver(), platform_config=config)


def test_image_quote_uses_model_and_size_only():
    transport = FakeTransport(lambda m, u, h, b: ajax_ok({"quote": 110, "baseCredits": 110, "multiplier": 1.0}))
    result = _image_api(transport).quote_image({"model": "pro", "resolution": "2K"})

    assert result["success"] is True
    assert result["data"]["quote"] == 110
    method, url, _, payload = transport.last
    assert (method, url) == ("POST", "http://platform.test/app/image/quote-preview")
    body = json.loads(payload.decode("utf-8"))
    assert body == {"model": "doubao-seedream-5-0-pro-260628", "size": "2K"}


def test_image_quote_rejects_an_unknown_size_but_not_an_unknown_model():
    # 尺寸是平台合法域，本地拦；模型属"能不能卖"，交给后端（能力清单已知，无需本地表）。
    transport = FakeTransport(lambda m, u, h, b: ajax_ok({"quote": 50}))
    api = _image_api(transport)
    assert api.quote_image({"model": "pro", "resolution": "8K"})["success"] is False
    assert transport.requests == []

    api.quote_image({"model": "doubao-seedream-9-9-brandnew", "resolution": "1K"})
    body = json.loads(transport.last[3].decode("utf-8"))
    assert body["model"] == "doubao-seedream-9-9-brandnew", "上游 ID 必须原样下发"


def test_image_quote_requires_login():
    from backend.api.seedream_api import SeedreamAPI

    transport = FakeTransport()
    api = SeedreamAPI(
        StubBatchManager(), media_resolver=MissingResolver(), platform_config=PlatformConfig(transport=transport)
    )
    result = api.quote_image({"model": "pro", "resolution": "1K"})
    assert result["success"] is False
    assert result["error"]["code"] == "PLATFORM_NOT_CONFIGURED"


def test_unpriced_image_model_surfaces_backend_message():
    """e.g. Flash currently has no price row — the raw msg must reach the UI."""
    transport = FakeTransport(lambda m, u, h, b: ajax_error(500, "该参数组合暂未定价"))
    result = _image_api(transport).quote_image({"model": "flash", "resolution": "1K"})
    assert result["success"] is False
    assert result["error"]["message"] == "该参数组合暂未定价"
