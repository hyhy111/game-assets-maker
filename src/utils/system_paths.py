"""Open validated directories with the platform file manager."""

import os
import subprocess
import sys
from pathlib import Path


def open_directory(path: Path) -> None:
    directory = path.resolve(strict=True)
    if not directory.is_dir():
        raise NotADirectoryError("The requested directory is not available")
    if sys.platform == "win32":
        os.startfile(str(directory))
    else:
        command = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.run([command, str(directory)], check=True)
