"""Step and parameter explanations for Agent-guided workflows."""

from copy import deepcopy
from typing import Any

STEP_EXPLANATIONS: dict[int, dict[str, Any]] = {
    1: {
        "step": 1,
        "name": "Frame extraction",
        "purpose": "Export selected video frames into the project frame output.",
        "requires_review": False,
        "parameters": [
            {
                "name": "frame_interval",
                "effect": "Exports every Nth frame. Higher values reduce frame count and smoothness.",
                "recommended": "1 for full animation quality; 2 or more for quick previews.",
                "risk": "Large intervals can make animation choppy.",
            },
            {
                "name": "start_frame",
                "effect": "First frame index to export.",
                "recommended": "Use 0 unless trimming the beginning.",
                "risk": "A value after the action start can remove important motion.",
            },
            {
                "name": "end_frame",
                "effect": "Last frame index to export; -1 means the end of the video.",
                "recommended": "-1 for full video, or a specific frame for action clips.",
                "risk": "Too small a value can cut off the animation.",
            },
        ],
    },
    2: {
        "step": 2,
        "name": "Background removal",
        "purpose": "Remove the background and produce transparent PNG frames.",
        "requires_review": True,
        "parameters": [
            {
                "name": "model",
                "effect": "Selects the rembg model used for segmentation.",
                "recommended": "u2net is the only supported background-removal model.",
                "risk": "Different models can change edge quality and subject retention.",
            },
            {
                "name": "alpha_matting",
                "effect": "Improves transparent edge transitions.",
                "recommended": "Enabled for most sprite extraction work.",
                "risk": "Can be slower and may need threshold tuning.",
            },
            {
                "name": "alpha_matting_erode_size",
                "effect": "Controls edge contraction before matting.",
                "recommended": "Start at 5.",
                "risk": "Too high can eat into the subject edge.",
            },
            {
                "name": "alpha_matting_background_threshold",
                "effect": "Controls what is treated as background.",
                "recommended": "Start at 120.",
                "risk": "Too low or high can leave background residue or remove subject details.",
            },
            {
                "name": "alpha_matting_foreground_threshold",
                "effect": "Controls what is treated as definite foreground.",
                "recommended": "Start at 240.",
                "risk": "Wrong values can make edges harsh or incomplete.",
            },
            {
                "name": "edge_erode",
                "effect": "Applies final edge erosion to reduce residue.",
                "recommended": "Start at 1.",
                "risk": "Too high removes fine details.",
            },
        ],
    },
    3: {
        "step": 3,
        "name": "Hole punching and alignment",
        "purpose": "Remove green-screen holes and optionally align sprite frames.",
        "requires_review": True,
        "parameters": [
            {
                "name": "green_intensity",
                "effect": "Controls green detection strength.",
                "recommended": "Start at 3.",
                "risk": "Too high may remove intended green details.",
            },
            {
                "name": "feather_radius",
                "effect": "Softens hole edges.",
                "recommended": "Start at 3.",
                "risk": "Too high can blur or expand transparent edges.",
            },
            {
                "name": "min_hole_size",
                "effect": "Ignores holes smaller than this pixel area.",
                "recommended": "Start at 5.",
                "risk": "Too high can preserve unwanted holes; too low can remove noise.",
            },
            {
                "name": "align_h",
                "effect": "Horizontally centers sprites.",
                "recommended": "Enable when animation jitters horizontally.",
                "risk": "Can change intended lateral motion.",
            },
            {
                "name": "align_v",
                "effect": "Bottom-aligns sprites vertically.",
                "recommended": "Enable for character animations grounded on a baseline.",
                "risk": "Can change intended vertical motion.",
            },
            {
                "name": "padding_bottom",
                "effect": "Adds bottom padding after alignment.",
                "recommended": "Start at 10.",
                "risk": "Too much padding wastes texture space.",
            },
        ],
    },
}


def explain_step(step: int, parameter: str | None = None) -> dict[str, Any]:
    """Return a structured explanation for a step or one parameter."""
    if step not in STEP_EXPLANATIONS:
        raise ValueError(f"Unsupported step: {step}")

    explanation = STEP_EXPLANATIONS[step]
    if parameter is None:
        return deepcopy(explanation)

    for item in explanation["parameters"]:
        if item["name"] == parameter:
            return {
                "step": step,
                "parameter": deepcopy(item),
                "requires_review": explanation["requires_review"],
            }
    raise ValueError(f"Unsupported parameter for step {step}: {parameter}")
