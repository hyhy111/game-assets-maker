"""Allowlisted resolution of locally persisted Seedance media."""

from __future__ import annotations

from pathlib import Path

from backend.seedance.repository import TaskRepository

_INPUT_ASSETS = {"first_frame", "last_frame"}
_OUTPUT_ASSETS = {"video", "returned_last_frame", "thumbnail"}
_ASSET_KEYS = _INPUT_ASSETS | _OUTPUT_ASSETS


class SeedanceMediaResolver:
    """Resolve only known, task-recorded cache assets for the local HTTP route."""

    def __init__(self, repository: TaskRepository) -> None:
        self._repository = repository

    def resolve(self, local_id: str, asset_key: str) -> Path:
        if asset_key not in _ASSET_KEYS:
            raise ValueError("Unknown Seedance media asset")

        task = self._repository.get(local_id)
        paths = task.input_paths if asset_key in _INPUT_ASSETS else task.output_paths
        relative_path = paths.get(asset_key)
        if not isinstance(relative_path, str) or not relative_path:
            raise FileNotFoundError("Seedance media asset is not available")

        path = self._repository.resolve_asset(local_id, relative_path)
        if not path.is_file():
            raise FileNotFoundError("Seedance media asset is not available")
        return path
