from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from backend.seedream.media import SeedreamMediaResolver
from backend.seedream.models import SeedreamRequest
from backend.seedream.repository import BatchRepository


def _reference_png(path: Path) -> Path:
    Image.new("RGB", (64, 64), "#3156d9").save(path, format="PNG")
    return path


def test_reference_asset_resolves_to_cached_reference_image(tmp_path):
    source = _reference_png(tmp_path / "source.png")
    repository = BatchRepository(tmp_path / "cache")
    batch = repository.create_batch(SeedreamRequest(prompt="hero", count=1, reference_image=str(source)))

    resolver = SeedreamMediaResolver(repository)

    resolved = resolver.resolve(batch.local_id, "reference")
    assert resolved.read_bytes() == source.read_bytes()


def test_reference_asset_rejected_for_batch_without_reference_image(tmp_path):
    repository = BatchRepository(tmp_path / "cache")
    batch = repository.create_batch(SeedreamRequest(prompt="hero", count=1))

    resolver = SeedreamMediaResolver(repository)

    with pytest.raises(FileNotFoundError):
        resolver.resolve(batch.local_id, "reference")


def test_unknown_asset_key_rejected(tmp_path):
    repository = BatchRepository(tmp_path / "cache")
    resolver = SeedreamMediaResolver(repository)

    with pytest.raises(ValueError):
        resolver.resolve("any", "unknown-key")
