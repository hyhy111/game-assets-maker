"""Persist normalized character-layout measurements beside edited images."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

_INTEGER_FIELDS = (
    "source_width",
    "source_height",
    "measured_top",
    "measured_bottom",
    "measured_height",
    "target_height",
    "bottom_distance",
)
_RATIO_FIELDS = ("character_height_ratio", "bottom_margin_ratio", "scale")


def layout_path(image_path: Path) -> Path:
    return image_path.with_name(f"{image_path.name}.layout.json")


def edit_source_path(image_path: Path) -> Path:
    return image_path.with_name(f"{image_path.name}.edit-source.png")


def validate_generation_layout(
    value: Any,
    *,
    width: int,
    height: int,
) -> dict[str, int | float]:
    if not isinstance(value, dict):
        raise ValueError("Generation layout must be an object")
    missing = [key for key in (*_INTEGER_FIELDS, *_RATIO_FIELDS) if key not in value]
    if missing:
        raise ValueError(f"Generation layout is missing {missing[0]}")

    layout: dict[str, int | float] = {}
    for key in _INTEGER_FIELDS:
        item = value[key]
        if not isinstance(item, int) or isinstance(item, bool):
            raise ValueError(f"Generation layout {key} must be an integer")
        layout[key] = item
    for key in _RATIO_FIELDS:
        item = value[key]
        if not isinstance(item, (int, float)) or isinstance(item, bool):
            raise ValueError(f"Generation layout {key} must be numeric")
        layout[key] = float(item)

    if layout["source_width"] != width or layout["source_height"] != height:
        raise ValueError("Generation layout dimensions must match the edited image")
    top = int(layout["measured_top"])
    bottom = int(layout["measured_bottom"])
    measured = int(layout["measured_height"])
    target = int(layout["target_height"])
    bottom_distance = int(layout["bottom_distance"])
    if top < 0 or bottom > height or top >= bottom or measured != bottom - top:
        raise ValueError("Generation layout character bounds are invalid")
    if target <= 0 or bottom_distance < 0 or target + bottom_distance > height:
        raise ValueError("Generation layout target placement is invalid")
    if abs(float(layout["character_height_ratio"]) - target / height) > 0.002:
        raise ValueError("Generation layout character ratio is inconsistent")
    if abs(float(layout["bottom_margin_ratio"]) - bottom_distance / height) > 0.002:
        raise ValueError("Generation layout bottom margin is inconsistent")
    if abs(float(layout["scale"]) - target / measured) > 0.002:
        raise ValueError("Generation layout scale is inconsistent")
    return layout


def read_generation_layout(image_path: Path, *, width: int, height: int) -> dict[str, int | float] | None:
    sidecar = layout_path(image_path)
    if not sidecar.is_file():
        return None
    try:
        return validate_generation_layout(
            json.loads(sidecar.read_text(encoding="utf-8")),
            width=width,
            height=height,
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def write_generation_layout(
    image_path: Path,
    value: Any,
    *,
    width: int,
    height: int,
) -> dict[str, int | float]:
    layout = validate_generation_layout(value, width=width, height=height)
    sidecar = layout_path(image_path)
    temporary = sidecar.with_name(f".{sidecar.name}.tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(layout, file, ensure_ascii=False, separators=(",", ":"))
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, sidecar)
    return layout


def copy_generation_layout(source: Path, destination: Path) -> None:
    source_sidecar = layout_path(source)
    if source_sidecar.is_file():
        shutil.copy2(source_sidecar, layout_path(destination))
    source_edit = edit_source_path(source)
    if source_edit.is_file():
        shutil.copy2(source_edit, edit_source_path(destination))


def delete_generation_layout(image_path: Path) -> None:
    layout_path(image_path).unlink(missing_ok=True)


def delete_edit_source(image_path: Path) -> None:
    edit_source_path(image_path).unlink(missing_ok=True)
