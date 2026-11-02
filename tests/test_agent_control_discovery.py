"""Real-socket coverage for control-port conflicts and CLI discovery."""

import errno
import json
import socket
from types import SimpleNamespace

import pytest

from backend.agent_control import server as server_module
from backend.agent_control.server import AgentControlServer
from src.agent_tools.ui_client import AgentUIClient


def test_default_server_survives_occupied_port_and_cli_discovers_it(tmp_path, monkeypatch):
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        monkeypatch.setattr(server_module, "DEFAULT_CONTROL_PORT", occupied.getsockname()[1], raising=False)
        server = AgentControlServer(None)
        client = AgentUIClient()
        try:
            server.start()
            assert server.port != occupied.getsockname()[1]
            assert client.status() == {
                "connected": True,
                "payload": {"ok": True, "service": "gam-agent-control"},
            }
            assert AgentUIClient(port=server.port).status()["connected"] is True
            endpoint = tmp_path / "cache" / "agent-control.json"
            assert json.loads(endpoint.read_text())["port"] == server.port
        finally:
            server.stop()
        assert not endpoint.exists()


def test_explicit_occupied_port_still_raises():
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        server = AgentControlServer(None, port=occupied.getsockname()[1])
        with pytest.raises(OSError) as error:
            server.start()
        assert error.value.errno == errno.EADDRINUSE or getattr(error.value, "winerror", None) in {10013, 10048}
        server.stop()


def test_client_refreshes_discovery_and_old_server_keeps_new_record(tmp_path, monkeypatch):
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(server_module, "DEFAULT_CONTROL_PORT", 0, raising=False)
    first = AgentControlServer(None)
    second = AgentControlServer(None)
    client = AgentUIClient()
    try:
        first.start()
        assert client.status()["connected"] is True
        second.start()
        first.stop()
        assert client.status()["connected"] is True
        endpoint = tmp_path / "cache" / "agent-control.json"
        assert json.loads(endpoint.read_text())["port"] == second.port
    finally:
        first.stop()
        second.stop()
    assert not endpoint.exists()


@pytest.mark.parametrize("record", ["{", "[]", "{}", '{"port": true}', '{"port": 0}', '{"port": 65536}'])
def test_invalid_discovery_uses_legacy_port(tmp_path, monkeypatch, record):
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    endpoint = tmp_path / "cache" / "agent-control.json"
    endpoint.parent.mkdir()
    endpoint.write_text(record)
    assert AgentUIClient().base_url == "http://127.0.0.1:8765"
    assert AgentUIClient(port=1234).base_url == "http://127.0.0.1:1234"


def test_default_server_does_not_hide_other_bind_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))

    def denied(*args):
        raise OSError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(server_module, "ReusableTCPServer", denied)
    with pytest.raises(OSError) as error:
        AgentControlServer(None).start()
    assert error.value.errno == errno.EACCES


def test_windows_exclusive_port_error_falls_back_only_for_automatic_port(tmp_path, monkeypatch):
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(server_module, "sys", SimpleNamespace(platform="win32"))
    calls = []
    bound = SimpleNamespace(server_address=("127.0.0.1", 12345), serve_forever=lambda: None)
    error = PermissionError(errno.EACCES, "synthetic exclusive port")
    error.winerror = 10013

    def bind(address, handler):
        calls.append(address)
        if address[1] != 0:
            raise error
        return bound

    monkeypatch.setattr(server_module, "ReusableTCPServer", bind)
    server = AgentControlServer(None)
    server.start()
    server.thread.join()
    assert calls == [("127.0.0.1", server_module.DEFAULT_CONTROL_PORT), ("127.0.0.1", 0)]
    assert server.port == 12345
    with pytest.raises(PermissionError) as caught:
        AgentControlServer(None, port=8765).start()
    assert caught.value is error


def test_discovery_write_failure_closes_server(tmp_path, monkeypatch):
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(server_module, "DEFAULT_CONTROL_PORT", 0)
    endpoint_parent = tmp_path / "cache"
    endpoint_parent.write_text("not a directory")
    server = AgentControlServer(None)
    with pytest.raises(OSError):
        server.start()
    assert server.httpd is None
    assert server.thread is None
