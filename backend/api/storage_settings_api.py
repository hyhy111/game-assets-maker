"""PyWebView-facing settings API for storage locations and migration.

Reads expose both the persisted config values (kept relative and migratable)
and the resolved absolute display paths. Saves re-resolve the draft against
the stable data root and compare normalized paths: equivalent spellings stay a
plain save, while a real change hands the whole settings draft to the
migration coordinator and returns its precheck summary. The draft is committed
only when the user confirms and ``execute_migration`` succeeds.
"""

from copy import deepcopy
from pathlib import Path
from typing import Any

from src.utils.app_config import load_app_config, merge_config_update, public_app_config, save_app_config
from src.utils.storage_locations import storage_locations_from_config
from src.utils.storage_migration import (
    AI_CACHE_LOCATION,
    PROJECT_LOCATION,
    LocationMigration,
    MigrationError,
    StorageMigrationCoordinator,
)


class StorageSettingsAPI:
    """Settings reads, change detection and migration for storage roots."""

    def __init__(self, *, coordinator: StorageMigrationCoordinator, data_root: Path):
        self._coordinator = coordinator
        self._data_root = Path(data_root)

    # ==================== Read ====================

    def get_settings(self) -> dict[str, Any]:
        """Return persisted storage values plus resolved display paths."""
        try:
            config = load_app_config()
            public = public_app_config(config)
            locations = storage_locations_from_config(config, data_root=self._data_root)
            return {
                "success": True,
                "settings": {
                    "project_dir": public.get("project_dir"),
                    "cache_dir": public["seedance"].get("cache_dir"),
                    "projects_root": str(locations.projects_root),
                    "ai_cache_root": str(locations.ai_cache_root),
                },
            }
        except Exception as error:
            return self._error_response("STORAGE_SETTINGS_UNAVAILABLE", str(error), stage="read")

    # ==================== Save (plain save or migration precheck) ====================

    def save_settings(self, draft: dict[str, Any]) -> dict[str, Any]:
        """Save the settings draft, or precheck a storage-location migration."""
        try:
            if not isinstance(draft, dict):
                raise ValueError("Storage settings draft must be an object")
            sanitized = self._sanitize_draft(draft)
            migrations = self._detect_migrations(sanitized)
            if not migrations:
                save_app_config(sanitized)
                return {"success": True, "migration_required": False}
            report = self._coordinator.precheck(migrations, sanitized)
            return {
                "success": True,
                "migration_required": True,
                "migration": {
                    "token": report.token,
                    "entries": [
                        {
                            "kind": entry.kind,
                            "source": str(entry.source),
                            "target": str(entry.target),
                            "file_count": entry.file_count,
                            "total_bytes": entry.total_bytes,
                        }
                        for entry in report.entries
                    ],
                },
            }
        except MigrationError as error:
            return self._error_response("MIGRATION_PRECHECK_FAILED", error.reason, stage=error.stage)
        except Exception as error:
            return self._error_response("STORAGE_SAVE_FAILED", str(error), stage="save")

    def execute_migration(self, token: str) -> dict[str, Any]:
        """Run the confirmed migration and commit the whole settings draft."""
        try:
            if not isinstance(token, str) or not token:
                raise ValueError("Migration confirmation token is required")
            self._coordinator.execute(token)
            return {"success": True, "restart_required": True}
        except MigrationError as error:
            return self._error_response("MIGRATION_FAILED", error.reason, stage=error.stage)
        except Exception as error:
            return self._error_response("MIGRATION_FAILED", str(error), stage="execute")

    # ==================== Internals ====================

    @staticmethod
    def _sanitize_draft(draft: dict[str, Any]) -> dict[str, Any]:
        """Drop read-only markers and never persist an empty API key field."""
        sanitized = deepcopy(draft)
        sanitized.pop("ark_audit_enabled", None)
        sanitized.pop("ark_audit_available", None)
        sanitized.pop("cli_generation_enabled", None)
        seedance = sanitized.get("seedance")
        if isinstance(seedance, dict):
            seedance.pop("api_key_configured", None)
            api_key = seedance.get("api_key")
            if api_key is not None and (not isinstance(api_key, str) or not api_key.strip()):
                seedance.pop("api_key", None)
        return sanitized

    def _detect_migrations(self, draft: dict[str, Any]) -> list[LocationMigration]:
        current = load_app_config()
        merged = merge_config_update(current, draft)
        existing = storage_locations_from_config(current, data_root=self._data_root)
        resolved = storage_locations_from_config(merged, data_root=self._data_root)
        migrations: list[LocationMigration] = []
        if resolved.projects_root != existing.projects_root:
            migrations.append(LocationMigration(PROJECT_LOCATION, existing.projects_root, resolved.projects_root))
        if resolved.ai_cache_root != existing.ai_cache_root:
            migrations.append(LocationMigration(AI_CACHE_LOCATION, existing.ai_cache_root, resolved.ai_cache_root))
        return migrations

    @staticmethod
    def _error_response(code: str, message: str, *, stage: str) -> dict[str, Any]:
        return {"success": False, "error": {"code": code, "message": message, "stage": stage}}
