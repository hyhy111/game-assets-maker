"""Manage imported media and image edits within the configured cache."""

import base64
import json
import math
import re
import shutil
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import uuid4

from PIL import Image, ImageOps

from backend.image_layout import edit_source_path, write_generation_layout
from src.utils.ai_cache_paths import LOCAL_IMAGE_CACHE_DIRNAME, LOCAL_VIDEO_CACHE_DIRNAME
from src.utils.file_operations import rename_path

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm"}
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
FILE_TYPES = ("Media files (" + ";".join(f"*{ext}" for ext in sorted(MEDIA_EXTENSIONS)) + ")",)
_ID = re.compile(r"[0-9a-f]{32}")


class SourceMediaLibrary:
    def __init__(self, cache_root: Path, legacy_root: Path | None = None):
        cache_root = cache_root.resolve()
        self.roots = {"image": cache_root / LOCAL_IMAGE_CACHE_DIRNAME, "video": cache_root / LOCAL_VIDEO_CACHE_DIRNAME}
        self.legacy_root = legacy_root.resolve() if legacy_root is not None else None

    def prepare(self) -> None:
        """Upgrade the old flat library once, without deleting or replacing its files."""
        for root in self.roots.values():
            if root.resolve() != root:
                raise ValueError("Invalid source media directory")
            root.mkdir(parents=True, exist_ok=True)
        legacy = self.legacy_root
        if legacy is None or not legacy.is_dir():
            return
        marker = legacy / ".migrated"
        if marker.is_file():
            return
        for directory in legacy.iterdir():
            if not _ID.fullmatch(directory.name):
                continue
            try:
                record = self._read_record(legacy, directory.name)
                names = ("media.json", f"original{record['extension']}", "thumbnail.png")
                files = [self._checked_file(directory / name) for name in names]
            except (FileNotFoundError, ValueError):
                continue
            root = self.roots[record["kind"]]
            target = root / directory.name
            if target.exists():
                self._read_record(root, directory.name, record["kind"])
                continue
            with TemporaryDirectory(dir=root, prefix=".migration-") as staging:
                # The old layout contains exactly these three files. Do not follow
                # other files or directories that may have been put beside them.
                copied = Path(staging) / directory.name
                copied.mkdir()
                for path in files:
                    shutil.copyfile(path, copied / path.name)
                rename_path(copied, target)
        marker.touch()

    def import_files(self, paths: tuple[str, ...]) -> dict[str, list]:
        items = []
        failed = []
        for path in paths:
            source = Path(path)
            try:
                items.append(self._import_file(source))
            except (OSError, ValueError, Image.DecompressionBombError):
                failed.append(source.name)
        return {"items": items, "failed": failed}

    def _import_file(self, source: Path) -> dict[str, Any]:
        extension = source.suffix.lower()
        if extension not in MEDIA_EXTENSIONS or not source.is_file():
            raise ValueError("Unsupported source media")

        media_id = uuid4().hex
        kind = "image" if extension in IMAGE_EXTENSIONS else "video"
        root = self.roots[kind]
        root.mkdir(parents=True, exist_ok=True)
        # Keep partial copies and invalid inputs out of the library.
        with TemporaryDirectory(dir=root, prefix=".import-") as staging:
            directory = Path(staging) / media_id
            directory.mkdir()
            original = directory / f"original{extension}"
            shutil.copyfile(source, original)
            thumbnail, duration = self._preview(original, kind)
            width, height = thumbnail.size
            thumbnail.thumbnail((480, 360))
            thumbnail.save(directory / "thumbnail.png")
            record = {
                "id": media_id,
                "name": source.name,
                "kind": kind,
                "extension": extension,
                "size_bytes": original.stat().st_size,
                "width": width,
                "height": height,
                "duration": duration,
                "imported_at": datetime.now(UTC).isoformat(),
            }
            (directory / "media.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            rename_path(directory, root / media_id)
        return record

    @staticmethod
    def _preview(original: Path, kind: str) -> tuple[Image.Image, float | None]:
        if kind == "image":
            with Image.open(original) as image:
                return ImageOps.exif_transpose(image).convert("RGBA"), None

        import cv2

        capture = cv2.VideoCapture(str(original))
        try:
            fps = capture.get(cv2.CAP_PROP_FPS)
            frames = capture.get(cv2.CAP_PROP_FRAME_COUNT)
            valid, frame = capture.read()
            if not valid or not math.isfinite(fps) or not math.isfinite(frames) or fps <= 0 or frames < 1:
                raise ValueError("Unreadable source video")
            return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)), frames / fps
        except cv2.error as error:
            raise ValueError("Unreadable source video") from error
        finally:
            capture.release()

    @staticmethod
    def _checked_file(path: Path) -> Path:
        if path.resolve() != path or not path.is_file():
            raise FileNotFoundError("Media asset is unavailable")
        return path

    @classmethod
    def _read_record(cls, root: Path, media_id: str, expected_kind: str | None = None) -> dict[str, Any]:
        metadata = cls._checked_file(root / media_id / "media.json")
        record = json.loads(metadata.read_text(encoding="utf-8"))
        if (
            not isinstance(record, dict)
            or record.get("id") != media_id
            or not isinstance(record.get("extension"), str)
            or record.get("extension") not in MEDIA_EXTENSIONS
            or record.get("kind") != ("image" if record["extension"] in IMAGE_EXTENSIONS else "video")
            or (expected_kind is not None and record.get("kind") != expected_kind)
            or not isinstance(record.get("imported_at"), str)
        ):
            raise ValueError("Invalid media record")
        return record

    def get(self, media_id: str) -> dict[str, Any]:
        if not isinstance(media_id, str) or not _ID.fullmatch(media_id):
            raise FileNotFoundError("Unknown source media")
        for kind, root in self.roots.items():
            try:
                return self._read_record(root, media_id, kind)
            except FileNotFoundError:
                continue
        raise FileNotFoundError("Unknown source media")

    def list(self) -> list[dict[str, Any]]:
        records = []
        for kind, root in self.roots.items():
            if not root.is_dir():
                continue
            for directory in root.iterdir():
                if not _ID.fullmatch(directory.name):
                    continue
                try:
                    records.append(self._read_record(root, directory.name, kind))
                except (OSError, RuntimeError, ValueError):
                    continue
        return sorted(records, key=lambda record: record.get("imported_at", ""), reverse=True)

    def resolve(self, media_id: str, asset: str) -> Path:
        record = self.get(media_id)
        directory = self.roots[record["kind"]] / media_id
        original = directory / f"original{record['extension']}"
        revision = record.get("edit_revision")
        if asset == "original":
            return self._checked_file(original)
        if record["kind"] == "image" and isinstance(revision, str) and _ID.fullmatch(revision):
            edited = directory / revision / "image.png"
            if asset == "image":
                return self._checked_file(edited)
            if asset == "edit-source":
                return self._checked_file(edit_source_path(edited))
            if asset == "thumbnail":
                return self._checked_file(edited.with_name("thumbnail.png"))
        if asset == "image" and record["kind"] == "image":
            return self._checked_file(original)
        if asset == "thumbnail":
            return self._checked_file(directory / "thumbnail.png")
        raise FileNotFoundError("Unknown media asset")

    @staticmethod
    def _editor_png(data_url: str, size: tuple[int, int]) -> Image.Image:
        prefix = "data:image/png;base64,"
        if not isinstance(data_url, str) or not data_url.startswith(prefix):
            raise ValueError("Edited image must be a PNG data URL")
        payload = data_url[len(prefix) :]
        if len(payload) > 64 * 1024 * 1024:
            raise ValueError("Edited image is too large")
        with Image.open(BytesIO(base64.b64decode(payload, validate=True))) as opened:
            if opened.format != "PNG" or opened.size != size:
                raise ValueError("Edited image must match the original dimensions")
            return opened.convert("RGBA")

    def _publish_record(self, directory: Path, record: dict[str, Any]) -> None:
        with TemporaryDirectory(dir=directory, prefix=".metadata-") as staging:
            temporary = Path(staging) / "media.json"
            temporary.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            rename_path(temporary, directory / "media.json", replace=True)

    def edit_image(self, media_id: str, data_url: str, source_url: str, layout: Any) -> dict[str, Any]:
        record = self.get(media_id)
        if record["kind"] != "image":
            raise ValueError("Only images can be edited")
        directory = self.resolve(media_id, "original").parent
        size = (record["width"], record["height"])
        edited = self._editor_png(data_url, size)
        edit_source = self._editor_png(source_url, size)
        revision = uuid4().hex
        with TemporaryDirectory(dir=directory, prefix=".edit-") as staging:
            staged = Path(staging) / revision
            staged.mkdir()
            output = staged / "image.png"
            edited.save(output)
            edit_source.save(edit_source_path(output))
            if layout is not None:
                layout = write_generation_layout(output, layout, width=size[0], height=size[1])
            edited.thumbnail((480, 360))
            edited.save(staged / "thumbnail.png")
            rename_path(staged, directory / revision)
        record.update(edit_revision=revision, generation_layout=layout)
        try:
            self._publish_record(directory, record)
        except OSError:
            shutil.rmtree(directory / revision, ignore_errors=True)
            raise
        return record

    def restore_image(self, media_id: str) -> dict[str, Any]:
        record = self.get(media_id)
        if record["kind"] != "image":
            raise ValueError("Only images can be restored")
        directory = self.resolve(media_id, "original").parent
        record.pop("edit_revision", None)
        record.pop("generation_layout", None)
        self._publish_record(directory, record)
        return record

    def delete(self, media_id: str) -> None:
        directory = self.resolve(media_id, "original").parent
        removed = directory.with_name(f".deleted-{uuid4().hex}")
        rename_path(directory, removed)
        shutil.rmtree(removed, ignore_errors=True)
