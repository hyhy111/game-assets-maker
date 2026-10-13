"""Stable CLI discovery, invocation and installed-entrypoint data isolation."""

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from src.utils.agent_launcher import install_agent_launcher, register_packaged_agent_launcher


def test_windows_launcher_forwards_arguments_output_exit_code_and_environment(tmp_path, monkeypatch):
    if sys.platform != "win32":
        pytest.skip("Requires Windows command and PowerShell runtimes")
    root = tmp_path / "用户's data & space"
    monkeypatch.setenv("GAM_DATA_ROOT", str(root))
    monkeypatch.setenv("GAM_CONFIG", str(root / "custom-config.json"))
    launcher = install_agent_launcher(Path(sys.executable))
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import json, os, sys\n"
        "print(json.dumps({'args': sys.argv[1:], 'root': os.environ['GAM_DATA_ROOT'], "
        "'config': os.environ['GAM_CONFIG']}))\n"
        "print('probe stderr', file=sys.stderr)\n"
        "raise SystemExit(7)\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(launcher), str(probe), "doctor", "--request-json", "含空格的 patch.json"],
        cwd=tmp_path,
        shell=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 7, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {
        "args": ["doctor", "--request-json", "含空格的 patch.json"],
        "root": str(root),
        "config": str(root / "custom-config.json"),
    }
    assert "probe stderr" in result.stderr


@pytest.mark.skipif(os.name != "posix", reason="Requires a POSIX shell")
def test_posix_launcher_forwards_arguments_output_and_exit_code(tmp_path, monkeypatch):
    root = tmp_path / "user data"
    monkeypatch.setenv("GAM_DATA_ROOT", str(root))
    cli = tmp_path / "Game Assets Maker's.app" / "Contents" / "MacOS" / "gam-agent"
    cli.parent.mkdir(parents=True)
    cli.write_text(
        f"#!{sys.executable}\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\nsys.exit(7)\n",
        encoding="utf-8",
    )
    cli.chmod(0o700)
    launcher = install_agent_launcher(cli)
    result = subprocess.run(
        [str(launcher), "doctor", "--request-json", "含空格的 patch.json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 7, result.stderr
    assert json.loads(result.stdout) == ["doctor", "--request-json", "含空格的 patch.json"]


def test_mac_launcher_quotes_bundle_paths_and_preserves_arguments(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path / "user-data"))
    cli = tmp_path / "Game Assets Maker's.app" / "Contents" / "MacOS" / "gam-agent"
    cli.parent.mkdir(parents=True)
    cli.touch()
    launcher = install_agent_launcher(cli)
    command = launcher.read_text(encoding="utf-8").splitlines()[-1]
    assert shlex.split(command) == ["exec", str(cli.resolve()), "$@"]
    if os.name == "posix":
        assert launcher.stat().st_mode & 0o100


@pytest.mark.parametrize("platform", ["win32", "darwin"])
@pytest.mark.parametrize("entrypoint", ["gui", "cli"])
def test_installed_entrypoints_register_launcher_outside_bundle(tmp_path, platform, entrypoint, repo_root):
    home = tmp_path / "user-home"
    bundle = tmp_path / "install" / "Game Assets Maker.app" / "Contents" / "MacOS"
    bundle.mkdir(parents=True)
    suffix = ".exe" if platform == "win32" else ""
    cli = bundle / f"gam-agent{suffix}"
    cli.touch()
    (bundle / "pyproject.toml").write_text('[project]\nversion = "1.2.3"\n', encoding="utf-8")
    original_bundle_files = sorted(path.name for path in bundle.iterdir())
    # Importing application modules can capture data paths; isolate simulated bundles.
    code = """
import sys
from pathlib import Path
from backend import main as gui
from src.cli import agent

platform, bundle, home, entrypoint = sys.argv[1:]
sys.platform = platform
sys.frozen = True
sys._MEIPASS = bundle
sys.executable = str(Path(bundle) / ('game-assets-maker.exe' if platform == 'win32' else 'game-assets-maker'))
Path.home = classmethod(lambda cls: Path(home))
if entrypoint == 'gui':
    class FakeApp:
        def run(self):
            print('GUI started')
    gui.MainApp = FakeApp
    gui.installed_main()
else:
    agent.installed_main(['--version'])
"""
    env = {**os.environ, "PYTHONPATH": str(repo_root), "HOME": str(home), "USERPROFILE": str(home)}
    for name in ("GAM_DATA_MODE", "GAM_DATA_ROOT", "GAM_CONFIG"):
        env.pop(name, None)
    result = subprocess.run(
        [sys.executable, "-c", code, platform, str(bundle), str(home), entrypoint],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ("GUI started" if entrypoint == "gui" else "1.2.3")
    launcher = home / ".gam" / ("gam-agent.cmd" if platform == "win32" else "gam-agent")
    assert launcher.is_file()
    assert sorted(path.name for path in bundle.iterdir()) == original_bundle_files
    assert not (tmp_path / launcher.name).exists()


def test_registration_honors_data_override_and_refreshes_after_app_move(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    root = tmp_path / "custom-data"
    monkeypatch.setenv("GAM_DATA_ROOT", str(root))
    suffix = ".exe" if sys.platform == "win32" else ""
    for name in ("original installation", "moved installation"):
        bundle = tmp_path / name
        bundle.mkdir()
        cli = bundle / f"gam-agent{suffix}"
        cli.touch()
        monkeypatch.setattr(sys, "executable", str(bundle / f"game-assets-maker{suffix}"))
        launcher = register_packaged_agent_launcher()
        assert launcher is not None and launcher.parent == root
        target_file = root / "gam-agent.ps1" if sys.platform == "win32" else launcher
        assert str(cli.resolve()) in target_file.read_text(encoding="utf-8-sig")
        modified = target_file.stat().st_mtime_ns
        register_packaged_agent_launcher()
        assert target_file.stat().st_mtime_ns == modified


@pytest.mark.parametrize("frozen,mode", [(False, "dev"), (False, "installed"), (True, "dev")])
def test_source_and_explicit_dev_runs_do_not_publish_installed_launcher(tmp_path, monkeypatch, frozen, mode):
    monkeypatch.setattr(sys, "frozen", frozen, raising=False)
    monkeypatch.setenv("GAM_DATA_MODE", mode)
    root = tmp_path / "user-data"
    monkeypatch.setenv("GAM_DATA_ROOT", str(root))
    assert register_packaged_agent_launcher() is None
    assert not root.exists()


def test_unmanaged_launcher_is_preserved_without_blocking_startup(tmp_path, monkeypatch, caplog):
    root = tmp_path / "user-data"
    root.mkdir()
    unmanaged = root / ("gam-agent.ps1" if sys.platform == "win32" else "gam-agent")
    unmanaged.write_text("user custom launcher", encoding="utf-8")
    suffix = ".exe" if sys.platform == "win32" else ""
    cli = tmp_path / f"gam-agent{suffix}"
    cli.touch()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / f"game-assets-maker{suffix}"))
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    monkeypatch.setenv("GAM_DATA_ROOT", str(root))
    assert register_packaged_agent_launcher() is None
    assert unmanaged.read_text(encoding="utf-8") == "user custom launcher"
    assert "Cannot register" in caplog.text
