"""Validate saved parameters through the public processing APIs."""

import json

import pytest

from backend.agent_control.steps import StepControl
from backend.api.process_api import ProcessAPI
from backend.api.project_api import ProjectAPI


@pytest.fixture
def controller(tmp_path):
    project = tmp_path / "hero" / "idle"
    (project / "cache").mkdir(parents=True)
    (project / "cache" / "global_params.json").write_text(
        json.dumps({"role": "hero", "action": "idle", "video_path": "/missing.mp4"})
    )
    process = ProcessAPI(projects_root=tmp_path)
    yield StepControl(ProjectAPI(projects_root=tmp_path), process)
    process.shutdown()


def test_save_merges_existing_values_and_preserves_other_steps(controller):
    before = controller.apply("step.get", {"project_id": "hero/idle", "step": 2})["params_used"]
    result = controller.apply(
        "step.set", {"project_id": "hero/idle", "step": 1, "patch": {"start_frame": 3, "end_frame": 8}}
    )
    assert result["params_used"]["frame_interval"] == 1
    assert controller.apply("step.get", {"project_id": "hero/idle", "step": 1})["params_used"]["start_frame"] == 3
    assert controller.apply("step.get", {"project_id": "hero/idle", "step": 2})["params_used"] == before


@pytest.mark.parametrize(
    "step,patch",
    [
        (1, {"frame_interval": True}),
        (1, {"start_frame": 5, "end_frame": 2}),
        (2, {"alpha_matting_background_threshold": 250}),
        (3, {"green_intensity": 6}),
        (3, {"align_h": 1}),
        (3, {"processed": True}),
    ],
)
def test_invalid_patch_never_changes_saved_values(controller, step, patch):
    payload = {"project_id": "hero/idle", "step": step}
    before = controller.apply("step.get", payload)
    with pytest.raises(ValueError):
        controller.apply("step.set", {**payload, "patch": patch})
    assert controller.apply("step.get", payload) == before


def test_actual_extraction_uses_saved_range_and_reports_task(controller, tmp_path):
    import time

    from PIL import Image

    project = tmp_path / "hero" / "idle"
    video = tmp_path / "source.mp4"
    video.write_bytes(b"test source: cached frames are the processing input")
    metadata = project / "cache" / "global_params.json"
    metadata.write_text(json.dumps({"role": "hero", "action": "idle", "video_path": str(video)}))
    cache = project / "cache" / "01_frames_cache"
    cache.mkdir()
    for index in range(6):
        Image.new("RGB", (32, 32), (index * 20, 100, 40)).save(cache / f"frame_{index:06d}.png")
    controller.apply(
        "step.set",
        {"project_id": "hero/idle", "step": 1, "patch": {"start_frame": 1, "end_frame": 4, "frame_interval": 2}},
    )
    result = controller.apply("step.run", {"project_id": "hero/idle", "step": 1})
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        status = controller.apply("step.status", {"task_id": result["task_id"]})
        if status["status"] in ("completed", "failed"):
            break
        time.sleep(0.01)
    assert status["status"] == "completed"
    assert controller.projects.get_project("hero/idle")["steps"]["1"]["completed"] is True
    assert len(list((project / "output" / "01_frames").glob("*.png"))) == 2
    assert result["params_used"]["start_frame"] == 1
    assert result["output_dir"] == str(project / "output" / "01_frames")


def test_manual_selection_is_saved_reopened_and_used_by_actual_extraction(controller, tmp_path):
    from PIL import Image

    from backend.api.process_api import Task

    project = tmp_path / "hero" / "idle"
    video = tmp_path / "source.mp4"
    video.write_bytes(b"Cached source frames")
    cache = project / "cache" / "01_frames_cache"
    cache.mkdir()
    for index in range(12):
        Image.new("RGB", (16, 16), (index * 20, 100, 40)).save(cache / f"frame_{index:06d}.png")
    params = controller.apply(
        "step.set",
        {
            "project_id": "hero/idle",
            "step": 1,
            "patch": {
                "start_frame": 1,
                "end_frame": 10,
                "frame_interval": 3,
                "frame_overrides": {"4": 5, "7": 6},
            },
        },
    )["params_used"]
    reopened = ProcessAPI(projects_root=tmp_path)
    try:
        assert reopened.get_step_params("hero/idle", 1)["frame_overrides"] == {"4": 5, "7": 6}
        reopened._run_step1(Task("custom-selection", "hero/idle", 1, {**params, "video_path": str(video)}))
    finally:
        reopened.shutdown()
    output = project / "output" / "01_frames"
    for slot, source_index in enumerate([1, 5, 6, 10]):
        assert (output / f"frame_{slot:06d}.png").read_bytes() == (cache / f"frame_{source_index:06d}.png").read_bytes()
    assert len(list(output.glob("*.png"))) == 4
    controller.apply("step.set", {"project_id": "hero/idle", "step": 1, "patch": {"frame_interval": 2}})
    assert controller.process.get_step_params("hero/idle", 1)["frame_overrides"] == {}


