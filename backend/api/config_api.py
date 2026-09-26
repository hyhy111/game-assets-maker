"""Config API - Application configuration management"""

from typing import Any

from src.utils.app_config import load_app_config, public_app_config, save_app_config


class ConfigAPI:
    """API for application configuration"""

    def get_config(self) -> dict[str, Any]:
        """Get application configuration"""
        return public_app_config(load_app_config())

    def save_config(self, config: dict[str, Any]) -> bool:
        """Save application configuration"""
        save_app_config(config)
        return True
