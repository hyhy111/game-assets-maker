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


@pytest.mark.parametrize("step, directory", [(2, "02_no_bg"), (3, "03_hole_punched")])
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
        assert saved["path"] == str(frame)
        assert Image.open(frame).getpixel((0, 0)) == (0, 0, 0, 0)
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
