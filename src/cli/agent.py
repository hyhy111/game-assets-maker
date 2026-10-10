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
    role_parser = subparsers.add_parser("roles", help="读取角色列表")
    role_parser.add_argument("--list", action="store_true")
    animation_parser = subparsers.add_parser("animations", help="按角色读取带稳定 ID 的动画列表")
    animation_parser.add_argument("--role")

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

    for command in ("get", "set", "execute"):
        command_parser = step_subparsers.add_parser(command)
        command_parser.add_argument("--project", required=True)
        command_parser.add_argument("--step", type=int, choices=[1, 2, 3], required=True)
        command_parser.add_argument("--param", action="append", default=[])
        command_parser.add_argument("--request-id")
    step_status = step_subparsers.add_parser("status")
    step_status.add_argument("--task-id", required=True)

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

    ui_navigate = ui_subparsers.add_parser("navigate", help="跳转界面并等待实际完成回执")
    ui_navigate.add_argument(
        "--target",
        required=True,
        choices=[
            "projects",
            "project-create",
            "editor",
            "batch-trim",
            "image-create",
            "video-create",
            "image-detail",
            "video-detail",
            "settings",
        ],
    )
    ui_navigate.add_argument("--project")
    ui_navigate.add_argument("--step", type=int, choices=[1, 2, 3])
    ui_navigate.add_argument("--id")
    ui_navigate.add_argument("--request-id")
    ui_request = ui_subparsers.add_parser("request", help="查询已有请求；超时不重复执行")
    ui_request.add_argument("--request-id", required=True)

    artifacts = subparsers.add_parser("artifacts", help="读取本地过程文件与 AI 缓存；列表不代表质量验收")
    artifact_commands = artifacts.add_subparsers(dest="artifact_command", required=True)
    listing = artifact_commands.add_parser("list")
    listing.add_argument("--project")
    listing.add_argument("--role")
    listing.add_argument("--step", type=int, choices=[1, 2, 3])
    listing.add_argument("--task-id")
    listing.add_argument("--source", choices=["project", "project-input", "image", "video"])
    listing.add_argument("--type", choices=["metadata", "media"])
    listing.add_argument("--limit", type=int, default=100)
    listing.add_argument("--offset", type=int, default=0)
    reading = artifact_commands.add_parser("read")
    reading.add_argument("--path", required=True)

    draft = subparsers.add_parser("draft", help="读取或填写草稿，不提交 AI 任务")
    draft_commands = draft.add_subparsers(dest="draft_command", required=True)
    for command in ("get", "patch"):
        command_parser = draft_commands.add_parser(command)
        command_parser.add_argument("--kind", choices=["image", "video"], required=True)
        command_parser.add_argument("--request-id")
        if command == "patch":
            command_parser.add_argument("--patch-json", required=True)

    restore = draft_commands.add_parser("restore", help="恢复历史草稿，不重新提交")
    restore.add_argument("--kind", choices=["image", "video"], required=True)
    restore.add_argument("--id", required=True)
    reuse = draft_commands.add_parser("reuse", help="选用过程或缓存图片填入指定字段")
    reuse.add_argument("--kind", choices=["image", "video"], required=True)
    reuse.add_argument("--path", required=True)
    reuse.add_argument("--field", choices=["reference_image", "first_frame", "last_frame"], required=True)

    generation = subparsers.add_parser("generation")
    generation_subparsers = generation.add_subparsers(dest="generation_command", required=True)
    generation_subparsers.add_parser("permission", help="读取运行中的应用 CLI 生成授权，不允许通过 CLI 开启")
    for kind in ("image", "video"):
        create = generation_subparsers.add_parser(kind, help="提交 AI 任务；须设置开启并取得当前对话首次确认")
        create.add_argument("--request-json", required=True, help="本地 JSON 请求文件")
        create.add_argument("--request-id")
    seedream = subparsers.add_parser("seedream")
    seedream_subparsers = seedream.add_subparsers(dest="seedream_command", required=True)
    seedream_create = seedream_subparsers.add_parser("create", help="提交图片任务；默认禁止 CLI 生成")
    seedream_create.add_argument("--request-json", required=True)
    seedream_create.add_argument("--request-id")

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
            if args.step_command == "status":
                return service.step_operation("step.status", {"task_id": args.task_id})
            if args.step_command in {"get", "set", "execute"}:
                try:
                    patch = _parse_params(args.param)
                except ParamParseError as error:
                    return error_response("step.set", "INPUT_INVALID", str(error))
                operation = "step.run" if args.step_command == "execute" else "step." + args.step_command
                return service.step_operation(
                    operation, {"project_id": args.project, "step": args.step, "patch": patch}, args.request_id
                )
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
                if service.ui_client.status().get("connected"):
                    return service.step_operation(
                        "step.run", {"project_id": args.project, "step": args.step, "patch": params}
                    )
                return service.run_step(project_id=args.project, step=args.step, params=params)

        if args.command == "roles":
            return service.selection_operation("roles.list", {})
        if args.command == "animations":
            return service.selection_operation("animations.list", {"role": args.role})
        if args.command == "batch-trim":
            return service.batch_trim(project_ids=args.projects, mode=args.mode)

        if args.command == "ui":
            if args.ui_command == "navigate":
                return service.ui_navigate(args.target, args.project, args.step, args.id, args.request_id)
            if args.ui_command == "request":
                return service.ui_client.request_status(args.request_id)
            if args.ui_command == "status":
                return service.ui_status()
            if args.ui_command == "open":
                return service.ui_open(project_id=args.project, step=args.step)

        if args.command == "artifacts":
            if args.artifact_command == "read":
                return service.artifact_operation("artifacts.read", {"path": args.path})
            return service.artifact_operation(
                "artifacts.list",
                {
                    "project_id": args.project,
                    "role": args.role,
                    "step": args.step,
                    "task_id": args.task_id,
                    "source": args.source,
                    "type": args.type,
                    "limit": args.limit,
                    "offset": args.offset,
                },
            )

        if args.command == "draft":
            if args.draft_command == "restore":
                return service.reuse_draft(args.kind, local_id=args.id)
            if args.draft_command == "reuse":
                return service.reuse_draft(args.kind, path=args.path, field=args.field)
            patch = None
            if args.draft_command == "patch":
                from pathlib import Path

                try:
                    patch = json.loads(Path(args.patch_json).read_text(encoding="utf-8"))
                    if not isinstance(patch, dict):
                        raise ValueError("Patch must be an object")
                except (OSError, ValueError):
                    return error_response("draft.patch", "INPUT_INVALID", "Provide a readable JSON object patch file")
            return service.draft_operation(args.kind, patch, args.request_id)

        if args.command == "generation" and args.generation_command == "permission":
            return service.generation_permission()
        if args.command in {"generation", "seedream"}:
            from pathlib import Path

            try:
                request = json.loads(Path(args.request_json).read_text(encoding="utf-8"))
                if not isinstance(request, dict):
                    raise ValueError("Request must be an object")
            except (OSError, ValueError):
                return error_response(
                    "generation.submit", "INPUT_INVALID", "Provide a readable JSON object request file"
                )
            kind = args.generation_command if args.command == "generation" else "image"
            return service.generation_submit(kind, request, args.request_id)

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
