"""Isolation between source-development and installed-release data locations.

Covers the acceptance criteria of the release-readiness ticket "隔离开发版与
正式安装版数据": installed builds resolve a stable per-user data root
independent of the launch directory, source development keeps the workspace
layout with a dedicated dev config, and explicit environment overrides keep
working in both modes.
"""

import json
import os
from pathlib import Path

import pytest

OVERRIDE_ENV_VARS = (
    "GAM_CONFIG",
    "GAM_DATA_MODE",
    "GAM_DATA_ROOT",
)


def _clear_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in OVERRIDE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def dev_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A source-development workspace: cwd is the project checkout."""
    _clear_overrides(monkeypatch)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def installed_data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An installed release with its per-user data root in a temp dir."""
    data_root = tmp_path / "user-data"
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    monkeypatch.setenv("GAM_DATA_ROOT", str(data_root))
    monkeypatch.setenv("GAM_CONFIG", str(data_root / "config.json"))
    return data_root


# ==================== Data root resolution ====================


def test_dev_mode_resolves_workspace_data_root(dev_workspace: Path):
    from src.utils import data_paths

    assert data_paths.data_mode() == "dev"
    assert data_paths.data_root() == dev_workspace
    assert data_paths.projects_root() == dev_workspace / "project"
    repo_root = Path(__file__).resolve().parents[1]
    assert data_paths.models_root() == repo_root / "models" / "rembg"


def test_installed_mode_resolves_per_user_data_root(installed_data_root: Path):
    from src.utils import data_paths

    assert data_paths.data_mode() == "installed"
    assert data_paths.data_root() == installed_data_root
    assert data_paths.projects_root() == installed_data_root / "project"
    assert data_paths.models_root() == installed_data_root / "models" / "rembg"


def test_installed_default_data_root_uses_home_dot_gam(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    monkeypatch.delenv("GAM_DATA_ROOT", raising=False)

    from src.utils import data_paths

    home = tmp_path / "developer-home"
    monkeypatch.setattr(data_paths.Path, "home", classmethod(lambda cls: home))

    assert data_paths.data_root() == home / ".gam"


def test_data_root_environment_override_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.delenv("GAM_DATA_MODE", raising=False)
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path / "custom-root"))

    from src.utils import data_paths

    assert data_paths.data_root() == tmp_path / "custom-root"
    assert data_paths.projects_root() == tmp_path / "custom-root" / "project"


