#!/usr/bin/env python3
"""Cross-platform, zero-cost automated test entry point."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class Stage:
    stage_id: str
    name: str
    command: tuple[str, ...]
    working_directory: Literal["workspace", "frontend"]
    requires_frontend_dependencies: bool = False
    timeout_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int


@dataclass(frozen=True, slots=True)
class StageResult:
    name: str
    status: str
    duration_seconds: float
    reason: str = ""
    returncode: int | None = None


@dataclass(frozen=True, slots=True)
class SuiteResult:
    stages: tuple[StageResult, ...]
    exit_code: int
    report_path: Path | None = None


CommandRunner = Callable[..., CommandResult]
SuiteRunner = Callable[..., SuiteResult]
ModelAvailabilityChecker = Callable[[Path, str], bool]


def build_default_stages(
    repo_root: Path,
    *,
    python_executable: str = sys.executable,
    npm_executable: str | None = None,
) -> tuple[Stage, ...]:
    """Return the default suite without executing or reimplementing test tools."""
    npm = npm_executable or shutil.which("npm") or "npm"
    tests = repo_root / "tests"
    return (
        Stage(
            "default.product-identity",
            "Product identity guard",
            (python_executable, str(repo_root / "scripts" / "check_product_identity.py")),
            "workspace",
        ),
        Stage(
            "default.python",
            "Python regression",
            (
                python_executable,
                "-m",
                "pytest",
                "-q",
                str(tests),
                f"--ignore={tests / 'seedance'}",
                "-k",
                "not test_frontend_build",
            ),
            "workspace",
        ),
        Stage(
            "default.seedance-contracts",
            "Seedance fake-transport contracts",
            (
                python_executable,
                "-m",
                "pytest",
                "-q",
                str(tests / "seedance"),
                "-k",
                "not urllib_transport",
            ),
            "workspace",
        ),
        Stage("default.frontend-unit", "Frontend unit tests", (npm, "run", "test"), "frontend"),
        Stage("default.frontend-typecheck", "Frontend typecheck", (npm, "run", "typecheck"), "frontend"),
        Stage(
            "default.frontend-build",
            "Frontend production build",
            (npm, "run", "build"),
            "frontend",
            requires_frontend_dependencies=True,
        ),
    )


def build_full_local_stages(
    repo_root: Path,
    *,
    python_executable: str = sys.executable,
) -> tuple[Stage, ...]:
    """Return the local media pipeline stage without starting rembg or Seedance."""
    return (
        Stage(
            "full-local.pipeline",
            "Local Step 1-3 pipeline",
            (
                python_executable,
                "-m",
                "pytest",
                "-q",
                str(repo_root / "tests" / "test_full_local_pipeline.py"),
                "-m",
                "full",
            ),
            "workspace",
            timeout_seconds=600,
        ),
    )


def build_frontend_stages(
    _repo_root: Path,
    *,
    npm_executable: str | None = None,
) -> tuple[Stage, ...]:
    npm = npm_executable or shutil.which("npm") or "npm"
    return (
        Stage("frontend.unit", "Frontend unit tests", (npm, "run", "test"), "frontend"),
        Stage("frontend.typecheck", "Frontend typecheck", (npm, "run", "typecheck"), "frontend"),
        Stage(
            "frontend.build",
            "Frontend production build",
            (npm, "run", "build"),
            "frontend",
            requires_frontend_dependencies=True,
        ),
    )


def build_all_free_stages(
    repo_root: Path,
    *,
    python_executable: str = sys.executable,
    npm_executable: str | None = None,
) -> tuple[Stage, ...]:
    return (
        *build_default_stages(
            repo_root,
            python_executable=python_executable,
            npm_executable=npm_executable,
        ),
        *build_full_local_stages(repo_root, python_executable=python_executable),
    )


def _local_model_available(repo_root: Path, model: str) -> bool:
    return (repo_root / "models" / "rembg" / f"{model}.onnx").is_file()


def _run_command(stage: Stage, *, cwd: Path, env: dict[str, str]) -> CommandResult:
    completed = subprocess.run(
        stage.command,
        cwd=cwd,
        env=env,
        check=False,
        timeout=stage.timeout_seconds,
    )
    return CommandResult(returncode=completed.returncode)


def _stage_for_workspace(stage: Stage, workspace: Path) -> Stage:
    if stage.stage_id != "full-local.pipeline":
        return stage
    return replace(stage, command=(*stage.command, "--basetemp", str(workspace / "pytest-temp")))


def _isolated_environment(repo_root: Path, workspace: Path) -> dict[str, str]:
    guard_dir = repo_root / "scripts" / "zero_cost_sitecustomize"
    node_guard = repo_root / "scripts" / "zero_cost_node_guard.cjs"
    existing_pythonpath = os.environ.get("PYTHONPATH", "")
    existing_node_options = os.environ.get("NODE_OPTIONS", "")
    python_paths = [str(guard_dir), str(repo_root)]
    if existing_pythonpath:
        python_paths.append(existing_pythonpath)

    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONPATH": os.pathsep.join(python_paths),
            "GAM_CONFIG": str(workspace / "runtime-config.json"),
            "GAM_ZERO_COST": "1",
            "NODE_OPTIONS": " ".join(
                part for part in (f'--require="{node_guard}"', existing_node_options) if part
            ),
        }
    )
    environment.pop("ARK_API_KEY", None)
    environment.pop("SEEDANCE_API_KEY", None)
    return environment


def _prepare_workspace(workspace: Path) -> None:
    (workspace / "project").mkdir()
    (workspace / "runtime-config.json").write_text(
        json.dumps({"seedance": {"api_key": "", "cache_dir": str(workspace / "seedance-cache")}}),
        encoding="utf-8",
    )


def _print_result(result: StageResult, secrets: tuple[str, ...] = ()) -> None:
    reason = result.reason
    for secret in secrets:
        if secret:
            reason = reason.replace(secret, "[REDACTED]")
    suffix = f" ({reason})" if reason else ""
    print(f"[{result.status}] {result.name} duration={result.duration_seconds:.2f}s{suffix}", flush=True)


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _write_json_report(report_path: Path, report: dict[str, Any], secrets: tuple[str, ...]) -> None:
    content = json.dumps(report, ensure_ascii=False, indent=2)
    for secret in secrets:
        if secret:
            content = content.replace(secret, "[REDACTED]")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = report_path.with_suffix(report_path.suffix + ".tmp")
    temporary_path.write_text(content + "\n", encoding="utf-8")
    temporary_path.replace(report_path)


def _workspace_ready(workspace: Path) -> bool:
    return (
        workspace.is_dir()
        and (workspace / "project").is_dir()
        and (workspace / "runtime-config.json").is_file()
    )


def _reported_workspace(report_path: Path, report: dict[str, Any]) -> Path:
    workspace = Path(report["workspace"])
    expected_workspace = report_path.parent / "workspace"
    if not workspace.is_absolute() or Path(os.path.abspath(workspace)) != expected_workspace:
        raise ValueError("Report workspace must be inside the report directory")
    if workspace.is_symlink():
        raise ValueError("Report workspace must not be a symbolic link")
    return workspace


def cleanup_run(report_path: Path) -> bool:
    """Remove a retained workspace while preserving its machine-readable report."""
    report_path = report_path.resolve()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    workspace = _reported_workspace(report_path, report)
    existed = workspace.is_dir()
    if existed:
        shutil.rmtree(workspace)
    report["workspace_retained"] = False
    report["cleaned_at"] = _timestamp()
    _write_json_report(report_path, report, ())
    return existed


def run_suite(
    suite: str,
    *,
    repo_root: Path,
    command_runner: CommandRunner = _run_command,
    npm_executable: str | None = None,
    local_model_available: ModelAvailabilityChecker = _local_model_available,
    report_path: Path | None = None,
    resume_from: Path | None = None,
) -> SuiteResult:
    if suite not in {"default", "frontend", "full-local", "all-free"}:
        raise ValueError(f"Unsupported free test suite: {suite}")

    repo_root = repo_root.resolve()
    if suite == "default":
        stages = build_default_stages(repo_root, npm_executable=npm_executable)
    elif suite == "frontend":
        stages = build_frontend_stages(repo_root, npm_executable=npm_executable)
    elif suite == "full-local":
        stages = build_full_local_stages(repo_root)
    else:
        stages = build_all_free_stages(repo_root, npm_executable=npm_executable)

    resuming = resume_from is not None
    if resuming:
        report_path = resume_from.resolve()
        if not report_path.is_file():
            raise ValueError(f"Resume report does not exist: {report_path}")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("suite") != suite:
            raise ValueError(f"Resume report is for suite {report.get('suite')!r}, not {suite!r}")
        stage_reports = report.get("stages", [])
        if [item.get("id") for item in stage_reports] != [stage.stage_id for stage in stages]:
            raise ValueError("Resume report stages do not match the current suite")
        workspace = _reported_workspace(report_path, report)
        workspace_was_ready = _workspace_ready(workspace)
        report["resume_count"] = int(report.get("resume_count", 0)) + 1
        report["status"] = "INTERRUPTED"
        report["ended_at"] = None
        report["workspace_retained"] = True
        previous_duration = float(report.get("duration_seconds", 0.0))
    elif report_path is None:
        run_root = Path(tempfile.mkdtemp(prefix="gam-test-run-")).resolve()
        report_path = run_root / "report.json"
    else:
        report_path = report_path.resolve()
        run_root = report_path.parent
        run_root.mkdir(parents=True, exist_ok=True)
        if report_path.exists():
            raise ValueError(f"Report already exists: {report_path}")
    if not resuming:
        workspace = run_root / "workspace"
        if workspace.exists():
            raise ValueError(f"Run workspace already exists: {workspace}")
        workspace_was_ready = False

    started_at = _timestamp()
    if resuming:
        report["last_attempt_started_at"] = started_at
    secrets = tuple(value for key in ("ARK_API_KEY", "SEEDANCE_API_KEY") if (value := os.environ.get(key)))
    if not resuming:
        stage_reports = [
            {
                "id": stage.stage_id,
                "name": stage.name,
                "command": list(stage.command),
                "working_directory": stage.working_directory,
                "status": "INTERRUPTED",
                "reason": "not started",
                "started_at": None,
                "ended_at": None,
                "duration_seconds": 0.0,
                "returncode": None,
                "artifact_path": str(workspace),
            }
            for stage in stages
        ]
        report = {
            "schema_version": 1,
            "run_id": uuid.uuid4().hex,
            "suite": suite,
            "status": "INTERRUPTED",
            "started_at": started_at,
            "ended_at": None,
            "duration_seconds": 0.0,
            "last_attempt_started_at": started_at,
            "last_attempt_duration_seconds": 0.0,
            "workspace": str(workspace),
            "workspace_retained": True,
            "resume_count": 0,
            "safety": {
                "api_keys_available_to_stages": False,
                "external_network": "blocked",
                "real_seedance_transport": "blocked",
            },
            "stages": stage_reports,
        }
    _write_json_report(report_path, report, secrets)

    results: list[StageResult] = []
    retain_workspace = False
    interrupted = False
    suite_started = time.perf_counter()
    try:
        if not workspace_was_ready:
            shutil.rmtree(workspace, ignore_errors=True)
            workspace.mkdir()
            _prepare_workspace(workspace)
        environment = _isolated_environment(repo_root, workspace)

        print(f"Running zero-cost suite: {suite}", flush=True)
        print(f"Isolated workspace: {workspace}", flush=True)
        print("External network and real Seedance transports: blocked", flush=True)

        for index, stage in enumerate(stages):
            if resuming and workspace_was_ready and stage_reports[index]["status"] in {"PASS", "SKIP"}:
                previous = stage_reports[index]
                results.append(
                    StageResult(
                        stage.name,
                        previous["status"],
                        float(previous["duration_seconds"]),
                        str(previous.get("reason", "")),
                        previous.get("returncode"),
                    )
                )
                continue
            execution_stage = _stage_for_workspace(stage, workspace)
            started = time.perf_counter()
            stage_reports[index].update(
                {
                    "name": execution_stage.name,
                    "command": list(execution_stage.command),
                    "working_directory": execution_stage.working_directory,
                    "status": "INTERRUPTED",
                    "reason": "stage started",
                    "started_at": _timestamp(),
                    "ended_at": None,
                }
            )
            _write_json_report(report_path, report, secrets)
            if execution_stage.stage_id == "full-local.pipeline" and not local_model_available(repo_root, "u2net"):
                result = StageResult(
                    stage.name,
                    "SKIP",
                    time.perf_counter() - started,
                    "u2net rembg model is not installed; prepare it explicitly with "
                    "`uv run python scripts/download_models.py u2net`",
                )
            elif execution_stage.requires_frontend_dependencies and not (
                repo_root / "frontend" / "node_modules"
            ).is_dir():
                result = StageResult(
                    stage.name,
                    "SKIP",
                    time.perf_counter() - started,
                    "allowed skip: node_modules missing",
                )
            else:
                if execution_stage.working_directory == "workspace":
                    cwd = workspace
                elif execution_stage.working_directory == "frontend":
                    cwd = repo_root / "frontend"
                else:
                    raise ValueError(f"Unknown stage working directory: {execution_stage.working_directory}")
                try:
                    completed = command_runner(execution_stage, cwd=cwd, env=environment)
                except KeyboardInterrupt:
                    result = StageResult(
                        stage.name,
                        "INTERRUPTED",
                        time.perf_counter() - started,
                        "interrupted by user",
                    )
                    interrupted = True
                except subprocess.TimeoutExpired:
                    timeout = stage.timeout_seconds or 0
                    result = StageResult(
                        stage.name,
                        "FAIL",
                        time.perf_counter() - started,
                        f"timed out after {timeout:g}s",
                    )
                except OSError as error:
                    result = StageResult(
                        stage.name,
                        "FAIL",
                        time.perf_counter() - started,
                        f"could not start command: {error}",
                    )
                else:
                    status = "PASS" if completed.returncode == 0 else "FAIL"
                    result = StageResult(
                        stage.name,
                        status,
                        time.perf_counter() - started,
                        returncode=completed.returncode,
                    )
            results.append(result)
            stage_reports[index].update(
                {
                    "status": result.status,
                    "reason": result.reason,
                    "ended_at": _timestamp(),
                    "duration_seconds": result.duration_seconds,
                    "returncode": result.returncode,
                }
            )
            _print_result(result, secrets)
            _write_json_report(report_path, report, secrets)
            if interrupted:
                for pending in stage_reports[index + 1 :]:
                    pending["reason"] = "not run after interruption"
                _write_json_report(report_path, report, secrets)
                break
        retain_workspace = any(result.status in {"FAIL", "INTERRUPTED"} for result in results)
    finally:
        if retain_workspace:
            print(f"Retained failed workspace: {workspace}", flush=True)
        else:
            shutil.rmtree(workspace, ignore_errors=True)

    failed = retain_workspace or any(result.status == "FAIL" for result in results)
    exit_code = 130 if interrupted else (1 if failed else 0)
    report.update(
        {
            "status": "INTERRUPTED" if interrupted else ("PASS" if exit_code == 0 else "FAIL"),
            "ended_at": _timestamp(),
            "duration_seconds": (previous_duration if resuming else 0.0)
            + (time.perf_counter() - suite_started),
            "last_attempt_duration_seconds": time.perf_counter() - suite_started,
            "workspace_retained": retain_workspace,
        }
    )
    _write_json_report(report_path, report, secrets)
    print(f"Suite result: {report['status']}", flush=True)
    print(f"JSON report: {report_path}", flush=True)
    return SuiteResult(tuple(results), exit_code, report_path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run isolated, zero-cost Game Assets Maker tests")
    parser.add_argument("suite", nargs="?", choices=("default", "frontend", "full-local", "all-free"))
    parser.add_argument("--report", type=Path, help="write the JSON report to this path")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--resume", type=Path, help="resume failed or interrupted stages from a report")
    action.add_argument("--cleanup", type=Path, help="remove the retained workspace recorded by a report")
    return parser


def _default_report_path(repo_root: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return repo_root / ".test-runs" / f"{timestamp}-{uuid.uuid4().hex[:8]}" / "report.json"


def main(
    argv: Sequence[str] | None = None,
    *,
    repo_root: Path | None = None,
    suite_runner: SuiteRunner = run_suite,
) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    root = (repo_root or Path(__file__).resolve().parents[1]).resolve()
    if args.cleanup:
        if args.suite or args.report:
            parser.error("--cleanup cannot be combined with a suite or --report")
        removed = cleanup_run(args.cleanup)
        print(f"Cleanup result: {'removed workspace' if removed else 'workspace already absent'}", flush=True)
        return 0

    if args.resume:
        if args.report:
            parser.error("--resume cannot be combined with --report")
        resume_path = args.resume.resolve()
        resume_report = json.loads(resume_path.read_text(encoding="utf-8"))
        suite = args.suite or resume_report.get("suite")
        if suite not in {"default", "frontend", "full-local", "all-free"}:
            parser.error("resume report does not contain a supported suite")
        return suite_runner(suite, repo_root=root, resume_from=resume_path).exit_code

    suite = args.suite or "default"
    report_path = args.report.resolve() if args.report else _default_report_path(root)
    return suite_runner(suite, repo_root=root, report_path=report_path).exit_code


if __name__ == "__main__":
    raise SystemExit(main())
