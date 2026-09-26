#!/usr/bin/env python3
"""
Optionally download U2Net for local development.
Release builds do not bundle model weights.
"""

import os
import sys
from pathlib import Path

# Set the model directory before importing rembg.
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
MODELS_DIR = PROJECT_ROOT / "models" / "rembg"
MODELS_DIR.mkdir(parents=True, exist_ok=True)
os.environ["U2NET_HOME"] = str(MODELS_DIR)

# Supported model for optional local download
AVAILABLE_MODELS = [
    "u2net",  # Default, general purpose (~176MB)
]


def download_model(model_name: str) -> bool:
    """Download a single model"""
    from src.core.rembg_model import download_u2net, validate_model

    try:
        print(f"Downloading {model_name}...", end=" ", flush=True)
        validate_model(model_name)
        download_u2net(MODELS_DIR)
        print(f"✓ Done ({MODELS_DIR / (model_name + '.onnx')})")
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        return False


def main():
    """Download all models"""
    print(f"Models will be saved to: {MODELS_DIR}\n")

    # Parse arguments
    if len(sys.argv) > 1:
        if sys.argv[1] in ["--help", "-h"]:
            print("Usage: python download_models.py [model_name]")
            print("\nAvailable models:")
            for m in AVAILABLE_MODELS:
                print(f"  - {m} (~176MB)")
            print("\nExamples:")
            print("  python download_models.py           # Download all models")
            print("  python download_models.py u2net     # Download specific model")
            return
        else:
            models_to_download = [sys.argv[1]]
    else:
        # Default: download the supported model
        models_to_download = AVAILABLE_MODELS
        print("Downloading U2Net:\n")

    success_count = 0
    for model in models_to_download:
        if download_model(model):
            success_count += 1

    print(f"\n{success_count}/{len(models_to_download)} models downloaded successfully.")
    print(f"Models location: {MODELS_DIR}")

    # Calculate total size
    total_size = sum(f.stat().st_size for f in MODELS_DIR.glob("*.onnx") if f.is_file())
    print(f"Total size: {total_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
