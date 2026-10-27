"""Stable release checks, credential boundaries and persisted version dismissal."""

import io
import json
import urllib.error
from unittest.mock import Mock

import pytest

from backend.api import update_api
from backend.api.config_api import ConfigAPI
from backend.api.update_api import UpdateAPI
from src.utils.app_config import load_app_config, save_app_config
from src.utils.app_version import app_version


def release(tag="v1.0.1", **changes):
    return {
        "tag_name": tag,
        "draft": False,
        "prerelease": False,
        "html_url": f"https://github.com/hyhy111/game-assets-maker/releases/tag/{tag}",
        "body": "Release notes <b>remain plain text</b>",
        **changes,
    }


@pytest.fixture
def setup_updates(tmp_path, monkeypatch):
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("GAM_CONFIG", str(tmp_path / "config.json"))
    monkeypatch.delenv("GAM_UPDATE_GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(update_api, "app_version", lambda: "1.0.0")
    transport = Mock(side_effect=lambda *args, **kwargs: io.BytesIO(json.dumps(release()).encode()))
    monkeypatch.setattr(update_api.urllib.request, "urlopen", transport)
    return transport


@pytest.mark.parametrize(
    ("tag", "status"),
    [
        ("v1.0.1", "available"),
        ("v1.0.10", "available"),
        ("v1.10.0", "available"),
        ("v1.0.0", "up_to_date"),
        ("v0.9.9", "up_to_date"),
        ("v1.0.0+build.2", "up_to_date"),
    ],
)
def test_checks_stable_semantic_versions_without_downgrades(setup_updates, tag, status):
    setup_updates.side_effect = lambda *args, **kwargs: io.BytesIO(json.dumps(release(tag)).encode())
    checker = UpdateAPI()
    result = checker.check()
    assert result["status"] == status
    assert result["current_version"] == "1.0.0"
    assert checker.check() == result
    assert setup_updates.call_count == 1


def test_version_comparison_is_numeric(setup_updates, monkeypatch):
    monkeypatch.setattr(update_api, "app_version", lambda: "1.0.9")
    setup_updates.side_effect = lambda *a, **kw: io.BytesIO(json.dumps(release("v1.0.10")).encode())
    assert UpdateAPI().check()["status"] == "available"


@pytest.mark.parametrize(
    "changes",
    [
        {"draft": True},
        {"prerelease": True},
        {"tag_name": "v2.0.0-rc.1"},
        {"tag_name": "bad"},
        {"html_url": "https://evil.example/releases/tag/v1.0.1"},
        {"html_url": "http://github.com/hyhy111/game-assets-maker/releases/tag/v1.0.1"},
        {"html_url": "https://github.com/another/repo/releases/tag/v1.0.1"},
        {"html_url": "https://github.com/hyhy111/game-assets-maker/releases/tag/v1.0.1?token=test"},
        {"body": {"unexpected": "object"}},
    ],
)
def test_invalid_release_never_enables_update_or_browser(setup_updates, monkeypatch, changes):
    setup_updates.side_effect = lambda *args, **kwargs: io.BytesIO(json.dumps(release(**changes)).encode())
    browser = Mock()
    monkeypatch.setattr(update_api.webbrowser, "open", browser)
    checker = UpdateAPI()
    assert checker.open_release() is False
    result = checker.check()
    assert result["status"] == "error"
    assert result["error"] == "INVALID_RELEASE"
    assert checker.open_release() is False
    browser.assert_not_called()


@pytest.mark.parametrize(
    ("code", "headers", "expected"),
    [
        (404, {}, "NOT_FOUND_OR_PRIVATE"),
        (401, {}, "ACCESS_DENIED"),
        (403, {}, "ACCESS_DENIED"),
        (403, {"X-RateLimit-Remaining": "0"}, "RATE_LIMITED"),
        (429, {}, "RATE_LIMITED"),
        (500, {}, "NETWORK_ERROR"),
    ],
)
def test_http_failures_do_not_claim_up_to_date_or_leak_messages(setup_updates, code, headers, expected):
    setup_updates.side_effect = urllib.error.HTTPError("secret-url", code, "private-message", headers, None)
    result = UpdateAPI().check()
    assert result["status"] == "error"
    assert result["error"] == expected
    assert "secret" not in json.dumps(result)
    assert "private-message" not in json.dumps(result)


@pytest.mark.parametrize("failure", [TimeoutError(), urllib.error.URLError("private-message")])
def test_network_failure_is_explicit(setup_updates, failure):
    setup_updates.side_effect = failure
    result = UpdateAPI().check()
    assert result["status"] == "error"
    assert result["error"] == "NETWORK_ERROR"


def test_private_test_token_is_transport_only(setup_updates, monkeypatch):
    monkeypatch.setenv("GAM_UPDATE_GITHUB_TOKEN", "test-token-never-persist")
    result = UpdateAPI().check()
    request = setup_updates.call_args.args[0]
    assert request.full_url == update_api.LATEST_RELEASE_URL
    assert request.get_header("Authorization") == "Bearer test-token-never-persist"
    assert setup_updates.call_args.kwargs["timeout"] == 8
    assert "test-token" not in json.dumps(result)
    assert "test-token" not in json.dumps(load_app_config())


def test_ignoring_version_survives_restart_and_does_not_hide_future_release(setup_updates, monkeypatch):
    browser = Mock(return_value=True)
    monkeypatch.setattr(update_api.webbrowser, "open", browser)
    save_app_config({"language": "en", "seedance": {"default_duration": 8}})
    checker = UpdateAPI()
    assert checker.ignore("1.0.1") is False
    assert checker.check()["status"] == "available"
    assert checker.ignore("2.0.0") is False
    assert checker.ignore("1.0.1") is True
    assert checker.check()["status"] == "ignored"
    assert checker.open_release() is True
    restarted = UpdateAPI()
    assert restarted.check()["status"] == "ignored"
    assert restarted.open_release() is True
    assert browser.call_count == 2
    config = load_app_config()
    assert config["language"] == "en"
    assert config["seedance"]["default_duration"] == 8
    assert config["ignored_update_version"] == "1.0.1"
    ConfigAPI().save_config({"ignored_update_version": "", "logger_enabled": True})
    assert load_app_config()["ignored_update_version"] == "1.0.1"
    setup_updates.side_effect = lambda *a, **kw: io.BytesIO(json.dumps(release("v1.0.2")).encode())
    assert UpdateAPI().check()["status"] == "available"


def test_failed_ignore_retains_notification(setup_updates, monkeypatch):
    checker = UpdateAPI()
    checker.check()
    monkeypatch.setattr(update_api, "save_app_config", Mock(side_effect=OSError("read-only")))
    assert checker.ignore("1.0.1") is False
    assert checker.check()["status"] == "available"


def test_update_opens_only_cached_release_page(setup_updates, monkeypatch):
    browser = Mock(return_value=True)
    monkeypatch.setattr(update_api.webbrowser, "open", browser)
    checker = UpdateAPI()
    checker.check()
    assert checker.open_release() is True
    browser.assert_called_once_with(release()["html_url"])
    assert setup_updates.call_count == 1


def test_bridge_exposes_shared_update_state(setup_updates):
    from backend.main import API

    bridge = API()
    assert bridge.get_app_version() == app_version()
    assert bridge.check_app_update()["status"] == "available"
    assert bridge.ignore_app_update("1.0.1") is True
    assert bridge.check_app_update()["status"] == "ignored"
    assert setup_updates.call_count == 1


@pytest.mark.parametrize("outcome", [True, False, OSError("blocked"), update_api.webbrowser.Error("unavailable")])
def test_repository_opens_without_release_check(setup_updates, monkeypatch, outcome):
    browser = Mock(side_effect=outcome) if isinstance(outcome, Exception) else Mock(return_value=outcome)
    monkeypatch.setattr(update_api.webbrowser, "open", browser)
    from backend.main import API

    bridge = API()
    assert bridge.open_github_repository() is (outcome is True)
    browser.assert_called_once_with("https://github.com/hyhy111/game-assets-maker")
    setup_updates.assert_not_called()
