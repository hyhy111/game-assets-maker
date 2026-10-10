"""Safe, durable audit events for desktop calls made with a user's Ark key."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.utils.app_config import ark_audit_enabled
from src.utils.data_paths import data_root

_WRITE_LOCK = threading.Lock()
_PROCESS_ID = uuid4().hex
_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar("ark_audit_context", default=None)
_MAX_BYTES = 5 * 1024 * 1024
_MAX_ARCHIVES = 5
_RETENTION_SECONDS = 90 * 24 * 3600
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_SAFE_CODE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,79}$")
_FIELDS = {
    "model",
    "size",
    "ratio",
    "duration",
    "input_images",
    "prompt_length",
    "prompt_sha256",
    "watermark",
    "generate_audio",
    "return_last_frame",
    "priority",
    "http_status",
    "request_id",
    "created",
    "generated_images",
    "output_tokens",
    "total_tokens",
    "data_count",
    "url_present",
    "remote_status",
    "video_url_present",
    "last_frame_url_present",
    "error_code",
    "error_type",
    "errno",
    "elapsed_ms",
    "persisted",
    "downloaded",
    "recovered_status",
    "response_bytes",
    "remote_id",
}


class AuditStorageError(RuntimeError):
    """A paid request was not sent because its pre-call audit could not be saved."""

    def __init__(self) -> None:
        super().__init__("Ark audit log is unavailable; the paid request was not sent")


@contextmanager
def audit_context(**ids: Any):
    """Attach existing local IDs without changing fake-client method signatures."""
    token = _CONTEXT.set(ids)
    try:
        yield ids
    finally:
        _CONTEXT.reset(token)


def _safe_id(value: Any) -> str | None:
    return value if isinstance(value, str) and _SAFE_ID.fullmatch(value) else None


def _safe_fields(values: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in values.items():
        if key not in _FIELDS or value is None:
            continue
        if key in {"request_id", "remote_id"}:
            value = _safe_id(value)
        elif key in {"error_code", "error_type", "remote_status", "recovered_status", "model", "size", "ratio"}:
            pattern = r"^[A-Za-z0-9:_.-]{1,80}$" if key == "ratio" else _SAFE_CODE
            value = value if isinstance(value, str) and re.fullmatch(pattern, value) else None
        elif key == "prompt_sha256":
            value = value if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) else None
        elif isinstance(value, bool):
            pass
        elif isinstance(value, int | float):
            value = value if 0 <= value < 10**12 else None
        else:
            value = None
        if value is not None:
            safe[key] = value
    return safe


def request_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract only metadata; never serialize request bodies or image bytes."""
    prompt = payload.get("prompt")
    content = payload.get("content")
    if not isinstance(prompt, str) and isinstance(content, list):
        prompt = next(
            (item.get("text") for item in content if isinstance(item, dict) and item.get("type") == "text"), None
        )
    image = payload.get("image")
    content_images = (
        sum(isinstance(item, dict) and item.get("type") == "image_url" for item in content)
        if isinstance(content, list)
        else 0
    )
    fields = {
        "model": payload.get("model"),
        "size": payload.get("size") or payload.get("resolution"),
        "ratio": payload.get("ratio"),
        "duration": payload.get("duration"),
        "watermark": payload.get("watermark"),
        "input_images": content_images or (len(image) if isinstance(image, list) else int(bool(image))),
        "generate_audio": payload.get("generate_audio"),
        "return_last_frame": payload.get("return_last_frame"),
        "priority": payload.get("priority"),
    }
    if isinstance(prompt, str):
        fields["prompt_length"] = len(prompt)
        fields["prompt_sha256"] = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    return _safe_fields(fields)


