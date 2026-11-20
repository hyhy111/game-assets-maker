"""Seedance task-cache accounting and retention cleanup."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from backend.seedance.models import SeedanceTask
from backend.seedance.repository import TaskRepository, utc_now_iso

_TERMINAL_REMOTE_STATUSES = {"succeeded", "failed", "expired", "cancelled"}
CONTINUATION_FRAME_PATH = "output/continuation_frame.png"
_DERIVED_IMAGE_NAMES = (Path(CONTINUATION_FRAME_PATH).name, "thumbnail.jpg", "thumbnail.png")


class ProjectLookup(Protocol):
    def get_project(self, project_id: str) -> dict | None: ...

    def create_project(self, role: str, action: str, video_path: str, frame_interval: int = 1) -> dict: ...

    def delete_project(self, project_id: str) -> bool: ...


class CacheManager:
    def __init__(self, repository: TaskRepository, project_api: ProjectLookup) -> None:
        self._repository = repository
        self._project_api = project_api

    @property
    def project_api(self) -> ProjectLookup:
        return self._project_api

    def status(self) -> dict[str, int]:
        tasks = [self._prune_handoffs(task.local_id) for task in self._repository.list()]
        protected_tasks = [task for task in tasks if task.handoffs]
        return {
            "total_bytes": sum(self._task_bytes(task) for task in tasks),
            "task_count": len(tasks),
            "protected_task_count": len(protected_tasks),
            "clearable_bytes": sum(
                path.stat().st_size
                for task in tasks
                if self._is_clearable(task) and not task.handoffs
                for path in self._derived_images(task)
            ),
        }

    def clean(self, older_than_days: int, allow_protected: bool = False) -> dict[str, int]:
        if older_than_days < 0:
            raise ValueError("older_than_days must not be negative")
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
        cutoff_timestamp = cutoff.timestamp()
        result = {"files_removed": 0, "bytes_released": 0, "tasks_cleared": 0, "protected_tasks_skipped": 0}

        for listed_task in self._repository.list():
            with self._repository.task_lock(listed_task.local_id):
                task = self._repository._read_unlocked(listed_task.local_id)
                protected = self._prune_handoffs_unlocked(task)
                if not self._finished_before(task, cutoff) or not self._is_clearable(task):
                    continue
                # Keep recently generated or reused frames available to continuation drafts.
                candidates = [(path, path.stat()) for path in self._derived_images(task)]
                expired = [(path, stat.st_size) for path, stat in candidates if stat.st_mtime < cutoff_timestamp]
                if not expired:
                    continue
                if protected and not allow_protected:
                    result["protected_tasks_skipped"] += 1
                    continue

                for path, size in expired:
                    path.unlink()
                    result["files_removed"] += 1
                    result["bytes_released"] += size
                result["tasks_cleared"] += 1
        return result

    def delete_task(self, local_id: str, allow_protected: bool = False) -> None:
        with self._repository.task_lock(local_id):
            task = self._repository._read_unlocked(local_id)
            if self._prune_handoffs_unlocked(task) and not allow_protected:
                raise ValueError("Cannot delete a task with existing project handoffs")
            self._repository._delete_unlocked(local_id)

    def _prune_handoffs(self, local_id: str) -> SeedanceTask:
        with self._repository.task_lock(local_id):
            task = self._repository._read_unlocked(local_id)
            self._prune_handoffs_unlocked(task)
            return task

    def _prune_handoffs_unlocked(self, task: SeedanceTask) -> bool:
        active_handoffs = [
            handoff
            for handoff in task.handoffs
            if isinstance(handoff.get("project_id"), str)
            and self._project_api.get_project(handoff["project_id"]) is not None
        ]
        if active_handoffs != task.handoffs:
            task.handoffs = active_handoffs
            task.updated_at = utc_now_iso()
            self._repository._write_unlocked(task)
        return bool(active_handoffs)

    def _is_clearable(self, task: SeedanceTask) -> bool:
        return (
            task.download_status != "downloading"
            and task.remote_status in _TERMINAL_REMOTE_STATUSES
            and task.finished_at is not None
        )

    def _finished_before(self, task: SeedanceTask, cutoff: datetime) -> bool:
        if task.finished_at is None:
            return False
        try:
            finished_at = datetime.fromisoformat(task.finished_at.replace("Z", "+00:00"))
        except ValueError:
            return False
        if finished_at.tzinfo is None:
            finished_at = finished_at.replace(tzinfo=UTC)
        return finished_at.astimezone(UTC) < cutoff

    def _task_bytes(self, task: SeedanceTask) -> int:
        task_dir = self._repository._existing_task_dir(task.local_id)
        return sum(path.stat().st_size for path in task_dir.rglob("*") if self._is_regular_file(path, task_dir))

    def _derived_images(self, task: SeedanceTask) -> list[Path]:
        task_dir = self._repository._existing_task_dir(task.local_id)
        root = task_dir / "output"
        if root.is_symlink() or not root.is_dir() or root.resolve() != root:
            return []
        original_paths = {
            Path(relative)
            for relative in (task.output_paths.get("video"), task.output_paths.get("returned_last_frame"))
            if isinstance(relative, str) and relative
        }
        candidates = (root / name for name in _DERIVED_IMAGE_NAMES)
        return [
            path
            for path in candidates
            if self._is_regular_file(path, root) and path.relative_to(task_dir) not in original_paths
        ]

    @staticmethod
    def _is_regular_file(path: Path, root: Path) -> bool:
        if path.is_symlink() or not path.is_file():
            return False
        return CacheManager._is_within(path, root)

    @staticmethod
    def _is_within(path: Path, root: Path) -> bool:
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError:
            return False
        return True
