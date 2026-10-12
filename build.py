#!/usr/bin/env python3
"""
Build script for Game Assets Maker.

Automatically rebuilds the frontend, packages the GUI and Agent CLI,
verifies the packaged CLI from an isolated working directory, and creates a DMG on macOS.

Usage:
    uv run python build.py           # build frontend + WebView UI (default)
"""

import argparse
import hashlib
import json
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from src.utils.app_version import app_version

REPO_ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = str(REPO_ROOT / "frontend")


def sync_frontend_version(frontend_dir: Path = Path(FRONTEND_DIR)) -> None:
    """Synchronize only the application versions; preserve dependency versions."""
    for filename in ("package.json", "package-lock.json"):
        path = frontend_dir / filename
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["version"] = app_version()
        if filename == "package-lock.json":
            payload["packages"][""]["version"] = app_version()
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_channel_code(value: str) -> str:
    """Preserve the supplied code exactly; keep wire and database limits aligned."""
    if len(value.encode("utf-16-le")) // 2 > 64 or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("Channel code must contain at most 64 characters and no control characters")
    return value


def verify_frontend_channel(channel_code: str, frontend_dir: Path = Path(FRONTEND_DIR)) -> None:
    manifest = frontend_dir / "dist" / "channel-code.json"
    if not manifest.is_file() or json.loads(manifest.read_text(encoding="utf-8")).get("channelCode") != channel_code:
        raise ValueError("Frontend channel code does not match --channel-code; rebuild without --skip-frontend")


def run(cmd: list[str], cwd: str | None = None, check: bool = True, env: dict[str, str] | None = None):
    """Run a shell command and stream output."""
    print(f">>> {' '.join(cmd)}")
    kwargs = {}
    if sys.platform == "win32":
        kwargs["shell"] = True
    subprocess.run(cmd, cwd=cwd, check=check, env=env, **kwargs)


def build_frontend(channel_code: str = ""):
    """Build Vue3 frontend to frontend/dist/."""
    print("=" * 60)
    print("Building frontend...")
    print("=" * 60)

    if not os.path.isdir(FRONTEND_DIR):
        print(f"Error: frontend directory not found: {FRONTEND_DIR}")
        sys.exit(1)

    # Install dependencies if node_modules is missing
    if not os.path.isdir(os.path.join(FRONTEND_DIR, "node_modules")):
        print("node_modules not found, running npm install...")
        run(["npm", "install"], cwd=FRONTEND_DIR)

    run(["npm", "run", "build"], cwd=FRONTEND_DIR, env={**os.environ, "GAM_BUILD_CHANNEL_CODE": channel_code})
    print("Frontend build complete. Output: frontend/dist/\n")


def pyinstaller(spec_file: str, dist_dir: Path, work_dir: Path):
    """Run PyInstaller for the given spec file."""
    print("=" * 60)
    print(f"Packaging {spec_file}...")
    print("=" * 60)

    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "-y",
            spec_file,
            "--distpath",
            str(dist_dir),
            "--workpath",
            str(work_dir),
        ],
        cwd=str(REPO_ROOT),
    )

    print(f"Packaging complete: {spec_file}\n")


