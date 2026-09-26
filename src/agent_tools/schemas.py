"""Shared JSON response helpers for Agent CLI commands."""

from enum import StrEnum
from typing import Any


class AgentErrorCode(StrEnum):
    """Stable error codes returned by the Agent CLI."""

    NOT_PROJECT_ROOT = "NOT_PROJECT_ROOT"
    VIDEO_NOT_FOUND = "VIDEO_NOT_FOUND"
    PROJECT_NOT_FOUND = "PROJECT_NOT_FOUND"
    PROJECT_EXISTS = "PROJECT_EXISTS"
    INVALID_STEP = "INVALID_STEP"
    STEP_INPUT_MISSING = "STEP_INPUT_MISSING"
    PROCESS_FAILED = "PROCESS_FAILED"
    UI_NOT_RUNNING = "UI_NOT_RUNNING"
    BATCH_TRIM_NO_SOURCE = "BATCH_TRIM_NO_SOURCE"
    CONFIG_INVALID = "CONFIG_INVALID"
    API_KEY_NOT_CONFIGURED = "API_KEY_NOT_CONFIGURED"
    SEEDANCE_NOT_FOUND = "SEEDANCE_NOT_FOUND"
    SEEDANCE_REQUEST_FAILED = "SEEDANCE_REQUEST_FAILED"
    WAIT_TIMEOUT = "WAIT_TIMEOUT"


def success_response(
    operation: str,
    data: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    next_actions: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Return a standard successful Agent CLI response."""
    return {
        "ok": True,
        "operation": operation,
        "data": data or {},
        "warnings": warnings or [],
        "next_actions": next_actions or [],
    }


def error_response(
    operation: str,
    code: AgentErrorCode | str,
    message: str,
    details: dict[str, Any] | None = None,
    next_actions: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Return a standard failed Agent CLI response."""
    return {
        "ok": False,
        "operation": operation,
        "error": {
            "code": code.value if isinstance(code, AgentErrorCode) else code,
            "message": message,
            "details": details or {},
        },
        "next_actions": next_actions or [],
    }


def redact_secret(value: Any, secret: str) -> Any:
    """Return a copy with a configured secret removed from values and mapping keys."""
    if not secret:
        return value
    if isinstance(value, str):
        return value.replace(secret, "[REDACTED]")
    if isinstance(value, dict):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            safe_key = key.replace(secret, "[REDACTED]") if isinstance(key, str) else key
            if isinstance(safe_key, str) and safe_key in redacted:
                suffix = 2
                while f"{safe_key}#{suffix}" in redacted:
                    suffix += 1
                safe_key = f"{safe_key}#{suffix}"
            redacted[safe_key] = redact_secret(item, secret)
        return redacted
    if isinstance(value, list):
        return [redact_secret(item, secret) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secret(item, secret) for item in value)
    return value
