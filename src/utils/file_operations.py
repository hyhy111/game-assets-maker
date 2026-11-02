"""Bounded retries for transient Windows rename failures."""

import os
import sys
import time
from pathlib import Path

_RENAME_DELAYS = (0.05, 0.1, 0.2, 0.4)


def rename_path(source: Path, target: Path, *, replace: bool = False) -> None:
    """Preserve rename/replace semantics while allowing short-lived Windows handles to close."""
    for attempt in range(len(_RENAME_DELAYS) + 1):
        try:
            operation = os.replace if replace else os.rename
            operation(source, target)
            return
        except OSError as error:
            if (
                sys.platform != "win32"
                or getattr(error, "winerror", None) not in {5, 32, 33}
                or attempt == len(_RENAME_DELAYS)
            ):
                raise
            time.sleep(_RENAME_DELAYS[attempt])
