#!/usr/bin/env python3
"""
Build script for Game Assets Maker.

Automatically rebuilds the frontend, then runs PyInstaller for the
desired target.

Usage:
    uv run python build.py           # build frontend + WebView UI (default)
"""

import argparse
import os
import shutil
import subprocess
import sys

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")


def run(cmd: list[str], cwd: str | None = None, check: bool = True):
    """Run a shell command and stream output."""
    print(f">>> {' '.join(cmd)}")
    kwargs = {}
    if sys.platform == "win32":
        kwargs["shell"] = True
    subprocess.run(cmd, cwd=cwd, check=check, **kwargs)


def build_frontend():
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

    run(["npm", "run", "build"], cwd=FRONTEND_DIR)
    print("Frontend build complete. Output: frontend/dist/\n")


def pyinstaller(spec_file: str):
    """Run PyInstaller for the given spec file."""
    print("=" * 60)
    print(f"Packaging {spec_file}...")
    print("=" * 60)

    if not shutil.which("pyinstaller"):
        # Fallback: uv run pyinstaller
        run(["uv", "run", "pyinstaller", "-y", spec_file])
    else:
        run(["pyinstaller", "-y", spec_file])

    print(f"Packaging complete: {spec_file}\n")


def main():
    parser = argparse.ArgumentParser(description="Build frontend and package the application.")
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
    args = parser.parse_args()

    if not args.skip_frontend:
        build_frontend()
    else:
        print("Skipping frontend rebuild as requested.\n")

    if args.target == "webview":
        pyinstaller("GameAssetsMaker.spec")

    print("=" * 60)
    print("All done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
