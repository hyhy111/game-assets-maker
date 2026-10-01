"""Lifecycle tests for MainApp normal shutdown and one-shot in-place restart.

Covers OpenSpec change "configure-project-and-ai-cache-storage" tasks 4.1/4.2:
- A normal exit must never trigger an in-place restart.
- A restart requested via the bridge runs strictly after the existing
  closed-event cleanup (asset server stop, agent server, managers).
- Repeated restart requests are idempotent (one-shot state, no errors).
- The os.execv restart command differs between frozen builds and source runs,
  inherits the current environment, and a failed execv is logged as a
  recoverable manual-start situation instead of raising.
"""

import os
import sys
from types import SimpleNamespace

import pytest


class _FakeEvent:
    """Minimal stand-in for a pywebview event subscription object."""

    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def fire(self):
        for handler in self.handlers:
            handler()


class _FakeWindow:
    """Fake pywebview window whose destroy() fires the closed event."""

    def __init__(self):
        self.events = SimpleNamespace(loaded=_FakeEvent(), closed=_FakeEvent(), closing=_FakeEvent())
        self.destroy_calls = 0

    def destroy(self):
        self.destroy_calls += 1
        self.events.closed.fire()


class _AppHarness:
    """Patches the GUI-facing collaborators of MainApp.run() with fakes.

    Records a shared timeline of cleanup and execv calls so tests can assert
    the ordering between closed-event cleanup and the in-place restart.
    """

    def __init__(self, monkeypatch):
        from backend import main as backend_main

        self.backend_main = backend_main
        self.window = _FakeWindow()
        self.timeline = []
        self.on_start = None

        monkeypatch.setattr(
            backend_main,
            "webview",
            SimpleNamespace(
                create_window=lambda *args, **kwargs: self.window,
                start=lambda **kwargs: self._start(),
            ),
        )
        # Bind instantly with a fixed port instead of opening a real socket.
        monkeypatch.setattr(
            backend_main,
            "start_assets_server",
            lambda *args, **kwargs: args[5].put(40123),
        )

        harness = self

        class FakeAgentControlServer:
            def __init__(self, window):
                self.window = window

            def start(self):
                pass

            def stop(self):
                harness.timeline.append(("cleanup", "agent_server.stop"))

        monkeypatch.setattr("backend.agent_control.server.AgentControlServer", FakeAgentControlServer)
        monkeypatch.setattr(os, "execv", lambda *args: harness.timeline.append(("execv",) + args))
        # run() ends the process with os._exit after cleanup; record it instead
        # of killing the pytest process.
        monkeypatch.setattr(os, "_exit", lambda code: harness.timeline.append(("exit", code)))

    def _start(self):
        if self.on_start is not None:
            self.on_start()

    def create_app(self):
        app = self.backend_main.MainApp()
        harness = self

        class FakeProcessAPI:
            def shutdown(self):
                harness.timeline.append(("cleanup", "process_api.shutdown"))

        # Avoid instantiating the heavy real ProcessAPI during shutdown.
        app.api._process_api_instance = FakeProcessAPI()
        return app


@pytest.fixture
def app_harness(monkeypatch, isolated_workspace):
    return _AppHarness(monkeypatch)


# ==================== Normal shutdown (no restart requested) ====================


def test_normal_exit_does_not_restart(app_harness):
    app = app_harness.create_app()
    app_harness.on_start = app_harness.window.destroy

    app.run()

    assert app.restart_requested is False
    assert not any(entry[0] == "execv" for entry in app_harness.timeline)
    # The regular closed-event cleanup still ran.
    assert ("cleanup", "agent_server.stop") in app_harness.timeline
    assert ("cleanup", "process_api.shutdown") in app_harness.timeline


# ==================== Restart requested via the bridge ====================


def test_restart_happens_after_closed_cleanup(app_harness):
    app = app_harness.create_app()
    # The frontend clicks "restart" while webview.start() is running.
    app_harness.on_start = app.api.request_app_restart

    app.run()

    assert app.restart_requested is True
    execv_entries = [entry for entry in app_harness.timeline if entry[0] == "execv"]
    assert len(execv_entries) == 1

    execv_index = app_harness.timeline.index(execv_entries[0])
    cleanup_indexes = [index for index, entry in enumerate(app_harness.timeline) if entry[0] == "cleanup"]
    assert cleanup_indexes, "closed-event cleanup did not run"
    assert max(cleanup_indexes) < execv_index


