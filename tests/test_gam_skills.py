"""Installer provenance, scoped update checks and safe global installation."""

import hashlib
import io
import json
import shutil
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.api import skills_api
from backend.api.skills_api import SKILLS, SkillsAPI

runtime = SkillsAPI._runtime


@pytest.fixture
def service(tmp_path, monkeypatch):
    for name in ("XDG_STATE_HOME", "XDG_CONFIG_HOME", "CODEX_HOME", "CLAUDE_CONFIG_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(SkillsAPI, "_runtime", staticmethod(lambda: (["/fake/npx"], {"PATH": "/fake"})))
    return SkillsAPI(tmp_path)


def installed(service, names=SKILLS, agent="codex", **entry_changes):
    canonical, target, lock_path = service._paths(agent)
    lock = {"version": 3, "skills": {}}
    if lock_path.exists():
        lock = json.loads(lock_path.read_text())
    for name in names:
        path = canonical / name
        path.mkdir(parents=True, exist_ok=True)
        (path / "SKILL.md").write_text(f"---\nname: {name}\n---\nGAM")
        if target != canonical:
            target.mkdir(parents=True, exist_ok=True)
            (target / name).symlink_to(path, target_is_directory=True)
        lock["skills"][name] = {
            "source": "hyhy111/gam-skills",
            "sourceType": "github",
            "skillPath": f"{name}/SKILL.md",
            "skillFolderHash": "a" * 40,
            **entry_changes,
        }
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps(lock))


def remote(monkeypatch, changed=(), **extra):
    files = []
    for name in SKILLS:
        data = ("Updated GAM CLI" if name in changed else f"---\nname: {name}\n---\nGAM").encode()
        files.append(
            {
                "type": "blob",
                "path": f"{name}/SKILL.md",
                "sha": hashlib.sha1(f"blob {len(data)}\0".encode() + data, usedforsecurity=False).hexdigest(),
            }
        )
    tree = {
        "sha": "b" * 40,
        "tree": [{"type": "tree", "path": name, "sha": ("b" if name in changed else "a") * 40} for name in SKILLS]
        + files,
        **extra,
    }
    transport = Mock(side_effect=lambda *a, **kw: io.BytesIO(json.dumps(tree).encode()))
    monkeypatch.setattr(skills_api, "logged_urlopen", transport)
    return transport


def test_absent_and_stale_records_never_trigger_remote_checks(service, monkeypatch):
    transport = remote(monkeypatch, changed=SKILLS)
    assert service.status("codex", True)["status"] == "not_installed"
    installed(service)
    for name in SKILLS:
        (service.home / ".agents" / "skills" / name / "SKILL.md").unlink()
    assert service.status("codex", True)["status"] == "unmanaged"
    transport.assert_not_called()


@pytest.mark.parametrize("location", ["canonical", "legacy", "manager", "git"])
def test_other_installers_are_not_reported_as_outdated_or_overwritten(service, monkeypatch, location):
    canonical, _, _ = service._paths("codex")
    root = service.home / ".codex" / "skills" if location == "legacy" else canonical
    root.mkdir(parents=True, exist_ok=True)
    path = root / SKILLS[0]
    if location == "git":
        installed(service, names=(SKILLS[0],))
        (path / ".git").mkdir()
    elif location == "manager":
        installed(service, names=(SKILLS[0],))
        (path / "SKILL.md").unlink()
        path.rmdir()
        managed_elsewhere = service.home / ".skills-manager" / SKILLS[0]
        managed_elsewhere.mkdir(parents=True)
        (managed_elsewhere / "SKILL.md").write_text("My managed skill")
        path.symlink_to(managed_elsewhere, target_is_directory=True)
    else:
        path.mkdir()
        (path / "SKILL.md").write_text("My manual skill")
    before = (path / "SKILL.md").read_text()
    transport = remote(monkeypatch, changed=SKILLS)
    runner = Mock()
    monkeypatch.setattr(skills_api.subprocess, "run", runner)
    state = service.status("codex", True)
    assert state["status"] == "unmanaged" and not state["can_install"]
    assert state["outdated"] == []
    assert not service.install("codex")["success"]
    assert (path / "SKILL.md").read_text() == before
    transport.assert_not_called()
    runner.assert_not_called()


