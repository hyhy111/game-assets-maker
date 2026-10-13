"""Publish a stable per-user entry without moving the bundled CLI runtime."""

import logging
import os
import shlex
import sys
import tempfile
from pathlib import Path

from src.utils.data_paths import INSTALLED_MODE, data_mode, data_root

_MARKER = "Managed by Game Assets Maker: gam-agent launcher"


def _write_launcher(path: Path, content: bytes, *, executable: bool = False) -> None:
    if path.exists():
        previous = path.read_bytes()
        if _MARKER.encode() not in previous:
            raise FileExistsError(f"Refusing to overwrite an unmanaged CLI launcher: {path}")
        if previous == content and (not executable or path.stat().st_mode & 0o100):
            return
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
        if executable:
            temporary.chmod(0o700)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def install_agent_launcher(cli_path: Path) -> Path:
    """Refresh the launcher in the effective data root, retaining package dependencies."""
    cli_path = cli_path.resolve(strict=True)
    if not cli_path.is_file():
        raise IsADirectoryError(cli_path)
    root = data_root()
    root.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        # Keep the batch file ASCII; PowerShell's BOM supports Unicode install paths.
        target = str(cli_path).replace("'", "''")
        script = f"# {_MARKER}\r\n$ErrorActionPreference = 'Stop'\r\n& '{target}' @args\r\nexit $LASTEXITCODE\r\n"
        _write_launcher(root / "gam-agent.ps1", script.encode("utf-8-sig"))
        launcher = root / "gam-agent.cmd"
        command = (
            f"@rem {_MARKER}\r\n@echo off\r\nsetlocal DisableDelayedExpansion\r\n"
            '"%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" '
            '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0gam-agent.ps1" %*\r\n'
            "exit /b %errorlevel%\r\n"
        )
        _write_launcher(launcher, command.encode("ascii"))
    else:
        launcher = root / "gam-agent"
        script = f'#!/bin/sh\n# {_MARKER}\nexec {shlex.quote(str(cli_path))} "$@"\n'
        _write_launcher(launcher, script.encode("utf-8"), executable=True)
    return launcher


def register_packaged_agent_launcher() -> Path | None:
    """Register only installed bundles; a launcher failure must not prevent startup."""
    if not getattr(sys, "frozen", False) or data_mode() != INSTALLED_MODE:
        return None
    suffix = ".exe" if sys.platform == "win32" else ""
    try:
        cli_path = Path(sys.executable).resolve().with_name(f"gam-agent{suffix}")
        return install_agent_launcher(cli_path)
    except OSError as error:
        logging.getLogger(__name__).warning("Cannot register the gam-agent launcher: %s", error)
        return None