@pytest.mark.parametrize("overrides", [{"3": 2}, {"4": True}, {"4": 11}, {"4": 7}, {"4": 8}, [5]])
def test_invalid_manual_selection_preserves_previous_output(tmp_path, overrides):
    from PIL import Image

    from backend.core.video_utils import export_frames_step1

    cache = tmp_path / "原始帧"
    output = tmp_path / "已提取帧"
    cache.mkdir()
    output.mkdir()
    previous = output / "frame_000000.png"
    previous.write_bytes(b"previous output")
    for index in range(12):
        Image.new("RGB", (2, 2)).save(cache / f"frame_{index:06d}.png")
    with pytest.raises(ValueError):
        export_frames_step1(str(cache), str(output), 1, 10, 3, frame_overrides=overrides)
    assert previous.read_bytes() == b"previous output"


def test_audio_export_uses_replaced_source_frames_and_skips_hidden_slots(tmp_path):
    import wave

    from backend.api.batch_trim_api import BatchTrimAPI

    project = tmp_path / "hero" / "idle"
    cache = project / "cache"
    audio_dir = cache / "01_audio"
    audio_dir.mkdir(parents=True)
    (cache / "steps_config.json").write_text(
        json.dumps(
            {
                "step1": {
                    "start_frame": 1,
                    "end_frame": 10,
                    "frame_interval": 3,
                    "frame_overrides": {"4": 5, "7": 6},
                }
            }
        )
    )
    (cache / "audio_timeline.json").write_text(
        json.dumps(
            {
                "source_fps": 10,
                "clips": [{"srcStartFrame": 0, "srcEndFrame": 2, "placementFrame": 5}],
            }
        )
    )
    with wave.open(str(audio_dir / "source.wav"), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(10)
        audio.writeframes(b"\x00\x00" * 20)
    source = project / "output" / "02_no_bg"
    source.mkdir(parents=True)
    for slot in range(4):
        (source / f"frame_{slot:06d}.png").touch()
    output = tmp_path / "export"
    output.mkdir()
    result = BatchTrimAPI(tmp_path)._export_audio_clips(
        "hero/idle",
        source,
        output,
        ["frame_000000.png", "frame_000001.png", "frame_000003.png"],
    )
    assert result == {"count": 1, "skipped": 0, "errors": []}
    manifest = json.loads((output / "_audio_timeline.json").read_text())
    assert manifest["clips"][0]["placement_frame"] == 1


def test_online_control_accepts_step_and_artifact_families(tmp_path, monkeypatch):
    from test_agent_navigation import BrowserWindow

    from backend.agent_control.server import AgentControlServer
    from backend.main import API

    monkeypatch.setenv("GAM_CONFIG", str(tmp_path / "config.json"))
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    api = API()
    project = api.storage_locations.projects_root / "hero" / "idle" / "cache"
    project.mkdir(parents=True)
    (project / "global_params.json").write_text(json.dumps({"role": "hero", "action": "idle"}))
    server = AgentControlServer(BrowserWindow(), api=api, port=0)
    server.operations.timeout = 0
    try:
        result = server.operations.execute(
            {"request_id": "get", "operation": "step.get", "payload": {"project_id": "hero/idle", "step": 1}}
        )
        assert result["ok"]
        result = server.operations.execute({"request_id": "list", "operation": "artifacts.list", "payload": {}})
        assert result["ok"] and result["data"]["items"]
        result = server.operations.execute(
            {
                "request_id": "set",
                "operation": "step.set",
                "payload": {"project_id": "hero/idle", "step": 1, "patch": {"start_frame": 2}},
            }
        )
        assert result["error"]["code"] == "UI_SYNC_TIMEOUT"
        assert result["error"]["details"]["persisted"] is True
    finally:
        api._process_api.shutdown()


def test_concurrent_patches_preserve_unmentioned_values(controller):
    import concurrent.futures

    patches = [{"start_frame": 2}, {"frame_interval": 3}]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        list(
            executor.map(
                lambda patch: controller.apply("step.set", {"project_id": "hero/idle", "step": 1, "patch": patch}),
                patches,
            )
        )
    saved = controller.apply("step.get", {"project_id": "hero/idle", "step": 1})["params_used"]
    assert saved["start_frame"] == 2 and saved["frame_interval"] == 3


def test_trim_partial_receipt_reports_real_counts_and_existing_directory(tmp_path):
    from backend.agent_control.trim import normalize_trim_results

    output = tmp_path / "trim"
    output.mkdir()
    result = normalize_trim_results(
        [
            {
                "projectId": "hero/idle",
                "status": "partial",
                "outputPath": str(output),
                "frameCount": 5,
                "successCount": 3,
                "failedCount": 2,
                "failedFrames": ["a.png"],
                "audioErrors": ["missing source"],
            }
        ],
        ["hero/idle"],
        "individual",
    )
    assert result["final"] is False
    assert result["persisted"] is True
    assert result["results"][0]["frame_count"] == 3
    assert result["results"][0]["failed_count"] == 2
    assert result["results"][0]["audio_errors"] == ["missing source"]
    assert result["results"][0]["final_frames_dir"] == str(output)
    result = normalize_trim_results(
        [{"status": "success", "outputPath": str(output / "missing"), "successCount": 5}], [], "global"
    )
    assert result["final"] is False
