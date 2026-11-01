"""Persist per-step initial frames and revision lineage without guessing legacy backup order."""

import hashlib
import os
import re
import tempfile
from pathlib import Path
from uuid import uuid4

_HASH = re.compile(r"[0-9a-f]{64}")
_GENERATION = re.compile(r"[0-9a-f]{32}")


def _safe(path: Path) -> Path:
    if path.resolve() != path or path.is_symlink():
        raise ValueError("FRAME_EDIT_INVALID_BACKUP")
    return path


def _base(project: Path, step: int) -> Path:
    if type(step) is not int or step not in (2, 3):
        raise ValueError("FRAME_EDIT_INVALID_STEP")
    return _safe(project.resolve() / "cache" / "frame_edits" / "initial" / f"step_{step}")


def _atomic_write(path: Path, content: bytes) -> None:
    _safe(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".initial-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def start_frame_edit_generation(project: Path, step: int) -> None:
    """Start a new initial-frame namespace after successful processing; retain older backups."""
    _atomic_write(_base(project, step) / "current", uuid4().hex.encode("ascii"))


def _generation(frame: Path, step: int) -> tuple[Path, bool]:
    base = _base(frame.parents[2], step)
    marker = _safe(base / "current")
    if marker.exists():
        generation = marker.read_text(encoding="ascii").strip()
        if not _GENERATION.fullmatch(generation):
            raise ValueError("FRAME_EDIT_INVALID_BACKUP")
        return _safe(base / generation), True
    return _safe(base / "legacy"), False


def _link(root: Path, frame: Path, payload: bytes) -> Path:
    revision = hashlib.sha256(payload).hexdigest()
    return _safe(root / "links" / frame.name / revision)


def _remember(root: Path, frame: Path, payload: bytes, initial: bytes) -> None:
    revision = hashlib.sha256(initial).hexdigest()
    image = _safe(root / "images" / f"{revision}.png")
    if not image.exists():
        _atomic_write(image, initial)
    elif image.read_bytes() != initial:
        raise ValueError("FRAME_EDIT_INVALID_BACKUP")
    # Write lineage before replacing the output PNG. A failed save only leaves an unused link.
    link = _link(root, frame, payload)
    if not link.exists():
        _atomic_write(link, revision.encode("ascii"))


def _backup_step_marker(directory: Path, filename: str, step: int) -> Path:
    return _safe(directory / f"{filename}.step_{step}")


def remember_backup_step(frame: Path, step: int, revision: str, created: bool) -> None:
    """Mark newly created backups by step; never guess provenance for older unmarked files."""
    directory = _safe(frame.parents[2] / "cache" / "frame_edits" / revision)
    if created or any(_backup_step_marker(directory, frame.name, item).is_file() for item in (2, 3)):
        _atomic_write(_backup_step_marker(directory, frame.name, step), b"1")


def _ambiguous_legacy_backups(frame: Path, step: int) -> bool:
    legacy = frame.parents[2] / "cache" / "frame_edits"
    if not legacy.exists():
        return False
    for directory in legacy.iterdir():
        if not _HASH.fullmatch(directory.name) or not (directory / frame.name).exists():
            continue
        known_current = _backup_step_marker(directory, frame.name, step).is_file()
        known_other = _backup_step_marker(directory, frame.name, 3 if step == 2 else 2).is_file()
        if known_current or not known_other:
            return True
    return False


def initial_frame(frame: Path, step: int, payload: bytes) -> bytes | None:
    """Return a proven baseline, capturing untouched frames lazily before the first manual edit."""
    root, processed_generation = _generation(frame, step)
    link = _link(root, frame, payload)
    if link.exists():
        revision = link.read_text(encoding="ascii").strip()
        if not _HASH.fullmatch(revision):
            return None
        image = _safe(root / "images" / f"{revision}.png")
        if not image.is_file():
            return None
        initial = image.read_bytes()
        return initial if hashlib.sha256(initial).hexdigest() == revision else None
    lineage = _safe(root / "links" / frame.name)
    if lineage.exists() and any(lineage.iterdir()):
        # An external replacement without recorded lineage is not a proven untouched output.
        return None
    # Old unscoped backups cannot prove a baseline for this step or processing generation.
    if not processed_generation and _ambiguous_legacy_backups(frame, step):
        return None
    _remember(root, frame, payload, payload)
    return payload


def remember_frame_edit(frame: Path, step: int, payload: bytes, initial: bytes | None) -> None:
    if initial is not None:
        root, _ = _generation(frame, step)
        _remember(root, frame, payload, initial)
