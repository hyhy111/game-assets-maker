import json
import os
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from uuid import uuid4

from filelock import FileLock

from backend.image_layout import copy_generation_layout
from backend.seedance.models import SeedanceRequest, SeedanceTask


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class TaskRepository:
    def __init__(self, cache_root: Path | str):
        self.cache_root = Path(cache_root)
        self.tasks_root = self.cache_root / "tasks"
        self.tasks_root.mkdir(parents=True, exist_ok=True)

    def create_draft(self, request: SeedanceRequest) -> SeedanceTask:
        task_dir, local_id = self._create_task_dir()
        with self.task_lock(local_id):
            input_paths = self._copy_inputs(task_dir, request)
            request_data = request.to_dict()
            request_data["first_frame"] = input_paths["first_frame"]
            request_data["last_frame"] = input_paths.get("last_frame")
            now = utc_now_iso()
            task = SeedanceTask(
                local_id=local_id,
                remote_id=None,
                remote_status="submitting",
                sync_status={},
                download_status="pending",
                cache_status="complete",
                request=request_data,
                input_paths=input_paths,
                output_paths={},
                created_at=now,
                updated_at=now,
                finished_at=None,
                remote={},
                error=None,
                retry_of=None,
                handoffs=[],
                source=request.source,
            )
            self._write_unlocked(task)
            return task

    def get(self, local_id: str) -> SeedanceTask:
        with self.task_lock(local_id):
            return self._read_unlocked(local_id)

    def list(self) -> list[SeedanceTask]:
        tasks: list[SeedanceTask] = []
        for task_path in self.tasks_root.glob("*/task.json"):
            try:
                tasks.append(self.get(task_path.parent.name))
            except FileNotFoundError:
                continue
        return sorted(tasks, key=lambda task: (task.created_at, task.local_id), reverse=True)

    def update(self, local_id: str, updater: Callable[[SeedanceTask], None]) -> SeedanceTask:
        with self.task_lock(local_id):
            task = self._read_unlocked(local_id)
            updater(task)
            task.updated_at = utc_now_iso()
            self._write_unlocked(task)
            return task

    def delete(self, local_id: str, allow_protected: bool = False) -> None:
        with self.task_lock(local_id):
            task = self._read_unlocked(local_id)
            if task.handoffs and not allow_protected:
                raise ValueError("Cannot delete a task with handoffs")
            self._delete_unlocked(local_id)

    def task_lock(self, local_id: str) -> FileLock:
        return FileLock(str(self._existing_task_dir(local_id) / ".task.lock"))

    def resolve_asset(self, local_id: str, relative_path: str) -> Path:
        asset_path = Path(relative_path)
        windows_path = PureWindowsPath(relative_path)
        if (
            asset_path.is_absolute()
            or windows_path.is_absolute()
            or windows_path.drive
            or asset_path == Path(".")
            or ".." in asset_path.parts
            or ".." in windows_path.parts
        ):
            raise ValueError("Asset path must be a relative path within its task directory")

        task_dir = self._existing_task_dir(local_id)
        resolved_asset = (task_dir / asset_path).resolve()
        try:
            resolved_asset.relative_to(task_dir)
        except ValueError as exc:
            raise ValueError("Asset path escapes its task directory") from exc
        return resolved_asset

    def _create_task_dir(self) -> tuple[Path, str]:
        while True:
            local_id = uuid4().hex
            task_dir = self.tasks_root / local_id
            try:
                task_dir.mkdir()
            except FileExistsError:
                continue
            return task_dir, local_id

    def _copy_inputs(self, task_dir: Path, request: SeedanceRequest) -> dict[str, str]:
        input_dir = task_dir / "input"
        input_dir.mkdir()
        paths = {
            "first_frame": self._copy_input(request.first_frame, input_dir, "first_frame"),
        }
        if request.last_frame is not None:
            paths["last_frame"] = self._copy_input(request.last_frame, input_dir, "last_frame")
        (task_dir / "output").mkdir()
        return paths

    @staticmethod
    def _copy_input(source: Path, input_dir: Path, name: str) -> str:
        destination = input_dir / f"{name}{source.suffix}"
        shutil.copy2(source, destination)
        copy_generation_layout(source, destination)
        return destination.relative_to(input_dir.parent).as_posix()

    def _read_unlocked(self, local_id: str) -> SeedanceTask:
        task_path = self._existing_task_dir(local_id) / "task.json"
        with task_path.open(encoding="utf-8") as file:
            return SeedanceTask.from_dict(json.load(file))

    def _write_unlocked(self, task: SeedanceTask) -> None:
        task_dir = self._existing_task_dir(task.local_id)
        temporary_path = task_dir / ".task.json.tmp"
        with temporary_path.open("w", encoding="utf-8") as file:
            json.dump(task.to_dict(), file, ensure_ascii=False, separators=(",", ":"))
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, task_dir / "task.json")

    def _delete_unlocked(self, local_id: str) -> None:
        shutil.rmtree(self._existing_task_dir(local_id))

    def _existing_task_dir(self, local_id: str) -> Path:
        task_dir = self._task_dir(local_id)
        if not task_dir.is_dir():
            raise FileNotFoundError(f"Seedance task not found: {local_id}")
        resolved_tasks_root = self.tasks_root.resolve()
        resolved_task_dir = task_dir.resolve()
        try:
            resolved_task_dir.relative_to(resolved_tasks_root)
        except ValueError as exc:
            raise ValueError("Task directory escapes the configured cache root") from exc
        return resolved_task_dir

    def _task_dir(self, local_id: str) -> Path:
        local_path = Path(local_id)
        if not local_id or local_path.is_absolute() or local_path.name != local_id or local_id in {".", ".."}:
            raise ValueError("Invalid local task ID")
        return self.tasks_root / local_id
