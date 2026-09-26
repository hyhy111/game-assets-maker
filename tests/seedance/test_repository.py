import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from PIL import Image

from backend.seedance.models import SeedanceRequest
from backend.seedance.repository import TaskRepository


def _write_image(path: Path) -> Path:
    Image.new("RGB", (300, 300), "white").save(path)
    return path


@pytest.fixture
def repository(tmp_path: Path) -> TaskRepository:
    return TaskRepository(tmp_path / "seedance-cache")


@pytest.fixture
def seedance_request(tmp_path: Path) -> SeedanceRequest:
    return SeedanceRequest(
        first_frame=_write_image(tmp_path / "first.png"),
        last_frame=_write_image(tmp_path / "last.png"),
    )


def test_create_draft_copies_inputs_and_persists_full_prompt(repository, seedance_request):
    seedance_request.prompt = "完整提示词"
    layout = {"character_height_ratio": 0.38}
    seedance_request.first_frame.with_name(f"{seedance_request.first_frame.name}.layout.json").write_text(
        json.dumps(layout), encoding="utf-8"
    )
    edit_source = seedance_request.first_frame.with_name(
        f"{seedance_request.first_frame.name}.edit-source.png"
    )
    _write_image(edit_source)

    task = repository.create_draft(seedance_request)
    stored = repository.get(task.local_id)

    assert stored.request["prompt"] == "完整提示词"
    assert stored.download_url_received_at is None
    assert not Path(stored.request["first_frame"]).is_absolute()
    assert not Path(stored.request["last_frame"]).is_absolute()
    assert not Path(stored.input_paths["first_frame"]).is_absolute()
    assert repository.resolve_asset(stored.local_id, stored.input_paths["first_frame"]).read_bytes() == (
        seedance_request.first_frame.read_bytes()
    )
    assert repository.resolve_asset(stored.local_id, stored.input_paths["last_frame"]).read_bytes() == (
        seedance_request.last_frame.read_bytes()
    )
    copied_first = repository.resolve_asset(stored.local_id, stored.input_paths["first_frame"])
    copied_layout = copied_first.with_name(f"{copied_first.name}.layout.json")
    assert json.loads(copied_layout.read_text(encoding="utf-8")) == layout
    assert copied_first.with_name(f"{copied_first.name}.edit-source.png").read_bytes() == edit_source.read_bytes()


def test_list_returns_newest_draft_first(repository, seedance_request):
    older = repository.create_draft(seedance_request)
    newer = repository.create_draft(seedance_request)

    assert [task.local_id for task in repository.list()] == [newer.local_id, older.local_id]


def test_concurrent_updates_keep_task_json_valid(repository, seedance_request):
    task = repository.create_draft(seedance_request)

    def increment() -> None:
        def update_counter(current):
            current.remote["count"] = current.remote.get("count", 0) + 1

        repository.update(task.local_id, update_counter)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: increment(), range(32)))

    task_path = repository.cache_root / "tasks" / task.local_id / "task.json"
    assert json.loads(task_path.read_text(encoding="utf-8"))["remote"]["count"] == 32
    assert repository.get(task.local_id).remote["count"] == 32


def test_malformed_task_json_is_reported_without_overwrite(repository, seedance_request):
    task = repository.create_draft(seedance_request)
    task_path = repository.cache_root / "tasks" / task.local_id / "task.json"
    malformed = "{not valid json"
    task_path.write_text(malformed, encoding="utf-8")

    with pytest.raises(ValueError):
        repository.update(task.local_id, lambda current: setattr(current, "remote_status", "submitted"))

    assert task_path.read_text(encoding="utf-8") == malformed


def test_delete_rejects_tasks_with_handoffs_unless_explicitly_allowed(repository, seedance_request):
    task = repository.create_draft(seedance_request)
    repository.update(task.local_id, lambda current: current.handoffs.append({"project_id": "project-1"}))

    with pytest.raises(ValueError, match="handoffs"):
        repository.delete(task.local_id)

    repository.delete(task.local_id, allow_protected=True)
    with pytest.raises(FileNotFoundError):
        repository.get(task.local_id)


def test_resolve_asset_rejects_absolute_traversal_and_symlink_escapes(repository, seedance_request, tmp_path: Path):
    task = repository.create_draft(seedance_request)
    task_dir = repository.cache_root / "tasks" / task.local_id
    outside = tmp_path / "outside.png"
    _write_image(outside)
    (task_dir / "input" / "escape.png").symlink_to(outside)

    candidates = (
        "/tmp/outside.png",
        r"C:\\outside.png",
        r"\\\\server\\share\\outside.png",
        "../outside.png",
        r"..\\outside.png",
        "input/escape.png",
    )
    for candidate in candidates:
        with pytest.raises(ValueError):
            repository.resolve_asset(task.local_id, candidate)
