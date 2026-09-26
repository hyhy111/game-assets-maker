import base64
from pathlib import Path

import pytest
from PIL import Image

from backend.seedance.models import MODEL_CAPABILITIES, SeedanceRequest, SeedanceTask
from backend.seedance.validation import ValidationError, build_api_payload, estimate_payload_bytes, validate_request


def _write_image(path: Path, *, size: tuple[int, int] = (300, 300), image_format: str = "PNG") -> Path:
    Image.new("RGB", size, "white").save(path, format=image_format)
    return path


@pytest.fixture
def seedance_request(tmp_path: Path) -> SeedanceRequest:
    return SeedanceRequest(first_frame=_write_image(tmp_path / "first.png"))


@pytest.mark.parametrize(
    ("model", "resolution", "valid"),
    [
        ("standard", "480p", True),
        ("standard", "720p", True),
        ("standard", "1080p", True),
        ("standard", "4k", False),
        ("fast", "480p", True),
        ("fast", "720p", True),
        ("fast", "1080p", False),
        ("fast", "4k", False),
        ("mini", "480p", True),
        ("mini", "720p", True),
        ("mini", "1080p", False),
        ("mini", "4k", False),
        ("unknown", "720p", False),
    ],
)
def test_model_resolution_combinations(seedance_request: SeedanceRequest, model: str, resolution: str, valid: bool):
    seedance_request.model = model
    seedance_request.resolution = resolution

    if valid:
        validate_request(seedance_request)
    else:
        with pytest.raises(ValidationError) as exc:
            validate_request(seedance_request)
        assert exc.value.field in {"model", "resolution"}


def test_model_capabilities_are_the_fixed_seedance_models():
    assert MODEL_CAPABILITIES == {
        "standard": {"id": "doubao-seedance-2-0-260128", "resolutions": ("480p", "720p", "1080p")},
        "fast": {"id": "doubao-seedance-2-0-fast-260128", "resolutions": ("480p", "720p")},
        "mini": {"id": "doubao-seedance-2-0-mini-260615", "resolutions": ("480p", "720p")},
    }


@pytest.mark.parametrize("ratio", ["adaptive", "16:9", "1:1", "4:3"])
def test_supported_ratios_are_valid(seedance_request: SeedanceRequest, ratio: str):
    seedance_request.ratio = ratio

    validate_request(seedance_request)


@pytest.mark.parametrize("duration", [-1, 4, 15])
def test_supported_duration_boundaries_are_valid(seedance_request: SeedanceRequest, duration: int):
    seedance_request.duration = duration

    validate_request(seedance_request)


@pytest.mark.parametrize("duration", [-1.0, 4.0, True, False])
def test_duration_requires_an_integer_sentinel_or_integer_seconds(seedance_request: SeedanceRequest, duration: object):
    seedance_request.duration = duration  # type: ignore[assignment]

    with pytest.raises(ValidationError) as exc:
        validate_request(seedance_request)

    assert exc.value.field == "duration"
    assert exc.value.code == "INVALID_DURATION"


@pytest.mark.parametrize(
    "field,value",
    [
        ("duration", 3),
        ("duration", 16),
        ("priority", -1),
        ("priority", 10),
        ("execution_expires_after", 3599),
        ("execution_expires_after", 259201),
    ],
)
def test_numeric_values_outside_supported_ranges_are_invalid(seedance_request: SeedanceRequest, field: str, value: int):
    setattr(seedance_request, field, value)

    with pytest.raises(ValidationError) as exc:
        validate_request(seedance_request)

    assert exc.value.field == field


@pytest.mark.parametrize(
    "field,value",
    [("priority", 0), ("priority", 9), ("execution_expires_after", 3600), ("execution_expires_after", 259200)],
)
def test_numeric_value_boundaries_are_valid(seedance_request: SeedanceRequest, field: str, value: int):
    setattr(seedance_request, field, value)

    validate_request(seedance_request)


def test_empty_prompt_is_allowed_and_trimmed_in_payload(seedance_request: SeedanceRequest):
    seedance_request.prompt = "   "

    payload = build_api_payload(seedance_request)

    assert payload["content"][0]["role"] == "first_frame"
    assert all(item["type"] != "text" for item in payload["content"])


def test_long_chinese_prompt_is_sent_without_local_length_rejection(seedance_request: SeedanceRequest):
    seedance_request.prompt = "中" + "a" * 500

    payload = build_api_payload(seedance_request)

    assert payload["content"][0] == {"type": "text", "text": seedance_request.prompt}


def test_long_cjk_extension_prompt_is_sent_without_local_length_rejection(seedance_request: SeedanceRequest):
    seedance_request.prompt = "\U00020000" + "a" * 500

    payload = build_api_payload(seedance_request)

    assert payload["content"][0] == {"type": "text", "text": seedance_request.prompt}


def test_chinese_prompt_allows_500_unicode_characters_after_outer_whitespace_is_trimmed(
    seedance_request: SeedanceRequest,
):
    seedance_request.prompt = "  中" + "a" * 499 + "  "

    payload = build_api_payload(seedance_request)

    assert payload["content"][0] == {"type": "text", "text": "中" + "a" * 499}


