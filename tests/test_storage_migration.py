"""Transactional storage migration: precheck, staged copy, publish and commit.

Covers the storage-location-management change: the precheck rejects unsafe
targets without touching files or configuration, active writers block the
migration, the staged copy never follows symlinks, and any failure keeps the
old config and source intact without leaving a formal target behind.
"""

import os
import shutil
from pathlib import Path

import pytest

from src.utils.storage_migration import (
    AI_CACHE_LOCATION,
    PROJECT_LOCATION,
    LocationMigration,
    MigrationError,
    StorageMigrationCoordinator,
)


@pytest.fixture
def source_project(tmp_path: Path) -> Path:
    root = tmp_path / "old" / "project"
    (root / "mage" / "walk" / "cache").mkdir(parents=True)
    (root / "mage" / "walk" / "cache" / "global_params.json").write_text('{"a": 1}', encoding="utf-8")
    (root / "mage" / "walk" / "output").mkdir(parents=True)
    (root / "mage" / "walk" / "output" / "frame.png").write_bytes(b"\x89PNG-frame")
    return root


@pytest.fixture
def source_cache(tmp_path: Path) -> Path:
    root = tmp_path / "old" / "cache"
    (root / "ai-pic-cache" / "batches" / "b1").mkdir(parents=True)
    (root / "ai-pic-cache" / "batches" / "b1" / "batch.json").write_text('{"id": "b1"}', encoding="utf-8")
    (root / "ai-video-cache" / "tasks" / "t1").mkdir(parents=True)
    (root / "ai-video-cache" / "tasks" / "t1" / "task.json").write_text('{"id": "t1"}', encoding="utf-8")
    (root / "ai-video-cache" / "edited-inputs").mkdir(parents=True)
    (root / "ai-video-cache" / "edited-inputs" / "edit.png").write_bytes(b"edit-bytes")
    return root


@pytest.fixture
def commits() -> list[dict]:
    return []


@pytest.fixture
def commit_config(commits: list[dict]):
    def _commit(draft: dict) -> dict:
        commits.append(draft)
        return draft

    return _commit


@pytest.fixture
def coordinator(commit_config) -> StorageMigrationCoordinator:
    return StorageMigrationCoordinator(commit_config=commit_config)


def _tree_snapshot(root: Path) -> dict[str, bytes | str]:
    snapshot: dict[str, bytes | str] = {}
    if not root.exists():
        return snapshot
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            snapshot[relative] = f"symlink:{os.readlink(path)}"
        elif path.is_file():
            snapshot[relative] = path.read_bytes()
        else:
            snapshot[relative] = "dir"
    return snapshot


# ==================== Precheck: path relationships ====================


def test_same_source_and_target_is_rejected(coordinator: StorageMigrationCoordinator, source_project: Path):
    before = _tree_snapshot(source_project)

    with pytest.raises(MigrationError, match="same"):
        coordinator.precheck(
            [LocationMigration(PROJECT_LOCATION, source_project, source_project)],
            {"project_dir": str(source_project)},
        )

    assert _tree_snapshot(source_project) == before


def test_equivalent_spellings_of_one_directory_are_rejected(
    coordinator: StorageMigrationCoordinator, source_project: Path
):
    spelled = source_project / ".." / "project"

    with pytest.raises(MigrationError, match="same"):
        coordinator.precheck(
            [LocationMigration(PROJECT_LOCATION, source_project, spelled)],
            {"project_dir": str(spelled)},
        )


def test_target_inside_source_is_rejected(coordinator: StorageMigrationCoordinator, source_project: Path):
    descendant = source_project / "nested" / "new-project"

    with pytest.raises(MigrationError, match="descendant|ancestor"):
        coordinator.precheck(
            [LocationMigration(PROJECT_LOCATION, source_project, descendant)],
            {"project_dir": str(descendant)},
        )

    assert not descendant.exists()


