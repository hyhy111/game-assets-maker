"""生成来源标识。

单独成模块是为了断开循环依赖：`seedance/validation.py` 需要判断"是不是平台源"
来决定跳过本地模型白名单，而该常量原先定义在 `seedance/manager.py`，
manager 又依赖 validation——放这里两边都能引，且零依赖。
"""

from __future__ import annotations

#: 走我方平台代生成
PLATFORM_SOURCE = "forfuner-ai"

#: 用户自付 API Key 直连上游
API_KEY_SOURCE = "api-key"