def test_legacy_environment_variables_do_not_override_gam_contract(
    dev_workspace: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setenv("VIDEO_TO_SHEET_DATA_MODE", "installed")
    monkeypatch.setenv("VIDEO_TO_SHEET_DATA_ROOT", str(tmp_path / "legacy-root"))
    monkeypatch.setenv("VIDEO_TO_SHEET_CONFIG", str(tmp_path / "legacy-config.json"))

    from src.utils import data_paths
    from src.utils.app_config import get_app_config_path

    assert data_paths.data_mode() == "dev"
    assert data_paths.data_root() == dev_workspace
    assert get_app_config_path() == dev_workspace / "config.dev.json"


def test_non_windows_credential_keystore_follows_data_root_override(tmp_path, monkeypatch):
    from backend.core import credential_crypto

    fake_home = tmp_path / "fake-home"
    isolated_root = tmp_path / "isolated-gam"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(credential_crypto.sys, "platform", "linux")
    monkeypatch.setenv("GAM_DATA_ROOT", str(isolated_root))

    crypto = credential_crypto.CredentialCrypto()
    encrypted = crypto.encrypt("secret")

    assert crypto.decrypt(encrypted) == "secret"
    assert (isolated_root / ".keystore").is_file()
    assert not (fake_home / ".gam" / ".keystore").exists()


# ==================== Config isolation ====================


def test_dev_config_lives_in_workspace_and_not_in_gam_user_data(dev_workspace: Path):
    from src.utils.app_config import get_app_config_path, load_app_config, save_app_config

    assert get_app_config_path() == dev_workspace / "config.dev.json"

    save_app_config({"language": "en"})

    assert json.loads((dev_workspace / "config.dev.json").read_text(encoding="utf-8"))["language"] == "en"
    assert load_app_config()["language"] == "en"
    assert not (dev_workspace / ".gam").exists()


def test_dev_config_seeded_once_from_previous_shared_config(
    dev_workspace: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    (dev_workspace / "config.json").write_text(json.dumps({"language": "zh"}), encoding="utf-8")
    home = tmp_path / "developer-home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    shared_config = home / ".gam" / "config.json"
    shared_config.parent.mkdir(parents=True)
    shared_content = {
        "language": "en",
        "seedance": {"api_key": "dev-secret", "cache_dir": str(tmp_path / "custom-cache")},
    }
    shared_config.write_text(json.dumps(shared_content), encoding="utf-8")
    from src.utils.app_config import load_app_config

    seeded = load_app_config()

    assert seeded["language"] == "en"
    assert seeded["seedance"]["api_key"] == "dev-secret"
    from src.utils.ai_cache_paths import ai_cache_root

    assert ai_cache_root(seeded["seedance"]["cache_dir"]) == dev_workspace / "cache"
    assert ai_cache_root(seeded["seedance"]["cache_dir"]) != ai_cache_root(shared_content["seedance"]["cache_dir"])
    assert (dev_workspace / "config.dev.json").exists()
    # The previous shared config stays untouched; only settings are adopted.
    assert json.loads(shared_config.read_text(encoding="utf-8")) == shared_content

    # Later dev runs no longer follow the shared (now installed) config.
    shared_config.write_text(json.dumps({"language": "fr"}), encoding="utf-8")
    assert load_app_config()["language"] == "en"


def test_dev_workspace_without_marker_does_not_read_shared_config(
    dev_workspace: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    home = tmp_path / "developer-home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    shared_config = home / ".gam" / "config.json"
    shared_config.parent.mkdir(parents=True)
    shared_config.write_text(json.dumps({"seedance": {"api_key": "installed-secret"}}), encoding="utf-8")
    from src.utils.app_config import load_app_config

    config = load_app_config()

    assert config["seedance"]["api_key"] == ""
    assert not (dev_workspace / "config.dev.json").exists()


def test_installed_config_uses_home_dot_gam(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _clear_overrides(monkeypatch)
    monkeypatch.setenv("GAM_DATA_MODE", "installed")

    from src.utils.app_config import get_app_config_path
    from src.utils import data_paths

    home = tmp_path / "developer-home"
    monkeypatch.setattr(data_paths.Path, "home", classmethod(lambda cls: home))

    assert get_app_config_path() == home / ".gam" / "config.json"


def test_config_environment_override_wins_in_installed_mode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _clear_overrides(monkeypatch)
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    override = tmp_path / "override" / "config.json"
    monkeypatch.setenv("GAM_CONFIG", str(override))

    from src.utils.app_config import get_app_config_path

    assert get_app_config_path() == override


# ==================== API behavior under each mode ====================


def test_installed_projects_survive_launch_from_other_directories(
    installed_data_root: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    from backend.api.project_api import ProjectAPI

    launch_a = tmp_path / "launch-a"
    launch_b = tmp_path / "launch-b"
    launch_a.mkdir()
    launch_b.mkdir()

    monkeypatch.chdir(launch_a)
    created = ProjectAPI().create_project("mage", "walk")
    assert created["path"].startswith(str(installed_data_root))
    assert (installed_data_root / "project" / "mage" / "walk" / "cache" / "global_params.json").exists()

    monkeypatch.chdir(launch_b)
    projects = ProjectAPI().get_projects()

    assert [project["id"] for project in projects] == ["mage/walk"]
    assert projects[0]["path"] == created["path"]


def test_installed_mode_never_writes_to_readonly_launch_directory(
    installed_data_root: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    from backend.api.config_api import ConfigAPI
    from backend.api.project_api import ProjectAPI

    launch_dir = tmp_path / "launch-readonly"
    launch_dir.mkdir()
    monkeypatch.chdir(launch_dir)
    launch_dir.chmod(0o555)
    try:
        created = ProjectAPI().create_project("robot", "idle")
        assert ConfigAPI().save_config({"language": "en"}) is True
    finally:
        launch_dir.chmod(0o755)

    assert created["path"].startswith(str(installed_data_root))
    assert os.listdir(launch_dir) == []
    assert json.loads((installed_data_root / "config.json").read_text(encoding="utf-8"))["language"] == "en"


def test_dev_mode_apis_keep_workspace_layout(dev_workspace: Path):
    from backend.api.frame_api import FrameAPI
    from backend.api.project_api import ProjectAPI

    assert ProjectAPI()._projects_root == dev_workspace / "project"
    frame_api = FrameAPI()
    assert frame_api._projects_root == dev_workspace / "project"
    assert frame_api._project_root == dev_workspace


def test_installed_frame_and_ai_cache_paths_follow_data_root(installed_data_root: Path):
    from backend.api.frame_api import FrameAPI
    from src.utils.ai_cache_paths import ai_pic_cache_root, ai_video_cache_root

    frame_api = FrameAPI("http://127.0.0.1:9000")
    frame = installed_data_root / "project" / "mage" / "walk" / "output" / "01_frames" / "frame_000001.png"
    assert frame_api.get_frame_url(str(frame)).startswith("http://127.0.0.1:9000/project/mage/walk/")

    assert ai_video_cache_root(None) == installed_data_root / "cache" / "ai-video-cache"
    assert ai_pic_cache_root(None) == installed_data_root / "cache" / "ai-pic-cache"
    # A relative configured cache directory resolves against the data root,
    # never against the launch directory.
    assert ai_video_cache_root("cache") == installed_data_root / "cache" / "ai-video-cache"


def test_installed_logger_defaults_to_gam_user_data_logs(installed_data_root: Path):
    from src.utils.logger import SafeLogger

    stats = SafeLogger().get_log_stats()

    assert Path(stats["log_dir"]) == installed_data_root / "logs"


def test_dev_ai_cache_paths_keep_workspace_layout(dev_workspace: Path):
    from src.utils.ai_cache_paths import ai_video_cache_root

    assert ai_video_cache_root(None) == dev_workspace / "cache" / "ai-video-cache"
    assert ai_video_cache_root("cache") == dev_workspace / "cache" / "ai-video-cache"


def test_dev_and_installed_modes_do_not_cross_contaminate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from backend.api.project_api import ProjectAPI
    from src.utils.app_config import load_app_config, save_app_config

    data_root = tmp_path / "user-data"
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    monkeypatch.setenv("GAM_DATA_ROOT", str(data_root))
    monkeypatch.setenv("GAM_CONFIG", str(data_root / "config.json"))
    ProjectAPI().create_project("mage", "walk")
    save_app_config({"language": "en"})

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("GAM_DATA_MODE", "dev")
    monkeypatch.delenv("GAM_DATA_ROOT", raising=False)
    monkeypatch.setenv("GAM_CONFIG", str(workspace / "config.dev.json"))
    monkeypatch.chdir(workspace)
    ProjectAPI().create_project("robot", "idle")
    save_app_config({"language": "zh"})

    assert (data_root / "project" / "mage" / "walk").is_dir()
    assert (workspace / "project" / "robot" / "idle").is_dir()
    assert not (data_root / "project" / "robot").exists()
    assert not (workspace / "project" / "mage").exists()
    assert load_app_config()["language"] == "zh"

    monkeypatch.setenv("GAM_CONFIG", str(data_root / "config.json"))
    assert load_app_config()["language"] == "en"


@pytest.mark.parametrize("explicit_config", [False, True])
def test_installed_first_run_ignores_launch_config(tmp_path, monkeypatch, explicit_config):
    from src.utils.app_config import load_app_config, save_app_config

    _clear_overrides(monkeypatch)
    launch = tmp_path / "launch"
    launch.mkdir()
    legacy = {"language": "en", "seedance": {"cache_dir": "/old-workspace/cache"}}
    (launch / "config.json").write_text(json.dumps(legacy))
    monkeypatch.chdir(launch)
    monkeypatch.setenv("GAM_DATA_MODE", "installed")
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path / "user"))
    if explicit_config:
        monkeypatch.setenv("GAM_CONFIG", str(tmp_path / "custom-config.json"))

    config = load_app_config()
    assert config["language"] == "zh"
    assert config["seedance"]["cache_dir"] == "cache"
    save_app_config({"theme": "light"})
    assert load_app_config()["seedance"]["cache_dir"] == "cache"
    assert json.loads((launch / "config.json").read_text()) == legacy


@pytest.mark.parametrize("mode", ["dev", "installed"])
def test_data_root_alone_isolates_config_writes(tmp_path, monkeypatch, mode):
    from src.utils.app_config import get_app_config_path, load_app_config, save_app_config

    _clear_overrides(monkeypatch)
    monkeypatch.chdir(tmp_path)
    shared = tmp_path / "shared-user-data"
    shared.mkdir()
    original = '{"language": "en", "seedance": {"api_key": "synthetic"}}'
    (shared / "config.json").write_text(original)
    isolated = tmp_path / "isolated"
    monkeypatch.setenv("GAM_DATA_MODE", mode)
    monkeypatch.setenv("GAM_DATA_ROOT", str(isolated))

    config = load_app_config()
    assert config["seedance"]["api_key"] == ""
    save_app_config({"language": "zh"})
    expected = isolated / ("config.json" if mode == "installed" else "config.dev.json")
    assert get_app_config_path() == expected
    assert json.loads(expected.read_text())["language"] == "zh"
    assert (shared / "config.json").read_text() == original


def test_explicit_dev_cache_location_is_preserved(dev_workspace):
    from src.utils.ai_cache_paths import ai_cache_root
    from src.utils.app_config import load_app_config, save_app_config

    custom = dev_workspace / "chosen-cache"
    save_app_config({"seedance": {"cache_dir": str(custom)}})
    assert ai_cache_root(load_app_config()["seedance"]["cache_dir"]) == custom