def test_update_check_compares_only_gam_folder_hashes(service, monkeypatch):
    installed(service)
    _, _, path = service._paths("codex")
    lock = json.loads(path.read_text())
    lock["skills"]["unrelated"] = {"source": "another/repository", "sourceType": "github"}
    path.write_text(json.dumps(lock))
    transport = remote(monkeypatch, changed=("gam-cli",))
    result = service.status("codex", True)
    assert result["status"] == "update_available"
    assert result["outdated"] == ["gam-cli"]
    transport.assert_called_once()
    assert "/hyhy111/gam-skills/" in transport.call_args.args[0].full_url
    assert service.status("codex")["status"] == "installed"


def test_repository_changes_outside_skill_folders_do_not_claim_updates(service, monkeypatch):
    installed(service)
    remote(monkeypatch)
    assert service.status("codex", True)["status"] == "up_to_date"


@pytest.mark.parametrize("failure", ["offline", "truncated", "missing"])
def test_failed_or_incomplete_checks_never_claim_latest(service, monkeypatch, failure):
    installed(service)
    transport = remote(monkeypatch, truncated=failure == "truncated", **({"tree": []} if failure == "missing" else {}))
    if failure == "offline":
        transport.side_effect = OSError("offline")
    state = service.status("codex", True)
    assert state["status"] == "error" and state["error"] == "CHECK_FAILED"
    assert state["outdated"] == []


def test_pinned_ref_and_custom_metadata_location_are_honored(service, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(service.home / "自定义 state"))
    installed(service, ref="feature/test")
    transport = remote(monkeypatch)
    assert service.status("codex", True)["status"] == "up_to_date"
    assert "/trees/feature%2Ftest?" in transport.call_args.args[0].full_url


def test_non_selected_agent_manual_copy_is_not_mistaken_for_npx(service, monkeypatch):
    installed(service)
    _, target, _ = service._paths("claude-code")
    (target / SKILLS[0]).mkdir(parents=True)
    (target / SKILLS[0] / "SKILL.md").write_text("Manual Claude skill")
    transport = remote(monkeypatch)
    assert service.status("claude-code", True)["status"] == "unmanaged"
    transport.assert_not_called()


@pytest.mark.parametrize("agent", skills_api.SHARED_AGENTS)
def test_universal_agents_use_shared_install_without_native_directory(service, monkeypatch, agent):
    installed(service)
    _, native, _ = service._paths(agent)
    if agent != "codex":
        assert not native.exists()
    remote(monkeypatch)
    state = service.status(agent, True)
    assert state["status"] == "up_to_date"
    assert state["installed_count"] == len(SKILLS)
    assert service.status("claude-code")["status"] == "not_installed"
    assert service.status("windsurf")["status"] == "not_installed"


def test_claude_default_copies_remain_recognized_after_cursor_install(service, monkeypatch):
    installed(service, agent="claude-code")
    canonical, target, _ = service._paths("claude-code")
    for name in SKILLS:
        (target / name).unlink()
        shutil.move(canonical / name, target / name)
    assert service.status("claude-code")["installed_count"] == len(SKILLS)
    installed(service)
    remote(monkeypatch)
    assert service.status("claude-code", True)["status"] == "up_to_date"
    assert service.status("cursor", True)["status"] == "up_to_date"


def test_new_shared_install_does_not_claim_old_claude_copy_is_latest_or_overwrite_it(service, monkeypatch):
    installed(service, agent="claude-code")
    canonical, target, _ = service._paths("claude-code")
    for name in SKILLS:
        (target / name).unlink()
        shutil.copytree(canonical / name, target / name)
    old = (target / "gam-cli" / "SKILL.md").read_bytes()
    (canonical / "gam-cli" / "SKILL.md").write_text("New shared version")
    transport = remote(monkeypatch)
    runner = Mock()
    monkeypatch.setattr(skills_api.subprocess, "run", runner)
    state = service.status("claude-code", True)
    assert state["status"] == "unmanaged"
    assert state["error"] == "COPY_VERSION_MISMATCH"
    assert not service.install("claude-code")["success"]
    assert (target / "gam-cli" / "SKILL.md").read_bytes() == old
    transport.assert_not_called()
    runner.assert_not_called()


