"""适配器接口一致性：管理器调用的方法，真实适配器必须都有。

起因：图生图第一次真机联调时，`SeedreamBatchManager._build_platform_payload` 调用了
`self._platform.upload_asset(...)`，而 `PlatformImageClient` 只有 `generate_image`
（视频侧的 `PlatformVideoClient` 有 `upload_asset`，图片侧漏了）。带参考图的图片生成
100% 失败，且**既有单测全绿**——因为测试替身 `FakePlatformImages` 自带 `upload_asset`，
接口比真类还宽，把缺陷盖住了。

所以这里不靠"写更多假替身"来防，而是直接对着管理器源码做接口核对：替身可以随便写，
真类缺方法就会被抓。
"""

from __future__ import annotations

import inspect
import re

import pytest

from backend.platform.images import PlatformImageClient
from backend.platform.video import PlatformVideoClient
from backend.seedance import manager as seedance_manager
from backend.seedream import manager as seedream_manager

# 管理器里对平台适配器的两种调用形态：
#   self._platform.<method>(...)                 —— 直接持有适配器
#   self._remote_client_for(task).<method>(...)  —— 按任务来源二选一（平台/Ark）
_DIRECT_CALL = re.compile(r"self\._platform\.(\w+)\(")
_INDIRECT_CALL = re.compile(r"self\._remote_client_for\([^)]*\)\.(\w+)\(")


def _called_methods(module) -> set[str]:
    source = inspect.getsource(module)
    return set(_DIRECT_CALL.findall(source)) | set(_INDIRECT_CALL.findall(source))


@pytest.mark.parametrize(
    ("module", "adapter", "expected"),
    [
        (
            seedance_manager,
            PlatformVideoClient,
            # 管理器实际调用的方法；`_remote_client_for` 可能返回 Ark 客户端，
            # 所以 Ark 侧同名方法也算——这里断言的是"平台适配器至少覆盖这些"。
            {"upload_asset", "create_task", "get_task", "delete_task"},
        ),
        (
            seedream_manager,
            PlatformImageClient,
            {"upload_asset", "generate_image"},
        ),
    ],
)
def test_adapter_covers_manager_calls(module, adapter, expected):
    called = _called_methods(module)
    assert expected <= called, (
        f"管理器调用面发生变化（解析到 {sorted(called)}）；"
        f"若新增了平台调用，请同步本用例的 expected 集合"
    )
    missing = sorted(name for name in called if not hasattr(adapter, name))
    assert not missing, (
        f"{adapter.__name__} 缺少 {module.__name__} 调用的方法: {missing}。"
        f"真实适配器接口窄于管理器所需 → 该路径在真机上必然 AttributeError。"
    )
