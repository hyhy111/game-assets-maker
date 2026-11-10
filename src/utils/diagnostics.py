"""Best-effort, redacted diagnostics for installed and source runtimes."""

from __future__ import annotations

import json
import logging
import re
import threading
import traceback
import urllib.request
from contextlib import contextmanager, suppress
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from src.utils.data_paths import data_root

_LOCK = threading.RLock()
_CHANNELS = {"seedream", "seedance", "network"}


def redact(text: str, secrets=()) -> str:
    for secret in sorted((str(value) for value in secrets if value), key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"https?://[^\s\"'<>]+", "[URL]", text)
    text = re.sub(r"data:[^\s\"'<>]+", "[DATA]", text)
    text = re.sub(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+\b", "[JWT]", text)
    text = re.sub(r"(?i)Bearer\s+[^\s,\"'<>]+", "Bearer [REDACTED]", text)
    text = re.sub(
        r"(?i)([\"']?(?:password|api[_-]?key|token|authorization|prompt|content)[\"']?\s*[:=]\s*)"
        r"(?:\"[^\"]*\"|'[^']*'|[^\s,}]+)",
        r"\1[REDACTED]",
        text,
    )
    return text.replace(str(Path.home()), "~")


def _safe_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if parsed.port:
            host += f":{parsed.port}"
        return (host + parsed.path)[:2048]
    except ValueError:
        return "[INVALID URL]"


def _write(channel: str, fields: dict, secrets=()) -> None:
    try:
        if channel not in _CHANNELS:
            return
        target = data_root() / "logs" / f"{channel}.log"
        payload = {key: redact(str(value), secrets)[:16384] for key, value in fields.items() if value is not None}
        with _LOCK:
            logger = logging.getLogger(f"gam.diagnostics.{channel}")
            logger.propagate = False
            logger.setLevel(logging.ERROR)
            if not logger.handlers or any(
                getattr(handler, "baseFilename", None) != str(target.resolve()) for handler in logger.handlers
            ):
                for handler in logger.handlers[:]:
                    logger.removeHandler(handler)
                    handler.close()
                target.parent.mkdir(parents=True, exist_ok=True)
                handler = RotatingFileHandler(target, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
                handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
                logger.addHandler(handler)
            logger.error(json.dumps(payload, ensure_ascii=False))
    except Exception:
        # Diagnostics must never replace the original failure or break offline work.
        pass


def record_exception(channel: str, error: Exception, *, secrets=(), **context) -> str:
    error_id = getattr(error, "_gam_error_id", "") or uuid4().hex[:12]
    with suppress(AttributeError, TypeError):
        error._gam_error_id = error_id
    tb = error.__traceback__
    operation = tb.tb_frame.f_code.co_name if tb else "unknown"
    identifiers = {}
    frame = tb
    while frame:
        for key in ("local_id", "batch_id", "attempt_index"):
            value = frame.tb_frame.f_locals.get(key)
            if key not in identifiers and isinstance(value, (str, int)):
                identifiers[key] = value
        frame = frame.tb_next
    try:
        message = str(error)
    except Exception:
        message = "[Exception message unavailable]"
    _write(
        channel,
        {
            "error_id": error_id,
            "operation": operation,
            "error_type": type(error).__name__,
            "message": message,
            "traceback": "".join(traceback.format_exception(error)),
            "request_id": getattr(error, "request_id", None),
            **identifiers,
            **context,
        },
        secrets,
    )
    return error_id


def record_network_error(method: str, url: str, error: Exception, *, secrets=(), **context) -> str:
    return record_exception("network", error, secrets=secrets, method=method, endpoint=_safe_url(url), **context)


def record_job_failure(method: str, url: str, payload: dict, *, secrets=()) -> None:
    """A successful HTTP exchange can still deliver a failed generation job."""
    status = str(payload.get("status", "")).lower()
    if status not in {"failed", "expired", "submission_unknown"}:
        return
    detail = payload.get("error")
    if isinstance(detail, str):
        try:
            detail = json.loads(detail)
        except ValueError:
            detail = {"message": detail}
    detail = detail if isinstance(detail, dict) else {}
    record_network_error(
        method,
        url,
        RuntimeError(str(detail.get("message") or f"Generation job {status}")),
        secrets=secrets,
        error_type="RemoteJobFailure",
        remote_status=status,
        code=detail.get("code"),
        job_id=payload.get("jobId") or payload.get("id"),
    )


def record_frontend_error(details: dict, *, secrets=()) -> None:
    if not isinstance(details, dict):
        return
    allowed = {
        key: details.get(key) for key in ("method", "http_status", "code", "error_type", "message", "stack", "retried")
    }
    allowed["endpoint"] = _safe_url(str(details.get("url", "")))
    allowed["source"] = "frontend"
    allowed["error_id"] = uuid4().hex[:12]
    _write("network", allowed, secrets)


@contextmanager
def logged_urlopen(request, **kwargs):
    """Preserve urllib exceptions and response bodies, including streamed-read errors."""
    url = request.full_url if isinstance(request, urllib.request.Request) else str(request)
    method = request.get_method() if isinstance(request, urllib.request.Request) else "GET"
    secrets = []
    if isinstance(request, urllib.request.Request):
        for name, value in request.header_items():
            if name.lower() in {"authorization", "x-api-key", "api-key"}:
                secrets.extend((value, value.removeprefix("Bearer ")))
    status = None
    try:
        with urllib.request.urlopen(request, **kwargs) as response:
            status = getattr(response, "status", None)
            yield response
    except Exception as error:
        record_network_error(method, url, error, secrets=secrets, http_status=getattr(error, "code", status))
        raise
