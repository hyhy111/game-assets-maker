import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
IDENTITY_CHECK = REPO_ROOT / "scripts" / "check_product_identity.py"


def test_game_assets_maker_release_identity_contract():
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert project["name"] == "game-assets-maker"
    assert project["scripts"] == {
        "gam": "backend.main:installed_main",
        "batch-processor": "src.cli.batch_processor:main",
        "gam-agent": "src.cli.agent:installed_main",
        "gam-seedance-smoke": "src.cli.seedance_paid_smoke:installed_main",
    }

    spec = REPO_ROOT / "GameAssetsMaker.spec"
    assert spec.is_file()
    assert not (REPO_ROOT / "VideoToSheetWebView.spec").exists()
    source = spec.read_text(encoding="utf-8")
    assert "APP_DISPLAY_NAME = 'Game Assets Maker'" in source
    assert "name='game-assets-maker'" in source
    assert "u2net.onnx" not in source

    assert "GameAssetsMaker.spec" in (REPO_ROOT / "build.py").read_text(encoding="utf-8")
    assert not list(REPO_ROOT.glob("*.sh"))


def test_runtime_identity_uses_gam_namespaces():
    expected_fragments = {
        "backend/main.py": '"Game Assets Maker"',
        "backend/core/credential_crypto.py": 'data_root() / ".keystore"',
        "src/utils/logger.py": 'logging.getLogger("GameAssetsMakerLogger")',
        "src/cli/agent.py": 'prog="gam-agent"',
        "src/cli/seedance_paid_smoke.py": 'prog="gam-seedance-smoke"',
        "src/agent_tools/service.py": '"command": "gam-agent doctor"',
        "frontend/index.html": "<title>Game Assets Maker</title>",
        "frontend/src/api/credentialVault.ts": "const STORAGE_KEY = 'gam:auth:credentials';",
        "frontend/src/api/http.ts": "const TOKEN_KEY = 'gam:auth:token';",
        "frontend/src/locales/index.ts": "const LOCALE_STORAGE_KEY = 'gam:locale'",
        "frontend/src/recent-media-favorites.ts": "const STORAGE_KEY = 'gam:recent-media-favorites';",
        "frontend/src/components/ai-creation/RecentGenerations.vue": (
            "const STACK_STORAGE_KEY = 'gam:stack-same-prompts';"
        ),
        "frontend/src/seedream-image-drag.ts": "application/x-gam-seedream-image",
    }

    for path, fragment in expected_fragments.items():
        source = (REPO_ROOT / path).read_text(encoding="utf-8")
        assert fragment in source, f"{path} is missing {fragment!r}"

    assert "Game Assets Maker" in (REPO_ROOT / "README.md").read_text(encoding="utf-8")


def run_identity_check(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(IDENTITY_CHECK), "--root", str(root)],
        capture_output=True,
        check=False,
        text=True,
    )


def test_identity_guard_rejects_old_brand_in_active_source(tmp_path):
    source = tmp_path / "src" / "feature.py"
    source.parent.mkdir(parents=True)
    source.write_text('APP_NAME = "Video to Sheet"\n', encoding="utf-8")

    result = run_identity_check(tmp_path)

    assert result.returncode == 1
    assert "src/feature.py:1" in result.stdout
    assert "Video to Sheet" in result.stdout


def test_identity_guard_allows_history_and_explicit_legacy_migration(tmp_path):
    archive = tmp_path / "docs" / "archive" / "old-release.md"
    archive.parent.mkdir(parents=True)
    archive.write_text("Video to Sheet release notes\n", encoding="utf-8")
    migration = tmp_path / "src" / "core" / "rembg_model.py"
    migration.parent.mkdir(parents=True)
    migration.write_text('legacy = root / "VideoToSheet" / "models"\n', encoding="utf-8")

    result = run_identity_check(tmp_path)

    assert result.returncode == 0, result.stdout