def test_target_as_ancestor_of_source_is_rejected(coordinator: StorageMigrationCoordinator, source_project: Path):
    ancestor = source_project.parent

    with pytest.raises(MigrationError, match="descendant|ancestor"):
        coordinator.precheck(
            [LocationMigration(PROJECT_LOCATION, source_project, ancestor)],
            {"project_dir": str(ancestor)},
        )

    assert (source_project / "mage").is_dir()


# ==================== Precheck: target state ====================


def test_non_empty_target_is_accepted_and_preserved(
    coordinator: StorageMigrationCoordinator,
    source_project: Path,
    tmp_path: Path,
    commits: list[dict],
):
    target = tmp_path / "new" / "project"
    target.mkdir(parents=True)
    (target / "pre-existing.txt").write_text("keep me", encoding="utf-8")
    source_before = _tree_snapshot(source_project)
    target_before = _tree_snapshot(target)
    draft = {"project_dir": str(target)}

    report = coordinator.precheck(
        [LocationMigration(PROJECT_LOCATION, source_project, target)],
        draft,
    )

    assert _tree_snapshot(source_project) == source_before
    assert _tree_snapshot(target) == target_before
    assert commits == []

    coordinator.execute(report.token)

    assert (target / "pre-existing.txt").read_text(encoding="utf-8") == "keep me"
    assert (target / "mage" / "walk" / "output" / "frame.png").is_file()
    assert (source_project / "mage" / "walk" / "output" / "frame.png").is_file()
    assert commits == [draft]


def test_non_empty_ai_cache_target_is_accepted_and_preserved(
    coordinator: StorageMigrationCoordinator,
    source_cache: Path,
    tmp_path: Path,
    commits: list[dict],
):
    target = tmp_path / "new" / "cache"
    target.mkdir(parents=True)
    (target / "pre-existing.txt").write_text("keep me", encoding="utf-8")
    source_before = _tree_snapshot(source_cache)
    target_before = _tree_snapshot(target)
    draft = {"seedance": {"cache_dir": str(target)}}

    report = coordinator.precheck(
        [LocationMigration(AI_CACHE_LOCATION, source_cache, target)],
        draft,
    )

    assert _tree_snapshot(source_cache) == source_before
    assert _tree_snapshot(target) == target_before
    assert commits == []

    coordinator.execute(report.token)

    assert (target / "pre-existing.txt").read_text(encoding="utf-8") == "keep me"
    assert (target / "ai-pic-cache" / "batches" / "b1" / "batch.json").is_file()
    assert (source_cache / "ai-pic-cache" / "batches" / "b1" / "batch.json").is_file()
    assert commits == [draft]


@pytest.mark.parametrize("occupant", ["file", "directory", "symlink"])
def test_conflicting_target_path_is_rejected(
    coordinator: StorageMigrationCoordinator, source_project: Path, tmp_path: Path, occupant: str
):
    target = tmp_path / "new" / "project"
    target.mkdir(parents=True)
    conflict = target / "mage"
    if occupant == "file":
        conflict.write_text("existing file", encoding="utf-8")
    elif occupant == "directory":
        conflict.mkdir()
    else:
        conflict.symlink_to("elsewhere")

    with pytest.raises(MigrationError, match="conflicting path: mage"):
        coordinator.precheck(
            [LocationMigration(PROJECT_LOCATION, source_project, target)],
            {"project_dir": str(target)},
        )

    assert conflict.exists() or conflict.is_symlink()


@pytest.mark.parametrize("occupant", ["file", "directory", "symlink"])
def test_conflicting_ai_cache_target_path_is_rejected(
    coordinator: StorageMigrationCoordinator,
    source_cache: Path,
    tmp_path: Path,
    occupant: str,
):
    target = tmp_path / "new" / "cache"
    target.mkdir(parents=True)
    conflict = target / "ai-pic-cache"
    if occupant == "file":
        conflict.write_text("existing file", encoding="utf-8")
    elif occupant == "directory":
        conflict.mkdir()
    else:
        conflict.symlink_to("elsewhere")

    with pytest.raises(MigrationError, match="conflicting path: ai-pic-cache"):
        coordinator.precheck(
            [LocationMigration(AI_CACHE_LOCATION, source_cache, target)],
            {"seedance": {"cache_dir": str(target)}},
        )

    assert conflict.exists() or conflict.is_symlink()


