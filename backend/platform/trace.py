"""平台调用的客户端侧追踪日志。

为什么需要：pywebview 在 Windows 上刻意关闭了 devtools（`backend/main.py`：`debug=True`
会卡死 WebView2），平台交互失败时前端只能看到一句内联横幅，拿不到请求/响应的现场。
本模块把每一次平台 HTTP 交互落盘到 `logs/platform.log`。

**Token 绝不入日志**（design D2）：只记录方法、路径、HTTP 状态、平台返回码与响应摘要，
绝不记录任何请求头。另有一道 `_scrub` 兜底——万一上游异常消息里夹带了 token，
写盘前会被替换成 `[REDACTED]`。
"""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from src.utils.data_paths import data_root

_LOGGER_NAME = "gam.platform"
_LOG_FILE_NAME = "platform.log"
_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 3
_PAYLOAD_PREVIEW = 160
_REDACTED = "[REDACTED]"

_logger: logging.Logger | None = None


def log_path() -> Path:
    """平台日志文件路径（`GAM_DATA_ROOT` 可覆盖根目录，测试据此隔离）。"""
    return data_root() / "logs" / _LOG_FILE_NAME


def _resolve_logger() -> logging.Logger:
    """惰性初始化：未用平台源时不产生任何文件。"""
    global _logger
    if _logger is not None:
        return _logger
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    # 不向 root 传播：既不污染控制台，也避免被 SafeLogger 的 ERROR 处理器重复收集。
    logger.propagate = False
    if not logger.handlers:
        try:
            target = log_path()
            target.parent.mkdir(parents=True, exist_ok=True)
            handler: logging.Handler = RotatingFileHandler(
                target, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
            )
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
            )
        except OSError:
            # 日志写不了不能反过来把业务搞挂。
            handler = logging.NullHandler()
        logger.addHandler(handler)
    _logger = logger
    return logger


def _scrub(text: str, secret: str | None) -> str:
    return text.replace(secret, _REDACTED) if secret and secret in text else text


def _preview(payload: Any) -> str:
    if payload is None:
        return ""
    try:
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        text = str(payload)
    return text if len(text) <= _PAYLOAD_PREVIEW else f"{text[:_PAYLOAD_PREVIEW]}…"


def trace_success(
    method: str, path: str, status: int, code: Any, payload: Any = None, *, secret: str | None = None
) -> None:
    """一次成功的平台交互（含 business code 非 200 但 HTTP 正常的情形，由调用方判定）。"""
    detail = f"http={status} code={code}"
    preview = _preview(payload)
    if preview:
        detail = f"{detail} {preview}"
    _resolve_logger().info(_scrub(f"{method} {path} <- {detail}", secret))


def trace_failure(
    method: str, path: str, kind: str, message: str, *, secret: str | None = None
) -> None:
    """一次失败的平台交互：网络异常、非 JSON、业务错误、401 等。"""
    _resolve_logger().error(_scrub(f"{method} {path} !! {kind}: {message}", secret))


def trace_event(message: str, *, secret: str | None = None) -> None:
    """非 HTTP 的关键事件（如前端推送平台配置、切换 base URL）。"""
    _resolve_logger().info(_scrub(message, secret))