def test_long_english_prompt_is_sent_without_local_length_rejection(seedance_request: SeedanceRequest):
    seedance_request.prompt = "word " * 1001

    payload = build_api_payload(seedance_request)

    assert payload["content"][0] == {"type": "text", "text": seedance_request.prompt.strip()}


@pytest.mark.parametrize(
    ("suffix", "image_format", "mime_type"),
    [
        ("jpg", "JPEG", "image/jpeg"),
        ("png", "PNG", "image/png"),
        ("webp", "WEBP", "image/webp"),
        ("bmp", "BMP", "image/bmp"),
        ("tiff", "TIFF", "image/tiff"),
        ("gif", "GIF", "image/gif"),
    ],
)
def test_supported_image_formats_are_sent_as_mime_specific_data_urls(
    tmp_path: Path, suffix: str, image_format: str, mime_type: str
):
    request = SeedanceRequest(first_frame=_write_image(tmp_path / f"first.{suffix}", image_format=image_format))

    payload = build_api_payload(request)

    data_url = payload["content"][0]["image_url"]["url"]
    assert data_url.startswith(f"data:{mime_type};base64,")
    assert base64.b64decode(data_url.rsplit(",", 1)[1]) == request.first_frame.read_bytes()


def test_unsupported_image_format_is_rejected(tmp_path: Path):
    request = SeedanceRequest(first_frame=_write_image(tmp_path / "first.ico", image_format="ICO"))

    with pytest.raises(ValidationError) as exc:
        validate_request(request)

    assert exc.value.field == "first_frame"
    assert exc.value.code == "UNSUPPORTED_IMAGE_FORMAT"


@pytest.mark.parametrize("size", [(299, 300), (6001, 300), (300, 299), (300, 6001), (300, 800), (800, 300)])
def test_invalid_image_dimensions_or_aspect_ratio_are_rejected(tmp_path: Path, size: tuple[int, int]):
    request = SeedanceRequest(first_frame=_write_image(tmp_path / "first.png", size=size))

    with pytest.raises(ValidationError) as exc:
        validate_request(request)

    assert exc.value.field == "first_frame"


def test_image_size_must_be_strictly_under_30_mib(seedance_request: SeedanceRequest, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("backend.image_input.file_size", lambda _: 30 * 1024 * 1024)

    with pytest.raises(ValidationError) as exc:
        validate_request(seedance_request)

    assert exc.value.field == "first_frame"
    assert exc.value.code == "IMAGE_TOO_LARGE"


def test_payload_has_ordered_roles_and_only_supported_body_fields(tmp_path: Path):
    request = SeedanceRequest(
        first_frame=_write_image(tmp_path / "first.png"),
        last_frame=_write_image(tmp_path / "last.png"),
        prompt="  animate this  ",
        generate_audio=True,
        return_last_frame=True,
        priority=9,
        execution_expires_after=3600,
    )

    payload = build_api_payload(request)

    assert payload["model"] == MODEL_CAPABILITIES["standard"]["id"]
    assert payload["content"] == [
        {"type": "text", "text": "animate this"},
        payload["content"][1],
        payload["content"][2],
    ]
    assert [item["role"] for item in payload["content"][1:]] == ["first_frame", "last_frame"]
    assert payload["watermark"] is False
    assert payload.keys() == {
        "model",
        "content",
        "resolution",
        "ratio",
        "duration",
        "generate_audio",
        "return_last_frame",
        "priority",
        "execution_expires_after",
        "watermark",
    }
    assert not {"web_search", "camera_fixed", "callback_url", "endpoint_id"} & payload.keys()


def test_payload_at_64_mib_is_rejected(seedance_request: SeedanceRequest, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("backend.seedance.validation._serialized_payload_bytes", lambda _: 64 * 1024 * 1024)

    with pytest.raises(ValidationError) as exc:
        build_api_payload(seedance_request)

    assert exc.value.field == "payload"
    assert exc.value.code == "PAYLOAD_TOO_LARGE"


def test_estimate_payload_bytes_matches_compact_utf8_json(seedance_request: SeedanceRequest):
    payload = build_api_payload(seedance_request)

    assert estimate_payload_bytes(seedance_request) == len(
        __import__("json").dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )


def test_seedance_task_round_trip_ignores_unknown_future_keys_and_defaults_link_received_time():
    values = {
        "local_id": "local-1",
        "remote_id": None,
        "remote_status": "queued",
        "sync_status": {},
        "download_status": "pending",
        "cache_status": "complete",
        "request": {},
        "input_paths": {},
        "output_paths": {},
        "created_at": "2026-07-17T00:00:00Z",
        "updated_at": "2026-07-17T00:00:00Z",
        "finished_at": None,
        "remote": {},
        "error": None,
        "retry_of": None,
        "handoffs": [],
        "future_key": "ignored",
    }

    task = SeedanceTask.from_dict(values)

    expected = {key: value for key, value in values.items() if key != "future_key"}
    expected["download_url_received_at"] = None
    assert task.to_dict() == expected
    with pytest.raises(ValueError, match="local_id"):
        SeedanceTask.from_dict({key: value for key, value in values.items() if key not in {"local_id", "future_key"}})
