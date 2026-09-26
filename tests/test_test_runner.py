from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.run_tests import (
    CommandResult,
    build_all_free_stages,
    build_default_stages,
    build_frontend_stages,
    build_full_local_stages,
    cleanup_run,
    main,
    run_suite,
)


def _zero_cost_python_env(repo_root: Path) -> dict[str, str]:
    guard_dir = repo_root / "scripts" / "zero_cost_sitecustomize"
    return {
        **os.environ,
        "PYTHONPATH": os.pathsep.join((str(guard_dir), str(repo_root))),
        "GAM_ZERO_COST": "1",
    }


def test_default_suite_uses_existing_tools_in_a_fixed_order(repo_root: Path) -> None:
    stages = build_default_stages(repo_root, python_executable="python-test", npm_executable="npm-test")

    assert [stage.name for stage in stages] == [
        "Product identity guard",
        "Python regression",
        "Seedance fake-transport contracts",
        "Frontend unit tests",
        "Frontend typecheck",
        "Frontend production build",
    ]
    assert stages[0].command == (
        "python-test",
        str(repo_root / "scripts" / "check_product_identity.py"),
    )
    assert stages[1].command[:4] == ("python-test", "-m", "pytest", "-q")
    assert stages[2].command[:4] == ("python-test", "-m", "pytest", "-q")
    assert stages[3].command == ("npm-test", "run", "test")
    assert stages[4].command == ("npm-test", "run", "typecheck")
    assert stages[5].command == ("npm-test", "run", "build")


def test_full_local_suite_targets_only_the_public_api_pipeline(repo_root: Path) -> None:
    stages = build_full_local_stages(repo_root, python_executable="python-test")

    assert [stage.name for stage in stages] == ["Local Step 1-3 pipeline"]
    assert stages[0].command == (
        "python-test",
        "-m",
        "pytest",
        "-q",
        str(repo_root / "tests" / "test_full_local_pipeline.py"),
        "-m",
        "full",
    )
    assert stages[0].timeout_seconds == 600


def test_all_free_combines_each_free_stage_once_in_a_fixed_order(repo_root: Path) -> None:
    frontend = build_frontend_stages(repo_root, npm_executable="npm-test")
    stages = build_all_free_stages(
        repo_root,
        python_executable="python-test",
        npm_executable="npm-test",
    )

    assert [stage.stage_id for stage in frontend] == [
        "frontend.unit",
        "frontend.typecheck",
        "frontend.build",
    ]
    assert [stage.stage_id for stage in stages] == [
        "default.product-identity",
        "default.python",
        "default.seedance-contracts",
        "default.frontend-unit",
        "default.frontend-typecheck",
        "default.frontend-build",
        "full-local.pipeline",
    ]


def test_all_free_keeps_keys_out_blocks_network_and_skips_missing_local_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "all-free-real-key"
    monkeypatch.setenv("ARK_API_KEY", secret)
    monkeypatch.setenv("SEEDANCE_API_KEY", secret)
    (tmp_path / "frontend" / "node_modules").mkdir(parents=True)
    report_path = tmp_path / "run" / "report.json"
    observed_stage_ids: list[str] = []

    def safe_command(stage, *, cwd, env):
        observed_stage_ids.append(stage.stage_id)
        assert env["GAM_ZERO_COST"] == "1"
        assert "zero_cost_sitecustomize" in env["PYTHONPATH"]
        assert "zero_cost_node_guard.cjs" in env["NODE_OPTIONS"]
        assert env.get("ARK_API_KEY") is None
        assert env.get("SEEDANCE_API_KEY") is None
        return CommandResult(returncode=0)

    result = run_suite(
        "all-free",
        repo_root=tmp_path,
        command_runner=safe_command,
        npm_executable="npm-test",
        local_model_available=lambda _root, _model: False,
        report_path=report_path,
    )

    assert result.exit_code == 0
    assert observed_stage_ids == [
        "default.product-identity",
        "default.python",
        "default.seedance-contracts",
        "default.frontend-unit",
        "default.frontend-typecheck",
        "default.frontend-build",
    ]
    report_text = report_path.read_text(encoding="utf-8")
    assert secret not in report_text
    report = json.loads(report_text)
    assert report["stages"][-1]["status"] == "SKIP"
    assert report["status"] == "PASS"


