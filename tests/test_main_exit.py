"""Shutdown epilogue tests for MainApp.

pywebview's Cocoa bridge threads are non-daemon and can block forever in
evaluate_js once the window's run loop stops, so MainApp exits the process
hard after the closed-event cleanup instead of letting interpreter
finalization join them. These tests pin that contract without launching a
window.
"""

from __future__ import annotations

import pytest

from src.utils.app_config import save_app_config


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path / "data-root"))
    monkeypatch.setenv("GAM_CONFIG", str(tmp_path / "runtime" / "config.json"))
    save_app_config({})
    return tmp_path


def test_on_window_closed_attempts_remaining_cleanup_after_failure(isolated_config):
    from backend.main import MainApp

    app = MainApp()

    class FailingProcessAPI:
        def shutdown(self):
            raise RuntimeError("boom")

    class RemainingAPI:
        def shutdown(self):
            stopped.append(True)

    stopped: list[bool] = []
    app.api._process_api_instance = FailingProcessAPI()
    app.api._seedance_api_instance = RemainingAPI()

    app.on_window_closed()

    assert app.stop_event.is_set()
    assert stopped == [True]
    assert app._closed_cleanup_done.is_set()
    assert app._closed_cleanup_failed


def test_exit_after_cleanup_hard_exits_without_restart(isolated_config, monkeypatch: pytest.MonkeyPatch):
    from backend.main import MainApp

    app = MainApp()
    app._closed_cleanup_done.set()
    exits: list[int] = []
    monkeypatch.setattr("os._exit", exits.append)

    app._exit_after_cleanup()

    assert exits == [0]


def test_exit_after_cleanup_restarts_before_exit(isolated_config, monkeypatch: pytest.MonkeyPatch):
    from backend.main import MainApp

    app = MainApp()
    app.restart_requested = True
    app._closed_cleanup_done.set()
    exits: list[int] = []
    restarts: list[bool] = []
    monkeypatch.setattr("os._exit", exits.append)
    monkeypatch.setattr(app, "_restart_in_place", lambda: restarts.append(True))

    app._exit_after_cleanup()

    assert restarts == [True]
    assert exits == [0]


def test_exit_after_cleanup_does_not_block_forever_on_missing_cleanup(isolated_config, monkeypatch: pytest.MonkeyPatch):
    from backend.main import MainApp

    app = MainApp()
    exits: list[int] = []
    monkeypatch.setattr("os._exit", exits.append)

    # Cleanup never signaled: the bounded wait must still give way to exit.
    app._exit_after_cleanup(cleanup_timeout=0.05)

    assert exits == [1]
