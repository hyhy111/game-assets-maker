from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from backend.seedream.models import SeedreamRequest
from backend.seedream.repository import BatchRepository


def _write_source_image(path: Path) -> Path:
    Image.new("RGB", (64, 64), "#3156d9").save(path, format="PNG")
    return path


def test_create_batch_persists_batch_and_attempt_before_remote_call(tmp_path):
    repo = BatchRepository(tmp_path / "cache")
    batch = repo.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))

    # The batch.json must exist on disk immediately after creation.
    batch_dir = repo._existing_batch_dir(batch.local_id)
    assert (batch_dir / "batch.json").is_file()

    persisted = repo.get(batch.local_id)
    assert persisted.local_id == batch.local_id
    assert len(persisted.attempts) == 1
    attempt = persisted.attempts[0]
    assert attempt.status == "queued"
    assert attempt.response == {}
    assert attempt.local_path is None
    assert attempt.error is None
    assert attempt.finished_at is None
    assert attempt.request == {
        "prompt": "hero",
        "model": "pro",
        "resolution": "1K",
        "ratio": "16:9",
        "count": 1,
        "reference_image": None,
        "source": "api-key",
    }


def test_list_returns_batches_sorted_by_creation_time(tmp_path):
    repo = BatchRepository(tmp_path / "cache")
    batch1 = repo.create_batch(SeedreamRequest(prompt="first", model="pro", resolution="1K", ratio="16:9", count=1))
    batch2 = repo.create_batch(SeedreamRequest(prompt="second", model="pro", resolution="1K", ratio="16:9", count=1))

    batches = repo.list()
    assert len(batches) == 2
    assert batches[0].local_id == batch2.local_id
    assert batches[1].local_id == batch1.local_id


def test_update_persists_response_before_download(tmp_path):
    repo = BatchRepository(tmp_path / "cache")
    batch = repo.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))

    response = {"created": 0, "data": [{"url": "https://example.com/img.jpg"}], "usage": {"total_tokens": 5}}

    def updater(b):
        b.attempts[0].response = response
        b.attempts[0].status = "downloading"

    repo.update(batch.local_id, updater)

    persisted = repo.get(batch.local_id)
    assert persisted.attempts[0].response == response
    assert persisted.attempts[0].status == "downloading"

    # Verify it was actually written to disk.
    batch_dir = repo._existing_batch_dir(batch.local_id)
    with (batch_dir / "batch.json").open() as f:
        raw = json.load(f)
    assert raw["attempts"][0]["response"] == response


def test_resolve_asset_rejects_path_traversal(tmp_path):
    repo = BatchRepository(tmp_path / "cache")
    batch = repo.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))

    import pytest

    with pytest.raises(ValueError):
        repo.resolve_asset(batch.local_id, "../../etc/passwd")
    with pytest.raises(ValueError):
        repo.resolve_asset(batch.local_id, "/absolute/path")


def test_delete_removes_batch_directory(tmp_path):
    repo = BatchRepository(tmp_path / "cache")
    batch = repo.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))

    repo.delete(batch.local_id)
    import pytest

    with pytest.raises(FileNotFoundError):
        repo.get(batch.local_id)


def test_images_directory_created_on_batch_creation(tmp_path):
    repo = BatchRepository(tmp_path / "cache")
    batch = repo.create_batch(SeedreamRequest(prompt="hero", model="pro", resolution="1K", ratio="16:9", count=1))

    batch_dir = repo._existing_batch_dir(batch.local_id)
    assert (batch_dir / "images").is_dir()


def test_create_batch_copies_reference_image_into_batch_directory(tmp_path):
    source = _write_source_image(tmp_path / "source.png")
    repo = BatchRepository(tmp_path / "cache")

    batch = repo.create_batch(SeedreamRequest(prompt="hero", reference_image=str(source)))

    persisted = repo.get(batch.local_id)
    stored = persisted.request["reference_image"]
    assert isinstance(stored, str) and stored
    assert stored != str(source)
    resolved = repo.resolve_asset(batch.local_id, stored)
    assert resolved.is_file()
    assert resolved.suffix == ".png"
    assert resolved.read_bytes() == source.read_bytes()
    assert persisted.attempts[0].request["reference_image"] == stored

    batch_dir = repo._existing_batch_dir(batch.local_id)
    with (batch_dir / "batch.json").open() as f:
        raw = json.load(f)
    assert raw["request"]["reference_image"] == stored
    assert str(source) not in json.dumps(raw)


def test_create_batch_without_reference_image_persists_none(tmp_path):
    repo = BatchRepository(tmp_path / "cache")

    batch = repo.create_batch(SeedreamRequest(prompt="hero"))

    persisted = repo.get(batch.local_id)
    assert persisted.request["reference_image"] is None


def test_create_batch_reference_image_uses_actual_format_extension(tmp_path):
    source = tmp_path / "mislabeled.png"
    Image.new("RGB", (64, 64), "#9c3fd6").save(source, format="JPEG")

    repo = BatchRepository(tmp_path / "cache")
    batch = repo.create_batch(SeedreamRequest(prompt="hero", reference_image=str(source)))

    persisted = repo.get(batch.local_id)
    resolved = repo.resolve_asset(batch.local_id, persisted.request["reference_image"])
    assert resolved.suffix == ".jpg"