def test_repeated_restart_request_is_idempotent(app_harness):
    app = app_harness.create_app()
    app.window = app_harness.window

    first = app.api.request_app_restart()
    second = app.api.request_app_restart()

    assert first["success"] is True
    assert second["success"] is True
    assert app.restart_requested is True
    # One-shot state: the main window is destroyed exactly once.
    assert app_harness.window.destroy_calls == 1


def test_bridge_restart_request_only_sets_state_and_destroys_window(app_harness):
    app = app_harness.create_app()
    app.window = app_harness.window

    result = app.api.request_app_restart()

    assert result == {"success": True, "restart_requested": True}
    assert app.restart_requested is True
    assert app_harness.window.destroy_calls == 1
    # The bridge itself never execs; the restart happens in run() after cleanup.
    assert not any(entry[0] == "execv" for entry in app_harness.timeline)


def test_bridge_restart_request_without_window_only_sets_state(app_harness):
    app = app_harness.create_app()

    result = app.api.request_app_restart()

    assert result["success"] is True
    assert app.restart_requested is True


def test_api_without_restart_handler_reports_unavailable(isolated_workspace):
    from backend.main import API

    api = API()

    result = api.request_app_restart()

    assert result["success"] is False


# ==================== Close without restart (restart-required overlay) ====================


def test_close_app_destroys_window_without_restart_intent(app_harness):
    app = app_harness.create_app()
    app.window = app_harness.window

    result = app.api.close_app()

    assert result == {"success": True, "close_requested": True}
    assert app.restart_requested is False
    assert app_harness.window.destroy_calls == 1


def test_close_app_runs_cleanup_and_exits_without_restart(app_harness):
    app = app_harness.create_app()
    # The frontend clicks "close app" on the restart-required overlay.
    app_harness.on_start = app.api.close_app

    app.run()

    assert app.restart_requested is False
    assert not any(entry[0] == "execv" for entry in app_harness.timeline)
    assert ("cleanup", "agent_server.stop") in app_harness.timeline


def test_api_without_close_handler_reports_unavailable(isolated_workspace):
    from backend.main import API

    api = API()

    result = api.close_app()

    assert result["success"] is False


# ==================== Restart command selection (task 4.2) ====================


def test_frozen_build_restart_command_uses_packaged_executable(monkeypatch):
    from backend.main import build_restart_command

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/opt/GameAssetsMaker/game-assets-maker")
    monkeypatch.setattr(sys, "argv", ["/opt/GameAssetsMaker/game-assets-maker", "--safe-mode"])

    assert build_restart_command() == ["/opt/GameAssetsMaker/game-assets-maker", "--safe-mode"]


def test_source_mode_restart_command_uses_module_entrypoint(monkeypatch):
    from backend.main import build_restart_command

    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "executable", "/usr/bin/python3")
    monkeypatch.setattr(sys, "argv", ["-m", "--verbose"])

    assert build_restart_command() == ["/usr/bin/python3", "-m", "backend.main", "--verbose"]


def test_restart_in_place_execs_with_current_environment(app_harness, monkeypatch):
    app = app_harness.create_app()
    monkeypatch.setenv("GAM_RESTART_MARKER", "present")
    environ_before = dict(os.environ)

    app._restart_in_place()

    execv_entries = [entry for entry in app_harness.timeline if entry[0] == "execv"]
    assert len(execv_entries) == 1
    _, file, argv = execv_entries[0]
    assert argv[0] == file
    # os.execv inherits the current environment; nothing may be mutated for it.
    assert dict(os.environ) == environ_before


def test_execv_failure_logs_manual_start_hint_and_exits_normally(app_harness, monkeypatch, capsys):
    def failing_execv(*args):
        raise OSError("exec format error")

    monkeypatch.setattr(os, "execv", failing_execv)
    app = app_harness.create_app()
    app_harness.on_start = app.api.request_app_restart

    # Must not raise: run() ends normally so the process exits with code 0.
    app.run()

    output = capsys.readouterr().out
    assert "manually" in output
    assert app.restart_requested is True


def test_execv_failure_does_not_propagate_from_restart_in_place(app_harness, monkeypatch, capsys):
    monkeypatch.setattr(os, "execv", lambda *args: (_ for _ in ()).throw(OSError("permission denied")))
    app = app_harness.create_app()

    app._restart_in_place()

    output = capsys.readouterr().out
    assert "manually" in output
