"""Transactional migration of project and AI cache storage locations.

The coordinator turns a settings save that changes storage roots into one
verifiable transaction: precheck every target, wait for the user to confirm a
specific precheck token, copy into a staging sibling on the target filesystem
without following symlinks, verify a size/count manifest plus every JSON
metadata file, publish the staging directory, and only then atomically commit the
whole settings draft. Any failure cleans up data this run created and keeps
the old config and source untouched; the source is never deleted.

The layer is pure orchestration with injected seams: the settings commit and
the activity queries of project/AI writers are callables supplied by the app
composition root, so nothing here performs hidden I/O or imports backend APIs.
"""

import json
import os
import shutil
import threading
import uuid
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.utils.ai_cache_paths import AI_PIC_CACHE_DIRNAME, AI_VIDEO_CACHE_DIRNAME
from src.utils.storage_locations import normalize_storage_path

PROJECT_LOCATION = "project"
AI_CACHE_LOCATION = "ai_cache"
_LOCATION_KINDS = {PROJECT_LOCATION, AI_CACHE_LOCATION}

# Staging directories live next to the target so the final publish is a
# same-filesystem rename.
_STAGING_SUFFIX = ".gam-migration"

ActivityProviders = Mapping[str, Callable[[], bool]]
ProgressCallback = Callable[[str, int, int], None]


class MigrationError(Exception):
    """A migration failure with the stage the user needs to react to."""

    def __init__(self, stage: str, reason: str, *, location: str | None = None):
        super().__init__(reason)
        self.stage = stage
        self.reason = reason
        self.location = location


@dataclass(frozen=True)
class LocationMigration:
    """One storage root to move; ``kind`` is ``project`` or ``ai_cache``."""

    kind: str
    source: Path
    target: Path


@dataclass(frozen=True)
class PrecheckEntry:
    kind: str
    source: Path
    target: Path
    file_count: int
    total_bytes: int


@dataclass(frozen=True)
class PrecheckReport:
    """Summary the user confirms; the token authorizes exactly one execute."""

    token: str
    entries: tuple[PrecheckEntry, ...]


@dataclass(frozen=True)
class _PendingMigration:
    token: str
    settings_draft: Mapping[str, Any]
    migrations: tuple[LocationMigration, ...]


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _nearest_existing_ancestor(path: Path) -> Path:
    """The path itself or its closest existing ancestor (always terminates at a filesystem root)."""
    anchor = path
    while not anchor.exists():
        anchor = anchor.parent
    return anchor


