"""
Safe error log collection system
Features:
- Config-controlled switch, disabled by default
- Log size limit to avoid filling the disk
- Scheduled old log cleanup
- Multiple exception guards to prevent recursive writes
"""

import json
import logging
import os
import threading
import time
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.utils.app_config import get_app_config_path, merge_app_config
from src.utils.data_paths import data_root


class SafeLogger:
    """Safe log collector."""

    def __init__(self, config_path: str | Path | None = None):
        self.config_path = Path(config_path) if config_path else get_app_config_path()
        self.config = self._load_config()
        self.logger = None
        self.cleanup_thread = None
        self._lock = threading.Lock()
        self._write_count = 0
        self._last_cleanup_check = 0
        self._cleanup_interval = 3600  # Check once per hour.
        self._max_write_count = 1000  # Safety threshold to prevent recursive writes.

        # Initialize logger when logging is enabled.
        if self.config.get("logger_enabled", False):
            self._init_logger()

    def _load_config(self) -> dict:
        """Load config file."""
        try:
            if self.config_path.exists():
                with open(self.config_path, encoding="utf-8") as f:
                    return merge_app_config(json.load(f))
        except Exception as e:
            # Use default config if reading config fails.
            print(f"Warning: Cannot load config: {e}")

        return merge_app_config()

    def _init_logger(self):
        """Initialize logger."""
        try:
            logger_config = self.config.get("logger_config", {})
            log_dir = self._log_dir()

            # Ensure log directory exists.
            Path(log_dir).mkdir(parents=True, exist_ok=True)

            # Create logger.
            self.logger = logging.getLogger("GameAssetsMakerLogger")
            self.logger.setLevel(logging.ERROR)

            # Avoid adding duplicate handlers.
            if self.logger.handlers:
                self.logger.handlers.clear()

            # Configure rotating file handler.
            max_size = logger_config.get("max_log_size_mb", 10) * 1024 * 1024  # Convert to bytes.
            backup_count = logger_config.get("max_log_files", 5)

            log_file = os.path.join(log_dir, "error.log")
            file_handler = RotatingFileHandler(log_file, maxBytes=max_size, backupCount=backup_count, encoding="utf-8")

            # Configure formatter.
            formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
            file_handler.setFormatter(formatter)
            file_handler.setLevel(logging.ERROR)

            self.logger.addHandler(file_handler)

            # Start cleanup thread.
            self._start_cleanup_thread()

        except Exception as e:
            print(f"Failed to initialize logger: {e}")
            self.logger = None

    def _start_cleanup_thread(self):
        """Start scheduled cleanup thread."""
        try:
            if self.cleanup_thread and self.cleanup_thread.is_alive():
                return

            self.cleanup_thread = threading.Thread(target=self._cleanup_worker, daemon=True)
            self.cleanup_thread.start()
        except Exception as e:
            print(f"Failed to start cleanup thread: {e}")

    def _cleanup_worker(self):
        """Scheduled cleanup worker thread."""
        while self.logger is not None:
            try:
                current_time = time.time()
                if current_time - self._last_cleanup_check >= self._cleanup_interval:
                    self._cleanup_old_logs()
                    self._last_cleanup_check = current_time
                time.sleep(300)  # Check every 5 minutes.
            except Exception as e:
                # Prevent cleanup exceptions from killing the thread.
                print(f"Cleanup error: {e}")
                time.sleep(3600)  # Wait 1 hour before retrying after an error.

    def _cleanup_old_logs(self):
        """Clean old log files."""
        try:
            with self._lock:
                logger_config = self.config.get("logger_config", {})
                log_dir = self._log_dir()
                max_days = logger_config.get("auto_cleanup_days", 30)
                cleanup_interval = logger_config.get("cleanup_interval_hours", 24)

                # Check cleanup interval.
                current_time = time.time()
                if hasattr(self, "_last_cleanup") and current_time - self._last_cleanup < cleanup_interval * 3600:
                    return
                self._last_cleanup = current_time

                if not os.path.exists(log_dir):
                    return

                # Clean log files older than the configured age.
                cutoff_time = current_time - (max_days * 24 * 3600)
                cleaned_count = 0

                for file_path in Path(log_dir).glob("*.log*"):
                    try:
                        if file_path.stat().st_mtime < cutoff_time:
                            file_path.unlink()
                            cleaned_count += 1
                    except Exception as e:
                        print(f"Failed to delete old log file {file_path}: {e}")

                if cleaned_count > 0:
                    print(f"Cleaned {cleaned_count} old log files")

        except Exception as e:
            print(f"Cleanup error: {e}")

    def _check_safety_conditions(self) -> bool:
        """Check safe-write conditions."""
        with self._lock:
            self._write_count += 1

            # Check write count to prevent recursive writes.
            if self._write_count > self._max_write_count:
                print("Safety stop: Maximum write count reached")
                return False

            # Reset counter every 1000 writes.
            if self._write_count >= self._max_write_count:
                self._write_count = 0

            return True

    def log_error(self, message: str, exception: Exception | None = None):
        """Log an error."""
        try:
            # Check whether logging is enabled.
            if not self.config.get("logger_enabled", False):
                return

            # Safety check.
            if not self._check_safety_conditions():
                return

            # Reload config to check whether logging was disabled.
            self.config = self._load_config()
            if not self.config.get("logger_enabled", False):
                return

            if self.logger is None:
                self._init_logger()

            if self.logger is None:
                return

            # Format error details.
            error_msg = f"ERROR: {message}"
            if exception:
                error_msg += f" - Exception: {str(exception)}"
                error_msg += f"\nTraceback: {traceback.format_exc()}"

            # Write log entry.
            self.logger.error(error_msg)

        except Exception as e:
            # Prevent log-write failures from raising.
            print(f"Logging failed: {e}")

    def log_info(self, message: str):
        """Log an info message for debugging only."""
        try:
            if not self.config.get("logger_enabled", False):
                return

            if not self._check_safety_conditions():
                return

            self.config = self._load_config()
            if not self.config.get("logger_enabled", False):
                return

            if self.logger is None:
                self._init_logger()

            if self.logger is None:
                return

            self.logger.info(f"INFO: {message}")

        except Exception as e:
            print(f"Info logging failed: {e}")

    def log_warning(self, message: str):
        """Log a warning."""
        try:
            if not self.config.get("logger_enabled", False):
                return

            if not self._check_safety_conditions():
                return

            self.config = self._load_config()
            if not self.config.get("logger_enabled", False):
                return

            if self.logger is None:
                self._init_logger()

            if self.logger is None:
                return

            self.logger.warning(f"WARNING: {message}")

        except Exception as e:
            print(f"Warning logging failed: {e}")

    def force_cleanup(self):
        """Force log file cleanup."""
        self._cleanup_old_logs()

    def get_log_stats(self) -> dict:
        """Return log statistics."""
        try:
            log_dir = self._log_dir()

            if not os.path.exists(log_dir):
                return {"enabled": False, "log_dir": log_dir, "total_size": 0, "file_count": 0}

            total_size = 0
            file_count = 0

            for file_path in Path(log_dir).glob("*.log*"):
                try:
                    total_size += file_path.stat().st_size
                    file_count += 1
                except Exception:
                    continue

            return {
                "enabled": self.config.get("logger_enabled", False),
                "log_dir": log_dir,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "file_count": file_count,
            }
        except Exception:
            return {"enabled": False, "error": "Cannot get log stats"}

    def _log_dir(self) -> Path:
        configured = Path(self.config.get("logger_config", {}).get("log_dir", "logs")).expanduser()
        return configured if configured.is_absolute() else data_root() / configured


# Global logger instance.
_global_logger = None


def get_logger() -> SafeLogger:
    """Return global logger instance."""
    global _global_logger
    if _global_logger is None:
        _global_logger = SafeLogger()
    return _global_logger


def log_error(message: str, exception: Exception | None = None):
    """Convenience error logging function."""
    get_logger().log_error(message, exception)


def log_info(message: str):
    """Convenience info logging function."""
    get_logger().log_info(message)


def log_warning(message: str):
    """Convenience warning logging function."""
    get_logger().log_warning(message)


def force_cleanup():
    """Convenience force-cleanup function."""
    get_logger().force_cleanup()


if __name__ == "__main__":
    # Test logging system.
    print("Testing logger system...")

    # Test 1: disabled state.
    print("\n1. Testing disabled state:")
    log_info("This should not appear")
    log_error("This should not appear", Exception("Test error"))

    # Test 2: enabled logging.
    print("\n2. Testing enabled state:")
    # Manually set logger_enabled to true in config.json to test.
    stats = get_logger().get_log_stats()
    print(f"Log stats: {stats}")
