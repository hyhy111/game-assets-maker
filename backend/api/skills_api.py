"""Manage only the global GAM Skills installations recorded by the Skills CLI."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

from src.utils.diagnostics import logged_urlopen

REPOSITORY = "hyhy111/gam-skills"
SKILLS = ("gam-cli", "gam-export", "gam-guide", "gam-pic-prompt", "gam-video-prompt", "gam-workflow")
AGENTS = ("codex", "claude-code", "cursor", "opencode", "gemini-cli", "github-copilot", "windsurf")
_SHA = re.compile(r"[0-9a-f]{40}")


class SkillsAPI:
    _install_lock = threading.Lock()

    def __init__(self, home: Path | None = None):
        self.home = home or Path.home()

    def _paths(self, agent: str) -> tuple[Path, Path, Path]:
        if agent not in AGENTS:
            raise ValueError("Unsupported agent")
        canonical = self.home / ".agents" / "skills"
        config = Path(os.environ.get("XDG_CONFIG_HOME") or self.home / ".config")
        targets = {
            "codex": canonical,
            "claude-code": Path(os.environ.get("CLAUDE_CONFIG_DIR") or self.home / ".claude") / "skills",
            "cursor": self.home / ".cursor" / "skills",
            "opencode": config / "opencode" / "skills",
            "gemini-cli": self.home / ".gemini" / "skills",
            "github-copilot": self.home / ".copilot" / "skills",
            "windsurf": self.home / ".codeium" / "windsurf" / "skills",
        }
        state = os.environ.get("XDG_STATE_HOME")
        lock = Path(state) / "skills" / ".skill-lock.json" if state else self.home / ".agents" / ".skill-lock.json"
        return canonical, targets[agent], lock

    @staticmethod
    def _runtime() -> tuple[list[str], dict[str, str]]:
        env = dict(os.environ)
        extra = (
            ["/opt/homebrew/bin", "/usr/local/bin"]
            if sys.platform != "win32"
            else [
                str(Path(env.get("ProgramFiles", r"C:\Program Files")) / "nodejs"),
                str(Path(env.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / "npm"),
            ]
        )
        env["PATH"] = os.pathsep.join([env.get("PATH") or os.defpath, *extra])
        npx = shutil.which("npx", path=env["PATH"])
        node = shutil.which("node", path=env["PATH"])
        if not npx or not node:
            return [], env
        if sys.platform == "win32":
            # Run npm's JS entry directly instead of shell-expanding a .cmd file.
            entry = Path(npx).parent / "node_modules" / "npm" / "bin" / "npx-cli.js"
            return ([node, str(entry)] if entry.is_file() else []), env
        return [npx], env

    @staticmethod
    def _same_copy(left: Path, right: Path) -> bool:
        def digest(root: Path):
            result = {}
            total = 0
            for path in root.rglob("*"):
                if path.is_symlink():
                    return None
                if path.is_file():
                    total += path.stat().st_size
                    if len(result) >= 500 or total > 8 * 1024 * 1024:
                        return None
                    result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).digest()
            return result

        first, second = digest(left), digest(right)
        return first is not None and first == second

    def _inspect(self, agent: str) -> tuple[dict[str, Any], dict[str, Any]]:
        canonical, target, lock_path = self._paths(agent)
        state = {
            "status": "not_installed",
            "source": "none",
            "installed_count": 0,
            "total_count": len(SKILLS),
            "outdated": [],
            "error": "",
            "can_check": False,
            "can_install": True,
            "node_available": bool(self._runtime()[0]),
        }
        lock = {}
        if lock_path.exists():
            if lock_path.stat().st_size > 2 * 1024 * 1024:
                raise ValueError("Invalid lock file")
            document = json.loads(lock_path.read_text(encoding="utf-8"))
            if (
                not isinstance(document, dict)
                or document.get("version") != 3
                or not isinstance(document.get("skills"), dict)
            ):
                raise ValueError("Invalid lock file")
            lock = document["skills"]
        roots = {canonical, target}
        if agent == "codex":
            roots.add(Path(os.environ.get("CODEX_HOME") or self.home / ".codex") / "skills")
        if any((root.is_symlink() and root.resolve() != canonical) or (root / ".git").exists() for root in roots):
            return {**state, "status": "unmanaged", "source": "other", "can_install": False}, {}
        entries = {}
        for name in SKILLS:
            entry = lock.get(name)
            owned = (
                isinstance(entry, dict) and entry.get("source") == REPOSITORY and entry.get("sourceType") == "github"
            )
            source = canonical / name
            source_owned = (
                owned and not source.is_symlink() and not (source / ".git").exists() and (source / "SKILL.md").is_file()
            )
            for root in roots:
                path = root / name
                if not (path.exists() or path.is_symlink()):
                    continue
                managed = source_owned and (path == source or (path.is_symlink() and path.resolve() == source))
                if (
                    not managed
                    and source_owned
                    and entry.get("installMode") == "copy"
                    and path.is_dir()
                    and not path.is_symlink()
                ):
                    managed = self._same_copy(path, source)
                if not managed:
                    return {**state, "status": "unmanaged", "source": "other", "can_install": False}, {}
            if source_owned and (target / name / "SKILL.md").is_file():
                entries[name] = entry
        if entries:
            tracked = all(
                _SHA.fullmatch(str(entry.get("skillFolderHash", ""))) and entry.get("skillPath")
                for entry in entries.values()
            )
            state.update(status="installed", source="npx", installed_count=len(entries), can_check=bool(tracked))
            if not tracked:
                state["error"] = "VERSION_UNTRACKED"
        return state, entries

    def status(
        self, agent: str = "codex", check_updates: bool = False, *, _trees: dict | None = None
    ) -> dict[str, Any]:
        try:
            state, entries = self._inspect(agent)
        except (OSError, ValueError, TypeError, RuntimeError):
            return {
                "status": "error",
                "source": "none",
                "installed_count": 0,
                "total_count": len(SKILLS),
                "outdated": [],
                "error": "DETECTION_FAILED",
                "can_check": False,
                "can_install": False,
                "node_available": bool(self._runtime()[0]),
            }
        if not check_updates or not state["can_check"]:
            return state
        try:
            trees = _trees if _trees is not None else {}
            for name, entry in entries.items():
                ref = entry.get("ref") or "HEAD"
                if not isinstance(ref, str):
                    raise ValueError("Invalid ref")
                if ref not in trees:
                    # Reuse both successful and failed fetches across a startup scan.
                    trees[ref] = None
                    url = f"https://api.github.com/repos/{REPOSITORY}/git/trees/{quote(ref, safe='')}?recursive=1"
                    request = urllib.request.Request(
                        url, headers={"Accept": "application/vnd.github+json", "User-Agent": "Game-Assets-Maker"}
                    )
                    with logged_urlopen(request, timeout=8) as response:
                        raw = response.read(2 * 1024 * 1024 + 1)
                    if len(raw) > 2 * 1024 * 1024:
                        raise ValueError("Response too large")
                    tree = json.loads(raw)
                    if not isinstance(tree, dict) or tree.get("truncated") or not isinstance(tree.get("tree"), list):
                        raise ValueError("Invalid tree")
                    trees[ref] = {item["path"]: item["sha"] for item in tree["tree"] if item.get("type") == "tree"}
                folder = entry["skillPath"].replace("\\", "/").rstrip("/")
                if folder.lower().endswith("/skill.md"):
                    folder = folder[:-9]
                if not folder or PurePosixPath(folder).is_absolute() or ".." in PurePosixPath(folder).parts:
                    raise ValueError("Invalid skill path")
                latest = trees[ref].get(folder)
                if not latest or not _SHA.fullmatch(latest):
                    raise ValueError("Skill missing upstream")
                if latest != entry["skillFolderHash"]:
                    state["outdated"].append(name)
            state["status"] = "update_available" if state["outdated"] else "up_to_date"
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            state.update(status="error", error="CHECK_FAILED", outdated=[])
        return state

    def updates(self) -> dict[str, dict[str, Any]]:
        """Check recognized global installs without scanning unrelated Skills."""
        trees = {}
        return {agent: self.status(agent, True, _trees=trees) for agent in AGENTS}

    def install(self, agent: str = "codex") -> dict[str, Any]:
        if not self._install_lock.acquire(blocking=False):
            return {"success": False, "state": {**self.status(agent), "error": "BUSY"}}
        try:
            state, entries = self._inspect(agent)
            command, env = self._runtime()
            if not state["can_install"]:
                return {"success": False, "state": state}
            if not command:
                return {"success": False, "state": {**state, "error": "NODE_REQUIRED"}}
            refs = {entry.get("ref") or "" for entry in entries.values()}
            if len(refs) > 1:
                return {"success": False, "state": {**state, "error": "MIXED_REFS"}}
            ref = next(iter(refs), "")
            source = f"https://github.com/{REPOSITORY}/tree/{quote(ref, safe='')}" if ref else REPOSITORY
            command += ["--yes", "skills@latest", "add", source, "-g", "-a", agent, "--skill", *SKILLS, "-y"]
            env.update(CI="1", NO_COLOR="1", DISABLE_TELEMETRY="1", DO_NOT_TRACK="1", GIT_TERMINAL_PROMPT="0")
            with tempfile.TemporaryDirectory(prefix="gam-skills-") as cwd, tempfile.TemporaryFile() as output:
                result = subprocess.run(
                    command,
                    cwd=cwd,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    timeout=180,
                    check=False,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
            current = self.status(agent)
            success = (
                result.returncode == 0 and current["source"] == "npx" and current["installed_count"] == len(SKILLS)
            )
            if not success:
                current["error"] = "INSTALL_FAILED"
            return {"success": success, "state": current}
        except subprocess.TimeoutExpired:
            return {"success": False, "state": {**self.status(agent), "error": "INSTALL_TIMEOUT"}}
        except (OSError, ValueError, TypeError, RuntimeError):
            return {"success": False, "state": {**self.status(agent), "error": "INSTALL_FAILED"}}
        finally:
            self._install_lock.release()