def test_conflict_prevents_the_entire_double_location_transaction(
    coordinator: StorageMigrationCoordinator,
    source_project: Path,
    source_cache: Path,
    tmp_path: Path,
    commits: list[dict],
):
    project_target = tmp_path / "new" / "project"
    cache_target = tmp_path / "new" / "cache"
    project_target.mkdir(parents=True)
    cache_target.mkdir(parents=True)
    (project_target / "mage").mkdir()
    (cache_target / "pre-existing.txt").write_text("keep me", encoding="utf-8")
    project_before = _tree_snapshot(project_target)
    cache_before = _tree_snapshot(cache_target)
    source_project_before = _tree_snapshot(source_project)
    source_cache_before = _tree_snapshot(source_cache)

    with pytest.raises(MigrationError, match="conflicting path: mage"):
        coordinator.precheck(
            [
                LocationMigration(PROJECT_LOCATION, source_project, project_target),
                LocationMigration(AI_CACHE_LOCATION, source_cache, cache_target),
            ],
            {"project_dir": str(project_target), "seedance": {"cache_dir": str(cache_target)}},
        )

    assert _tree_snapshot(project_target) == project_before
    assert _tree_snapshot(cache_target) == cache_before
    assert _tree_snapshot(source_project) == source_project_before
    assert _tree_snapshot(source_cache) == source_cache_before
    assert commits == []


def test_unwritable_target_parent_is_rejected(
    coordinator: StorageMigrationCoordinator, source_project: Path, tmp_path: Path
):
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root ignores permission bits")
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o555)
    try:
        with pytest.raises(MigrationError, match="writable"):
            coordinator.precheck(
                [LocationMigration(PROJECT_LOCATION, source_project, locked / "project")],
                {"project_dir": str(locked / "project")},
            )
    finally:
        locked.chmod(0o755)

    assert not (locked / "project").exists()


