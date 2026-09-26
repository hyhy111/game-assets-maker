from pathlib import Path

import pytest


@pytest.fixture
def runtime_config_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "runtime" / "config.json"
    monkeypatch.setenv("GAM_CONFIG", str(path))
    return path
