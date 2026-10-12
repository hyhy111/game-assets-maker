"""Package channel identity and stale-build protection."""

import json

import pytest

import build


@pytest.mark.parametrize("code", ["", " douyin ", "渠道A", "x" * 64, "😀" * 32])
def test_channel_code_is_preserved(code):
    assert build.validate_channel_code(code) == code


@pytest.mark.parametrize("code", ["x" * 65, "😀" * 33, "bad\ncode", "bad\x00code"])
def test_invalid_code_fails_before_packaging(code):
    with pytest.raises(ValueError):
        build.validate_channel_code(code)


def test_skipped_frontend_rejects_missing_or_stale_channel(tmp_path):
    with pytest.raises(ValueError):
        build.verify_frontend_channel("", tmp_path)
    (tmp_path / "dist").mkdir()
    manifest = tmp_path / "dist" / "channel-code.json"
    manifest.write_text(json.dumps({"channelCode": "old"}))
    with pytest.raises(ValueError):
        build.verify_frontend_channel("new", tmp_path)
    build.verify_frontend_channel("old", tmp_path)
    manifest.write_text(json.dumps({"channelCode": ""}))
    build.verify_frontend_channel("", tmp_path)


def test_build_parameter_overrides_inherited_channel(monkeypatch, tmp_path):
    monkeypatch.setattr(build, "FRONTEND_DIR", str(tmp_path))
    (tmp_path / "node_modules").mkdir()
    monkeypatch.setenv("GAM_BUILD_CHANNEL_CODE", "stale")
    calls = []
    monkeypatch.setattr(build, "run", lambda cmd, **kwargs: calls.append(kwargs["env"]))
    build.build_frontend("new")
    build.build_frontend()
    assert [env["GAM_BUILD_CHANNEL_CODE"] for env in calls] == ["new", ""]
