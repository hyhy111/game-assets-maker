"""JSON-first command line interface for agent workflows."""

from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import redirect_stdout
from typing import Any

from src.agent_tools.schemas import AgentErrorCode, error_response
from src.agent_tools.service import AgentWorkflowService


class ParamParseError(ValueError):
    def __init__(self, raw_param: str):
        super().__init__(f"Invalid --param value: {raw_param}")
        self.raw_param = raw_param


def _print_json(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


def _parse_params(raw_params: list[str] | None) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for raw_param in raw_params or []:
        key, separator, raw_value = raw_param.partition("=")
        if not separator or not key:
            raise ParamParseError(raw_param)
        value: Any
        if raw_value.lower() == "true":
            value = True
        elif raw_value.lower() == "false":
            value = False
        else:
            try:
                value = int(raw_value)
            except ValueError:
                value = raw_value
        params[key] = value
    return params


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gam-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor")

    project_parser = subparsers.add_parser("project")
    project_subparsers = project_parser.add_subparsers(dest="project_command", required=True)

    project_subparsers.add_parser("list")

    project_create = project_subparsers.add_parser("create")
    project_create.add_argument("--video", required=True)
    project_create.add_argument("--role", required=True)
    project_create.add_argument("--action", required=True)
    project_create.add_argument("--frame-interval", type=int, default=1)

    project_summary = project_subparsers.add_parser("summary")
    project_summary.add_argument("--project", required=True)

    step_parser = subparsers.add_parser("step")
    step_subparsers = step_parser.add_subparsers(dest="step_command", required=True)

    step_explain = step_subparsers.add_parser("explain")
    step_explain.add_argument("--step", type=int, required=True)
    step_explain.add_argument("--param")

    step_run = step_subparsers.add_parser("run")
    step_run.add_argument("--project", required=True)
    step_run.add_argument("--step", type=int, required=True)
    step_run.add_argument("--param", action="append", default=[])

    batch_trim = subparsers.add_parser("batch-trim")
    batch_trim.add_argument("--projects", nargs="+", required=True)
    batch_trim.add_argument("--mode", choices=["global", "individual"], default="global")

    ui_parser = subparsers.add_parser("ui")
    ui_subparsers = ui_parser.add_subparsers(dest="ui_command", required=True)

    ui_subparsers.add_parser("status")

    ui_open = ui_subparsers.add_parser("open")
    ui_open.add_argument("--project", required=True)
    ui_open.add_argument("--step", type=int, required=True)

    seedance = subparsers.add_parser("seedance")
    seedance_subparsers = seedance.add_subparsers(dest="seedance_command", required=True)

    seedance_create = seedance_subparsers.add_parser("create")
    seedance_create.add_argument("--first-frame", required=True)
    seedance_create.add_argument("--last-frame")
    seedance_create.add_argument("--prompt")
    seedance_create.add_argument("--model", choices=["standard", "fast", "mini"])
    seedance_create.add_argument("--resolution", choices=["480p", "720p", "1080p", "4k"])
    seedance_create.add_argument("--ratio", choices=["adaptive", "16:9", "1:1", "4:3"])
    seedance_create.add_argument("--duration", type=int)
    seedance_create.add_argument("--audio", action="store_true")
    seedance_create.add_argument("--return-last-frame", action="store_true")
    seedance_create.add_argument("--priority", type=int)
    seedance_create.add_argument("--expires-after", type=int)

    seedance_list = seedance_subparsers.add_parser("list")
    seedance_list.add_argument("--status")

    for command in ("summary", "wait", "cancel", "handoff", "ui-open"):
        command_parser = seedance_subparsers.add_parser(command)
        command_parser.add_argument("--task", required=True)
        if command == "wait":
            command_parser.add_argument("--timeout", type=float, default=60)
        if command == "handoff":
            command_parser.add_argument("--role", required=True)
            command_parser.add_argument("--action", required=True)

    seedance_cache = seedance_subparsers.add_parser("cache")
    seedance_cache_subparsers = seedance_cache.add_subparsers(dest="seedance_cache_command", required=True)
    seedance_cache_subparsers.add_parser("status")
    seedance_cache_clean = seedance_cache_subparsers.add_parser("clean")
    seedance_cache_clean.add_argument("--older-than-days", type=int)

    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    service = AgentWorkflowService()
    try:
        if args.command == "doctor":
            return service.doctor()

        if args.command == "project":
            if args.project_command == "list":
                return service.list_projects()
            if args.project_command == "create":
                return service.create_project(
                    role=args.role,
                    action=args.action,
                    video_path=args.video,
                    frame_interval=args.frame_interval,
                )
            if args.project_command == "summary":
                return service.project_summary(args.project)

        if args.command == "step":
            if args.step_command == "explain":
                return service.explain(step=args.step, parameter=args.param)
            if args.step_command == "run":
                try:
                    params = _parse_params(args.param)
                except ParamParseError as exc:
                    return error_response(
                        operation="step.run",
                        code=AgentErrorCode.CONFIG_INVALID,
                        message=str(exc),
                        details={"param": exc.raw_param},
                    )
                return service.run_step(project_id=args.project, step=args.step, params=params)

        if args.command == "batch-trim":
            return service.batch_trim(project_ids=args.projects, mode=args.mode)

        if args.command == "ui":
            if args.ui_command == "status":
                return service.ui_status()
            if args.ui_command == "open":
                return service.ui_open(project_id=args.project, step=args.step)

        if args.command == "seedance":
            if args.seedance_command == "create":
                return service.seedance_create(
                    first_frame=args.first_frame,
                    last_frame=args.last_frame,
                    prompt=args.prompt,
                    model=args.model,
                    resolution=args.resolution,
                    ratio=args.ratio,
                    duration=args.duration,
                    audio=args.audio,
                    return_last_frame=args.return_last_frame,
                    priority=args.priority,
                    expires_after=args.expires_after,
                )
            if args.seedance_command == "list":
                return service.seedance_list(args.status)
            if args.seedance_command == "summary":
                return service.seedance_summary(args.task)
            if args.seedance_command == "wait":
                return service.seedance_wait(args.task, args.timeout)
            if args.seedance_command == "cancel":
                return service.seedance_cancel(args.task)
            if args.seedance_command == "handoff":
                return service.seedance_handoff(args.task, args.role, args.action)
            if args.seedance_command == "ui-open":
                return service.seedance_ui_open(args.task)
            if args.seedance_command == "cache":
                if args.seedance_cache_command == "status":
                    return service.seedance_cache_status()
                if args.seedance_cache_command == "clean":
                    return service.seedance_cache_clean(args.older_than_days)

        raise ValueError(f"Unsupported command: {args.command}")
    finally:
        service.close()


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    with redirect_stdout(sys.stderr):
        payload = run(args)
    return _print_json(payload)


def installed_main(argv: list[str] | None = None) -> int:
    """Run the installed CLI against the stable per-user GAM data root."""
    os.environ.setdefault("GAM_DATA_MODE", "installed")
    return main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