def response_fields(operation: str, response: dict[str, Any]) -> dict[str, Any]:
    if operation == "image.create":
        usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
        data = response.get("data") if isinstance(response.get("data"), list) else []
        return _safe_fields(
            {
                "model": response.get("model"),
                "created": response.get("created"),
                "generated_images": usage.get("generated_images"),
                "output_tokens": usage.get("output_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "data_count": len(data),
                "url_present": any(isinstance(item, dict) and bool(item.get("url")) for item in data),
            }
        )
    content = response.get("content") if isinstance(response.get("content"), dict) else {}
    return _safe_fields(
        {
            "remote_id": response.get("id"),
            "remote_status": response.get("status"),
            "video_url_present": bool(content.get("video_url")),
            "last_frame_url_present": bool(content.get("last_frame_url")),
        }
    )


def provider_request_id(headers: dict[str, str], body: bytes | None = None, secret: str = "") -> str | None:
    request_id = None
    for key, value in headers.items():
        if key.lower() in {"x-request-id", "request-id"}:
            request_id = _safe_id(value)
            break
    if request_id is None and body:
        try:
            parsed = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            return None
        if isinstance(parsed, dict):
            direct = _safe_id(parsed.get("request_id"))
            error = parsed.get("error")
            request_id = direct or (_safe_id(error.get("request_id")) if isinstance(error, dict) else None)
    return None if request_id and secret and secret in request_id else request_id


class ArkAudit:
    """Small synchronous JSONL journal, independent of the optional error logger."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path or data_root() / "logs" / "ark-custom-key.jsonl"

    def record(
        self,
        operation: str,
        phase: str,
        *,
        call_id: str | None = None,
        fields: dict[str, Any] | None = None,
        critical: bool = False,
        ids: dict[str, Any] | None = None,
    ) -> None:
        if not ark_audit_enabled():
            return
        context = ids if ids is not None else _CONTEXT.get() or {}
        entry = {
            "schema": 1,
            "process_id": _PROCESS_ID,
            "at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "call_id": call_id or _safe_id(context.get("call_id")),
            "operation": operation,
            "phase": phase,
            "batch_id": _safe_id(context.get("batch_id")),
            "attempt_index": context.get("attempt_index") if type(context.get("attempt_index")) is int else None,
            "task_id": _safe_id(context.get("task_id")),
            "remote_id": _safe_id(context.get("remote_id")),
            "fields": _safe_fields(fields or {}),
        }
        payload = (json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        try:
            with _WRITE_LOCK:
                if not ark_audit_enabled():
                    return
                path = self.path
                path.parent.mkdir(parents=True, exist_ok=True)
                self._rotate(path, len(payload))
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                try:
                    os.fchmod(fd, 0o600)
                    view = memoryview(payload)
                    while view:
                        view = view[os.write(fd, view) :]
                    os.fsync(fd)
                finally:
                    os.close(fd)
        except OSError as error:
            if critical:
                raise AuditStorageError() from error
            # Logging failures must not interrupt task polling or local recovery.
            print("Ark audit log write failed", flush=True)

    @staticmethod
    def _rotate(path: Path, incoming_bytes: int) -> None:
        if not path.exists():
            return
        stat = path.stat()
        if stat.st_size + incoming_bytes < _MAX_BYTES and time.time() - stat.st_mtime < 24 * 3600:
            return
        for index in range(_MAX_ARCHIVES, 0, -1):
            source = path.with_name(f"{path.name}.{index}")
            if source.exists():
                if index == _MAX_ARCHIVES or time.time() - source.stat().st_mtime > _RETENTION_SECONDS:
                    source.unlink()
                else:
                    source.replace(path.with_name(f"{path.name}.{index + 1}"))
        path.replace(path.with_name(f"{path.name}.1"))

    def begin(self, operation: str, *, payload: dict[str, Any] | None = None, paid: bool = False) -> AuditCall:
        call = AuditCall(self, operation, uuid4().hex, time.monotonic())
        fields = request_fields(payload or {})
        context = _CONTEXT.get()
        if context is not None and context.get("ratio"):
            fields.update(_safe_fields({"ratio": context["ratio"]}))
        self.record(operation, "intent", call_id=call.call_id, fields=fields, critical=paid)
        if context is not None:
            context["call_id"] = call.call_id
        return call

    def reconcile(self) -> None:
        """Label prior-process calls from journal evidence, never from billing guesses."""
        if not ark_audit_enabled():
            return
        path = self.path
        paths = [path.with_name(f"{path.name}.{index}") for index in range(_MAX_ARCHIVES, 0, -1)] + [path]
        calls: dict[str, dict[str, Any]] = {}
        for candidate in paths:
            try:
                lines = candidate.open(encoding="utf-8")
            except FileNotFoundError:
                continue
            except OSError:
                continue
            with lines:
                for line in lines:
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(event, dict) or event.get("operation") not in {"image.create", "video.create"}:
                        continue
                    call_id = _safe_id(event.get("call_id"))
                    if not call_id:
                        continue
                    if event.get("phase") == "intent":
                        if event.get("process_id") != _PROCESS_ID:
                            calls[call_id] = {"intent": event, "phases": set()}
                    elif call_id in calls:
                        calls[call_id]["phases"].add(event.get("phase"))
        settled = {"failure", "local_unknown", "local_failed", "download_succeeded", "download_failed", "recovered"}
        for call_id, item in calls.items():
            phases = item["phases"]
            if phases & settled or any(str(phase).startswith("interrupted_") for phase in phases):
                continue
            if "response_persisted" in phases or "task_persisted" in phases:
                phase = "interrupted_after_persistence"
            elif "parsed_response" in phases:
                phase = "interrupted_before_persistence"
            elif "http_response" in phases:
                phase = "interrupted_after_http"
            else:
                phase = "interrupted_unresolved"
            intent = item["intent"]
            self.record(
                intent["operation"],
                phase,
                call_id=call_id,
                ids={key: intent.get(key) for key in ("batch_id", "attempt_index", "task_id", "remote_id")},
            )


@dataclass(slots=True)
class AuditCall:
    audit: ArkAudit
    operation: str
    call_id: str
    started: float

    def event(self, phase: str, **fields: Any) -> None:
        self.audit.record(
            self.operation,
            phase,
            call_id=self.call_id,
            fields={"elapsed_ms": round((time.monotonic() - self.started) * 1000, 1), **fields},
        )
