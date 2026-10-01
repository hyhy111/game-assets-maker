"""Local-only verification of custom-key Ark audit events."""

import json
import os
import subprocess
import sys
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from backend import ark_audit
from backend.ark_audit import ArkAudit, AuditStorageError, audit_context, provider_request_id
from backend.seedance.client import ArkClient as VideoClient
from backend.seedance.client import HttpResponse as VideoResponse
from backend.seedance.manager import SeedanceTaskManager
from backend.seedance.models import SeedanceRequest
from backend.seedance.repository import TaskRepository
from backend.seedream.client import ArkAPIError as ImageAPIError
from backend.seedream.client import ArkClient as ImageClient
from backend.seedream.client import HttpResponse as ImageResponse
from backend.seedream.downloader import ImageDownloader
from backend.seedream.manager import SeedreamBatchManager
from backend.seedream.models import SeedreamRequest
from backend.seedream.repository import BatchRepository


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def request(self, method, url, headers, body, timeout):
        self.calls.append((method, url))
        return self.response


def _events(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_image_call_audits_response_without_secrets(tmp_path):
    path = tmp_path / "ark.jsonl"
    secret_url = "https://example.test/private?signature=secret-url"
    response = ImageResponse(
        200,
        {"X-Request-Id": "request-123"},
        json.dumps(
            {
                "model": "doubao-seedream-5-0-flash-260915",
                "created": 1790786175,
                "data": [{"url": secret_url}],
                "usage": {"generated_images": 1, "output_tokens": 4450, "total_tokens": 4450},
            }
        ).encode(),
    )
    transport = FakeTransport(response)
    client = ImageClient("secret-api-key", transport=transport, audit=ArkAudit(path))
    with audit_context(batch_id="batch123", attempt_index=0):
        result = client.generate_image(
            {
                "model": "doubao-seedream-5-0-flash-260915",
                "prompt": "secret prompt",
                "size": "2K",
                "watermark": False,
            }
        )
    assert result["data"][0]["url"] == secret_url
    events = _events(path)
    assert [event["phase"] for event in events] == ["intent", "http_response", "parsed_response"]
    assert len({event["call_id"] for event in events}) == 1
    assert events[1]["fields"]["request_id"] == "request-123"
    assert events[2]["fields"]["generated_images"] == 1
    assert events[2]["fields"]["url_present"] is True
    log = path.read_text()
    for secret in ("secret-api-key", "secret prompt", secret_url):
        assert secret not in log
    assert transport.calls[0][0] == "POST"


def test_video_calls_keep_remote_id_and_safe_metadata(tmp_path):
    path = tmp_path / "ark.jsonl"
    audit = ArkAudit(path)
    create = FakeTransport(VideoResponse(200, {}, json.dumps({"id": "remote123", "status": "queued"}).encode()))
    client = VideoClient("secret-api-key", transport=create, audit=audit)
    with audit_context(task_id="local123"):
        assert (
            client.create_task(
                {
                    "model": "doubao-seedance-2-0",
                    "content": [
                        {"type": "text", "text": "secret prompt"},
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64,secret-image"}},
                    ],
                    "resolution": "720p",
                    "ratio": "16:9",
                    "duration": 5,
                }
            )["id"]
            == "remote123"
        )
    assert _events(path)[-1]["fields"]["remote_id"] == "remote123"
    assert _events(path)[0]["fields"]["input_images"] == 1
    client._transport = FakeTransport(
        VideoResponse(200, {}, json.dumps({"id": "remote123", "status": "running"}).encode())
    )
    with audit_context(task_id="local123", remote_id="remote123"):
        client.get_task("remote123")
    assert _events(path)[-1]["fields"]["remote_status"] == "running"
    client._transport = FakeTransport(VideoResponse(200, {}, b'{"data":[]}'))
    with audit_context():
        client.list_tasks(page_size=1)
    client._transport = FakeTransport(VideoResponse(204, {}, b""))
    with audit_context(task_id="local123", remote_id="remote123"):
        assert client.delete_task("remote123") is None
    assert {event["operation"] for event in _events(path)} == {
        "video.create",
        "video.get",
        "video.list",
        "video.delete",
    }
    for secret in ("secret-api-key", "secret prompt", "secret-image"):
        assert secret not in path.read_text()


def test_paid_post_is_not_sent_if_intent_cannot_be_saved(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    transport = FakeTransport(ImageResponse(200, {}, b"{}"))
    client = ImageClient("secret-api-key", transport=transport, audit=ArkAudit(blocker / "ark.jsonl"))
    with pytest.raises(AuditStorageError):
        client.generate_image({"model": "test", "prompt": "test"})
    assert transport.calls == []


def test_provider_request_id_cannot_echo_key_into_log():
    assert provider_request_id({"X-Request-Id": "prefix-secret-api-key"}, secret="secret-api-key") is None


def test_http_error_logs_code_without_provider_message(tmp_path):
    path = tmp_path / "ark.jsonl"
    response = ImageResponse(
        401, {"X-Request-Id": "request-401"}, b'{"error":{"code":"InvalidKey","message":"secret provider detail"}}'
    )
    client = ImageClient("secret-api-key", transport=FakeTransport(response), audit=ArkAudit(path))
    with pytest.raises(ImageAPIError):
        client.generate_image({"model": "test", "prompt": "secret prompt"})
    assert [event["phase"] for event in _events(path)] == ["intent", "http_response", "failure"]
    assert _events(path)[-1]["fields"]["error_code"] == "InvalidKey"
    assert "secret provider detail" not in path.read_text()


def test_prior_process_intent_is_reconciled_without_billing_claim(tmp_path, monkeypatch):
    path = tmp_path / "ark.jsonl"
    audit = ArkAudit(path)
    with audit_context(batch_id="batch123", attempt_index=0):
        audit.begin("image.create", payload={"model": "test", "prompt": "secret"}, paid=True)
    monkeypatch.setattr(ark_audit, "_PROCESS_ID", "next-process")
    audit.reconcile()
    audit.reconcile()
    events = _events(path)
    assert [event["phase"] for event in events] == ["intent", "interrupted_unresolved"]
    assert "bill" not in path.read_text().lower()


def test_image_manager_records_complete_local_timeline(tmp_path):
    path = tmp_path / "ark.jsonl"
    transport = FakeTransport(
        ImageResponse(
            200,
            {},
            json.dumps({"data": [{"url": "https://example.test/signed"}], "usage": {"generated_images": 1}}).encode(),
        )
    )

    class Download:
        def download(self, url):
            assert url == "https://example.test/signed"
            buffer = BytesIO()
            Image.new("RGB", (2, 2)).save(buffer, format="JPEG")
            return buffer.getvalue()

    repository = BatchRepository(tmp_path / "cache")
    batch = repository.create_batch(SeedreamRequest(prompt="test image", model="flash", count=1))
    client = ImageClient("secret-api-key", transport=transport, audit=ArkAudit(path))
    manager = SeedreamBatchManager(client, repository, ImageDownloader(repository, Download()))
    manager._run_attempt(batch.local_id, 0)
    assert repository.get(batch.local_id).attempts[0].status == "succeeded"
    assert [event["phase"] for event in _events(path)] == [
        "intent",
        "http_response",
        "parsed_response",
        "response_persisted",
        "download_started",
        "download_succeeded",
    ]
    assert len(transport.calls) == 1


def test_audit_uses_installed_data_root_override(tmp_path, monkeypatch):
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path / "user-data"))
    audit = ArkAudit()
    audit.record("video.list", "intent")
    assert audit.path == tmp_path / "user-data" / "logs" / "ark-custom-key.jsonl"
    assert audit.path.is_file()


