"""Delete legacy generation records without removing an acquired lock file."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError

import pytest
from PIL import Image

from backend.seedance.models import SeedanceRequest
from backend.seedance.repository import TaskRepository
from backend.seedream.models import SeedreamRequest
from backend.seedream.repository import BatchRepository


@pytest.fixture(params=["video", "image"])
def records(request, tmp_path):
    cache = tmp_path / "cache"
    if request.param == "video":
        source = tmp_path / "first.png"
        Image.new("RGB", (64, 64), "white").save(source)
        repo = TaskRepository(cache)
        record = repo.create_draft(SeedanceRequest(first_frame=source))
        directory = repo.tasks_root / record.local_id
        legacy_lock = ".task.lock"
        lock = repo.task_lock
    else:
        repo = BatchRepository(cache)
        record = repo.create_batch(SeedreamRequest(prompt="synthetic test"))
        directory = repo.batches_root / record.local_id
        legacy_lock = ".batch.lock"
        lock = repo.batch_lock
    return repo, record, directory, legacy_lock, lock


def test_record_lock_survives_deletion_until_released(records):
    repo, record, directory, _, lock = records
    with lock(record.local_id) as acquired:
        repo._delete_unlocked(record.local_id)
        assert acquired.is_locked
        assert not directory.exists()


def test_legacy_record_with_old_lock_file_can_be_reopened_and_deleted(records):
    repo, record, directory, legacy_lock, _ = records
    (directory / legacy_lock).touch()
    reopened = type(repo)(repo.cache_root)

    assert reopened.get(record.local_id).to_dict() == record.to_dict()
    reopened.delete(record.local_id)

    assert not directory.exists()
    assert reopened.list() == []
    with pytest.raises(FileNotFoundError):
        reopened.get(record.local_id)
    assert not directory.exists()


def test_delete_waits_for_another_repository_instance_to_release_the_record(records):
    repo, record, directory, _, lock = records
    reopened = type(repo)(repo.cache_root)

    with ThreadPoolExecutor(max_workers=1) as executor:
        with lock(record.local_id):
            deleted = executor.submit(reopened.delete, record.local_id)
            with pytest.raises(TimeoutError):
                deleted.result(timeout=0.1)
            assert directory.exists()
        deleted.result(timeout=5)

    assert not directory.exists()
