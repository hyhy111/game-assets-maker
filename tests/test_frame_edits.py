import base64
import hashlib
import io
import json

import pytest
from PIL import Image

from backend.api.frame_api import FrameAPI


def png(size=(16, 12), color=(100, 120, 140, 255)):
    image = Image.new("RGBA", size, color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def data_url(payload):
    return "data:image/png;base64," + base64.b64encode(payload).decode()


@pytest.fixture
def frames(tmp_path):
    project = tmp_path / "hero/idle"
    (project / "cache").mkdir(parents=True)
    (project / "cache/global_params.json").write_text(json.dumps({"role": "hero", "action": "idle"}))
    output = project / "output/03_hole_punched"
    output.mkdir(parents=True)
    (output / "frame_000000.png").write_bytes(png())
    (output / "frame_000001.png").write_bytes(png(color=(200, 50, 70, 255)))
    return FrameAPI(projects_root=tmp_path), project, output / "frame_000000.png"


def test_open_returns_exact_png_and_revision(frames):
    api, _, frame = frames
    opened = api.get_editable_frame("hero/idle", frame.name)
    assert opened["revision"] == hashlib.sha256(frame.read_bytes()).hexdigest()
    assert opened["width"] == 16 and opened["height"] == 12
    assert base64.b64decode(opened["image_data_url"].split(",", 1)[1]) == frame.read_bytes()


def test_save_changes_only_target_and_retains_exact_backup(frames):
    api, project, frame = frames
    original = frame.read_bytes()
    neighbor = frame.with_name("frame_000001.png").read_bytes()
    opened = api.get_editable_frame("hero/idle", frame.name)
    edited = Image.open(io.BytesIO(original)).convert("RGBA")
    edited.putpixel((3, 4), (0, 0, 0, 0))
    buffer = io.BytesIO()
    edited.save(buffer, format="PNG")
    saved = api.save_frame_edit("hero/idle", frame.name, data_url(buffer.getvalue()), opened["revision"])
    assert saved["success"]
    assert Image.open(frame).getpixel((3, 4)) == (0, 0, 0, 0)
    assert Image.open(frame).size == (16, 12)
    assert frame.with_name("frame_000001.png").read_bytes() == neighbor
    assert (project / "cache/frame_edits" / opened["revision"] / frame.name).read_bytes() == original
    assert len(list(frame.parent.glob("*.png"))) == 2
    assert saved["revision"] != opened["revision"]


@pytest.mark.parametrize(
    "filename", ["../frame_000000.png", "/tmp/frame.png", "nested/frame.png", "..\\frame.png", "frame.jpg", "", 7]
)
def test_filename_cannot_escape_processed_frames(frames, filename):
    api, _, _ = frames
    with pytest.raises(ValueError, match="FRAME_EDIT_INVALID_FILENAME"):
        api.get_editable_frame("hero/idle", filename)


def test_symlink_frame_is_not_editable(frames, tmp_path):
    api, _, frame = frames
    outside = tmp_path / "outside.png"
    outside.write_bytes(png())
    link = frame.with_name("linked.png")
    link.symlink_to(outside)
    with pytest.raises(ValueError, match="FRAME_EDIT_NOT_FOUND"):
        api.get_editable_frame("hero/idle", link.name)


@pytest.mark.parametrize(
    "value", ["data:image/jpeg;base64,AAAA", "data:image/png;base64,not-valid", data_url(b"not an image")]
)
def test_invalid_image_never_replaces_frame(frames, value):
    api, project, frame = frames
    original = frame.read_bytes()
    with pytest.raises(ValueError, match="FRAME_EDIT_INVALID_PNG"):
        api.save_frame_edit("hero/idle", frame.name, value, hashlib.sha256(original).hexdigest())
    assert frame.read_bytes() == original
    assert not (project / "cache/frame_edits").exists()


def test_dimension_change_is_rejected(frames):
    api, _, frame = frames
    before = frame.read_bytes()
    with pytest.raises(ValueError, match="FRAME_EDIT_SIZE_CHANGED"):
        api.save_frame_edit("hero/idle", frame.name, data_url(png((8, 6))), hashlib.sha256(before).hexdigest())
    assert frame.read_bytes() == before


def test_stale_editor_cannot_overwrite_reprocessed_frame(frames):
    api, _, frame = frames
    opened = api.get_editable_frame("hero/idle", frame.name)
    reprocessed = png(color=(10, 20, 30, 255))
    frame.write_bytes(reprocessed)
    with pytest.raises(ValueError, match="FRAME_EDIT_STALE"):
        api.save_frame_edit("hero/idle", frame.name, data_url(png()), opened["revision"])
    assert frame.read_bytes() == reprocessed


def test_atomic_replace_failure_keeps_source_and_cleans_temporary(frames, monkeypatch):
    api, _, frame = frames
    original = frame.read_bytes()

    def fail(*args):
        raise OSError("simulated replacement failure")

    monkeypatch.setattr("backend.api.frame_api.os.replace", fail)
    with pytest.raises(OSError, match="replacement failure"):
        api.save_frame_edit("hero/idle", frame.name, data_url(png()), hashlib.sha256(original).hexdigest())
    assert frame.read_bytes() == original
    assert not list(frame.parent.glob(".frame-edit-*"))


@pytest.mark.parametrize("step, directory", [(2, "02_no_bg"), (3, "03_hole_punched"), (3, "02_no_bg")])
def test_public_bridge_blocks_manual_save_while_processing(tmp_path, monkeypatch, step, directory):
    from backend.main import API

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GAM_CONFIG", str(tmp_path / "config.json"))
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("GAM_DATA_MODE", "dev")
    project = tmp_path / "project/hero/idle"
    (project / "cache").mkdir(parents=True)
    (project / "cache/global_params.json").write_text(json.dumps({"role": "hero", "action": "idle"}))
    frame = project / "output" / directory / "frame_000000.png"
    frame.parent.mkdir(parents=True)
    original = png()
    frame.write_bytes(original)
    api = API()
    try:
        monkeypatch.setattr(api._process_api, "has_active_writes", lambda: True)
        with pytest.raises(ValueError, match="PROCESSING_ACTIVE"):
            api.save_frame_edit("hero/idle", frame.name, data_url(png()), hashlib.sha256(original).hexdigest(), step)
        assert frame.read_bytes() == original
        monkeypatch.setattr(api._process_api, "has_active_writes", lambda: False)
        opened = api.get_editable_frame("hero/idle", frame.name, step)
        saved = api.save_frame_edit(
            "hero/idle", frame.name, data_url(png(color=(0, 0, 0, 0))), opened["revision"], step
        )
        target = project / "output/03_hole_punched" / frame.name if step == 3 else frame
        assert saved["path"] == str(target)
        assert Image.open(target).getpixel((0, 0)) == (0, 0, 0, 0)
        if step == 3:
            config = json.loads((project / "cache/steps_config.json").read_text(encoding="utf-8"))
            assert config["step3"]["processed"] is True
            assert api._project_api.get_project("hero/idle")["steps"]["3"]["completed"] is True
        if directory == "02_no_bg" and step == 3:
            assert frame.read_bytes() == original
    finally:
        api._process_api.shutdown()


@pytest.mark.parametrize("project_id", ["../hero", "/hero/idle", "hero/../idle", "hero/idle/extra", "..\\hero", 7])
def test_project_identity_cannot_escape_or_alias_paths(frames, project_id):
    api, _, frame = frames
    with pytest.raises(ValueError, match="FRAME_EDIT_INVALID_PROJECT"):
        api.get_editable_frame(project_id, frame.name)


@pytest.mark.parametrize("step, directory", [(2, "02_no_bg"), (3, "03_hole_punched")])
def test_edit_is_scoped_to_requested_step(frames, step, directory):
    api, project, step3_frame = frames
    step2 = project / "output/02_no_bg"
    step2.mkdir()
    step2_frame = step2 / step3_frame.name
    step2_frame.write_bytes(png(color=(20, 210, 40, 255)))
    neighbor = step2 / "frame_000001.png"
    neighbor.write_bytes(png(color=(50, 60, 70, 255)))
    before = {path: path.read_bytes() for path in project.glob("output/*/*.png")}
    target = project / "output" / directory / step3_frame.name
    opened = api.get_editable_frame("hero/idle", target.name, step)
    assert base64.b64decode(opened["image_data_url"].split(",", 1)[1]) == before[target]
    edited = png(color=(0, 0, 0, 0))
    saved = api.save_frame_edit("hero/idle", target.name, data_url(edited), opened["revision"], step)
    assert saved["path"] == str(target)
    assert Image.open(target).getpixel((0, 0)) == (0, 0, 0, 0)
    assert (project / "cache/frame_edits" / opened["revision"] / target.name).read_bytes() == before[target]
    for path, content in before.items():
        if path != target:
            assert path.read_bytes() == content


@pytest.mark.parametrize("step", [1, 4, -1, "2", True, None, 2.0])
def test_manual_edit_rejects_unsupported_steps(frames, step):
    api, _, frame = frames
    before = frame.read_bytes()
    with pytest.raises(ValueError, match="FRAME_EDIT_INVALID_STEP"):
        api.get_editable_frame("hero/idle", frame.name, step)
    with pytest.raises(ValueError, match="FRAME_EDIT_INVALID_STEP"):
        api.save_frame_edit("hero/idle", frame.name, data_url(png()), hashlib.sha256(before).hexdigest(), step)
    assert frame.read_bytes() == before


def test_revision_from_step2_does_not_authorize_overwriting_step3(frames):
    api, project, frame = frames
    step2 = project / "output/02_no_bg"
    step2.mkdir()
    (step2 / frame.name).write_bytes(png(color=(20, 210, 40, 255)))
    opened = api.get_editable_frame("hero/idle", frame.name, 2)
    original = frame.read_bytes()
    with pytest.raises(ValueError, match="FRAME_EDIT_STALE"):
        api.save_frame_edit("hero/idle", frame.name, data_url(png()), opened["revision"], 3)
    assert frame.read_bytes() == original


def test_initial_version_survives_multiple_saves_and_a_new_api_instance(frames):
    api, _, frame = frames
    original = frame.read_bytes()
    opened = api.get_editable_frame("hero/idle", frame.name)
    assert base64.b64decode(opened["initial_image_data_url"].split(",", 1)[1]) == original
    for alpha in (100, 0):
        api.save_frame_edit("hero/idle", frame.name, data_url(png(color=(10, 20, 30, alpha))), opened["revision"])
        api = FrameAPI(projects_root=frame.parents[4])
        opened = api.get_editable_frame("hero/idle", frame.name)
        assert base64.b64decode(opened["initial_image_data_url"].split(",", 1)[1]) == original
    # Reading an initial image does not change the output; restoration is committed through the normal save API.
    assert Image.open(frame).getpixel((0, 0)) == (10, 20, 30, 0)
    api.save_frame_edit("hero/idle", frame.name, opened["initial_image_data_url"], opened["revision"])
    assert frame.read_bytes() == original


def test_initial_versions_are_isolated_between_steps(frames):
    api, project, frame = frames
    step2 = project / "output/02_no_bg" / frame.name
    step2.parent.mkdir()
    step2.write_bytes(png(color=(10, 200, 30, 255)))
    before = {2: step2.read_bytes(), 3: frame.read_bytes()}
    for step, target in ((2, step2), (3, frame)):
        opened = api.get_editable_frame("hero/idle", target.name, step)
        api.save_frame_edit("hero/idle", target.name, data_url(png(color=(0, 0, 0, 0))), opened["revision"], step)
    opened3 = api.get_editable_frame("hero/idle", frame.name, 3)
    unchanged_step2 = step2.read_bytes()
    api.save_frame_edit("hero/idle", frame.name, opened3["initial_image_data_url"], opened3["revision"], 3)
    assert frame.read_bytes() == before[3]
    assert step2.read_bytes() == unchanged_step2
    assert (
        base64.b64decode(api.get_editable_frame("hero/idle", step2.name, 2)["initial_image_data_url"].split(",", 1)[1])
        == before[2]
    )


def test_unscoped_legacy_backup_is_not_guessed_to_be_the_step3_initial_frame(frames):
    api, project, frame = frames
    unknown = png(color=(40, 150, 60, 255))
    backup = project / "cache/frame_edits" / hashlib.sha256(unknown).hexdigest() / frame.name
    backup.parent.mkdir(parents=True)
    backup.write_bytes(unknown)
    opened = api.get_editable_frame("hero/idle", frame.name)
    assert opened["initial_image_data_url"] is None
    assert base64.b64decode(opened["image_data_url"].split(",", 1)[1]) == frame.read_bytes()
    assert backup.read_bytes() == unknown


def test_successful_reprocessing_establishes_a_new_initial_version_and_preserves_step2(frames):
    from backend.api.process_api import ProcessAPI, Task

    api, project, frame = frames
    original = frame.read_bytes()
    opened = api.get_editable_frame("hero/idle", frame.name)
    api.save_frame_edit("hero/idle", frame.name, data_url(png(color=(0, 0, 0, 0))), opened["revision"])
    source = project / "output/02_no_bg" / frame.name
    source.parent.mkdir()
    source.write_bytes(png(color=(50, 60, 200, 255)))
    source_before = source.read_bytes()
    process = ProcessAPI(projects_root=project.parents[1])
    try:
        task = Task("reprocess-initial", "hero/idle", 3, {"enabled": False, "align_enabled": False})
        process._run_task(task)
        assert task.status == "completed", task.error
        opened = api.get_editable_frame("hero/idle", frame.name)
        assert base64.b64decode(opened["initial_image_data_url"].split(",", 1)[1]) == source_before
        assert source.read_bytes() == source_before
        assert (
            project / "cache/frame_edits" / hashlib.sha256(original).hexdigest() / frame.name
        ).read_bytes() == original
    finally:
        process.shutdown()


def test_missing_initial_snapshot_disables_restoration_without_replacing_the_frame(frames):
    api, project, frame = frames
    opened = api.get_editable_frame("hero/idle", frame.name)
    api.save_frame_edit("hero/idle", frame.name, data_url(png(color=(0, 0, 0, 0))), opened["revision"])
    for image in (project / "cache/frame_edits/initial").rglob("images/*.png"):
        image.unlink()
    current = frame.read_bytes()
    assert api.get_editable_frame("hero/idle", frame.name)["initial_image_data_url"] is None
    assert frame.read_bytes() == current


def test_initial_history_symlinks_cannot_escape_the_project(frames, tmp_path):
    api, project, frame = frames
    outside = tmp_path / "outside-history"
    outside.mkdir()
    history = project / "cache/frame_edits"
    history.mkdir()
    (history / "initial").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="FRAME_EDIT_INVALID_BACKUP"):
        api.get_editable_frame("hero/idle", frame.name)
    assert not list(outside.iterdir())


