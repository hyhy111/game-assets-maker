"""Allowlisted resolution of locally persisted Seedream media."""

from __future__ import annotations

from pathlib import Path

from backend.image_layout import edit_source_path
from backend.seedream.repository import BatchRepository

_ASSET_KEYS = {"image", "edit-source", "reference"}


class SeedreamMediaResolver:
    """Resolve only known, batch-recorded cache assets for the local HTTP route."""

    def __init__(self, repository: BatchRepository) -> None:
        self._repository = repository

    def resolve(self, local_id: str, asset_key: str, attempt_index: int = 0) -> Path:
        if asset_key not in _ASSET_KEYS:
            raise ValueError("Unknown Seedream media asset")

        if asset_key == "reference":
            return self._resolve_reference(local_id)

        batch = self._repository.get(local_id)
        for attempt in batch.attempts:
            if attempt.index != attempt_index:
                continue
            relative_path = attempt.local_path
            if not isinstance(relative_path, str) or not relative_path:
                raise FileNotFoundError("Seedream media asset is not available")
            path = self._repository.resolve_asset(local_id, relative_path)
            if path.is_file():
                if asset_key == "edit-source":
                    source = edit_source_path(path)
                    return source if source.is_file() else path
                return path
            raise FileNotFoundError("Seedream media asset is not available")
        raise FileNotFoundError("Seedream media asset is not available")

    def _resolve_reference(self, local_id: str) -> Path:
        batch = self._repository.get(local_id)
        request = batch.request if isinstance(batch.request, dict) else {}
        stored = request.get("reference_image")
        if not isinstance(stored, str) or not stored:
            raise FileNotFoundError("Seedream media asset is not available")
        path = self._repository.resolve_asset(local_id, stored)
        if path.is_file():
            return path
        raise FileNotFoundError("Seedream media asset is not available")
