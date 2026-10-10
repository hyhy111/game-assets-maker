import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from src.agent_tools.explain import explain_step
from src.agent_tools.schemas import AgentErrorCode, error_response, success_response
from src.agent_tools.service import AgentWorkflowService
from src.agent_tools.ui_client import AgentUIClient


def _run_agent_cli(*args, cwd=None, env=None):
    if env is None:
        # Keep test runs on an isolated runtime config so the agent CLI never
        # reads or seeds the developer's real configuration.
        env = {
            **os.environ,
            "GAM_CONFIG": str(Path(tempfile.mkdtemp()) / "runtime-config.json"),
        }
    return subprocess.run(
        [sys.executable, "-m", "src.cli.agent", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _copy_trim_source(
    test_assets: Path,
    source_role: str,
    source_action: str,
    target_project_id: str,
    step_dir: str = "02_no_bg",
):
    target_role, target_action = target_project_id.split("/", 1)
    source = test_assets / "trim_sources" / source_role / source_action
    target = Path("project") / target_role / target_action / "output" / step_dir
    target.mkdir(parents=True, exist_ok=True)
    for image_path in source.glob("*.png"):
        shutil.copy2(image_path, target / image_path.name)


def test_agent_cli_doctor_outputs_json():
    result = _run_agent_cli("doctor")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["operation"] == "doctor"


def test_installed_agent_entrypoint_defaults_to_home_gam(tmp_path, repo_root):
    launch_dir = tmp_path / "launch"
    launch_dir.mkdir()
    fake_home = tmp_path / "developer-home"
    env = {**os.environ, "HOME": str(fake_home), "USERPROFILE": str(fake_home), "PYTHONPATH": str(repo_root)}
    for name in ("GAM_CONFIG", "GAM_DATA_MODE", "GAM_DATA_ROOT"):
        env.pop(name, None)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from src.cli.agent import installed_main; raise SystemExit(installed_main())",
            "doctor",
        ],
        cwd=launch_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert Path(payload["data"]["project_root"]) == fake_home / ".gam"


def test_agent_cli_step_explain_outputs_json():
    result = _run_agent_cli("step", "explain", "--step", "2")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["data"]["step"] == 2


def test_agent_cli_missing_video_exits_nonzero(tmp_path):
    result = _run_agent_cli(
        "project",
        "create",
        "--role",
        "hero",
        "--action",
        "idle",
        "--video",
        str(tmp_path / "missing.mp4"),
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "VIDEO_NOT_FOUND"


def test_agent_cli_project_create_stdout_is_json_only(isolated_workspace, test_assets, asset_catalog, repo_root):
    sample = asset_catalog[0]
    video = test_assets / "videos" / sample["role"] / f"{sample['actions'][0]}.mp4"

    result = _run_agent_cli(
        "project",
        "create",
        "--role",
        "hero",
        "--action",
        "idle",
        "--video",
        str(video),
        cwd=isolated_workspace,
        env={**os.environ, "PYTHONPATH": str(repo_root)},
    )

    assert result.returncode == 0
    assert result.stdout.startswith("{")
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["operation"] == "project.create"


def test_agent_cli_step_run_malformed_param_outputs_json(isolated_workspace, repo_root):
    result = _run_agent_cli(
        "step",
        "run",
        "--project",
        "agent/idle",
        "--step",
        "1",
        "--param",
        "badparam",
        cwd=isolated_workspace,
        env={**os.environ, "PYTHONPATH": str(repo_root)},
    )

    assert result.returncode == 1
    assert result.stdout.startswith("{")
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["operation"] == "step.run"
    assert payload["error"]["code"] == "CONFIG_INVALID"
    assert payload["error"]["details"]["param"] == "badparam"


def test_success_response_shape():
    response = success_response(
        operation="doctor",
        data={"project_root": "."},
        warnings=["model missing"],
        next_actions=[{"command": "gam-agent doctor", "reason": "Re-check environment"}],
    )

    assert response == {
        "ok": True,
        "operation": "doctor",
        "data": {"project_root": "."},
        "warnings": ["model missing"],
        "next_actions": [{"command": "gam-agent doctor", "reason": "Re-check environment"}],
    }
    json.dumps(response)


def test_error_response_shape():
    response = error_response(
        operation="project.create",
        code=AgentErrorCode.VIDEO_NOT_FOUND,
        message="Video file not found: missing.mp4",
        details={"video_path": "missing.mp4"},
        next_actions=[{"command": "gam-agent doctor", "reason": "Check workspace"}],
    )

    assert response["ok"] is False
    assert response["operation"] == "project.create"
    assert response["error"]["code"] == "VIDEO_NOT_FOUND"
    assert response["error"]["details"]["video_path"] == "missing.mp4"
    assert response["next_actions"][0]["command"] == "gam-agent doctor"


def test_explain_step2_contains_review_relevant_parameters():
    response = explain_step(step=2)

    assert response["step"] == 2
    parameter_names = {item["name"] for item in response["parameters"]}
    assert "alpha_matting_erode_size" in parameter_names
    assert "alpha_matting_background_threshold" in parameter_names
    assert response["requires_review"] is True


def test_explain_step_returns_independent_copies():
    first = explain_step(step=2)
    first["parameters"].append(
        {
            "name": "fake_parameter",
            "effect": "fake",
            "recommended": "fake",
            "risk": "fake",
        }
    )

    second = explain_step(step=2)
    parameter_names = {item["name"] for item in second["parameters"]}
    assert "fake_parameter" not in parameter_names

    first_parameter = explain_step(step=2, parameter="alpha_matting_erode_size")
    first_parameter["parameter"]["recommended"] = "fake recommendation"

    second_parameter = explain_step(step=2, parameter="alpha_matting_erode_size")
    assert second_parameter["parameter"]["recommended"] == "默认值：5"


def test_doctor_reports_project_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='game-assets-maker'\n", encoding="utf-8")
    (tmp_path / "frontend").mkdir()
    (tmp_path / "backend").mkdir()
    (tmp_path / "project").mkdir()

    service = AgentWorkflowService(root=tmp_path, ui_client=AgentUIClient(port=1))
    response = service.doctor()

    assert response["ok"] is True
    assert response["operation"] == "doctor"
    assert response["data"]["project_root"] == str(tmp_path)
    assert response["data"]["checks"]["pyproject"] is True
    assert response["data"]["checks"]["project_dir"] is True


def test_doctor_does_not_create_missing_project_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='game-assets-maker'\n", encoding="utf-8")
    (tmp_path / "frontend").mkdir()
    (tmp_path / "backend").mkdir()

    service = AgentWorkflowService(root=tmp_path, ui_client=AgentUIClient(port=1))
    response = service.doctor()

    assert response["data"]["checks"]["project_dir"] is False
    assert (tmp_path / "project").exists() is False


def test_doctor_reads_installed_model_from_gam_user_data(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "pyproject.toml").write_text("[project]\nname='game-assets-maker'\n", encoding="utf-8")
    (workspace / "frontend").mkdir()
    (workspace / "backend").mkdir()
    gam_root = tmp_path / ".gam"
    model = gam_root / "models" / "rembg" / "u2net.onnx"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"model")
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    monkeypatch.setenv("GAM_DATA_ROOT", str(gam_root))

    response = AgentWorkflowService(root=workspace, ui_client=AgentUIClient(port=1)).doctor()

    assert response["data"]["checks"]["u2net_model"] is True


def test_doctor_import_has_no_workspace_side_effects(tmp_path):
    script = """
import json
from pathlib import Path
from src.agent_tools.service import AgentWorkflowService
from src.agent_tools.ui_client import AgentUIClient
AgentWorkflowService(root=Path.cwd(), ui_client=AgentUIClient(port=1)).doctor()
print(json.dumps({name: Path(name).exists() for name in ["project", "models", "logs"]}))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(Path.cwd())},
        capture_output=True,
        text=True,
        check=True,
    )

    assert json.loads(result.stdout) == {"project": False, "models": False, "logs": False}


def test_project_create_returns_json_summary(api, test_assets, asset_catalog):
    sample = asset_catalog[0]
    video = test_assets / "videos" / sample["role"] / f"{sample['actions'][0]}.mp4"

    service = AgentWorkflowService(root=Path.cwd(), ui_client=AgentUIClient(port=1))
    response = service.create_project(role="agent", action="idle", video_path=video, frame_interval=1)

    assert response["ok"] is True
    assert response["operation"] == "project.create"
    assert response["data"]["project_id"] == "agent/idle"
    assert Path(response["data"]["project_path"]).exists()
    assert response["data"]["steps"]["1"]["data_ready"] is True
    assert response["next_actions"][0]["command"] == "gam-agent step run --project agent/idle --step 1"


def test_project_create_preserves_step1_unprocessed_state(api, test_assets, asset_catalog):
    sample = asset_catalog[0]
    video = test_assets / "videos" / sample["role"] / f"{sample['actions'][0]}.mp4"

    service = AgentWorkflowService(root=Path.cwd(), ui_client=AgentUIClient(port=1))
    response = service.create_project(role="agent", action="fresh", video_path=video, frame_interval=1)

    project_path = Path(response["data"]["project_path"])
    config = json.loads((project_path / "cache" / "steps_config.json").read_text(encoding="utf-8"))
    step1_status = response["data"]["steps"]["1"]

    assert config["step1"]["processed"] is False
    assert config["step1"]["processing_time"] == 0
    assert step1_status["processed"] is False
    assert step1_status["completed"] is False
    assert step1_status["data_ready"] is True
    assert step1_status["count"] > 0


def test_service_run_step1_completes_project(api, test_assets, asset_catalog):
    sample = asset_catalog[0]
    video = test_assets / "videos" / sample["role"] / f"{sample['actions'][0]}.mp4"
    service = AgentWorkflowService(root=Path.cwd(), ui_client=AgentUIClient(port=1))
    created = service.create_project("agent", "step1", video)

    response = service.run_step(created["data"]["project_id"], 1, {"end_frame": 3, "fps": 6})

    assert response["ok"] is True
    assert response["operation"] == "step.run"
    assert response["data"]["step"] == 1
    assert response["data"]["status"] == "completed"
    assert response["data"]["requires_review"] is False


def test_service_run_step_timeout_cancels_task(tmp_path):
    class FakeProjectAPI:
        def get_project(self, project_id):
            return {"id": project_id, "video_path": str(tmp_path / "input.mp4")}

    class FakeProcessAPI:
        def parameter_transaction(self, project_id):
            from contextlib import nullcontext

            return nullcontext()

        def save_step_params(self, project_id, step, params):
            return True

        def get_step_params(self, project_id, step):
            from backend.api.process_api import ProcessAPI

            return ProcessAPI.DEFAULT_STEP_PARAMS[step].copy()

        def __init__(self):
            self.cancelled_task_id = None

        def start_processing(self, project_id, step, params):
            return "task-timeout"

        def get_task_status(self, task_id):
            return {"success": True, "task_id": task_id, "status": "running"}

        def cancel_task(self, task_id):
            self.cancelled_task_id = task_id
            return True

    process_api = FakeProcessAPI()
    service = AgentWorkflowService(root=tmp_path, ui_client=AgentUIClient(port=1))
    service._project_api = FakeProjectAPI()
    service._process_api = process_api

    response = service.run_step("agent/timeout", 1, timeout_seconds=0)

    assert response["ok"] is False
    assert response["operation"] == "step.run"
    assert response["error"]["code"] == "PROCESS_FAILED"
    assert response["error"]["details"]["project_id"] == "agent/timeout"
    assert response["error"]["details"]["step"] == 1
    assert response["error"]["details"]["task_id"] == "task-timeout"
    assert response["error"]["details"]["timeout_seconds"] == 0
    assert process_api.cancelled_task_id == "task-timeout"


def test_service_run_step_unknown_task_status_fails_without_looping(tmp_path):
    class FakeProjectAPI:
        def get_project(self, project_id):
            return {"id": project_id, "video_path": str(tmp_path / "input.mp4")}

    class FakeProcessAPI:
        def parameter_transaction(self, project_id):
            from contextlib import nullcontext

            return nullcontext()

        def save_step_params(self, project_id, step, params):
            return True

        def get_step_params(self, project_id, step):
            from backend.api.process_api import ProcessAPI

            return ProcessAPI.DEFAULT_STEP_PARAMS[step].copy()

        def __init__(self):
            self.cancelled_task_id = None
            self.status_calls = 0

        def start_processing(self, project_id, step, params):
            return "task-missing"

        def get_task_status(self, task_id):
            self.status_calls += 1
            return {"success": False, "error": "Task not found"}

        def cancel_task(self, task_id):
            self.cancelled_task_id = task_id
            return True

    process_api = FakeProcessAPI()
    service = AgentWorkflowService(root=tmp_path, ui_client=AgentUIClient(port=1))
    service._project_api = FakeProjectAPI()
    service._process_api = process_api

    response = service.run_step("agent/missing-task", 1)

    assert response["ok"] is False
    assert response["operation"] == "step.run"
    assert response["error"]["code"] == "PROCESS_FAILED"
    assert response["error"]["details"]["project_id"] == "agent/missing-task"
    assert response["error"]["details"]["step"] == 1
    assert response["error"]["details"]["task_id"] == "task-missing"
    assert response["error"]["details"]["task"] == {"success": False, "error": "Task not found"}
    assert process_api.status_calls == 1
    assert process_api.cancelled_task_id is None


def test_service_run_step_unexpected_task_status_fails_without_looping(tmp_path):
    class FakeProjectAPI:
        def get_project(self, project_id):
            return {"id": project_id, "video_path": str(tmp_path / "input.mp4")}

    class FakeProcessAPI:
        def parameter_transaction(self, project_id):
            from contextlib import nullcontext

            return nullcontext()

        def save_step_params(self, project_id, step, params):
            return True

        def get_step_params(self, project_id, step):
            from backend.api.process_api import ProcessAPI

            return ProcessAPI.DEFAULT_STEP_PARAMS[step].copy()

        def __init__(self):
            self.cancelled_task_id = None
            self.status_calls = 0

        def start_processing(self, project_id, step, params):
            return "task-lost"

        def get_task_status(self, task_id):
            self.status_calls += 1
            return {"success": True, "task_id": task_id, "status": "lost"}

        def cancel_task(self, task_id):
            self.cancelled_task_id = task_id
            return True

    process_api = FakeProcessAPI()
    service = AgentWorkflowService(root=tmp_path, ui_client=AgentUIClient(port=1))
    service._project_api = FakeProjectAPI()
    service._process_api = process_api

    response = service.run_step("agent/lost-task", 1)

    assert response["ok"] is False
    assert response["operation"] == "step.run"
    assert response["error"]["code"] == "PROCESS_FAILED"
    assert response["error"]["details"]["project_id"] == "agent/lost-task"
    assert response["error"]["details"]["step"] == 1
    assert response["error"]["details"]["task_id"] == "task-lost"
    assert response["error"]["details"]["task"]["status"] == "lost"
    assert process_api.status_calls == 1
    assert process_api.cancelled_task_id is None


def test_service_batch_trim_global_returns_final_output(api, test_assets, asset_catalog):
    sample = asset_catalog[0]
    video = test_assets / "videos" / sample["role"] / f"{sample['actions'][0]}.mp4"
    service = AgentWorkflowService(root=Path.cwd(), ui_client=AgentUIClient(port=1))
    created = service.create_project("agent", "trim", video)
    project_id = created["data"]["project_id"]
    _copy_trim_source(test_assets, sample["role"], sample["actions"][0], project_id)

    response = service.batch_trim([project_id], mode="global")

    assert response["ok"] is True
    assert response["operation"] == "batch-trim"
    assert response["data"]["final"] is True
    assert response["data"]["mode"] == "global"
    assert response["data"]["results"][0]["project_id"] == project_id


def test_service_batch_trim_mixed_sources_keeps_valid_result(api, test_assets, asset_catalog):
    sample = asset_catalog[0]
    video = test_assets / "videos" / sample["role"] / f"{sample['actions'][0]}.mp4"
    service = AgentWorkflowService(root=Path.cwd(), ui_client=AgentUIClient(port=1))
    created = service.create_project("agent", "trim-valid", video)
    valid_project_id = created["data"]["project_id"]
    missing_project_id = "agent/trim-missing"
    _copy_trim_source(test_assets, sample["role"], sample["actions"][0], valid_project_id)

    response = service.batch_trim([valid_project_id, missing_project_id], mode="global")

    assert response["ok"] is False
    assert response["error"]["code"] == "BATCH_TRIM_PARTIAL"
    results = {result["project_id"]: result for result in response["error"]["details"]["results"]}
    assert results[valid_project_id]["status"] == "success"
    assert results[valid_project_id]["frame_count"] > 0
    assert results[missing_project_id]["status"] == "failed"


def test_project_create_missing_video_returns_structured_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    service = AgentWorkflowService(root=tmp_path, ui_client=AgentUIClient(port=1))

    response = service.create_project(role="agent", action="idle", video_path=tmp_path / "missing.mp4")

    assert response["ok"] is False
    assert response["error"]["code"] == "VIDEO_NOT_FOUND"
    assert response["operation"] == "project.create"


def test_service_explain_uses_step_explain_operation():
    service = AgentWorkflowService()

    response = service.explain(step=2)
    invalid_response = service.explain(step=99)

    assert response["ok"] is True
    assert response["operation"] == "step.explain"
    assert response["data"]["step"] == 2
    assert invalid_response["ok"] is False
    assert invalid_response["operation"] == "step.explain"
    assert invalid_response["error"]["code"] == "INVALID_STEP"