def test_insufficient_space_is_rejected(
    coordinator: StorageMigrationCoordinator,
    source_project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    target = tmp_path / "new" / "project"
    target.parent.mkdir(parents=True)
    required = sum(path.stat().st_size for path in source_project.rglob("*") if path.is_file())
    fake_usage = shutil.disk_usage(target.parent)._replace(free=required - 1)
    monkeypatch.setattr(shutil, "disk_usage", lambda path: fake_usage)

    with pytest.raises(MigrationError, match="space"):
        coordinator.precheck(
            [LocationMigration(PROJECT_LOCATION, source_project, target)],
            {"project_dir": str(target)},
        )

    assert not target.exists()


# ==================== Precheck: symlink boundaries ====================


def test_symlink_target_is_rejected(coordinator: StorageMigrationCoordinator, source_project: Path, tmp_path: Path):
    real = tmp_path / "real-target"
    real.mkdir()
    link = tmp_path / "link-target"
    link.symlink_to(real, target_is_directory=True)

    with pytest.raises(MigrationError, match="symlink"):
        coordinator.precheck(
            [LocationMigration(PROJECT_LOCATION, source_project, link)],
            {"project_dir": str(link)},
        )

    assert list(real.iterdir()) == []


def test_target_through_symlinked_ancestor_into_source_is_rejected(
    coordinator: StorageMigrationCoordinator, source_project: Path, tmp_path: Path
):
    alias = tmp_path / "alias"
    alias.symlink_to(source_project.parent, target_is_directory=True)

    with pytest.raises(MigrationError, match="same|descendant|ancestor|symlink"):
        coordinator.precheck(
            [LocationMigration(PROJECT_LOCATION, source_project, alias / "project")],
            {"project_dir": str(alias / "project")},
        )


# ==================== Precheck: success and summary ====================


def test_valid_precheck_returns_summary_without_modifying_anything(
    coordinator: StorageMigrationCoordinator, source_project: Path, tmp_path: Path
):
    target = tmp_path / "new" / "project"
    target.parent.mkdir(parents=True)
    before = _tree_snapshot(source_project)

    report = coordinator.precheck(
        [LocationMigration(PROJECT_LOCATION, source_project, target)],
        {"project_dir": str(target)},
    )

    assert report.token
    assert len(report.entries) == 1
    entry = report.entries[0]
    assert entry.kind == PROJECT_LOCATION
    assert entry.source == source_project
    assert entry.target == target
    assert entry.file_count == 2
    assert entry.total_bytes == len('{"a": 1}') + len(b"\x89PNG-frame")
    assert not target.exists()
    assert _tree_snapshot(source_project) == before


def test_empty_target_directory_is_accepted(coordinator: StorageMigrationCoordinator, tmp_path: Path):
    target = tmp_path / "empty-target"
    target.mkdir()

    report = coordinator.precheck([LocationMigration(PROJECT_LOCATION, tmp_path / "missing-source", target)], {})

    assert report.entries[0].file_count == 0
    assert target.is_dir()


def test_precheck_without_changes_is_rejected(coordinator: StorageMigrationCoordinator):
    with pytest.raises(MigrationError, match="no storage location"):
        coordinator.precheck([], {"language": "en"})


# ==================== Staged copy ====================


def _run(coordinator: StorageMigrationCoordinator, migrations, draft):
    report = coordinator.precheck(migrations, draft)
    coordinator.execute(report.token)


def test_project_tree_copies_completely_and_source_stays_untouched(
    coordinator: StorageMigrationCoordinator, source_project: Path, tmp_path: Path
):
    target = tmp_path / "new" / "project"
    target.parent.mkdir(parents=True)
    progress: list[tuple[str, int, int]] = []
    coordinator._progress_callback = lambda kind, copied, total: progress.append((kind, copied, total))
    before = _tree_snapshot(source_project)

    _run(
        coordinator,
        [LocationMigration(PROJECT_LOCATION, source_project, target)],
        {"project_dir": str(target)},
    )

    assert coordinator.restart_required is True
    assert _tree_snapshot(target) == before
    assert _tree_snapshot(source_project) == before
    assert [copied for _, copied, _ in progress] == sorted(copied for _, copied, _ in progress)
    assert progress[-1][1] == progress[-1][2] == 2
    assert all(kind == PROJECT_LOCATION for kind, _, _ in progress)


def test_symlinks_are_preserved_not_followed(
    coordinator: StorageMigrationCoordinator, source_project: Path, tmp_path: Path
):
    (source_project / "mage" / "walk" / "output" / "latest.png").symlink_to("frame.png")
    (source_project / "current").symlink_to("mage", target_is_directory=True)
    target = tmp_path / "new" / "project"
    target.parent.mkdir(parents=True)

    _run(coordinator, [LocationMigration(PROJECT_LOCATION, source_project, target)], {"project_dir": str(target)})

    copied_file_link = target / "mage" / "walk" / "output" / "latest.png"
    assert copied_file_link.is_symlink()
    assert os.readlink(copied_file_link) == "frame.png"
    copied_dir_link = target / "current"
    assert copied_dir_link.is_symlink()
    assert os.readlink(copied_dir_link) == "mage"
    # The link target was copied as an entry, not flattened through the link.
    assert (target / "mage" / "walk" / "output" / "frame.png").is_file()


def test_ai_cache_scope_only_copies_the_two_shared_subtrees(
    coordinator: StorageMigrationCoordinator, source_cache: Path, tmp_path: Path
):
    (source_cache / "other-data").mkdir()
    (source_cache / "other-data" / "unrelated.bin").write_bytes(b"not-migrated")
    target = tmp_path / "new" / "cache"
    target.parent.mkdir(parents=True)

    _run(
        coordinator,
        [LocationMigration(AI_CACHE_LOCATION, source_cache, target)],
        {"seedance": {"cache_dir": str(target)}},
    )

    assert (target / "ai-pic-cache" / "batches" / "b1" / "batch.json").is_file()
    assert (target / "ai-video-cache" / "tasks" / "t1" / "task.json").is_file()
    assert (target / "ai-video-cache" / "edited-inputs" / "edit.png").read_bytes() == b"edit-bytes"
    assert not (target / "other-data").exists()
    assert (source_cache / "other-data" / "unrelated.bin").read_bytes() == b"not-migrated"


def test_verify_detects_a_missing_file_and_cleans_up(
    coordinator: StorageMigrationCoordinator, source_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    target = tmp_path / "new" / "project"
    target.parent.mkdir(parents=True)
    real_copy2 = shutil.copy2

    def skip_frame(source, destination):
        if Path(source).name == "frame.png":
            return None
        return real_copy2(source, destination)

    monkeypatch.setattr(shutil, "copy2", skip_frame)
    before = _tree_snapshot(source_project)

    with pytest.raises(MigrationError) as caught:
        _run(coordinator, [LocationMigration(PROJECT_LOCATION, source_project, target)], {})

    assert caught.value.stage == "verify"
    assert not target.exists()
    assert not list(target.parent.glob("*.gam-migration-*"))
    assert _tree_snapshot(source_project) == before


# ==================== Publish, atomic commit and restart state ====================


def test_single_path_migration_commits_draft_and_requires_restart(
    coordinator: StorageMigrationCoordinator, source_project: Path, tmp_path: Path, commits: list[dict]
):
    target = tmp_path / "new" / "project"
    target.parent.mkdir(parents=True)
    draft = {"project_dir": str(target), "language": "en"}

    _run(coordinator, [LocationMigration(PROJECT_LOCATION, source_project, target)], draft)

    assert coordinator.restart_required is True
    assert commits == [draft]
    assert (target / "mage" / "walk" / "output" / "frame.png").is_file()


def test_double_migration_commits_both_locations_in_one_transaction(
    coordinator: StorageMigrationCoordinator,
    source_project: Path,
    source_cache: Path,
    tmp_path: Path,
    commits: list[dict],
):
    project_target = tmp_path / "new" / "project"
    cache_target = tmp_path / "new" / "cache"
    project_target.parent.mkdir(parents=True)
    draft = {
        "project_dir": str(project_target),
        "seedance": {"cache_dir": str(cache_target)},
        "language": "en",
    }

    _run(
        coordinator,
        [
            LocationMigration(PROJECT_LOCATION, source_project, project_target),
            LocationMigration(AI_CACHE_LOCATION, source_cache, cache_target),
        ],
        draft,
    )

    assert coordinator.restart_required is True
    assert commits == [draft]
    assert (project_target / "mage").is_dir()
    assert (cache_target / "ai-video-cache" / "tasks" / "t1" / "task.json").is_file()


def test_copy_interruption_keeps_source_config_and_drops_staging(
    coordinator: StorageMigrationCoordinator,
    source_project: Path,
    tmp_path: Path,
    commits: list[dict],
    monkeypatch: pytest.MonkeyPatch,
):
    target = tmp_path / "new" / "project"
    target.parent.mkdir(parents=True)
    calls = {"count": 0}
    real_copy2 = shutil.copy2

    def fail_on_second(source, destination):
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("disk vanished")
        return real_copy2(source, destination)

    monkeypatch.setattr(shutil, "copy2", fail_on_second)
    before = _tree_snapshot(source_project)

    with pytest.raises(MigrationError) as caught:
        _run(coordinator, [LocationMigration(PROJECT_LOCATION, source_project, target)], {"project_dir": str(target)})

    assert caught.value.stage == "copy"
    assert not target.exists()
    assert not list(target.parent.glob("*.gam-migration-*"))
    assert commits == []
    assert coordinator.restart_required is False
    assert _tree_snapshot(source_project) == before


def test_publish_failure_leaves_no_formal_target(
    coordinator: StorageMigrationCoordinator,
    source_project: Path,
    tmp_path: Path,
    commits: list[dict],
    monkeypatch: pytest.MonkeyPatch,
):
    target = tmp_path / "new" / "project"
    target.parent.mkdir(parents=True)
    monkeypatch.setattr(os, "rename", lambda source, destination: (_ for _ in ()).throw(OSError("rename denied")))

    with pytest.raises(MigrationError) as caught:
        _run(coordinator, [LocationMigration(PROJECT_LOCATION, source_project, target)], {})

    assert caught.value.stage == "publish"
    assert not target.exists()
    assert not list(target.parent.glob("*.gam-migration-*"))
    assert commits == []
    assert (source_project / "mage").is_dir()


def test_publish_failure_recreates_preexisting_empty_target(
    coordinator: StorageMigrationCoordinator,
    source_project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    target = tmp_path / "new" / "project"
    target.mkdir(parents=True)  # pre-existing empty target confirmed by precheck
    monkeypatch.setattr(os, "rename", lambda source, destination: (_ for _ in ()).throw(OSError("rename denied")))

    with pytest.raises(MigrationError, match="publish"):
        _run(coordinator, [LocationMigration(PROJECT_LOCATION, source_project, target)], {})

    # The failed publish must leave the target as the precheck found it.
    assert target.is_dir()
    assert not any(target.iterdir())
    assert not list(target.parent.glob("*.gam-migration-*"))


def test_conflict_after_confirmation_does_not_overwrite_the_target(
    coordinator: StorageMigrationCoordinator,
    source_project: Path,
    tmp_path: Path,
    commits: list[dict],
):
    target = tmp_path / "new" / "project"
    target.mkdir(parents=True)
    report = coordinator.precheck(
        [LocationMigration(PROJECT_LOCATION, source_project, target)],
        {"project_dir": str(target)},
    )
    (target / "mage").mkdir()
    (target / "mage" / "user-file.txt").write_text("keep me", encoding="utf-8")

    with pytest.raises(MigrationError, match="conflicting path: mage") as caught:
        coordinator.execute(report.token)

    assert caught.value.stage == "publish"
    assert (target / "mage" / "user-file.txt").read_text(encoding="utf-8") == "keep me"
    assert not list(target.parent.glob("*.gam-migration-*"))
    assert (source_project / "mage" / "walk" / "output" / "frame.png").is_file()
    assert commits == []


def test_second_publish_failure_rolls_back_only_new_entries_from_existing_target(
    coordinator: StorageMigrationCoordinator,
    source_project: Path,
    source_cache: Path,
    tmp_path: Path,
    commits: list[dict],
    monkeypatch: pytest.MonkeyPatch,
):
    project_target = tmp_path / "new" / "project"
    cache_target = tmp_path / "new" / "cache"
    project_target.mkdir(parents=True)
    cache_target.mkdir(parents=True)
    (project_target / "project-note.txt").write_text("keep project", encoding="utf-8")
    (cache_target / "cache-note.txt").write_text("keep cache", encoding="utf-8")
    original_publish = coordinator._publish

    def fail_cache_publish(migration: LocationMigration, staging: Path):
        if migration.kind == AI_CACHE_LOCATION:
            raise MigrationError("publish", "simulated cache publish failure")
        return original_publish(migration, staging)

    monkeypatch.setattr(coordinator, "_publish", fail_cache_publish)

    with pytest.raises(MigrationError, match="simulated cache publish failure") as caught:
        _run(
            coordinator,
            [
                LocationMigration(PROJECT_LOCATION, source_project, project_target),
                LocationMigration(AI_CACHE_LOCATION, source_cache, cache_target),
            ],
            {"project_dir": str(project_target), "seedance": {"cache_dir": str(cache_target)}},
        )

    assert caught.value.stage == "publish"
    assert (project_target / "project-note.txt").read_text(encoding="utf-8") == "keep project"
    assert (cache_target / "cache-note.txt").read_text(encoding="utf-8") == "keep cache"
    assert not (project_target / "mage").exists()
    assert not (cache_target / "ai-pic-cache").exists()
    assert (source_project / "mage" / "walk" / "output" / "frame.png").is_file()
    assert (source_cache / "ai-pic-cache" / "batches" / "b1" / "batch.json").is_file()
    assert commits == []


def test_commit_failure_rolls_back_published_targets(source_project: Path, source_cache: Path, tmp_path: Path):
    def broken_commit(draft):
        raise OSError("config disk full")

    coordinator = StorageMigrationCoordinator(commit_config=broken_commit)
    project_target = tmp_path / "new" / "project"
    cache_target = tmp_path / "new" / "cache"
    project_target.mkdir(parents=True)
    cache_target.mkdir(parents=True)
    (project_target / "project-note.txt").write_text("keep project", encoding="utf-8")
    (cache_target / "cache-note.txt").write_text("keep cache", encoding="utf-8")

    with pytest.raises(MigrationError) as caught:
        _run(
            coordinator,
            [
                LocationMigration(PROJECT_LOCATION, source_project, project_target),
                LocationMigration(AI_CACHE_LOCATION, source_cache, cache_target),
            ],
            {"project_dir": str(project_target)},
        )

    assert caught.value.stage == "commit"
    assert (project_target / "project-note.txt").read_text(encoding="utf-8") == "keep project"
    assert (cache_target / "cache-note.txt").read_text(encoding="utf-8") == "keep cache"
    assert not (project_target / "mage").exists()
    assert not (cache_target / "ai-pic-cache").exists()
    assert not list((tmp_path / "new").glob("*.gam-migration-*"))
    assert coordinator.restart_required is False
    assert (source_project / "mage").is_dir()
    assert (source_cache / "ai-pic-cache").is_dir()


# ==================== Confirmation token rules ====================


def test_wrong_token_is_rejected(coordinator: StorageMigrationCoordinator, source_project: Path, tmp_path: Path):
    target = tmp_path / "new" / "project"
    target.parent.mkdir(parents=True)
    coordinator.precheck([LocationMigration(PROJECT_LOCATION, source_project, target)], {})

    with pytest.raises(MigrationError, match="confirmation"):
        coordinator.execute("not-the-token")

    assert not target.exists()


def test_token_is_single_use(coordinator: StorageMigrationCoordinator, source_project: Path, tmp_path: Path):
    target = tmp_path / "new" / "project"
    target.parent.mkdir(parents=True)
    report = coordinator.precheck([LocationMigration(PROJECT_LOCATION, source_project, target)], {})
    coordinator.execute(report.token)

    with pytest.raises(MigrationError, match="confirmation"):
        coordinator.execute(report.token)


def test_new_precheck_invalidates_the_previous_token(
    coordinator: StorageMigrationCoordinator, source_project: Path, tmp_path: Path
):
    first_target = tmp_path / "new" / "project-a"
    second_target = tmp_path / "new" / "project-b"
    (tmp_path / "new").mkdir(parents=True)
    first = coordinator.precheck([LocationMigration(PROJECT_LOCATION, source_project, first_target)], {})
    coordinator.precheck([LocationMigration(PROJECT_LOCATION, source_project, second_target)], {})

    with pytest.raises(MigrationError, match="confirmation"):
        coordinator.execute(first.token)

    assert not first_target.exists()
    assert not second_target.exists()


def test_concurrent_execute_is_rejected(coordinator: StorageMigrationCoordinator, source_project: Path, tmp_path: Path):
    target = tmp_path / "new" / "project"
    target.parent.mkdir(parents=True)
    report = coordinator.precheck([LocationMigration(PROJECT_LOCATION, source_project, target)], {})

    assert coordinator._execute_lock.acquire(blocking=False)
    try:
        with pytest.raises(MigrationError, match="already running"):
            coordinator.execute(report.token)
    finally:
        coordinator._execute_lock.release()

    assert not target.exists()
