"""Preserve rename semantics while handling transient Windows directory locks."""

import errno
from types import SimpleNamespace

import pytest

from src.utils import file_operations


def windows_error(code):
    error = PermissionError(errno.EACCES, "synthetic Windows directory lock")
    error.winerror = code
    return error


@pytest.mark.parametrize("code", [5, 32, 33])
def test_transient_windows_rename_retries_then_preserves_contents(tmp_path, monkeypatch, code):
    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir()
    (source / "legacy.json").write_text('{"original":true}', encoding="utf-8")
    rename = file_operations.os.rename
    calls = []
    delays = []

    def locked_once(old, new):
        calls.append((old, new))
        if len(calls) == 1:
            raise windows_error(code)
        return rename(old, new)

    monkeypatch.setattr(file_operations, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(file_operations.os, "rename", locked_once)
    monkeypatch.setattr(file_operations.time, "sleep", delays.append)

    file_operations.rename_path(source, target)

    assert len(calls) == 2
    assert delays == [0.05]
    assert not source.exists()
    assert (target / "legacy.json").read_text(encoding="utf-8") == '{"original":true}'


def test_persistent_windows_denial_is_bounded_and_preserves_source(tmp_path, monkeypatch):
    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir()
    calls = []
    delays = []
    error = windows_error(5)

    def denied(*args):
        calls.append(args)
        raise error

    monkeypatch.setattr(file_operations, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(file_operations.os, "rename", denied)
    monkeypatch.setattr(file_operations.time, "sleep", delays.append)

    with pytest.raises(PermissionError) as caught:
        file_operations.rename_path(source, target)

    assert caught.value is error
    assert len(calls) == 5
    assert sum(delays) < 1
    assert source.is_dir()
    assert not target.exists()


@pytest.mark.parametrize("platform,code", [("darwin", 5), ("linux", 32), ("win32", 183)])
def test_other_errors_propagate_without_retry(tmp_path, monkeypatch, platform, code):
    error = windows_error(code)

    def denied(*args):
        raise error

    def unexpected_sleep(delay):
        pytest.fail("This error must not be retried")

    monkeypatch.setattr(file_operations, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setattr(file_operations.os, "rename", denied)
    monkeypatch.setattr(file_operations.time, "sleep", unexpected_sleep)

    with pytest.raises(PermissionError) as caught:
        file_operations.rename_path(tmp_path / "source", tmp_path / "target")
    assert caught.value is error


def test_replace_retries_without_losing_previous_file(tmp_path, monkeypatch):
    source, target = tmp_path / "new.json", tmp_path / "config.json"
    source.write_text("new settings", encoding="utf-8")
    target.write_text("old settings", encoding="utf-8")
    replace = file_operations.os.replace
    calls = []

    def locked_once(old, new):
        calls.append((old, new))
        if len(calls) == 1:
            assert target.read_text(encoding="utf-8") == "old settings"
            raise windows_error(32)
        return replace(old, new)

    monkeypatch.setattr(file_operations, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(file_operations.os, "replace", locked_once)
    monkeypatch.setattr(file_operations.time, "sleep", lambda delay: None)

    file_operations.rename_path(source, target, replace=True)

    assert len(calls) == 2
    assert target.read_text(encoding="utf-8") == "new settings"
    assert not source.exists()