def test_success_writes_sanitized_json_report_and_cleans_workspace(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "report-must-not-contain-this-key"
    monkeypatch.setenv("ARK_API_KEY", secret)
    (tmp_path / "frontend" / "node_modules").mkdir(parents=True)
    report_path = tmp_path / "reports" / "report.json"
    observed_workspace: Path | None = None

    def successful_command(stage, *, cwd, env):
        nonlocal observed_workspace
        observed_workspace = Path(env["GAM_CONFIG"]).parent
        assert env.get("ARK_API_KEY") is None
        return CommandResult(returncode=0)

    result = run_suite(
        "frontend",
        repo_root=tmp_path,
        command_runner=successful_command,
        npm_executable="npm-test",
        report_path=report_path,
    )

    assert result.exit_code == 0
    assert result.report_path == report_path
    assert observed_workspace is not None and not observed_workspace.exists()
    report_text = report_path.read_text(encoding="utf-8")
    assert secret not in report_text
    report = json.loads(report_text)
    assert report["suite"] == "frontend"
    assert report["status"] == "PASS"
    assert report["workspace_retained"] is False
    assert report["safety"] == {
        "api_keys_available_to_stages": False,
        "external_network": "blocked",
        "real_seedance_transport": "blocked",
    }
    assert [stage["status"] for stage in report["stages"]] == ["PASS", "PASS", "PASS"]
    assert all(stage["command"] for stage in report["stages"])
    assert [stage["returncode"] for stage in report["stages"]] == [0, 0, 0]
    assert all(stage["started_at"] and stage["ended_at"] for stage in report["stages"])
    assert all(stage["duration_seconds"] >= 0 for stage in report["stages"])
    assert f"JSON report: {report_path}" in capsys.readouterr().out


def test_keyboard_interrupt_is_reported_and_leaves_remaining_stages_resumable(tmp_path: Path) -> None:
    (tmp_path / "frontend" / "node_modules").mkdir(parents=True)
    report_path = tmp_path / "run" / "report.json"
    calls: list[str] = []

    def interrupt_first_stage(stage, *, cwd, env):
        calls.append(stage.stage_id)
        raise KeyboardInterrupt

    result = run_suite(
        "default",
        repo_root=tmp_path,
        command_runner=interrupt_first_stage,
        npm_executable="npm-test",
        report_path=report_path,
    )

    assert result.exit_code == 130
    assert calls == ["default.product-identity"]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "INTERRUPTED"
    assert [stage["status"] for stage in report["stages"]] == ["INTERRUPTED"] * 6
    assert report["stages"][0]["reason"] == "interrupted by user"
    assert all(stage["reason"] for stage in report["stages"][1:])
    assert Path(report["workspace"]).is_dir()


def test_resume_reruns_only_failed_stages_and_keeps_completed_results(tmp_path: Path) -> None:
    (tmp_path / "frontend" / "node_modules").mkdir(parents=True)
    report_path = tmp_path / "run" / "report.json"

    def fail_seedance(stage, *, cwd, env):
        return CommandResult(returncode=1 if stage.stage_id == "default.seedance-contracts" else 0)

    first = run_suite(
        "default",
        repo_root=tmp_path,
        command_runner=fail_seedance,
        npm_executable="npm-test",
        report_path=report_path,
    )
    assert first.exit_code == 1

    resumed_calls: list[str] = []

    def successful_resume(stage, *, cwd, env):
        resumed_calls.append(stage.stage_id)
        return CommandResult(returncode=0)

    resumed = run_suite(
        "default",
        repo_root=tmp_path,
        command_runner=successful_resume,
        npm_executable="npm-test",
        resume_from=report_path,
    )

    assert resumed.exit_code == 0
    assert resumed_calls == ["default.seedance-contracts"]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["resume_count"] == 1
    assert {stage["status"] for stage in report["stages"]} == {"PASS"}
    assert not Path(report["workspace"]).exists()


def test_resume_revalidates_all_stages_when_the_isolated_workspace_was_lost(tmp_path: Path) -> None:
    (tmp_path / "frontend" / "node_modules").mkdir(parents=True)
    report_path = tmp_path / "run" / "report.json"

    def fail_last(stage, *, cwd, env):
        return CommandResult(returncode=1 if stage.stage_id == "default.frontend-build" else 0)

    first = run_suite(
        "default",
        repo_root=tmp_path,
        command_runner=fail_last,
        npm_executable="npm-test",
        report_path=report_path,
    )
    assert first.exit_code == 1
    workspace = Path(json.loads(report_path.read_text(encoding="utf-8"))["workspace"])
    shutil.rmtree(workspace)

    resumed_calls: list[str] = []

    def successful_command(stage, *, cwd, env):
        resumed_calls.append(stage.stage_id)
        return CommandResult(returncode=0)

    resumed = run_suite(
        "default",
        repo_root=tmp_path,
        command_runner=successful_command,
        npm_executable="npm-test",
        resume_from=report_path,
    )

    assert resumed.exit_code == 0
    assert resumed_calls == [
        "default.product-identity",
        "default.python",
        "default.seedance-contracts",
        "default.frontend-unit",
        "default.frontend-typecheck",
        "default.frontend-build",
    ]


def test_explicit_cleanup_removes_only_the_reported_run_workspace(tmp_path: Path) -> None:
    (tmp_path / "frontend" / "node_modules").mkdir(parents=True)
    report_path = tmp_path / "run" / "report.json"

    result = run_suite(
        "frontend",
        repo_root=tmp_path,
        command_runner=lambda stage, **kwargs: CommandResult(returncode=1),
        npm_executable="npm-test",
        report_path=report_path,
    )
    assert result.exit_code == 1
    workspace = Path(json.loads(report_path.read_text(encoding="utf-8"))["workspace"])
    assert workspace.is_dir()

    assert cleanup_run(report_path) is True

    assert not workspace.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["workspace_retained"] is False
    assert report["cleaned_at"]


def test_explicit_cleanup_rejects_a_workspace_symlink_without_deleting_its_target(tmp_path: Path) -> None:
    run_directory = tmp_path / "run"
    run_directory.mkdir()
    external_directory = tmp_path / "external"
    external_directory.mkdir()
    marker = external_directory / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    workspace = run_directory / "workspace"
    workspace.symlink_to(external_directory, target_is_directory=True)
    report_path = run_directory / "report.json"
    report_path.write_text(
        json.dumps({"workspace": str(workspace), "workspace_retained": True}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="symbolic link"):
        cleanup_run(report_path)

    assert marker.read_text(encoding="utf-8") == "keep"


def test_resume_rejects_a_workspace_symlink_without_deleting_its_target(tmp_path: Path) -> None:
    (tmp_path / "frontend" / "node_modules").mkdir(parents=True)
    report_path = tmp_path / "run" / "report.json"
    result = run_suite(
        "frontend",
        repo_root=tmp_path,
        command_runner=lambda stage, **kwargs: CommandResult(returncode=1),
        npm_executable="npm-test",
        report_path=report_path,
    )
    assert result.exit_code == 1
    workspace = Path(json.loads(report_path.read_text(encoding="utf-8"))["workspace"])
    shutil.rmtree(workspace)
    external_directory = tmp_path / "external"
    external_directory.mkdir()
    marker = external_directory / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    workspace.symlink_to(external_directory, target_is_directory=True)

    with pytest.raises(ValueError, match="symbolic link"):
        run_suite(
            "frontend",
            repo_root=tmp_path,
            command_runner=lambda stage, **kwargs: CommandResult(returncode=0),
            npm_executable="npm-test",
            resume_from=report_path,
        )

    assert marker.read_text(encoding="utf-8") == "keep"


def test_failure_manifest_is_retained_and_redacts_configured_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    secret = "failure-report-secret"
    monkeypatch.setenv("SEEDANCE_API_KEY", secret)
    (tmp_path / "frontend" / "node_modules").mkdir(parents=True)
    report_path = tmp_path / "run" / "report.json"

    def fail_with_secret(stage, *, cwd, env):
        if stage.stage_id == "frontend.typecheck":
            raise OSError(f"tool failed near {secret}")
        return CommandResult(returncode=0)

    result = run_suite(
        "frontend",
        repo_root=tmp_path,
        command_runner=fail_with_secret,
        npm_executable="npm-test",
        report_path=report_path,
    )

    assert result.exit_code == 1
    report_text = report_path.read_text(encoding="utf-8")
    assert secret not in report_text
    assert secret not in capsys.readouterr().out
    report = json.loads(report_text)
    assert report["status"] == "FAIL"
    assert [stage["status"] for stage in report["stages"]] == ["PASS", "FAIL", "PASS"]
    assert report["stages"][1]["reason"] == "could not start command: tool failed near [REDACTED]"
    assert report["workspace_retained"] is True
    assert Path(report["workspace"]).is_dir()
    cleanup_run(report_path)


def test_full_local_suite_skips_before_execution_when_model_is_missing(
    repo_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[str] = []

    def unexpected_command(stage, *, cwd, env):
        calls.append(stage.name)
        return CommandResult(returncode=0)

    result = run_suite(
        "full-local",
        repo_root=repo_root,
        command_runner=unexpected_command,
        local_model_available=lambda _root, _model: False,
        report_path=tmp_path / "run" / "report.json",
    )

    assert result.exit_code == 0
    assert calls == []
    assert result.stages[0].status == "SKIP"
    output = capsys.readouterr().out
    assert "u2net rembg model is not installed" in output
    assert "uv run python scripts/download_models.py u2net" in output
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["stages"][0]["status"] == "SKIP"


def test_full_local_failure_retains_the_isolated_workspace(
    repo_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    observed_workspace: Path | None = None

    def failing_pipeline(stage, *, cwd, env):
        nonlocal observed_workspace
        observed_workspace = Path(env["GAM_CONFIG"]).parent
        basetemp_index = stage.command.index("--basetemp") + 1
        basetemp = Path(stage.command[basetemp_index])
        assert basetemp == observed_workspace / "pytest-temp"
        basetemp.mkdir()
        (basetemp / "failed-stage.txt").write_text(stage.name, encoding="utf-8")
        return CommandResult(returncode=1)

    result = run_suite(
        "full-local",
        repo_root=repo_root,
        command_runner=failing_pipeline,
        local_model_available=lambda _root, _model: True,
    )

    assert result.exit_code == 1
    assert observed_workspace is not None
    try:
        assert (observed_workspace / "pytest-temp" / "failed-stage.txt").read_text(encoding="utf-8") == (
            "Local Step 1-3 pipeline"
        )
        assert f"Retained failed workspace: {observed_workspace}" in capsys.readouterr().out
        assert result.report_path is not None
        assert cleanup_run(result.report_path) is True
        assert not observed_workspace.exists()
    finally:
        shutil.rmtree(observed_workspace, ignore_errors=True)


def test_default_suite_is_isolated_and_blocks_real_seedance_transport(
    repo_root: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "must-not-enter-zero-cost-suite"
    monkeypatch.setenv("ARK_API_KEY", secret)
    monkeypatch.setenv("SEEDANCE_API_KEY", secret)
    observations: list[dict[str, object]] = []

    def successful_command(stage, *, cwd, env):
        observations.append(
            {
                "stage": stage.name,
                "cwd": cwd,
                "config": Path(env["GAM_CONFIG"]),
                "guard": env["GAM_ZERO_COST"],
                "pythonpath": env["PYTHONPATH"],
                "node_options": env["NODE_OPTIONS"],
                "ark_api_key": env.get("ARK_API_KEY"),
                "seedance_api_key": env.get("SEEDANCE_API_KEY"),
            }
        )
        assert cwd.is_dir()
        workspace = Path(env["GAM_CONFIG"]).parent
        assert (workspace / "project").is_dir()
        return CommandResult(returncode=0)

    result = run_suite(
        "default",
        repo_root=repo_root,
        command_runner=successful_command,
        npm_executable="npm-test",
    )

    assert result.exit_code == 0
    assert len({item["config"] for item in observations}) == 1
    assert all(item["guard"] == "1" for item in observations)
    assert all("zero_cost_sitecustomize" in str(item["pythonpath"]) for item in observations)
    assert all("zero_cost_node_guard.cjs" in str(item["node_options"]) for item in observations)
    assert all(Path(item["config"]).name == "runtime-config.json" for item in observations)
    assert all(item["ark_api_key"] is None for item in observations)
    assert all(item["seedance_api_key"] is None for item in observations)
    output = capsys.readouterr().out
    assert secret not in output
    assert "PASS" in output
    assert "Python regression" in output
    assert "duration" in output


def test_optional_build_is_reported_as_allowed_skip_without_frontend_dependencies(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "frontend").mkdir()
    calls: list[str] = []

    def successful_command(stage, *, cwd, env):
        calls.append(stage.name)
        return CommandResult(returncode=0)

    result = run_suite(
        "default",
        repo_root=tmp_path,
        command_runner=successful_command,
        npm_executable="npm-test",
    )

    assert result.exit_code == 0
    assert "Frontend production build" not in calls
    assert result.stages[-1].status == "SKIP"
    assert "allowed skip" in capsys.readouterr().out


def test_required_stage_failure_produces_nonzero_exit_and_remaining_results(
    repo_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail_typecheck(stage, *, cwd, env):
        return CommandResult(returncode=2 if stage.name == "Frontend typecheck" else 0)

    result = run_suite(
        "default",
        repo_root=repo_root,
        command_runner=fail_typecheck,
        npm_executable="npm-test",
    )

    assert result.exit_code == 1
    assert [stage.status for stage in result.stages].count("FAIL") == 1
    assert len(result.stages) == 6
    assert "FAIL" in capsys.readouterr().out


def test_command_start_failure_is_reported_and_does_not_abort_remaining_stages(
    repo_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[str] = []

    def missing_python(stage, *, cwd, env):
        calls.append(stage.name)
        if stage.name == "Python regression":
            raise FileNotFoundError("python-test was not found")
        return CommandResult(returncode=0)

    result = run_suite(
        "default",
        repo_root=repo_root,
        command_runner=missing_python,
        npm_executable="npm-test",
    )

    assert result.exit_code == 1
    assert len(calls) == 6
    assert result.stages[1].status == "FAIL"
    assert result.stages[1].reason == "could not start command: python-test was not found"
    assert "[FAIL] Python regression" in capsys.readouterr().out


def test_cli_defaults_to_free_suite_and_rejects_unknown_suite(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected: list[str] = []

    def fake_run_suite(suite, **kwargs):
        selected.append(suite)
        return type("Result", (), {"exit_code": 0})()

    assert main([], repo_root=repo_root, suite_runner=fake_run_suite) == 0
    assert selected == ["default"]

    with pytest.raises(SystemExit):
        main(["paid"], repo_root=repo_root, suite_runner=fake_run_suite)


def test_cli_resume_uses_the_reported_suite_and_report_path(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({"suite": "frontend"}), encoding="utf-8")
    observed: dict[str, object] = {}

    def fake_run_suite(suite, **kwargs):
        observed.update({"suite": suite, **kwargs})
        return type("Result", (), {"exit_code": 0})()

    assert main(["--resume", str(report_path)], repo_root=tmp_path, suite_runner=fake_run_suite) == 0
    assert observed["suite"] == "frontend"
    assert observed["resume_from"] == report_path.resolve()


def test_zero_cost_python_guard_rejects_real_transport_before_a_request(repo_root: Path, tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", "from backend.seedance.client import ArkClient; ArkClient('fake-test-key')"],
        cwd=tmp_path,
        env=_zero_cost_python_env(repo_root),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "real Seedance transport is disabled" in result.stderr


def test_zero_cost_python_guard_allows_loopback_but_blocks_external_connections(
    repo_root: Path, tmp_path: Path
) -> None:
    probe = """
import socket

loopback = socket.socket()
try:
    loopback.connect(("127.0.0.1", 9))
except RuntimeError as error:
    raise SystemExit(f"loopback was blocked: {error}")
except OSError:
    pass
finally:
    loopback.close()

external = socket.socket()
try:
    external.connect(("203.0.113.1", 80))
except RuntimeError as error:
    if "external network is disabled" not in str(error):
        raise
except OSError as error:
    raise SystemExit(f"external connection reached the OS: {error}")
else:
    raise SystemExit("external connection was not blocked")
finally:
    external.close()

try:
    socket.getaddrinfo("ark.cn-beijing.volces.com", 443)
except RuntimeError as error:
    if "external network is disabled" in str(error):
        raise SystemExit(0)
    raise
except OSError as error:
    raise SystemExit(f"external DNS reached the OS: {error}")
raise SystemExit("external DNS was not blocked")
"""
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=tmp_path,
        env=_zero_cost_python_env(repo_root),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_zero_cost_node_guard_blocks_external_connections_and_dns(repo_root: Path, tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    guard = repo_root / "scripts" / "zero_cost_node_guard.cjs"
    probe = """
const net = require('node:net');
const dns = require('node:dns');
try {
  net.connect({ host: '203.0.113.1', port: 80 });
  process.exit(2);
} catch (error) {
  if (!String(error).includes('external network is disabled')) throw error;
}
try {
  dns.lookup('ark.cn-beijing.volces.com', () => {});
  process.exit(3);
} catch (error) {
  if (!String(error).includes('external network is disabled')) throw error;
}
"""
    result = subprocess.run(
        [node, "-e", probe],
        cwd=tmp_path,
        env={**os.environ, "NODE_OPTIONS": f'--require="{guard}"'},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