class StorageMigrationCoordinator:
    """Serialize precheck/confirm/execute for storage-location migrations."""

    def __init__(
        self,
        *,
        commit_config: Callable[[Mapping[str, Any]], Mapping[str, Any]],
        activity_providers: ActivityProviders | None = None,
        progress_callback: ProgressCallback | None = None,
    ):
        self._commit_config = commit_config
        self._activity_providers = dict(activity_providers or {})
        self._progress_callback = progress_callback
        self._state_lock = threading.Lock()
        self._execute_lock = threading.Lock()
        self._pending: _PendingMigration | None = None
        self._restart_required = False

    @property
    def restart_required(self) -> bool:
        """True once a migration committed; the runtime must restart."""
        return self._restart_required

    # ==================== Precheck ====================

    def precheck(
        self,
        migrations: list[LocationMigration] | tuple[LocationMigration, ...],
        settings_draft: Mapping[str, Any],
    ) -> PrecheckReport:
        """Validate every target and return a one-shot confirmation token."""
        normalized = tuple(self._normalize(migration) for migration in migrations)
        if not normalized:
            raise MigrationError("precheck", "no storage location changed")
        self._ensure_no_active_writers(stage="precheck")
        entries = tuple(self._precheck_one(migration) for migration in normalized)
        pending = _PendingMigration(
            token=uuid.uuid4().hex,
            settings_draft=dict(settings_draft),
            migrations=normalized,
        )
        with self._state_lock:
            self._pending = pending
        return PrecheckReport(token=pending.token, entries=entries)

    def _normalize(self, migration: LocationMigration) -> LocationMigration:
        if migration.kind not in _LOCATION_KINDS:
            raise MigrationError("precheck", f"unknown storage location kind: {migration.kind}")
        return LocationMigration(
            migration.kind,
            normalize_storage_path(Path(migration.source).expanduser()),
            normalize_storage_path(Path(migration.target).expanduser()),
        )

    def _ensure_no_active_writers(self, *, stage: str) -> None:
        active = sorted(name for name, is_active in self._activity_providers.items() if is_active())
        if active:
            raise MigrationError(
                stage,
                "active tasks may still write data: " + ", ".join(active),
            )

    def _precheck_one(self, migration: LocationMigration) -> PrecheckEntry:
        source, target = migration.source, migration.target
        self._check_path_relationship(source, target)
        self._check_target_state(migration)
        file_count, total_bytes = self._measure_source(migration)
        self._check_space(target, total_bytes)
        return PrecheckEntry(migration.kind, source, target, file_count, total_bytes)

    def _check_path_relationship(self, source: Path, target: Path) -> None:
        if source == target:
            raise MigrationError("precheck", "source and target are the same directory")
        if _is_within(target, source):
            raise MigrationError("precheck", "target is a descendant of the source")
        if _is_within(source, target):
            raise MigrationError("precheck", "target is an ancestor of the source")
        # A symlinked ancestor can make a lexically safe target physically
        # overlap the source, so repeat the check on resolved paths.
        real_source = Path(os.path.realpath(source))
        real_target = Path(os.path.realpath(target))
        if real_source == real_target or _is_within(real_target, real_source) or _is_within(real_source, real_target):
            raise MigrationError("precheck", "target resolves through a symlink into the source boundary")

    def _check_target_state(self, migration: LocationMigration) -> None:
        target = migration.target
        if target.is_symlink():
            raise MigrationError("precheck", "target must not be a symlink", location=migration.kind)
        if target.exists():
            if not target.is_dir():
                raise MigrationError("precheck", "target exists and is not a directory", location=migration.kind)
            if any(target.iterdir()):
                raise MigrationError("precheck", "target directory is not empty", location=migration.kind)
            if not os.access(target, os.W_OK):
                raise MigrationError("precheck", "target directory is not writable", location=migration.kind)
            return
        anchor = _nearest_existing_ancestor(target.parent)
        if not os.access(anchor, os.W_OK | os.X_OK):
            raise MigrationError("precheck", "target parent is not writable", location=migration.kind)

    def _measure_source(self, migration: LocationMigration) -> tuple[int, int]:
        file_count = 0
        total_bytes = 0
        for path in self._iter_scoped_files(migration):
            file_count += 1
            total_bytes += path.lstat().st_size
        return file_count, total_bytes

    def _iter_scoped_files(self, migration: LocationMigration):
        """Files in migration scope: the whole project tree, or the two shared AI cache subtrees."""
        for root, _ in self._scoped_roots(migration):
            for path in root.rglob("*"):
                if path.is_dir() and not path.is_symlink():
                    continue
                yield path

    def _check_space(self, target: Path, required_bytes: int) -> None:
        free = shutil.disk_usage(_nearest_existing_ancestor(target)).free
        if free < required_bytes:
            raise MigrationError(
                "precheck",
                f"insufficient space: need {required_bytes} bytes, only {free} available",
            )

    # ==================== Execute ====================

    def execute(self, token: str) -> None:
        """Run the confirmed migration and commit the whole settings draft."""
        with self._state_lock:
            pending = self._pending
        if pending is None or pending.token != token:
            raise MigrationError("execute", "missing or expired migration confirmation")
        if not self._execute_lock.acquire(blocking=False):
            raise MigrationError("execute", "a migration is already running")
        try:
            # Late activity keeps the confirmation token alive so the user can
            # retry once tasks finish; real failures require a fresh precheck.
            self._ensure_no_active_writers(stage="execute")
            self._run(pending)
        finally:
            self._execute_lock.release()

    def _run(self, pending: _PendingMigration) -> None:
        staged: list[tuple[LocationMigration, Path]] = []
        published: list[tuple[LocationMigration, bool]] = []
        try:
            for migration in pending.migrations:
                staged.append((migration, self._stage(migration, pending.token)))
            for migration, staging in staged:
                removed_empty = self._publish(migration, staging)
                published.append((migration, removed_empty))
            try:
                self._commit_config(pending.settings_draft)
            except Exception as error:
                raise MigrationError("commit", f"failed to save settings: {error}") from error
        except Exception as error:
            leftovers = self._rollback(staged[len(published) :], published)
            with self._state_lock:
                self._pending = None
            if leftovers:
                raise MigrationError(
                    "rollback",
                    "failed to remove published target(s), manual cleanup required: "
                    + ", ".join(str(path) for path in leftovers),
                ) from error
            raise
        with self._state_lock:
            self._pending = None
            self._restart_required = True

    def _rollback(
        self,
        unpublished: list[tuple[LocationMigration, Path]],
        published: list[tuple[LocationMigration, bool]],
    ) -> list[Path]:
        """Remove only data this run created; the source is never touched.

        Returns any published targets that could not be removed so the caller
        can surface that a formal target was left behind instead of hiding it.
        """
        leftovers: list[Path] = []
        for _, staging in unpublished:
            shutil.rmtree(staging, ignore_errors=True)
        for migration, removed_empty in reversed(published):
            shutil.rmtree(migration.target, ignore_errors=True)
            if migration.target.exists():
                leftovers.append(migration.target)
            elif removed_empty:
                with suppress(OSError):
                    migration.target.mkdir()
        return leftovers

    # ==================== Staged copy ====================

    def _scoped_roots(self, migration: LocationMigration, root: Path | None = None) -> list[tuple[Path, Path]]:
        """(source subtree, relative destination) pairs covered by one migration.

        ``root`` defaults to the migration source; pass the staging directory
        to enumerate the same scope on the copied side.
        """
        base = migration.source if root is None else root
        if migration.kind == AI_CACHE_LOCATION:
            return [
                (base / name, Path(name))
                for name in (AI_PIC_CACHE_DIRNAME, AI_VIDEO_CACHE_DIRNAME)
                if (base / name).exists()
            ]
        return [(base, Path("."))] if base.exists() else []

    def _stage(self, migration: LocationMigration, token: str) -> Path:
        staging = migration.target.parent / f".{migration.target.name}{_STAGING_SUFFIX}-{token[:8]}"
        if staging.exists() or staging.is_symlink():
            raise MigrationError("copy", f"staging path already exists: {staging}")
        staging.mkdir(parents=True)
        try:
            scopes = self._scoped_roots(migration)
            total = sum(1 for _ in self._iter_scoped_files(migration))
            copied = 0
            for scope_source, relative_destination in scopes:
                copied = self._copy_tree(scope_source, staging / relative_destination, migration.kind, copied, total)
            self._verify(migration, staging)
        except MigrationError:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        except OSError as error:
            shutil.rmtree(staging, ignore_errors=True)
            raise MigrationError("copy", f"failed to copy {migration.source}: {error}") from error
        return staging

    def _copy_tree(self, source_root: Path, staging_root: Path, kind: str, copied: int, total: int) -> int:
        """Copy a tree without following symlinks, reporting per-file progress."""
        staging_root.mkdir(parents=True, exist_ok=True)
        for dirpath, dirnames, filenames in os.walk(source_root, followlinks=False):
            current = Path(dirpath)
            target_dir = staging_root / current.relative_to(source_root)
            target_dir.mkdir(parents=True, exist_ok=True)
            for name in dirnames:
                entry = current / name
                if entry.is_symlink():
                    self._copy_symlink(entry, target_dir / name)
                    copied += 1
                    self._report_progress(kind, copied, total)
            for name in filenames:
                entry = current / name
                destination = target_dir / name
                if entry.is_symlink():
                    self._copy_symlink(entry, destination)
                else:
                    shutil.copy2(entry, destination)
                copied += 1
                self._report_progress(kind, copied, total)
        return copied

    @staticmethod
    def _copy_symlink(source: Path, destination: Path) -> None:
        os.symlink(os.readlink(source), destination)

    def _report_progress(self, kind: str, copied: int, total: int) -> None:
        if self._progress_callback is not None:
            self._progress_callback(kind, copied, total)

    # ==================== Verification ====================

    def _verify(self, migration: LocationMigration, staging: Path) -> None:
        source_manifest = self._build_manifest(migration, migration.source)
        staged_manifest = self._build_manifest(migration, staging)
        if source_manifest != staged_manifest:
            missing = sorted(set(source_manifest) - set(staged_manifest))
            detail = f", first missing: {missing[0]}" if missing else ""
            raise MigrationError("verify", f"copied content does not match the source{detail}")
        for relative in sorted(source_manifest):
            if not relative.endswith(".json") or source_manifest[relative][0] != "file":
                continue
            self._verify_json(migration, staging, relative)

    def _build_manifest(self, migration: LocationMigration, root: Path):
        manifest: dict[str, tuple[str, Any]] = {}
        for scope_root, relative_base in self._scoped_roots(migration, root):
            for dirpath, dirnames, filenames in os.walk(scope_root, followlinks=False):
                current = Path(dirpath)
                entries = [(name, True) for name in dirnames] + [(name, False) for name in filenames]
                for name, is_dir_entry in entries:
                    entry = current / name
                    if is_dir_entry and not entry.is_symlink():
                        continue
                    relative = (relative_base / entry.relative_to(scope_root)).as_posix()
                    if entry.is_symlink():
                        manifest[relative] = ("link", os.readlink(entry))
                    else:
                        manifest[relative] = ("file", entry.stat().st_size)
        return manifest

    def _verify_json(self, migration: LocationMigration, staging: Path, relative: str) -> None:
        try:
            source_data = json.loads((migration.source / relative).read_text(encoding="utf-8"))
            staged_data = json.loads((staging / relative).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise MigrationError("verify", f"key metadata {relative} is not valid JSON: {error}") from error
        if source_data != staged_data:
            raise MigrationError("verify", f"key metadata {relative} differs after copy")

    # ==================== Publish ====================

    def _publish(self, migration: LocationMigration, staging: Path) -> bool:
        """Rename the verified staging directory onto the target root."""
        target = migration.target
        removed_empty = False
        if target.is_symlink() or (target.exists() and not target.is_dir()):
            raise MigrationError("publish", "target changed since the confirmed precheck")
        try:
            if target.exists():
                # The confirmed precheck found an empty directory; rmdir only
                # succeeds when it is still empty, so nothing is overwritten.
                target.rmdir()
                removed_empty = True
            os.rename(staging, target)
        except OSError as error:
            if removed_empty:
                # Restore the pre-existing empty target so a failed publish
                # leaves the target as the confirmed precheck found it.
                with suppress(OSError):
                    target.mkdir()
            raise MigrationError("publish", f"failed to publish {target}: {error}") from error
        return removed_empty