@pytest.mark.parametrize("agent", ["codex", "claude-code", "windsurf"])
def test_latest_shared_lock_cannot_hide_stale_actual_files(service, monkeypatch, agent):
    installed(service, agent=agent, skillFolderHash="b" * 40)
    canonical, target, _ = service._paths(agent)
    if target != canonical:
        for name in SKILLS:
            (target / name).unlink()
            shutil.move(canonical / name, target / name)
    remote(monkeypatch, changed=SKILLS)
    state = service.status(agent, True)
    assert state["status"] == "update_available"
    assert state["outdated"] == list(SKILLS)


def test_content_check_covers_nested_files_but_ignores_installer_exclusions(service, monkeypatch):
    installed(service)
    canonical, _, _ = service._paths("codex")
    transport = remote(monkeypatch)
    for relative in ("__pycache__/cache.pyc", "metadata.json"):
        path = canonical / "gam-cli" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("runtime metadata")
    assert service.status("codex", True)["status"] == "up_to_date"
    script = canonical / "gam-cli" / "scripts" / "tool.py"
    script.parent.mkdir()
    script.write_bytes(b"print('old')\n")
    data = b"print('new')\n"
    tree = json.loads(transport().getvalue())
    tree["tree"].append(
        {
            "type": "blob",
            "path": "gam-cli/scripts/tool.py",
            "sha": hashlib.sha1(f"blob {len(data)}\0".encode() + data, usedforsecurity=False).hexdigest(),
        }
    )
    transport.side_effect = lambda *a, **kw: io.BytesIO(json.dumps(tree).encode())
    assert service.status("codex", True)["outdated"] == ["gam-cli"]
    script.write_bytes(data)
    assert service.status("codex", True)["status"] == "up_to_date"


@pytest.mark.parametrize("agent", [agent for agent in skills_api.AGENTS if agent != "codex"])
@pytest.mark.parametrize("explicit_copy", [False, True])
def test_agent_only_npx_copies_support_detection_and_updates(service, monkeypatch, agent, explicit_copy):
    installed(service, agent=agent, **({"installMode": "copy"} if explicit_copy else {}))
    canonical, target, lock_path = service._paths(agent)
    for name in SKILLS:
        (target / name).unlink()
        shutil.move(canonical / name, target / name)

    state = service.status(agent)
    assert state["source"] == "npx"
    assert state["installed_count"] == len(SKILLS)
    assert state["can_check"] and state["can_install"]
    assert service.status("codex")["status"] == "not_installed"

    remote(monkeypatch, changed=("gam-cli",))
    pending = service.status(agent, True)
    assert pending["status"] == "update_available" and pending["outdated"] == ["gam-cli"]

    def run(command, **kwargs):
        assert command[command.index("-a") + 1] == agent
        (target / "gam-cli" / "SKILL.md").write_text("Updated GAM CLI")
        lock = json.loads(lock_path.read_text())
        lock["skills"]["gam-cli"]["skillFolderHash"] = "b" * 40
        lock_path.write_text(json.dumps(lock))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(skills_api.subprocess, "run", run)
    result = service.install(agent)
    assert result["success"] and result["state"]["installed_count"] == len(SKILLS)
    assert service.status(agent, True)["status"] == "up_to_date"
    assert all(not (canonical / name).exists() for name in SKILLS)


def test_install_uses_fixed_arguments_and_verifies_files_and_records(service, monkeypatch):
    def run(command, **kwargs):
        assert command == [
            "/fake/npx",
            "--yes",
            "skills@latest",
            "add",
            "hyhy111/gam-skills",
            "-g",
            "-a",
            "claude-code",
            "--skill",
            *SKILLS,
            "-y",
        ]
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert kwargs["env"]["DISABLE_TELEMETRY"] == "1"
        assert "shell" not in kwargs
        installed(service, agent="claude-code")
        return SimpleNamespace(returncode=0)

    runner = Mock(side_effect=run)
    monkeypatch.setattr(skills_api.subprocess, "run", runner)
    result = service.install("claude-code")
    assert result["success"]
    assert result["state"]["installed_count"] == 6
    runner.assert_called_once()


@pytest.mark.parametrize("returncode", [0, 1])
def test_process_exit_alone_never_claims_installed(service, monkeypatch, returncode):
    monkeypatch.setattr(skills_api.subprocess, "run", Mock(return_value=SimpleNamespace(returncode=returncode)))
    result = service.install()
    assert not result["success"] and result["state"]["error"] == "INSTALL_FAILED"


