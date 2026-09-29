"""Unified pure resolution of project and AI cache storage roots.

Covers the storage-location-management change: default relative values stay
anchored to the stable data root, custom absolute directories are honored as
the root itself, GAM_DATA_ROOT keeps overriding the anchor, and equivalent
spellings of one physical directory normalize to the same path.
"""

import os
from pathlib import Path

import pytest

from src.utils.storage_locations import (
    DEFAULT_AI_CACHE_DIR,
    DEFAULT_PROJECT_DIR,
    resolve_storage_locations,
    resolve_storage_root,
)


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    return tmp_path / "data-root"


# ==================== Default relative values ====================


def test_defaults_resolve_under_the_data_root(data_root: Path):
    locations = resolve_storage_locations(None, None, data_root=data_root)

    assert locations.projects_root == data_root / "project"
    assert locations.ai_cache_root == data_root / "cache"


def test_default_constants_match_existing_layout():
    assert DEFAULT_PROJECT_DIR == "project"
    assert DEFAULT_AI_CACHE_DIR == "cache"


def test_explicit_relative_values_resolve_against_data_root(data_root: Path):
    locations = resolve_storage_locations("project", "cache", data_root=data_root)

    assert locations.projects_root == data_root / "project"
    assert locations.ai_cache_root == data_root / "cache"


def test_blank_configured_values_fall_back_to_defaults(data_root: Path):
    locations = resolve_storage_locations("", "  ", data_root=data_root)

    assert locations.projects_root == data_root / "project"
    assert locations.ai_cache_root == data_root / "cache"


# ==================== Custom absolute directories ====================


def test_absolute_project_directory_is_the_root_itself(data_root: Path, tmp_path: Path):
    custom = tmp_path / "chosen-projects"

    locations = resolve_storage_locations(str(custom), None, data_root=data_root)

    assert locations.projects_root == custom
    assert locations.ai_cache_root == data_root / "cache"


def test_absolute_ai_cache_directory_is_the_shared_root(data_root: Path, tmp_path: Path):
    custom = tmp_path / "chosen-cache"

    locations = resolve_storage_locations(None, str(custom), data_root=data_root)

    assert locations.ai_cache_root == custom
    assert locations.projects_root == data_root / "project"


def test_tilde_in_configured_directory_expands_to_home(
    data_root: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))

    assert resolve_storage_root("~/gam-projects", default="project", data_root=data_root) == home / "gam-projects"


# ==================== GAM_DATA_ROOT override ====================


def test_data_root_override_flows_into_both_roots(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    override = tmp_path / "pinned-root"
    monkeypatch.setenv("GAM_DATA_ROOT", str(override))

    from src.utils.data_paths import data_root

    locations = resolve_storage_locations(None, None, data_root=data_root())

    assert locations.projects_root == override / "project"
    assert locations.ai_cache_root == override / "cache"


def test_relative_values_never_resolve_against_the_launch_directory(
    data_root: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    launch = tmp_path / "launch"
    launch.mkdir()
    monkeypatch.chdir(launch)

    locations = resolve_storage_locations("project", "cache", data_root=data_root)

    assert locations.projects_root == data_root / "project"
    assert locations.ai_cache_root == data_root / "cache"


# ==================== Equivalent path normalization ====================


def test_relative_and_absolute_spellings_of_the_default_match(data_root: Path):
    relative = resolve_storage_root("cache", default="cache", data_root=data_root)
    absolute = resolve_storage_root(str(data_root / "cache"), default="cache", data_root=data_root)

    assert relative == absolute


def test_redundant_separators_dots_and_parent_segments_collapse(data_root: Path):
    messy = resolve_storage_root("nested/.././cache/", default="cache", data_root=data_root)

    assert messy == data_root / "cache"


def test_data_root_itself_is_normalized(data_root: Path):
    messy_root = Path(os.path.join(str(data_root), ".", ""))

    locations = resolve_storage_locations(None, None, data_root=messy_root)

    assert locations.projects_root == data_root / "project"
    assert locations.ai_cache_root == data_root / "cache"


def test_distinct_directories_do_not_collapse(data_root: Path):
    assert resolve_storage_root("cache", default="cache", data_root=data_root) != resolve_storage_root(
        "other-cache", default="cache", data_root=data_root
    )