def test_failed_output_replace_does_not_advance_the_initial_version(frames, monkeypatch):
    import os

    api, _, frame = frames
    original = frame.read_bytes()
    opened = api.get_editable_frame("hero/idle", frame.name)
    replace = os.replace

    def fail_output(source, target):
        if target == frame:
            raise OSError("failed output replace")
        return replace(source, target)

    with monkeypatch.context() as patch:
        patch.setattr("backend.api.frame_api.os.replace", fail_output)
        with pytest.raises(OSError, match="failed output replace"):
            api.save_frame_edit("hero/idle", frame.name, data_url(png(color=(0, 0, 0, 0))), opened["revision"])
    assert frame.read_bytes() == original
    reopened = api.get_editable_frame("hero/idle", frame.name)
    assert reopened["revision"] == opened["revision"]
    assert reopened["initial_image_data_url"] == opened["initial_image_data_url"]


def test_external_replacement_is_not_misidentified_as_a_new_initial_frame(frames):
    api, _, frame = frames
    opened = api.get_editable_frame("hero/idle", frame.name)
    api.save_frame_edit("hero/idle", frame.name, data_url(png(color=(0, 0, 0, 0))), opened["revision"])
    external = png(color=(10, 90, 200, 255))
    frame.write_bytes(external)
    reopened = api.get_editable_frame("hero/idle", frame.name)
    assert reopened["initial_image_data_url"] is None
    assert base64.b64decode(reopened["image_data_url"].split(",", 1)[1]) == external