def test_audit_intent_survives_hard_exit(tmp_path):
    path = tmp_path / "ark.jsonl"
    script = (
        "import os,sys; from pathlib import Path; from backend.ark_audit import ArkAudit; "
        "ArkAudit(Path(sys.argv[1])).begin('image.create',payload={'model':'test'},paid=True); os._exit(0)"
    )
    result = subprocess.run([sys.executable, "-c", script, str(path)], check=False, capture_output=True)
    assert result.returncode == 0
    assert _events(path)[0]["phase"] == "intent"
    assert os.stat(path).st_mode & 0o777 == 0o600


def test_audit_rotation_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(ark_audit, "_MAX_BYTES", 200)
    path = tmp_path / "ark.jsonl"
    audit = ArkAudit(path)
    for _ in range(30):
        audit.record("video.list", "intent")
    files = list(tmp_path.glob("ark.jsonl*"))
    assert len(files) <= ark_audit._MAX_ARCHIVES + 1
    assert all(file.stat().st_size <= 400 for file in files)


def test_video_manager_distinguishes_create_poll_and_download(tmp_path):
    path = tmp_path / "ark.jsonl"
    first_frame = tmp_path / "first.png"
    Image.new("RGB", (300, 300)).save(first_frame)
    repository = TaskRepository(tmp_path / "video-cache")

    class Downloader:
        def download_task(self, task):
            return repository.update(task.local_id, lambda current: setattr(current, "download_status", "downloaded"))

    transport = FakeTransport(VideoResponse(200, {}, b'{"id":"remote123","status":"queued"}'))
    client = VideoClient("secret-api-key", transport=transport, audit=ArkAudit(path))
    manager = SeedanceTaskManager(client, repository, Downloader(), object(), {"retention_days": 90})
    task = manager.create(SeedanceRequest(first_frame=first_frame, prompt="secret prompt"))
    assert task["remote_id"] == "remote123"
    client._transport = FakeTransport(
        VideoResponse(
            200, {}, b'{"id":"remote123","status":"succeeded","content":{"video_url":"https://example.test/signed"}}'
        )
    )
    manager._sync(task["local_id"])
    phases = [(event["operation"], event["phase"]) for event in _events(path)]
    assert ("video.create", "task_persisted") in phases
    assert ("video.get", "task_persisted") in phases
    assert ("video.get", "download_succeeded") in phases
    assert "https://example.test/signed" not in path.read_text()


def test_video_create_lost_response_stays_unknown_in_audit(tmp_path):
    path = tmp_path / "ark.jsonl"
    first_frame = tmp_path / "first.png"
    Image.new("RGB", (300, 300)).save(first_frame)
    repository = TaskRepository(tmp_path / "video-cache")

    class BrokenTransport:
        def request(self, method, url, headers, body, timeout):
            raise OSError("secret provider detail")

    client = VideoClient("secret-api-key", transport=BrokenTransport(), audit=ArkAudit(path))
    manager = SeedanceTaskManager(client, repository, object(), object(), {"retention_days": 90})
    task = manager.create(SeedanceRequest(first_frame=first_frame))
    assert task["remote_status"] == "submission_unknown"
    assert [event["phase"] for event in _events(path)] == ["intent", "failure", "local_unknown"]
    assert "secret provider detail" not in path.read_text()
