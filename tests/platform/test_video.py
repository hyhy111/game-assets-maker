"""PlatformVideoClient / PlatformImageClient mapping to the Ark-shaped contract."""

from __future__ import annotations

import pytest
from platform_test_helpers import FakeTransport, ajax_ok

from backend.platform.client import PlatformClient
from backend.platform.images import PlatformImageClient
from backend.platform.video import PlatformVideoClient, artifact_url, local_status, parse_error_json


def make_video_client(transport: FakeTransport) -> PlatformVideoClient:
    return PlatformVideoClient(PlatformClient("http://platform.test", "token", transport=transport))


def make_image_client(transport: FakeTransport) -> PlatformImageClient:
    return PlatformImageClient(PlatformClient("http://platform.test", "token", transport=transport))


def describe(status: str, **extra):
    payload = {
        "jobId": "9001",
        "jobType": "video",
        "status": status,
        "remoteStatus": "queued",
        "quote": 100,
        "error": None,
        "createdAt": "2026-09-27T00:00:00Z",
    }
    payload.update(extra)
    return ajax_ok(payload)


@pytest.mark.parametrize(
    ("platform_status", "expected"),
    [
        ("QUEUED", "queued"),
        ("SUBMITTING", "running"),
        ("RUNNING", "running"),
        ("SUBMISSION_UNKNOWN", "running"),
        ("CANCEL_REQUESTED", "cancelling"),
        ("SUCCEEDED", "succeeded"),
        ("FAILED", "failed"),
        ("CANCELLED", "cancelled"),
    ],
)
def test_status_mapping_table(platform_status, expected):
    assert local_status(platform_status) == expected


def test_create_task_maps_job_id_and_quote():
    transport = FakeTransport(
        lambda m, u, h, b: ajax_ok(
            {"jobId": "9001", "status": "QUEUED", "quote": 500, "quoteDetail": "{}", "idemReplay": False}
        )
    )
    mapped = make_video_client(transport).create_task({"idemKey": "gam-x"})
    assert mapped["id"] == "9001"
    assert mapped["status"] == "queued"
    assert mapped["platform_status"] == "QUEUED"
    assert mapped["quote"] == 500


def test_get_task_success_without_direct_link_keeps_pseudo_placeholder():
    """v1：服务端不再下发 downloadUrl；无新鲜直链时 video_url 退化伪地址占位。"""
    transport = FakeTransport(lambda m, u, h, b: describe("SUCCEEDED"))
    mapped = make_video_client(transport).get_task("9001")
    assert mapped["status"] == "succeeded"
    assert mapped["content"]["video_url"] == artifact_url("9001")
    assert "upstream_url" not in mapped["content"]


def test_get_task_running_has_no_content():
    transport = FakeTransport(lambda m, u, h, b: describe("RUNNING"))
    mapped = make_video_client(transport).get_task("9001")
    assert mapped["status"] == "running"
    assert "content" not in mapped


def test_get_task_failed_parses_error_json():
    transport = FakeTransport(
        lambda m, u, h, b: describe("FAILED", error='{"class":"ACCOUNT_EXHAUSTED","message":"余额不足"}')
    )
    mapped = make_video_client(transport).get_task("9001")
    assert mapped["status"] == "failed"
    assert mapped["error"]["message"] == "余额不足"


def test_get_task_submission_unknown_stays_pollable():
    transport = FakeTransport(lambda m, u, h, b: describe("SUBMISSION_UNKNOWN"))
    mapped = make_video_client(transport).get_task("9001")
    assert mapped["status"] == "running"
    assert mapped["platform_status"] == "SUBMISSION_UNKNOWN"


def test_cancel_maps_describe_response():
    transport = FakeTransport(lambda m, u, h, b: describe("CANCEL_REQUESTED"))
    mapped = make_video_client(transport).delete_task("9001")
    assert mapped["status"] == "cancelling"
    assert mapped["platform_status"] == "CANCEL_REQUESTED"


def test_parse_error_json_variants():
    assert parse_error_json(None) is None
    assert parse_error_json("") is None
    assert parse_error_json({"code": "X"}) == {"code": "X"}
    assert parse_error_json('{"code": "Y"}') == {"code": "Y"}
    assert parse_error_json("plain failure") == {"code": "PLATFORM_ERROR", "message": "plain failure"}


def test_image_client_success_maps_upstream_url():
    """v1：url 即上游地址本身（唯一交付载体），不再是平台伪地址。"""
    transport = FakeTransport(
        lambda m, u, h, b: ajax_ok(
            {
                "jobId": "42",
                "status": "SUCCEEDED",
                "quote": 30,
                "images": [
                    {
                        "url": "https://upstream.example/i.png",
                        "upstreamUrl": "https://upstream.example/i.png",
                        "upstreamExpiresAt": 9999999999999,
                    }
                ],
                "error": None,
            }
        )
    )
    mapped = make_image_client(transport).generate_image({"idemKey": "gam-i"})
    assert mapped["platform_status"] == "SUCCEEDED"
    assert mapped["data"][0]["url"] == "https://upstream.example/i.png"


def test_image_client_failed_carries_error():
    transport = FakeTransport(
        lambda m, u, h, b: ajax_ok(
            {
                "jobId": "42",
                "status": "FAILED",
                "quote": 0,
                "images": [],
                "error": '{"class":"RATE_LIMITED","message":"触发限流"}',
            }
        )
    )
    mapped = make_image_client(transport).generate_image({"idemKey": "gam-i"})
    assert mapped["platform_status"] == "FAILED"
    assert mapped["error"]["message"] == "触发限流"
    assert mapped["data"] == []
