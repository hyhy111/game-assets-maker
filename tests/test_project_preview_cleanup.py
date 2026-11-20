import json
from pathlib import Path

import pytest

from tests.conftest import _write_video, wait_for_task


def _project(api, video: Path, name: str, created_at: str) -> tuple[str, Path]:
    project = api.create_project("角色", name, str(video))
    path = Path(project["path"])
    metadata = path / "cache" / "global_params.json"
    data = json.loads(metadata.read_text(encoding="utf-8"))
    metadata.write_text(json.dumps({**data, "timestamp": created_at}), encoding="utf-8")
    return project["id"], path


def _preview_files(project: Path) -> list[Path]:
    return sorted((project / "cache" / "01_frames_cache").glob("frame_*.png"))


def test_preview_cleanup_filters_creation_dates_and_rebuilds_on_editor_entry(api, tmp_path):
    video = tmp_path / "源视频.mp4"
    _write_video(video, (40, 80, 220))
    selected, project = _project(api, video, "selected", "2026-10-03T23:59:59")
    other, other_project = _project(api, video, "other", "2026-10-04T00:00:00")
    missing_source = tmp_path / "removed.mp4"
    _write_video(missing_source, (75, 110, 210))
    _, missing_project = _project(api, missing_source, "missing", "2026-10-03T00:00:00")
    missing_source.unlink()
    first_pass = api.start_processing(
        selected, 1, {"start_frame": 1, "end_frame": 4, "frame_interval": 2, "processed": True}
    )
    assert wait_for_task(api, first_pass)["status"] == "completed"

    cache_files = _preview_files(project)
    pictures = [path.read_bytes() for path in cache_files]
    expected_bytes = sum(map(len, pictures))
    original = video.read_bytes()
    results = []
    for step in ("01_frames", "02_no_bg", "03_hole_punched"):
        target = project / "output" / step / "frame_000000.png"
        if not target.exists():
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(pictures[-1])
        results.append(target)
    untouched = cache_files[0].with_name("original.png")
    untouched.write_bytes(pictures[-1])
    result_bytes = [path.read_bytes() for path in results]
    settings = api.get_step_params(selected, 1)

    assert api.get_preview_cleanup_plan("2026-10-03", "2026-10-03") == {
        "project_ids": [selected],
        "frame_count": 8,
        "bytes": expected_bytes,
        "skipped": 1,
        "failed": 0,
    }
    assert set(api.get_preview_cleanup_plan("2026-10-03", "")["project_ids"]) == {selected, other}
    assert api.get_preview_cleanup_plan("", "2026-10-03")["project_ids"] == [selected]
    assert api.clean_project_preview_frames("", "2026-10-03", [selected, other])["bytes"] == expected_bytes
    assert _preview_files(project) == []
    assert untouched.exists() and _preview_files(other_project) and _preview_files(missing_project)
    assert video.read_bytes() == original
    assert [path.read_bytes() for path in results] == result_bytes
    assert api.get_step_params(selected, 1) == settings
    status = api.get_project(selected)["steps"]["1"]
    assert status["completed"] and not status["data_ready"]

    library = api.get_frames(selected, 1, page_size=12)
    assert library["total"] == 2 and _preview_files(project) == []
    rebuilt = api.get_frames(selected, 1, rebuild_preview=True)
    assert rebuilt["total"] == 8
    assert [path.read_bytes() for path in _preview_files(project)] == pictures
    assert [path.read_bytes() for path in results] == result_bytes
    assert api.get_project(selected)["steps"]["1"]["data_ready"]


def test_reextract_rebuilds_cache_using_the_saved_source_and_range(api, tmp_path):
    video = tmp_path / "source.mp4"
    _write_video(video, (220, 120, 40))
    project_id, project = _project(api, video, "reextract", "2026-10-03")
    before = [path.read_bytes() for path in _preview_files(project)]
    assert api.clean_project_preview_frames("", "", [project_id])["frame_count"] == 8
    job = api.start_processing(project_id, 1, {"start_frame": 2, "end_frame": 7, "frame_interval": 3})
    assert wait_for_task(api, job)["status"] == "completed"
    output = project / "output" / "01_frames"
    assert [frame.read_bytes() for frame in sorted(output.glob("*.png"))] == [before[2], before[5]]


def test_cleanup_never_follows_a_linked_preview_directory(api, tmp_path):
    video = tmp_path / "source.mp4"
    _write_video(video, (110, 120, 220))
    project_id, project = _project(api, video, "linked", "2026-10-03")
    directory = project / "cache" / "01_frames_cache"
    outside = tmp_path / "outside-preview"
    directory.rename(outside)
    directory.symlink_to(outside, target_is_directory=True)
    assert api.get_preview_cleanup_plan("", "")["skipped"] == 1
    assert api.clean_project_preview_frames("", "", [project_id])["frame_count"] == 0
    assert len(list(outside.glob("*.png"))) == 8
    with pytest.raises(OSError, match="Invalid preview cache directory"):
        api.get_frames(project_id, 1, rebuild_preview=True)
    with pytest.raises(ValueError, match="INVALID_PREVIEW_DATES"):
        api.get_preview_cleanup_plan("2026-10-05", "2026-10-03")


def test_partial_cleanup_does_not_use_incomplete_frames(api, tmp_path, monkeypatch):
    video = tmp_path / "source.mp4"
    _write_video(video, (100, 70, 204))
    project_id, project = _project(api, video, "locked", "2026-10-03")
    locked = _preview_files(project)[0]
    unlink = Path.unlink

    def locked_unlink(path, *args, **kwargs):
        if path == locked:
            raise PermissionError("A reader still holds this frame")
        return unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", locked_unlink)
        result = api.clean_project_preview_frames("", "", [project_id])
    assert result["frame_count"] == 7 and result["failed"] == 1
    assert _preview_files(project) == [locked]
    assert api.get_frames(project_id, 1)["total"] == 0
    assert api.get_frames(project_id, 1, rebuild_preview=True)["total"] == 8
