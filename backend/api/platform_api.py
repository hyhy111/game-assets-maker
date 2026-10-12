"""平台源级操作的桥接门面。

与 SeedanceAPI / SeedreamAPI 的区别：那两个按**媒体域**组织，这个按**来源**组织——
可售能力清单回答的是"平台当前能卖什么"，对视频和图片是两个并列的分支，
不属于任何一个媒体域，因此单独放一处，也避免在两个 API 里各写一份。

返回信封与其它 API 保持一致：成功 `{success: True, data: ...}`，
失败 `{success: False, error: {code, message, field}}`。
"""

from __future__ import annotations

from typing import Any

from backend.platform.client import PlatformError, PlatformUnauthorizedError
from backend.platform.config import PlatformConfig


class PlatformFacade:
    """平台源级只读操作。"""

    def __init__(self, config: PlatformConfig) -> None:
        self._config = config

    def capabilities(self) -> dict[str, Any]:
        """可售能力清单（只读，无副作用）。

        客户端据此渲染平台源下的模型与参数选项；失败时**不返回任何兜底清单**
        ——回退到客户端预设表会把"必然失败的组合"重新放出来（design D3）。
        """
        if not self._config.configured():
            return _failure("PLATFORM_NOT_CONFIGURED", "请先登录 ForFuner 账户")
        try:
            return {"success": True, "data": self._config.client().get_capabilities()}
        except PlatformUnauthorizedError as error:
            return _failure("UNAUTHORIZED", error.message)
        except PlatformError as error:
            return _failure(error.code, error.message)
        except Exception as error:  # 网络异常等：原文透传，前端据此提示重试
            return _failure("INTERNAL_ERROR", str(error))


def _failure(code: str, message: str) -> dict[str, Any]:
    return {"success": False, "error": {"code": code, "message": message, "field": None}}
