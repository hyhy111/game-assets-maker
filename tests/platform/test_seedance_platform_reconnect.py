"""Regression: SeedanceAPI must re-attach platform support to a manager built
while unconfigured.

User-visible symptom this guards against: the UI is signed in (credits, quotes
all work — those go through the shared PlatformClient), yet every video
generation fails with "Platform generation is not configured; sign in first"
because the task manager was rebuilt during a logged-out window and the
set_token-only path of update_platform never re-attached the platform client.
SeedreamAPI has _refresh_manager_platform for exactly this; SeedanceAPI must
behave the same.
"""

from __future__ import annotations

import pytest

from backend.api.seedance_api import SeedanceAPI
from backend.platform.config import PlatformConfig

BASE = "https://platform.test"


@pytest.fixture
def seedance_api(isolated_workspace):
    api = SeedanceAPI(platform_config=PlatformConfig())
    yield api
    api.shutdown()


def _manager_build(seedance_api: SeedanceAPI) -> None:
    """Force the lazy manager build (window is None in tests, so _replace_manager
    defers the rebuild until the next access — same as any bridge call in prod)."""
    seedance_api.cache_status()


def test_manager_built_while_logged_out_recovers_on_login(seedance_api):
    """Client exists from an earlier login; token cleared; manager built while
    unconfigured; token pushed again via the set_token-only path."""
    seedance_api.update_platform(BASE, "token-1")
    seedance_api.update_platform(BASE, None)
    _manager_build(seedance_api)
    assert seedance_api._manager is not None
    assert seedance_api._manager._platform is None

    seedance_api.update_platform(BASE, "token-2")
    _manager_build(seedance_api)

    assert seedance_api._manager is not None
    assert seedance_api._manager._platform is not None
    assert seedance_api._manager._platform._platform.token == "token-2"


def test_healthy_manager_survives_token_refresh_without_rebuild(seedance_api):
    """The set_token path must keep the same manager instance when platform
    support is already attached — polling state must not be discarded."""
    seedance_api.update_platform(BASE, "token-1")
    _manager_build(seedance_api)
    manager = seedance_api._manager
    assert manager._platform is not None

    seedance_api.update_platform(BASE, "token-2")

    assert seedance_api._manager is manager
    assert seedance_api._platform_client.token == "token-2"


def test_logout_does_not_detach_platform_wrapper(seedance_api):
    """A logout push (token=None, same base) only clears the token; the manager
    keeps its platform wrapper so a later login can refresh it in place."""
    seedance_api.update_platform(BASE, "token-1")
    _manager_build(seedance_api)
    manager = seedance_api._manager

    seedance_api.update_platform(BASE, None)

    assert seedance_api._manager is manager
    assert seedance_api._manager._platform is not None
    assert seedance_api._platform_client.token is None