def verify_packaged_cli(dist_dir: Path = Path("dist")) -> None:
    """Run the bundled CLI without a checkout or external Python runtime."""
    if sys.platform == "darwin":
        bundle_dir = dist_dir / "Game Assets Maker.app" / "Contents" / "MacOS"
    else:
        bundle_dir = dist_dir / "game-assets-maker"
    suffix = ".exe" if sys.platform == "win32" else ""
    cli_path = (bundle_dir / f"gam-agent{suffix}").resolve()
    gui_path = bundle_dir / f"game-assets-maker{suffix}"
    if not cli_path.is_file() or not gui_path.is_file():
        raise RuntimeError(f"Packaged GUI or Agent CLI is missing from {bundle_dir}")

    with tempfile.TemporaryDirectory(prefix="gam-package-check-") as directory:
        workspace = Path(directory).resolve()
        user_data = workspace / "user-data"
        env = {
            **os.environ,
            "GAM_DATA_MODE": "installed",
            "GAM_DATA_ROOT": str(user_data),
            "GAM_CONFIG": str(user_data / "config.json"),
        }
        version_result = subprocess.run(
            [str(cli_path), "--version"],
            cwd=workspace,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        if version_result.stdout.strip() != app_version():
            raise RuntimeError("Packaged Agent CLI version does not match project metadata")
        result = subprocess.run(
            [str(cli_path), "doctor"],
            cwd=workspace,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        payload = json.loads(result.stdout)
        if not payload.get("ok") or Path(payload["data"]["project_root"]).resolve() != user_data:
            raise RuntimeError("Packaged Agent CLI did not use the isolated user-data root")
        if not payload["data"]["checks"]["frontend_dist"]:
            raise RuntimeError("Packaged frontend resources are missing")
    print(f"Packaged Agent CLI verified: {cli_path}")


def create_macos_dmg(dist_dir: Path) -> Path:
    """Create a compressed drag-to-Applications image and its checksum."""
    bundle = dist_dir / "Game Assets Maker.app"
    with (bundle / "Contents" / "Info.plist").open("rb") as stream:
        info = plistlib.load(stream)
    for key in ("CFBundleShortVersionString", "CFBundleVersion"):
        if info.get(key) != app_version():
            raise RuntimeError(f"Bundle {key} does not match project metadata")
    architecture = {"aarch64": "arm64", "x86_64": "x64"}.get(platform.machine(), platform.machine())
    output = dist_dir / f"GameAssetsMaker-{app_version()}-macos-{architecture}.dmg"
    with tempfile.TemporaryDirectory(prefix="gam-dmg-", dir=dist_dir) as directory:
        workspace = Path(directory)
        staging = workspace / "contents"
        staging.mkdir()
        shutil.copytree(bundle, staging / bundle.name, symlinks=True)
        (staging / "Applications").symlink_to("/Applications", target_is_directory=True)
        (staging / "安装说明 - Installation.txt").write_text(
            "将 Game Assets Maker.app 拖入 Applications。更新前请退出旧版本，再替换应用。\n"
            "用户数据默认保存在 ~/.gam，模型需要在应用内另行下载。\n"
            "本测试包没有 Developer ID 签名或 Apple 公证。若系统阻止打开，请先尝试打开一次，\n"
            "再到 系统设置 → 隐私与安全性 → 仍要打开。\n\n"
            "Drag Game Assets Maker.app into Applications. Quit the old version before replacing it.\n"
            "User data defaults to ~/.gam. Download model weights in the app.\n"
            "This test build has no Developer ID signature or Apple notarization. If blocked, try opening\n"
            "the app, then use System Settings > Privacy & Security > Open Anyway.\n",
            encoding="utf-8",
        )
        temporary_output = workspace / "package.dmg"
        run(
            [
                "hdiutil",
                "create",
                "-volname",
                "Game Assets Maker",
                "-srcfolder",
                str(staging),
                "-format",
                "UDZO",
                "-ov",
                str(temporary_output),
            ]
        )
        run(["hdiutil", "verify", str(temporary_output)])
        temporary_output.replace(output)
    with output.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    output.with_suffix(".dmg.sha256").write_text(f"{checksum}  {output.name}\n", encoding="utf-8")
    print(f"DMG created: {output}")
    return output


def main():
    parser = argparse.ArgumentParser(description="Build and verify the desktop application and Agent CLI.")
    parser.add_argument(
        "--target",
        choices=["webview"],
        default="webview",
        help="Which UI to package (default: webview)",
    )
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="Skip frontend rebuild and package directly",
    )
    parser.add_argument("--dist-dir", type=Path, default=REPO_ROOT / "dist", help="Package output directory")
    parser.add_argument("--work-dir", type=Path, default=REPO_ROOT / "build", help="PyInstaller work directory")
    parser.add_argument("--skip-dmg", action="store_true", help="Build only the app bundle on macOS")
    parser.add_argument("--channel-code", default="", help="Embed this channel code in the package (default: empty)")
    args = parser.parse_args()
    try:
        channel_code = validate_channel_code(args.channel_code)
    except ValueError as error:
        parser.error(str(error))
    dist_dir = args.dist_dir.resolve()
    work_dir = args.work_dir.resolve()
    sync_frontend_version()

    if not args.skip_frontend:
        build_frontend(channel_code)
    else:
        print("Skipping frontend rebuild as requested.\n")

    verify_frontend_channel(channel_code)

    if args.target == "webview":
        pyinstaller("GameAssetsMaker.spec", dist_dir, work_dir)
        verify_packaged_cli(dist_dir)
        if sys.platform == "darwin" and not args.skip_dmg:
            create_macos_dmg(dist_dir)

    print("=" * 60)
    print("All done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
