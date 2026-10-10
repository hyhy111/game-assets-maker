"""Read local assets without exposing credentials or delivery URLs."""

import json

import pytest

from src.utils.storage_locations import StorageLocations


def test_artifact_listing_paginates_and_safe_read_redacts(tmp_path):
    from backend.agent_control.artifacts import LocalArtifacts

    roots = StorageLocations(tmp_path / "project", tmp_path / "cache")
    project = roots.projects_root / "hero" / "idle" / "output" / "01_frames"
    project.mkdir(parents=True)
    for index in range(3):
        (project / f"{index}.png").write_bytes(b"png")
    task = roots.ai_video_cache_root / "tasks" / "task1"
    task.mkdir(parents=True)
    metadata = task / "task.json"
    metadata.write_text(
        json.dumps(
            {
                "request": {"prompt": "walk", "api_key": "secret"},
                "remote": {"video_url": "https://example.com/signed?token=secret"},
            }
        )
    )
    artifacts = LocalArtifacts(roots)
    first = artifacts.list({"project_id": "hero/idle", "limit": 2})
    second = artifacts.list({"project_id": "hero/idle", "limit": 2, "offset": 2})
    assert len(first["items"]) == 2 and len(second["items"]) == 1
    assert all(item["step"] == 1 for item in first["items"])
    content = artifacts.read(str(metadata))["content"]
    assert content["request"]["prompt"] == "walk"
    assert "secret" not in json.dumps(content)
    assert "https://" not in json.dumps(content)


def test_artifacts_reject_symlink_escape_and_unrecorded_external_file(tmp_path):
    from backend.agent_control.artifacts import LocalArtifacts

    roots = StorageLocations(tmp_path / "project", tmp_path / "cache")
    roots.projects_root.mkdir()
    outside = tmp_path / "private.json"
    outside.write_text("{}")
    link = roots.projects_root / "escape.json"
    link.symlink_to(outside)
    artifacts = LocalArtifacts(roots)
    assert not artifacts.list({})["items"]
    for path in (str(link), str(outside), str(roots.projects_root / "../private.json")):
        with pytest.raises(ValueError):
            artifacts.read(path)


def test_cache_credentials_are_removed_from_nonstandard_provider_fields():
    from backend.agent_control.artifacts import safe_metadata

    content = safe_metadata(
        {
            "client_secret": "secret",
            "session_token": "session",
            "security_token": "security",
            "access_key": "access",
            "request": {"prompt": "walk"},
            "usage": {"total_tokens": 20},
        }
    )
    assert content == {"request": {"prompt": "walk"}, "usage": {"total_tokens": 20}}


def test_legacy_and_cropped_files_keep_animation_ids(tmp_path):
    from types import SimpleNamespace

    from backend.agent_control.artifacts import LocalArtifacts

    root = tmp_path / "projects"
    for relative in ("old/cache/global_params.json", "hero/batch-trim-2/idle/_frame_data.json"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
    artifacts = LocalArtifacts(
        SimpleNamespace(
            projects_root=root, ai_pic_cache_root=tmp_path / "pics", ai_video_cache_root=tmp_path / "videos"
        )
    )
    assert artifacts.list({"project_id": "old"})["total"] == 1
    assert artifacts.list({"project_id": "hero/idle"})["total"] == 1


def test_recorded_external_source_is_readable_and_missing_local_asset_is_explicit(tmp_path):
    from backend.agent_control.artifacts import LocalArtifacts

    roots = StorageLocations(tmp_path / "project", tmp_path / "cache")
    metadata = roots.projects_root / "hero" / "idle" / "cache" / "global_params.json"
    metadata.parent.mkdir(parents=True)
    external = tmp_path / "source.mp4"
    external.write_bytes(b"recorded source")
    metadata.write_text(json.dumps({"video_path": str(external)}))
    artifacts = LocalArtifacts(roots)
    assert artifacts.read(str(external))["source"] == "project-input"
    with pytest.raises(ValueError, match="ASSET_MISSING"):
        artifacts.read(str(metadata.parent / "missing.png"))
    link = metadata.parent / "linked.mp4"
    link.symlink_to(external)
    with pytest.raises(ValueError, match="PATH_NOT_ALLOWED"):
        artifacts.read(str(link))