@pytest.fixture
def manual_frames(tmp_path):
    project = tmp_path / "hero/idle"
    source = project / "output/02_no_bg"
    source.mkdir(parents=True)
    originals = {f"frame_{index:06d}.png": png(color=(index * 50, 100, 200, 255)) for index in range(3)}
    for name, payload in originals.items():
        (source / name).write_bytes(payload)
    return FrameAPI(projects_root=tmp_path), project, source, originals


@pytest.mark.parametrize("empty_output", [False, True])
def test_manual_cleanup_before_step3_publishes_complete_sequence_and_preserves_step2(manual_frames, empty_output):
    from backend.api.project_api import ProjectAPI

    api, project, source, originals = manual_frames
    output = project / "output/03_hole_punched"
    if empty_output:
        output.mkdir()
    name = "frame_000001.png"
    opened = api.get_editable_frame("hero/idle", name)
    assert opened["image_data_url"] == data_url(originals[name])
    assert opened["initial_image_data_url"] == data_url(originals[name])
    assert not list(output.glob("*.png")), "opening a tool must not mark the sequence complete"
    saved = api.save_frame_edit("hero/idle", name, data_url(png(color=(0, 0, 0, 0))), opened["revision"])
    assert saved["path"] == str(output / name)
    assert set(path.name for path in output.glob("*.png")) == set(originals)
    assert Image.open(output / name).getpixel((0, 0)) == (0, 0, 0, 0)
    for filename, payload in originals.items():
        assert (source / filename).read_bytes() == payload
        if filename != name:
            assert (output / filename).read_bytes() == payload
    status = ProjectAPI(projects_root=project.parents[1])._get_step_status(project)
    assert status["3"]["completed"] is True
    assert status["3"]["count"] == len(originals)
    reopened = FrameAPI(projects_root=project.parents[1]).get_editable_frame("hero/idle", name)
    assert reopened["revision"] == saved["revision"]
    assert reopened["initial_image_data_url"] == data_url(originals[name])
    api.save_frame_edit("hero/idle", name, reopened["initial_image_data_url"], reopened["revision"])
    assert (output / name).read_bytes() == originals[name]


