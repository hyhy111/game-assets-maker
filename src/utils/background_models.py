"""Platform background-removal capabilities shared by config and processing."""

import sys

LITE_MODEL = "birefnet-lite-onnx"


def background_models() -> tuple[str, ...]:
    return ("u2net", LITE_MODEL) if sys.platform == "win32" else ("u2net", "birefnet-comfy")


def default_background_model() -> str:
    return LITE_MODEL if sys.platform == "win32" else "u2net"


def is_birefnet(model: str) -> bool:
    return model in ("birefnet-comfy", LITE_MODEL)
