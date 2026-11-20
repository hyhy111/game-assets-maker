"""Application configuration defaults for local processing."""

import pytest

from src.utils.app_config import DEFAULT_APP_CONFIG, load_app_config, merge_app_config, save_app_config


def test_processing_background_model_defaults_to_u2net():
    merged = merge_app_config()
    assert merged["processing"]["background_model"] == "u2net"


def test_processing_background_model_rejects_unknown_values():
    merged = merge_app_config({"processing": {"background_model": "unknown-model"}})
    assert merged["processing"]["background_model"] == DEFAULT_APP_CONFIG["processing"]["background_model"]


def test_processing_section_recovers_from_non_dict_persisted_value():
    merged = merge_app_config({"processing": "junk"})
    assert merged["processing"]["background_model"] == DEFAULT_APP_CONFIG["processing"]["background_model"]


def test_processing_background_model_round_trips_through_save(isolated_workspace):
    save_app_config({"processing": {"background_model": "birefnet-comfy"}})
    assert load_app_config()["processing"]["background_model"] == "birefnet-comfy"


def test_processing_background_model_survives_public_projection(isolated_workspace):
    from src.utils.app_config import public_app_config

    save_app_config({"processing": {"background_model": "birefnet-comfy"}})
    public = public_app_config(load_app_config())
    assert public["processing"]["background_model"] == "birefnet-comfy"


@pytest.fixture(autouse=True)
def macos_background_model_compatibility(monkeypatch):
    """These legacy Comfy workflow cases exercise the retained macOS backend."""
    monkeypatch.setattr("sys.platform", "darwin")
