"""Ensure installer build failures cannot masquerade as a successful package."""

import subprocess
from pathlib import Path

import pytest

import build


def installer_inputs(tmp_path):
    bundle = tmp_path / "game-assets-maker"
    frontend = bundle / "_internal" / "frontend" / "dist"
    frontend.mkdir(parents=True)
    paths = [bundle / "game-assets-maker.exe", bundle / "gam-agent.exe", frontend / "index.html"]
    paths += [tmp_path / "ISCC.exe", tmp_path / "MicrosoftEdgeWebview2Setup.exe"]
    for path in paths:
        path.write_bytes(b"fixture")
    return paths


@pytest.mark.parametrize("missing_index", range(5))
def test_missing_installer_input_fails_before_compilation(tmp_path, monkeypatch, missing_index):
    paths = installer_inputs(tmp_path)
    paths[missing_index].unlink()

    def unexpected_compiler(*args, **kwargs):
        pytest.fail("Compiler must not run with incomplete inputs")

    monkeypatch.setattr(build.subprocess, "run", unexpected_compiler)
    with pytest.raises(FileNotFoundError):
        build.create_windows_installer(tmp_path, paths[-2], paths[-1])


def test_existing_installer_is_preserved(tmp_path, monkeypatch):
    paths = installer_inputs(tmp_path)
    monkeypatch.setattr(build, "app_version", lambda: "1.2.3")
    output = tmp_path / "GameAssetsMaker-1.2.3-windows-x64-Setup.exe"
    output.write_bytes(b"previous installer")
    with pytest.raises(FileExistsError):
        build.create_windows_installer(tmp_path, paths[-2], paths[-1])
    assert output.read_bytes() == b"previous installer"


def test_compiler_failure_does_not_create_checksum(tmp_path, monkeypatch):
    paths = installer_inputs(tmp_path)
    monkeypatch.setattr(build, "app_version", lambda: "1.2.3")

    def failed_compiler(command, **kwargs):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(build.subprocess, "run", failed_compiler)
    with pytest.raises(subprocess.CalledProcessError):
        build.create_windows_installer(tmp_path, paths[-2], paths[-1])
    assert not list(Path(tmp_path).glob("*.sha256"))