def test_early_manual_save_rejects_stale_source_without_creating_final_output(manual_frames):
    api, project, source, originals = manual_frames
    name = next(iter(originals))
    opened = api.get_editable_frame("hero/idle", name)
    changed = png(color=(10, 20, 30, 255))
    (source / name).write_bytes(changed)
    with pytest.raises(ValueError, match="FRAME_EDIT_STALE"):
        api.save_frame_edit("hero/idle", name, data_url(png()), opened["revision"])
    assert (source / name).read_bytes() == changed
    assert not (project / "output/03_hole_punched").exists()


def test_first_manual_save_preserves_existing_non_frame_files(manual_frames):
    api, project, source, originals = manual_frames
    output = project / "output/03_hole_punched"
    (output / "notes").mkdir(parents=True)
    extras = {".DS_Store": b"synthetic Finder metadata", "notes/keep.txt": b"keep this file"}
    for filename, payload in extras.items():
        (output / filename).write_bytes(payload)
    name = next(iter(originals))
    opened = api.get_editable_frame("hero/idle", name)

    saved = api.save_frame_edit("hero/idle", name, data_url(png(color=(0, 0, 0, 0))), opened["revision"])

    assert saved["path"] == str(output / name)
    assert set(path.name for path in output.glob("*.png")) == set(originals)
    for filename, payload in extras.items():
        assert (output / filename).read_bytes() == payload
    for filename, payload in originals.items():
        assert (source / filename).read_bytes() == payload
    assert not list(output.parent.glob(".manual-step3-*"))


