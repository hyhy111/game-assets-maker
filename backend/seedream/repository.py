import json
import os
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from uuid import uuid4

from filelock import FileLock

from backend.image_input import read_image_metadata
from backend.seedream.models import ImageAttempt, ImageBatch, SeedreamRequest

_REFERENCE_EXTENSIONS = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
    "BMP": ".bmp",
    "TIFF": ".tiff",
    "GIF": ".gif",
    "HEIC": ".heic",
    "HEIF": ".heif",
}


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class BatchRepository:
    def __init__(self, cache_root: Path | str):
        self.cache_root = Path(cache_root)
        self.batches_root = self.cache_root / "batches"
        self.batches_root.mkdir(parents=True, exist_ok=True)

    def create_batch(self, request: SeedreamRequest) -> ImageBatch:
        # Validate the reference image before creating anything on disk so an
        # invalid path never leaves a half-built batch directory behind.
        reference_format = None
        if request.reference_image:
            reference_format, _, _ = read_image_metadata(Path(request.reference_image))
        batch_dir, local_id = self._create_batch_dir()
        (batch_dir / "images").mkdir()
        stored_reference = self._copy_reference_image(batch_dir, request.reference_image, reference_format)
        request_data = dict(request.to_dict(), reference_image=stored_reference)
        now = utc_now_iso()
        count = max(1, request.count)
        attempts = [
            ImageAttempt(
                local_id=uuid4().hex,
                index=index,
                status="queued",
                request=dict(request_data),
                response={},
                local_path=None,
                created_at=now,
                updated_at=now,
                finished_at=None,
                error=None,
            )
            for index in range(count)
        ]
        batch = ImageBatch(
            local_id=local_id,
            request=request_data,
            attempts=attempts,
            created_at=now,
            updated_at=now,
        )
        with self.batch_lock(local_id):
            self._write_unlocked(batch)
        return batch

    @staticmethod
    def _copy_reference_image(
        batch_dir: Path,
        reference_image: str | None,
        reference_format: str | None,
    ) -> str | None:
        """Copy the reference image into the batch directory and return its relative path.

        The extension comes from the image's actual format (not the source file
        name) so the local media route serves the correct MIME type.
        """
        if not reference_image or reference_format is None:
            return None
        relative_path = f"reference/reference{_REFERENCE_EXTENSIONS[reference_format]}"
        (batch_dir / "reference").mkdir()
        shutil.copyfile(Path(reference_image), batch_dir / relative_path)
        return relative_path

    def get(self, local_id: str) -> ImageBatch:
        with self.batch_lock(local_id):
            return self._read_unlocked(local_id)

    def list(self) -> list[ImageBatch]:
        batches: list[ImageBatch] = []
        for batch_path in self.batches_root.glob("*/batch.json"):
            try:
                batches.append(self.get(batch_path.parent.name))
            except FileNotFoundError:
                continue
        return sorted(batches, key=lambda batch: (batch.created_at, batch.local_id), reverse=True)

    def update(self, local_id: str, updater: Callable[[ImageBatch], None]) -> ImageBatch:
        with self.batch_lock(local_id):
            batch = self._read_unlocked(local_id)
            updater(batch)
            batch.updated_at = utc_now_iso()
            self._write_unlocked(batch)
            return batch

    def delete(self, local_id: str) -> None:
        with self.batch_lock(local_id):
            self._read_unlocked(local_id)
            self._delete_unlocked(local_id)

    def batch_lock(self, local_id: str) -> FileLock:
        return FileLock(str(self._existing_batch_dir(local_id) / ".batch.lock"))

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
            raise ValueError("Asset path must be a relative path within its batch directory")

        batch_dir = self._existing_batch_dir(local_id)
        resolved_asset = (batch_dir / asset_path).resolve()
        try:
            resolved_asset.relative_to(batch_dir)
        except ValueError as exc:
            raise ValueError("Asset path escapes its batch directory") from exc
        return resolved_asset

    def _create_batch_dir(self) -> tuple[Path, str]:
        while True:
            local_id = uuid4().hex
            batch_dir = self.batches_root / local_id
            try:
                batch_dir.mkdir()
            except FileExistsError:
                continue
            return batch_dir, local_id

    def _read_unlocked(self, local_id: str) -> ImageBatch:
        batch_path = self._existing_batch_dir(local_id) / "batch.json"
        with batch_path.open(encoding="utf-8") as file:
            return ImageBatch.from_dict(json.load(file))

    def _write_unlocked(self, batch: ImageBatch) -> None:
        batch_dir = self._existing_batch_dir(batch.local_id)
        temporary_path = batch_dir / ".batch.json.tmp"
        with temporary_path.open("w", encoding="utf-8") as file:
            json.dump(batch.to_dict(), file, ensure_ascii=False, separators=(",", ":"))
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, batch_dir / "batch.json")

    def _delete_unlocked(self, local_id: str) -> None:
        shutil.rmtree(self._existing_batch_dir(local_id))

    def _existing_batch_dir(self, local_id: str) -> Path:
        batch_dir = self._batch_dir(local_id)
        if not batch_dir.is_dir():
            raise FileNotFoundError(f"Seedream batch not found: {local_id}")
        resolved_batches_root = self.batches_root.resolve()
        resolved_batch_dir = batch_dir.resolve()
        try:
            resolved_batch_dir.relative_to(resolved_batches_root)
        except ValueError as exc:
            raise ValueError("Batch directory escapes the configured cache root") from exc
        return resolved_batch_dir

    def _batch_dir(self, local_id: str) -> Path:
        local_path = Path(local_id)
        if not local_id or local_path.is_absolute() or local_path.name != local_id or local_id in {".", ".."}:
            raise ValueError("Invalid local batch ID")
        return self.batches_root / local_id
