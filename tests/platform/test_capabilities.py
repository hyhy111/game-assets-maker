"""可售能力清单：PlatformClient 取数 + PlatformFacade 信封（tasks 2.1/2.2）。"""

from __future__ import annotations

import pytest
from platform_test_helpers import FakeTransport, ajax_error, ajax_ok, reset_trace_logger

from backend.api.platform_api import PlatformFacade
from backend.platform.client import PlatformClient
from backend.platform.config import PlatformConfig

CAPABILITIES = {
    "video": {
        "models": [
            {"model": "doubao-seedance-2-0-260128", "resolutions": ["480p", "720p", "1080p"], "durations": [4, 5, 6]},
        ],
        "ratios": ["adaptive", "16:9", "1:1", "4:3"],
    },
    "image": {"models": [{"model": "doubao-seedream-5-0-pro-260628", "sizes": ["1K", "1.5K", "2K"]}]},
}


def test_client_get_capabilities_hits_endpoint_and_returns_payload():
    transport = FakeTransport(lambda m, u, h, b: ajax_ok(CAPABILITIES))
    client = PlatformClient("http://platform.test", "token-1", transport=transport)

    data = client.get_capabilities()

    assert data == CAPABILITIES
    method, url, headers, _ = transport.last
    assert (method, url) == ("GET", "http://platform.test/app/gen/capabilities")
    assert headers["Authorization"] == "Bearer token-1"


def _facade(transport: FakeTransport, token: str | None = "token-1") -> PlatformFacade:
    config = PlatformConfig(transport=transport)
    config.set("http://platform.test", token)
    return PlatformFacade(config)


def test_facade_wraps_success_in_envelope():
    transport = FakeTransport(lambda m, u, h, b: ajax_ok(CAPABILITIES))
    result = _facade(transport).capabilities()
    assert result["success"] is True
    assert result["data"] == CAPABILITIES


def test_facade_requires_login_without_calling_platform():
    transport = FakeTransport()
    result = _facade(transport, token=None).capabilities()
    assert result["success"] is False
    assert result["error"]["code"] == "PLATFORM_NOT_CONFIGURED"
    assert transport.requests == []


def test_facade_maps_401_to_unauthorized():
    transport = FakeTransport(lambda m, u, h, b: ajax_error(401, "未登录"))
    result = _facade(transport).capabilities()
    assert result["success"] is False
    assert result["error"]["code"] == "UNAUTHORIZED"


def test_facade_surfaces_business_error_message():
    transport = FakeTransport(lambda m, u, h, b: ajax_error(500, "平台暂时不可用"))
    result = _facade(transport).capabilities()
    assert result["success"] is False
    assert result["error"]["message"] == "平台暂时不可用"


def test_facade_never_falls_back_to_a_default_list():
    """design D3：拉不到就报错，绝不返回本地兜底清单（那会放出必失败的组合）。"""
    transport = FakeTransport(lambda m, u, h, b: ajax_error(500, "boom"))
    result = _facade(transport).capabilities()
    assert "data" not in result


def test_capabilities_request_is_logged_without_token(monkeypatch, tmp_path):
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    from backend.platform import trace as trace_module

    reset_trace_logger()
    try:
        transport = FakeTransport(lambda m, u, h, b: ajax_ok(CAPABILITIES))
        _facade(transport).capabilities()
        content = trace_module.log_path().read_text(encoding="utf-8")
        assert "GET /app/gen/capabilities" in content
        assert "token-1" not in content
    finally:
        reset_trace_logger()


# --------------------------------------------------------------------------
# 下架模型对能力清单的影响（gen-price-admin-tree）
# --------------------------------------------------------------------------

def test_capabilities_spec_excludes_disabled_rows():
    """下架 = 把该模型的行全部置停用；能力清单只认 status='1'，故该模型随之消失。

    这是"下架"能生效的机制保证——客户端不需要任何额外逻辑，
    清单里没有它，下拉框里就没有它。
    """
    # 只有生效行会进入 selectEffectiveCapabilities（见 Mapper XML 的 where status='1'）。
    # 这里锁住"清单按 status 过滤"这一契约：若日后改成不过滤，下架会静默失效。
    from pathlib import Path

    xml = Path("../RuoYi-Vue/ruoyi-business/src/main/resources/mapper/business/AppGenPriceMapper.xml")
    if not xml.is_file():
        xml = Path("I:/heyang/code/RuoYi-Vue/ruoyi-business/src/main/resources/mapper/business/AppGenPriceMapper.xml")
    if not xml.is_file():
        pytest.skip("External RuoYi server mapper is not available in this checkout")
    text = xml.read_text(encoding="utf-8")
    start = text.index('id="selectEffectiveCapabilities"')
    block = text[start:text.index("</select>", start)]
    assert "status = '1'" in block, "能力清单必须只取生效行，否则下架不会生效"