def test_failed_first_manual_save_restores_existing_non_frame_files(manual_frames, monkeypatch):
    import os

    api, project, _, originals = manual_frames
    output = project / "output/03_hole_punched"
    output.mkdir()
    metadata = b"synthetic Finder metadata"
    (output / ".DS_Store").write_bytes(metadata)
    name = next(iter(originals))
    opened = api.get_editable_frame("hero/idle", name)
    replace = os.replace

    def fail_publication(staged, target):
        if target == output and staged.name == "03_hole_punched":
            raise OSError("failed sequence publication")
        return replace(staged, target)

    monkeypatch.setattr("backend.api.frame_api.os.replace", fail_publication)
    with pytest.raises(OSError, match="failed sequence publication"):
        api.save_frame_edit("hero/idle", name, data_url(png()), opened["revision"])

    assert (output / ".DS_Store").read_bytes() == metadata
    assert not list(output.glob("*.png"))
    assert not list(output.parent.glob(".manual-step3-*"))


def test_failed_first_manual_rollback_keeps_recovery_directory(manual_frames, monkeypatch):
    import os

    api, project, source, originals = manual_frames
    output = project / "output/03_hole_punched"
    output.mkdir()
    metadata = b"synthetic Finder metadata"
    (output / ".DS_Store").write_bytes(metadata)
    name = next(iter(originals))
    opened = api.get_editable_frame("hero/idle", name)
    replace = os.replace

    def fail_publication_and_rollback(staged, target):
        if target == output:
            raise OSError("output unavailable")
        return replace(staged, target)

    monkeypatch.setattr("backend.api.frame_api.os.replace", fail_publication_and_rollback)
    with pytest.raises(OSError, match="output unavailable"):
        api.save_frame_edit("hero/idle", name, data_url(png()), opened["revision"])

    backups = list(output.parent.glob(".manual-step3-backup-*"))
    assert len(backups) == 1
    assert (backups[0] / ".DS_Store").read_bytes() == metadata
    for filename, payload in originals.items():
        assert (source / filename).read_bytes() == payload


def test_failed_first_manual_publication_keeps_step2_and_does_not_publish_partial_sequence(manual_frames, monkeypatch):
    import os

    api, project, source, originals = manual_frames
    name = next(iter(originals))
    output = project / "output/03_hole_punched"
    opened = api.get_editable_frame("hero/idle", name)
    replace = os.replace

    def fail_publication(staged, target):
        if target == output:
            raise OSError("failed sequence publication")
        return replace(staged, target)

    monkeypatch.setattr("backend.api.frame_api.os.replace", fail_publication)
    with pytest.raises(OSError, match="failed sequence publication"):
        api.save_frame_edit("hero/idle", name, data_url(png()), opened["revision"])
    assert not list(output.glob("*.png"))
    assert not list(output.parent.glob(".manual-step3-*"))
    for filename, payload in originals.items():
        assert (source / filename).read_bytes() == payload
