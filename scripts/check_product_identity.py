#!/usr/bin/env python3
"""Reject obsolete product identifiers outside explicit legacy contexts."""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

FORBIDDEN_IDENTIFIERS = (
    "VIDEO_TO_SHEET_",
    "Video to Sheet",
    "VideoToSheet",
    "video-to-sheet",
    "video_to_sheet",
)

IGNORED_PARTS = {
    ".codegraph",
    ".git",
    ".pytest_cache",
    ".test-runs",
    ".venv",
    "__pycache__",
    "dist",
    "htmlcov",
    "node_modules",
}

HISTORICAL_PREFIXES = (
    ".scratch/",
    ".superpowers/",
    "docs/adr/",
    "docs/archive/",
    "docs/product/",
    "docs/research/",
    "docs/specs/",
    "openspec/changes/archive/",
)

# These entries assert explicit compatibility boundaries. Keep this list small
# and remove exemptions as the corresponding migration is completed.
ALLOWLISTED_FILES = {
    "scripts/check_product_identity.py",
    "tests/test_data_isolation.py",
    "tests/test_product_identity.py",
    "tests/test_rembg_model.py",
}

LEGACY_MARKERS = (
    "legacy",
    "old-",
    "old ",
    "historical",
    "旧版",
    "旧的",
    "旧 ",
)


@dataclass(frozen=True)
class Violation:
    path: str
    line_number: int
    identifier: str
    line: str


def _is_ignored(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    return any(part in IGNORED_PARTS for part in relative.parts)


def _is_allowed(relative_path: str, line: str) -> bool:
    if relative_path in ALLOWLISTED_FILES:
        return True
    if relative_path.startswith(HISTORICAL_PREFIXES):
        return True
    lowered = line.lower()
    return any(marker in lowered for marker in LEGACY_MARKERS)


def iter_text_files(root: Path) -> Iterable[Path]:
    tracked = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        capture_output=True,
        check=False,
    )
    if tracked.returncode == 0:
        candidates = (root / item for item in tracked.stdout.decode("utf-8").split("\0") if item)
    else:
        candidates = root.rglob("*")
    for path in sorted(candidates):
        if path.is_file() and not path.is_symlink() and not _is_ignored(path, root):
            yield path


def find_violations(root: Path) -> list[Violation]:
    root = root.resolve()
    violations: list[Violation] = []
    for path in iter_text_files(root):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        relative_path = path.relative_to(root).as_posix()
        for line_number, line in enumerate(lines, start=1):
            if _is_allowed(relative_path, line):
                continue
            for identifier in FORBIDDEN_IDENTIFIERS:
                if identifier in line:
                    violations.append(Violation(relative_path, line_number, identifier, line.strip()))
                    break
    return violations


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    violations = find_violations(args.root)
    if not violations:
        print("Product identity check passed.")
        return 0

    print("Obsolete product identifiers found:")
    for violation in violations:
        print(
            f"{violation.path}:{violation.line_number}: "
            f"{violation.identifier!r}: {violation.line}"
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
