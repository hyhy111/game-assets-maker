"""Shared primitives for interruptible local model downloads."""


class ModelDownloadCancelledError(Exception):
    """Raised when the user cancels an in-progress model download."""
