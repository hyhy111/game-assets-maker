"""Step and parameter explanations for Agent-guided workflows."""

from copy import deepcopy
from typing import Any

STEP_EXPLANATIONS: dict[int, dict[str, Any]] = {
    1: {
        "step": 1,
        "name": "帧提取",
        "purpose": "按已保存的起始、结束帧与间隔输出序列帧。",
        "requires_review": False,
        "parameters": [
            {
                "name": "frame_interval",
                "effect": "每隔 N 帧提取一帧；数值越大，帧数越少。",
                "default": 1,
                "recommended": "默认值：1",
                "risk": "大间隔可能造成动作跳跃。",
            },
            {
                "name": "start_frame",
                "effect": "从零开始的首个提取帧索引。",
                "default": 0,
                "recommended": "默认值：0",
                "risk": "过晚的起点会丢失动作开头。",
            },
            {
                "name": "end_frame",
                "effect": "最后提取帧索引；-1 表示直到末尾。",
                "default": -1,
                "recommended": "默认值：-1",
                "risk": "应不小于起始帧。",
            },
            {
                "name": "fps",
                "effect": "预览播放速度，范围 1–60；不改变帧提取间隔。",
                "default": 30,
                "recommended": "默认值：30",
                "risk": "各动画可使用不同的预览 FPS。",
            },
        ],
    },
    2: {
        "step": 2,
        "name": "背景去除",
        "purpose": "使用本地模型输出带透明通道的 PNG。",
        "requires_review": True,
        "parameters": [
            {
                "name": "model",
                "effect": "选择本地分割模型，目前支持 u2net。",
                "default": "u2net",
                "recommended": "默认值：u2net",
                "risk": "执行前模型必须就绪。",
            },
            {
                "name": "alpha_matting",
                "effect": "优化半透明边缘。",
                "default": True,
                "recommended": "默认值：True",
                "risk": "可能增加处理时间。",
            },
            {
                "name": "alpha_matting_erode_size",
                "effect": "抠图前的腐蚀大小，范围 0–20。",
                "default": 5,
                "recommended": "默认值：5",
                "risk": "过大会损失细节。",
            },
            {
                "name": "alpha_matting_background_threshold",
                "effect": "背景阈值，范围 0–255。",
                "default": 120,
                "recommended": "默认值：120",
                "risk": "必须小于前景阈值。",
            },
            {
                "name": "alpha_matting_foreground_threshold",
                "effect": "前景阈值，范围 100–250。",
                "default": 240,
                "recommended": "默认值：240",
                "risk": "不当阈值可能损伤主体边缘。",
            },
            {
                "name": "edge_erode",
                "effect": "旧参数：最终边缘腐蚀。",
                "default": 1,
                "recommended": "默认值：1",
                "risk": "新 CLI 补丁不支持调整此字段。",
            },
            {
                "name": "fps",
                "effect": "预览播放速度，范围 1–60；不改变帧提取间隔。",
                "default": 10,
                "recommended": "默认值：10",
                "risk": "各动画可使用不同的预览 FPS。",
            },
        ],
    },
    3: {
        "step": 3,
        "name": "挖空与对齐",
        "purpose": "清理主体内部背景，并可对齐动画帧。",
        "requires_review": True,
        "parameters": [
            {
                "name": "enabled",
                "effect": "开启挖空处理。",
                "default": True,
                "recommended": "默认值：True",
                "risk": "主体自身背景色区域也可能被清除。",
            },
            {
                "name": "green_intensity",
                "effect": "检测强度，范围 1–5。",
                "default": 3,
                "recommended": "默认值：3",
                "risk": "过高可能损伤主体颜色。",
            },
            {
                "name": "feather_radius",
                "effect": "羽化半径，范围 0–10。",
                "default": 3,
                "recommended": "默认值：3",
                "risk": "过大可能模糊透明边缘。",
            },
            {
                "name": "min_hole_size",
                "effect": "最小挖空面积，范围 0–500 像素。",
                "default": 5,
                "recommended": "默认值：5",
                "risk": "过大可能保留细小背景区域。",
            },
            {
                "name": "align_enabled",
                "effect": "开启帧对齐。",
                "default": False,
                "recommended": "默认值：False",
                "risk": "关闭时水平、底部对齐不起作用。",
            },
            {
                "name": "align_h",
                "effect": "水平居中；须开启帧对齐。",
                "default": False,
                "recommended": "默认值：False",
                "risk": "可能改变原有横向位移。",
            },
            {
                "name": "align_v",
                "effect": "底部对齐；须开启帧对齐。",
                "default": False,
                "recommended": "默认值：False",
                "risk": "可能改变跳跃轨迹。",
            },
            {
                "name": "padding_bottom",
                "effect": "旧参数：对齐后的底部留白。",
                "default": 10,
                "recommended": "默认值：10",
                "risk": "新 CLI 补丁不支持调整此字段。",
            },
            {
                "name": "fps",
                "effect": "预览播放速度，范围 1–60；不改变帧提取间隔。",
                "default": 10,
                "recommended": "默认值：10",
                "risk": "各动画可使用不同的预览 FPS。",
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
