"""Fixtures for the platform integration tests.

Shared fakes/helpers live in `platform_test_helpers.py` (a unique module
name) because sibling test dirs also have conftest.py files and a bare
`from conftest import ...` in test modules would resolve to whichever
conftest won the module-name race.
"""

from __future__ import annotations

import pytest
from PIL import Image

import platform_test_helpers as helpers
from platform_test_helpers import reset_trace_logger


@pytest.fixture(autouse=True)
def isolate_platform_trace_log(tmp_path, monkeypatch):
    """Keep the platform trace log (a real-machine debugging aid) out of the app's logs/.

    Without this, any test that instantiates PlatformClient appends to
    `<repo>/logs/platform.log` — polluting the very file we read when debugging
    a live session.
    """
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    reset_trace_logger()
    yield
    reset_trace_logger()


@pytest.fixture
def png_bytes() -> bytes:
    return helpers.png_bytes()


@pytest.fixture
def png_file(tmp_path, png_bytes):
    path = tmp_path / "input.png"
    path.write_bytes(png_bytes)
    return path
