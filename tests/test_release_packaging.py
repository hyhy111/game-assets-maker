"""Version and local macOS distribution contracts."""

import json
import plistlib
import subprocess
import sys
from pathlib import Path

import pytest

import build
from src.utils.app_version import app_version


def test_frozen_version_uses_bundle_metadata_not_user_data(tmp_path, monkeypatch):
    bundled = tmp_path / "bundle"
    bundled.mkdir()
    (bundled / "pyproject.toml").write_text('[project]\nversion = "1.2.3"\n')
    user_data = tmp_path / "user-data"
    user_data.mkdir()
    (user_data / "pyproject.toml").write_text('[project]\nversion = "9.9.9"\n')
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundled), raising=False)
    monkeypatch.setenv("GAM_DATA_ROOT", str(user_data))
    monkeypatch.chdir(user_data)
    assert app_version() == "1.2.3"
    (bundled / "pyproject.toml").unlink()
    with pytest.raises(FileNotFoundError):
        app_version()


def test_frontend_sync_preserves_dependency_versions(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "app_version", lambda: "1.2.3")
    package = {"version": "2.0.0", "dependencies": {"example": "2.0.0"}}
    lock = {"version": "2.0.0", "packages": {"": package, "node_modules/example": {"version": "2.0.0"}}}
    (tmp_path / "package.json").write_text(json.dumps(package))
    (tmp_path / "package-lock.json").write_text(json.dumps(lock))
    build.sync_frontend_version(tmp_path)
    assert json.loads((tmp_path / "package.json").read_text()) == {
        "version": "1.2.3",
        "dependencies": {"example": "2.0.0"},
    }
    synced = json.loads((tmp_path / "package-lock.json").read_text())
    assert synced["version"] == synced["packages"][""]["version"] == "1.2.3"
    assert synced["packages"]["node_modules/example"]["version"] == "2.0.0"


def test_dmg_verification_failure_preserves_previous_package(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "app_version", lambda: "1.2.3")
    monkeypatch.setattr(build.platform, "machine", lambda: "arm64")
    contents = tmp_path / "Game Assets Maker.app" / "Contents"
    contents.mkdir(parents=True)
    (contents / "Info.plist").write_bytes(
        plistlib.dumps({"CFBundleVersion": "1.2.3", "CFBundleShortVersionString": "1.2.3"})
    )
    (contents / "original").write_text("shared library")
    (contents / "linked").symlink_to("original")
    output = tmp_path / "GameAssetsMaker-1.2.3-macos-arm64.dmg"
    output.write_bytes(b"previous package")

    def fake_run(cmd):
        if cmd[1] == "verify":
            raise subprocess.CalledProcessError(1, cmd)
        staging = Path(cmd[cmd.index("-srcfolder") + 1])
        assert (staging / "Applications").readlink() == Path("/Applications")
        assert (staging / "Game Assets Maker.app" / "Contents" / "linked").is_symlink()
        assert (staging / "安装说明 - Installation.txt").is_file()
        Path(cmd[-1]).write_bytes(b"new package")

    monkeypatch.setattr(build, "run", fake_run)
    with pytest.raises(subprocess.CalledProcessError):
        build.create_macos_dmg(tmp_path)
    assert output.read_bytes() == b"previous package"
    assert not output.with_suffix(".dmg.sha256").exists()
