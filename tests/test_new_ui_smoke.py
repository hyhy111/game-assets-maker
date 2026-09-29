import json
import shutil
import subprocess
import wave
from pathlib import Path

import pytest

from backend.api.project_paths import LEGACY_ROLE, UNKNOWN_ROLE
from backend.api.video_api import VideoAPI
from backend.core.smart_remove_background import check_model_available
from tests.conftest import wait_for_task


def _video(test_assets: Path, role: str, action: str) -> str:
    return str(test_assets / "videos" / role / f"{action}.mp4")


def _copy_trim_source(test_assets: Path, source_role: str, source_action: str, target_project_id: str, step_dir: str = "02_no_bg"):
    target_role, target_action = target_project_id.split("/", 1)
    source = test_assets / "trim_sources" / source_role / source_action
    target = Path("project") / target_role / target_action / "output" / step_dir
    target.mkdir(parents=True, exist_ok=True)
    for image_path in source.glob("*.png"):
        shutil.copy2(image_path, target / image_path.name)


def _create_project(api, role: str, action: str, video_path: str):
    project = api.create_project(role, action, video_path, 1)
    assert project["id"] == f"{role}/{action}"
    assert project["role"] == role
    assert project["action"] == action
    assert Path(project["path"]).exists()
    return project


def _write_audio_timeline(project_path: Path, placement_frame: int = 1):
    audio_dir = project_path / "cache" / "01_audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    with wave.open(str(audio_dir / "source.wav"), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(10)
        wav_file.writeframes(b"\x00\x00" * 20)

    (project_path / "cache" / "audio_timeline.json").write_text(
        json.dumps(
            {
                "source_fps": 10,
                "total_frames": 20,
                "source_wav": "",
                "clips": [
                    {
                        "name": "step",
                        "srcStartFrame": 1,
                        "srcEndFrame": 4,
                        "placementFrame": placement_frame,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_project_role_action_lifecycle(api, test_assets, asset_catalog):
    first_role = asset_catalog[0]
    second_role = asset_catalog[1]
    created = [
        _create_project(api, first_role["role"], first_role["actions"][0], _video(test_assets, first_role["role"], first_role["actions"][0])),
        _create_project(api, first_role["role"], first_role["actions"][1], _video(test_assets, first_role["role"], first_role["actions"][1])),
        _create_project(api, second_role["role"], second_role["actions"][0], _video(test_assets, second_role["role"], second_role["actions"][0])),
        _create_project(api, second_role["role"], second_role["actions"][1], _video(test_assets, second_role["role"], second_role["actions"][1])),
    ]

    roles = {role["name"]: role["projectCount"] for role in api.get_roles()}
    assert roles[first_role["role"]] == 2
    assert roles[second_role["role"]] == 2

    projects = api.get_projects()
    assert {project["id"] for project in projects} >= {project["id"] for project in created}
    listed = {project["id"]: project for project in projects}
    assert listed[created[0]["id"]]["steps"]["1"]["data_ready"] is True
    assert listed[created[0]["id"]]["steps"]["1"]["count"] > 0

    project = api.get_project(f"{first_role['role']}/{first_role['actions'][0]}")
    assert project["output_path"].endswith(f"project/{first_role['role']}/{first_role['actions'][0]}/output")
    assert project["steps"]["1"]["data_ready"] is True

    updated = api.update_project(f"{first_role['role']}/{first_role['actions'][0]}", {"name": "walk-renamed", "fps": 12})
    assert updated["name"] == "walk-renamed"

    assert api.delete_project(f"{second_role['role']}/{second_role['actions'][1]}") is True
    assert not (Path("project") / second_role["role"] / second_role["actions"][1]).exists()


def test_unknown_role_default(api, test_assets, asset_catalog):
    sample = asset_catalog[0]
    project = api.create_project("", "mystery", _video(test_assets, sample["role"], sample["actions"][0]), 1)
    assert project["role"] == UNKNOWN_ROLE
    assert project["id"] == f"{UNKNOWN_ROLE}/mystery"
    assert Path("project") / UNKNOWN_ROLE / "mystery"


def test_legacy_project_migration(api, test_assets):
    legacy_source = test_assets / "legacy_projects" / "legacy_walk"
    shutil.copytree(legacy_source, Path("project") / "legacy_walk")

    legacy = api.get_project("legacy_walk")
    assert legacy["legacy"] is True
    assert legacy["role"] == LEGACY_ROLE

    result = api.migrate_legacy_projects("restored")
    assert result["success"] is True
    assert result["migrated"][0]["to"] == "restored/legacy_walk"
    assert not Path("project/legacy_walk").exists()
    assert Path("project/restored/legacy_walk").exists()

    migrated = api.get_project("restored/legacy_walk")
    assert migrated["legacy"] is False
    assert migrated["role"] == "restored"


def test_legacy_project_migration_accepts_per_project_targets(api, test_assets):
    legacy_source = test_assets / "legacy_projects" / "legacy_walk"
    shutil.copytree(legacy_source, Path("project") / "legacy_walk")
    shutil.copytree(legacy_source, Path("project") / "legacy_attack")

    result = api.migrate_legacy_projects([
        {"projectId": "legacy_walk", "targetRole": "hero", "targetAction": "walk"},
        {"projectId": "legacy_attack", "targetRole": "enemy", "targetAction": "attack"},
    ])

    assert result["success"] is True
    assert {item["to"] for item in result["migrated"]} == {"hero/walk", "enemy/attack"}
    assert not Path("project/legacy_walk").exists()
    assert not Path("project/legacy_attack").exists()
    assert Path("project/hero/walk").exists()
    assert Path("project/enemy/attack").exists()

    walk = api.get_project("hero/walk")
    attack = api.get_project("enemy/attack")
    assert walk["role"] == "hero"
    assert walk["action"] == "walk"
    assert attack["role"] == "enemy"
    assert attack["action"] == "attack"


def test_import_legacy_project_directory_copies_projects_without_overwriting(api, test_assets, tmp_path):
    source_root = tmp_path / "old-video-to-sheet" / "project"
    source_project = source_root / "legacy_walk"
    shutil.copytree(test_assets / "legacy_projects" / "legacy_walk", source_project)

    imported = api.import_legacy_project_directory(str(source_root))

    assert imported["success"] is True
    assert [item["projectId"] for item in imported["imported"]] == ["legacy_walk"]
    assert imported["skipped"] == []
    assert imported["failed"] == []
    assert source_project.is_dir()
    assert Path("project/legacy_walk/cache/global_params.json").is_file()

    source_meta = source_project / "cache" / "global_params.json"
    destination_meta = Path("project/legacy_walk/cache/global_params.json")
    destination_meta.write_text('{"sentinel": "keep-newer-copy"}', encoding="utf-8")

    repeated = api.import_legacy_project_directory(str(source_root))

    assert repeated["success"] is True
    assert repeated["imported"] == []
    assert repeated["skipped"][0]["projectId"] == "legacy_walk"
    assert json.loads(destination_meta.read_text(encoding="utf-8")) == {"sentinel": "keep-newer-copy"}
    assert source_meta.is_file()


def test_import_legacy_project_directory_rejects_directory_without_projects(api, tmp_path):
    source_root = tmp_path / "not-a-project-root"
    source_root.mkdir()
    (source_root / "notes.txt").write_text("unrelated", encoding="utf-8")
    (source_root / "empty-cache" / "cache").mkdir(parents=True)
    broken_meta = source_root / "broken-metadata" / "cache" / "global_params.json"
    broken_meta.parent.mkdir(parents=True)
    broken_meta.write_text("{broken", encoding="utf-8")
    missing_name = source_root / "missing-project-name" / "cache" / "global_params.json"
    missing_name.parent.mkdir(parents=True)
    missing_name.write_text("{}", encoding="utf-8")

    result = api.import_legacy_project_directory(str(source_root))

    assert result["success"] is False
    assert result["imported"] == []
    assert result["skipped"] == []
    assert result["failed"] == [{"projectId": "", "reason": "所选目录中没有有效的旧项目"}]
    assert not any(Path("project").iterdir())


def test_import_legacy_project_directory_accepts_parent_application_directory(api, test_assets, tmp_path):
    app_root = tmp_path / "old-video-to-sheet"
    source_project = app_root / "project" / "legacy_walk"
    shutil.copytree(test_assets / "legacy_projects" / "legacy_walk", source_project)
    (app_root / "unrelated").mkdir()

    result = api.import_legacy_project_directory(str(app_root))

    assert result["success"] is True
    assert Path(result["source"]).resolve() == (app_root / "project").resolve()
    assert [item["projectId"] for item in result["imported"]] == ["legacy_walk"]
    assert result["skipped"] == []
    assert result["failed"] == []
    assert source_project.is_dir()
    assert Path("project/legacy_walk/cache/global_params.json").is_file()


def test_import_legacy_project_directory_prefers_selected_directory_over_project_child(api, test_assets, tmp_path):
    source_root = tmp_path / "legacy-root"
    shutil.copytree(test_assets / "legacy_projects" / "legacy_walk", source_root / "direct_pick")
    shutil.copytree(test_assets / "legacy_projects" / "legacy_walk", source_root / "project" / "nested_pick")

    result = api.import_legacy_project_directory(str(source_root))

    assert result["success"] is True
    assert Path(result["source"]).resolve() == source_root.resolve()
    assert [item["projectId"] for item in result["imported"]] == ["direct_pick"]
    assert Path("project/direct_pick").is_dir()
    assert not Path("project/nested_pick").exists()


def test_import_legacy_project_directory_does_not_recurse_into_other_directories(api, test_assets, tmp_path):
    source_root = tmp_path / "legacy-root"
    shutil.copytree(test_assets / "legacy_projects" / "legacy_walk", source_root / "other" / "legacy_walk")
    shutil.copytree(test_assets / "legacy_projects" / "legacy_walk", source_root / "project" / "nested" / "legacy_walk")

    result = api.import_legacy_project_directory(str(source_root))

    assert result["success"] is False
    assert result["imported"] == []
    assert result["failed"] == [{"projectId": "", "reason": "所选目录中没有有效的旧项目"}]
    assert not any(Path("project").iterdir())


def test_import_legacy_project_directory_rejects_current_project_root(api, test_assets):
    current_root = Path("project").resolve()
    shutil.copytree(test_assets / "legacy_projects" / "legacy_walk", current_root / "legacy_walk")

    with pytest.raises(ValueError, match="所选目录已经是当前项目目录"):
        api.import_legacy_project_directory(str(current_root))

    with pytest.raises(ValueError, match="所选目录已经是当前项目目录"):
        api.import_legacy_project_directory(str(current_root.parent))

    assert (current_root / "legacy_walk" / "cache" / "global_params.json").is_file()


def test_import_legacy_project_directory_skips_invalid_project_metadata(api, test_assets, tmp_path):
    source_root = tmp_path / "legacy-root"
    shutil.copytree(test_assets / "legacy_projects" / "legacy_walk", source_root / "valid_pick")
    invalid_cache = source_root / "invalid_pick" / "cache"
    invalid_cache.mkdir(parents=True)
    (invalid_cache / "global_params.json").write_text("{broken", encoding="utf-8")

    result = api.import_legacy_project_directory(str(source_root))

    assert result["success"] is True
    assert [item["projectId"] for item in result["imported"]] == ["valid_pick"]
    assert not Path("project/invalid_pick").exists()


def test_import_legacy_project_directory_records_failure_and_cleans_staging(api, test_assets, tmp_path, monkeypatch):
    source_root = tmp_path / "legacy-root"
    shutil.copytree(test_assets / "legacy_projects" / "legacy_walk", source_root / "broken_copy")
    shutil.copytree(test_assets / "legacy_projects" / "legacy_walk", source_root / "good_copy")

    real_copytree = shutil.copytree

    def flaky_copytree(src, dst, *args, **kwargs):
        if Path(src).name == "broken_copy":
            raise OSError("simulated copy failure")
        return real_copytree(src, dst, *args, **kwargs)

    monkeypatch.setattr("backend.api.project_api.shutil.copytree", flaky_copytree)

    result = api.import_legacy_project_directory(str(source_root))

    assert result["success"] is False
    assert [item["projectId"] for item in result["imported"]] == ["good_copy"]
    assert [item["projectId"] for item in result["failed"]] == ["broken_copy"]
    assert "simulated copy failure" in result["failed"][0]["reason"]
    assert Path("project/good_copy/cache/global_params.json").is_file()
    assert not list(Path("project").glob(".gam-import-*"))
    assert (source_root / "broken_copy" / "cache" / "global_params.json").is_file()


def test_delete_role(api, test_assets, asset_catalog):
    sample = asset_catalog[0]
    _create_project(api, "delete_me", "walk", _video(test_assets, sample["role"], sample["actions"][0]))
    _create_project(api, "delete_me", "attack", _video(test_assets, sample["role"], sample["actions"][1]))

    assert Path("project/delete_me").exists()
    assert api.delete_role("delete_me") is True
    assert not Path("project/delete_me").exists()
    assert "delete_me" not in {role["name"] for role in api.get_roles()}


def test_config_and_step_params(api, test_assets, asset_catalog):
    sample = asset_catalog[0]
    project = _create_project(api, sample["role"], "config", _video(test_assets, sample["role"], sample["actions"][0]))

    config = api.get_config()
    config["logger_enabled"] = True
    assert api.save_config(config) is True
    assert api.get_config()["logger_enabled"] is True
    seedance_settings = api.seedance_get_settings()
    assert "api_key" not in seedance_settings
    assert api.seedance_test_connection()["success"] is False

    params = api.get_step_params(project["id"], 1)
    params["frame_interval"] = 2
    assert api.save_step_params(project["id"], 1, params) is True
    assert api.get_step_params(project["id"], 1)["frame_interval"] == 2


def test_video_validation_step1_and_frame_api(api, test_assets, asset_catalog):
    sample = asset_catalog[0]
    project = _create_project(api, sample["role"], "frames", _video(test_assets, sample["role"], sample["actions"][0]))

    info = api.get_video_info(project["video_path"])
    assert info["success"] is True
    assert info["frame_count"] > 0
    assert api.validate_video(project["video_path"])["valid"] is True

    task_id = api.start_processing(project["id"], 1, {
        "video_path": project["video_path"],
        "frame_interval": 1,
        "start_frame": 0,
        "end_frame": 3,
        "fps": 6,
    })
    status = wait_for_task(api, task_id)
    assert status["status"] == "completed"

    frames = api.get_frames(project["id"], 1, page=1, page_size=10, use_cache=False)
    assert frames["success"] is True
    assert frames["total"] == 4

    frame_path = frames["frames"][0]["path"]
    assert api.get_frame_image(frame_path)
    assert api.get_frame_thumbnail(frame_path, 32)
    assert "http://localhost:8080/" in api.get_frame_url(frame_path)


def test_api_propagates_dynamic_assets_base_url(isolated_workspace):
    from backend.main import API

    assets_base_url = "http://127.0.0.1:54321"
    api = API()
    frame_api = api._frame_api
    audio_api = api._audio_api
    seedance_api = api._seedance_api
    seedream_api = api._seedream_api

    api.set_assets_base_url(assets_base_url)

    assert frame_api.assets_base_url == assets_base_url
    assert audio_api.assets_base_url == assets_base_url
    assert seedance_api._media_base_url == assets_base_url
    assert seedream_api._media_base_url == assets_base_url


def test_video_validation_allows_vertical_1080p_with_no_resolution_warning(monkeypatch):
    video_api = VideoAPI()

    monkeypatch.setattr(video_api, "get_video_info", lambda _path: {
        "success": True,
        "fps": 30,
        "frame_count": 900,
        "width": 1080,
        "height": 1920,
        "duration": 30,
        "duration_formatted": "00:30",
    })

    result = video_api.validate_video("vertical.mp4")

    assert result["valid"] is True
    assert result["errors"] == []
    assert result["warnings"] == []


def test_video_validation_warns_when_width_or_height_exceeds_2160(monkeypatch):
    video_api = VideoAPI()

    monkeypatch.setattr(video_api, "get_video_info", lambda _path: {
        "success": True,
        "fps": 30,
        "frame_count": 900,
        "width": 1200,
        "height": 2200,
        "duration": 30,
        "duration_formatted": "00:30",
    })

    result = video_api.validate_video("large-vertical.mp4")

    assert result["valid"] is True
    assert result["errors"] == []
    assert result["warnings"] == ["分辨率过高，抠像处理可能会偏慢"]


def test_video_validation_allows_up_to_60_seconds_and_rejects_longer(monkeypatch):
    video_api = VideoAPI()

    monkeypatch.setattr(video_api, "get_video_info", lambda _path: {
        "success": True,
        "fps": 30,
        "frame_count": 1800,
        "width": 1920,
        "height": 1080,
        "duration": 60,
        "duration_formatted": "01:00",
    })

    result = video_api.validate_video("one-minute.mp4")

    assert result["valid"] is True
    assert result["errors"] == []

    monkeypatch.setattr(video_api, "get_video_info", lambda _path: {
        "success": True,
        "fps": 30,
        "frame_count": 1830,
        "width": 1920,
        "height": 1080,
        "duration": 61,
        "duration_formatted": "01:01",
    })

    result = video_api.validate_video("too-long.mp4")

    assert result["valid"] is False
    assert result["errors"] == ["视频过长: 01:01 (最大支持 60 秒)"]


def test_batch_trim_global_and_individual(api, test_assets, asset_catalog):
    sample = asset_catalog[0]
    ids = []
    for action in sample["actions"][:2]:
        project = _create_project(api, sample["role"], f"trim_{action}", _video(test_assets, sample["role"], action))
        ids.append(project["id"])
        _copy_trim_source(test_assets, sample["role"], action, project["id"])
        if len(ids) == 1:
            _write_audio_timeline(Path(project["path"]))

    statuses = api.check_projects_for_trim(ids)
    assert {status["status"] for status in statuses} == {"fallback"}

    global_results = api.execute_batch_trim({"projectIds": ids, "mode": "global", "outputDir": ""})
    assert all(result["status"] == "success" for result in global_results)
    for result in global_results:
        output = Path(result["outputPath"])
        assert output.parts[-3] == sample["role"]
        assert output.parts[-2].startswith("batch-trim")
        assert any(output.glob("*.png"))
    global_audio_output = Path(next(result for result in global_results if result["projectId"] == ids[0])["outputPath"])
    assert len(list(global_audio_output.glob("*.wav"))) == 1
    audio_manifest = json.loads((global_audio_output / "_audio_timeline.json").read_text(encoding="utf-8"))
    assert audio_manifest["clips"][0]["placement_frame"] == 1
    with wave.open(str(next(global_audio_output.glob("*.wav"))), "rb") as exported_wav:
        assert exported_wav.getnframes() == 3

    individual_results = api.execute_batch_trim({"projectIds": ids, "mode": "individual", "outputDir": ""})
    assert all(result["status"] == "success" for result in individual_results)
    for result in individual_results:
        assert (Path(result["outputPath"]) / "_frame_data.json").exists()
    individual_audio_output = Path(next(result for result in individual_results if result["projectId"] == ids[0])["outputPath"])
    assert len(list(individual_audio_output.glob("*.wav"))) == 1
    assert (individual_audio_output / "_audio_timeline.json").exists()


def test_hidden_frames_are_reversible_and_excluded_from_preview_and_export(api, test_assets, asset_catalog):
    sample = asset_catalog[0]
    action = sample["actions"][0]
    project = _create_project(api, sample["role"], "hidden_frames", _video(test_assets, sample["role"], action))
    _copy_trim_source(test_assets, sample["role"], action, project["id"], "02_no_bg")
    _copy_trim_source(test_assets, sample["role"], action, project["id"], "03_hole_punched")
    _write_audio_timeline(Path(project["path"]), placement_frame=2)

    initial = api.get_frames(project["id"], 2, page=1, page_size=10)
    assert initial["timeline_total"] == initial["total"]
    assert [frame["timeline_index"] for frame in initial["frames"]] == list(range(initial["total"]))
    hidden_filename = initial["frames"][1]["filename"]
    hidden_path = Path(initial["frames"][1]["path"])

    hidden = api.set_frame_hidden(project["id"], hidden_filename, True)
    assert hidden == {"success": True, "hidden_frames": [hidden_filename]}
    assert api.get_hidden_frames(project["id"]) == [hidden_filename]
    assert hidden_path.exists()

    for step in (2, 3):
        preview = api.get_frames(project["id"], step, page=1, page_size=10)
        assert preview["total"] == initial["total"] - 1
        assert hidden_filename not in {frame["filename"] for frame in preview["frames"]}
        assert preview["hidden_count"] == 1
        assert preview["timeline_total"] == initial["total"]
        assert [frame["timeline_index"] for frame in preview["frames"][:2]] == [0, 2]

    config_path = Path(project["path"]) / "cache" / "steps_config.json"
    assert json.loads(config_path.read_text(encoding="utf-8"))["hidden_frames"] == [hidden_filename]

    for mode in ("global", "individual"):
        result = api.execute_batch_trim({"projectIds": [project["id"]], "mode": mode, "outputDir": ""})[0]
        assert result["status"] == "success"
        assert result["frameCount"] == initial["total"] - 1
        output_path = Path(result["outputPath"])
        assert len(list(output_path.glob("*.png"))) == initial["total"] - 1
        if mode == "individual":
            frame_data = json.loads((output_path / "_frame_data.json").read_text(encoding="utf-8"))
            assert hidden_filename not in {frame["filename"] for frame in frame_data["frames"]}
        audio_manifest = json.loads((output_path / "_audio_timeline.json").read_text(encoding="utf-8"))
        assert audio_manifest["clips"][0]["source_placement_frame"] == 2
        assert audio_manifest["clips"][0]["placement_frame"] == 1

    restored = api.set_frame_hidden(project["id"], hidden_filename, False)
    assert restored == {"success": True, "hidden_frames": []}
    assert api.get_frames(project["id"], 2, page=1, page_size=10)["total"] == initial["total"]

    api.set_frame_hidden(project["id"], hidden_filename, True)
    assert api.restore_hidden_frames(project["id"]) == {"success": True, "hidden_frames": []}
    assert hidden_path.exists()


@pytest.mark.full
def test_full_rembg_pipeline(api, test_assets, asset_catalog):
    if not check_model_available("u2net"):
        pytest.skip("u2net rembg model is not available locally")

    sample = asset_catalog[0]
    project = _create_project(api, "full", sample["actions"][0], _video(test_assets, sample["role"], sample["actions"][0]))

    step1 = api.start_processing(project["id"], 1, {
        "video_path": project["video_path"],
        "frame_interval": 1,
        "start_frame": 0,
        "end_frame": 2,
        "fps": 6,
    })
    assert wait_for_task(api, step1, timeout=20)["status"] == "completed"

    step2 = api.start_processing(project["id"], 2, {
        "model": "u2net",
        "alpha_matting": False,
        "edge_erode": 0,
        "fps": 6,
    })
    assert wait_for_task(api, step2, timeout=120)["status"] == "completed"

    step3 = api.start_processing(project["id"], 3, {
        "enabled": True,
        "green_intensity": 3,
        "feather_radius": 1,
        "min_hole_size": 0,
        "align_enabled": False,
        "fps": 6,
    })
    assert wait_for_task(api, step3, timeout=30)["status"] == "completed"

    frames = api.get_frames(project["id"], 3, page=1, page_size=10)
    assert frames["total"] > 0


def test_frontend_build(repo_root):
    frontend_dir = repo_root / "frontend"
    if not (frontend_dir / "node_modules").exists():
        pytest.skip("frontend/node_modules is missing; skipping build without installing dependencies")

    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=frontend_dir,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (frontend_dir / "dist" / "index.html").exists()
    assert any((frontend_dir / "dist" / "assets").glob("*.js"))