def test_missing_runtime_timeout_busy_and_invalid_agent_are_explicit(service, monkeypatch):
    monkeypatch.setattr(skills_api.subprocess, "run", Mock(side_effect=subprocess.TimeoutExpired("npx", 180)))
    assert service.install()["state"]["error"] == "INSTALL_TIMEOUT"
    service._install_lock.acquire()
    try:
        assert service.install()["state"]["error"] == "BUSY"
    finally:
        service._install_lock.release()
    monkeypatch.setattr(SkillsAPI, "_runtime", staticmethod(lambda: ([], {})))
    assert service.install()["state"]["error"] == "NODE_REQUIRED"
    assert not service.status("codex; arbitrary command")["can_install"]


def test_windows_runtime_uses_node_entry_without_command_shell(service, tmp_path, monkeypatch):
    root = tmp_path / "Node 工具 with spaces"
    entry = root / "node_modules" / "npm" / "bin" / "npx-cli.js"
    entry.parent.mkdir(parents=True)
    entry.write_text("// npm entry")
    monkeypatch.setattr(skills_api.sys, "platform", "win32")
    monkeypatch.setattr(
        skills_api.shutil, "which", lambda name, **kwargs: str(root / ("npx.cmd" if name == "npx" else "node.exe"))
    )
    command, _ = runtime()
    assert command == [str(root / "node.exe"), str(entry)]


@pytest.mark.parametrize("content", ["broken", '{"version": 2, "skills": {}}'])
def test_invalid_or_old_lock_is_not_overwritten(service, content):
    _, _, lock = service._paths("codex")
    lock.parent.mkdir(parents=True)
    lock.write_text(content)
    assert service.status()["error"] == "DETECTION_FAILED"
    assert not service.install()["success"]
    assert lock.read_text() == content


def test_untracked_npx_install_does_not_claim_an_available_update(service, monkeypatch):
    installed(service, skillFolderHash="")
    transport = remote(monkeypatch, changed=SKILLS)
    state = service.status("codex", True)
    assert state["source"] == "npx" and not state["can_check"]
    assert state["error"] == "VERSION_UNTRACKED" and state["outdated"] == []
    transport.assert_not_called()


def test_bridge_delegates_only_agent_and_check_flag():
    from backend.main import API

    bridge = API.__new__(API)
    bridge._skills_api_instance = Mock()
    bridge.get_gam_skills_status("cursor", True)
    bridge._skills_api_instance.status.assert_called_once_with("cursor", True)
    bridge.install_gam_skills("codex")
    bridge._skills_api_instance.install.assert_called_once_with("codex")
    bridge.get_gam_skills_updates()
    bridge._skills_api_instance.updates.assert_called_once_with()


@pytest.mark.parametrize("modified", [False, True])
def test_copy_mode_requires_matching_canonical_content(service, monkeypatch, modified):
    installed(service, installMode="copy")
    canonical, target, _ = service._paths("cursor")
    for name in SKILLS:
        shutil.copytree(canonical / name, target / name)
    if modified:
        (target / SKILLS[0] / "SKILL.md").write_text("User changes")
    transport = remote(monkeypatch, changed=SKILLS)
    result = service.status("cursor", True)
    if modified:
        assert result["status"] == "unmanaged" and not result["can_install"]
        transport.assert_not_called()
    else:
        assert result["status"] == "update_available" and result["source"] == "npx"


@pytest.mark.parametrize("offline", [False, True])
def test_startup_scan_covers_non_default_agents_and_reuses_remote_fetches(service, monkeypatch, offline):
    installed(service, agent="claude-code")
    transport = remote(monkeypatch, changed=("gam-cli",))
    if offline:
        transport.side_effect = OSError("offline")
    result = service.updates()
    assert set(result) == set(skills_api.AGENTS)
    transport.assert_called_once()
    expected = "error" if offline else "update_available"
    assert result["claude-code"]["status"] == expected
    assert result["codex"]["status"] == expected
    assert all(result[agent]["status"] == expected for agent in skills_api.SHARED_AGENTS)
    assert result["windsurf"]["status"] == "not_installed"


def test_startup_scan_without_npx_installs_never_contacts_upstream(service, monkeypatch):
    transport = remote(monkeypatch, changed=SKILLS)
    canonical, _, _ = service._paths("codex")
    (canonical / SKILLS[0]).mkdir(parents=True)
    (canonical / SKILLS[0] / "SKILL.md").write_text("Manual skill")
    assert all(state["status"] != "update_available" for state in service.updates().values())
    transport.assert_not_called()
