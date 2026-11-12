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
        "name": "背景移除",
        "purpose": "使用所选本地模型生成透明 PNG，整批成功后替换当前结果。",
        "requires_review": True,
        "parameters": [
            {
                "name": "model",
                "effect": "选择 u2net（rembg）或 birefnet-comfy（BiRefNet，Comfy-Org）。",
                "default": "u2net",
                "recommended": "默认值：u2net",
                "risk": "模型须就绪。重新去背成功后会清除步骤 03 结果和逐帧修整。",
            },
            {
                "name": "alpha_matting",
                "effect": "在 u2net 路径中优化半透明边缘。",
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
        "name": "后处理",
        "purpose": "按挖孔、缩减边缘、对齐的顺序运行已启用的工具。",
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
                "name": "alpha_contrast",
                "effect": "Alpha 对比度，范围 0.5–3.0；大于 1 半透明边缘更硬，小于 1 更柔和。",
                "default": 1.0,
                "recommended": "默认值：1.0（模型原始输出）",
                "risk": "过高会削掉弱alpha细节并产生锯齿。",
            },
            {
                "name": "alpha_threshold",
                "effect": "Alpha 阈值，范围 0–254；截断低于阈值的半透明像素。",
                "default": 0,
                "recommended": "默认值：0（关闭）",
                "risk": "过高会削掉该保留的柔和边缘。",
            },
            {
                "name": "defringe_enabled",
                "effect": "开启边缘去色。",
                "default": False,
                "recommended": "边缘残留背景色/白边时开启。",
                "risk": "过强会让边缘颜色发闷。",
            },
            {
                "name": "defringe_px",
                "effect": "去色宽度，范围 0–20 像素。",
                "default": 2,
                "recommended": "默认值：2",
                "risk": "过宽可能影响接近边缘的主体颜色。",
            },
            {
                "name": "defringe_amount",
                "effect": "去色强度，范围 0.0–1.0。",
                "default": 0.5,
                "recommended": "默认值：0.5",
                "risk": "过强会让边缘颜色发闷。",
            },
            {
                "name": "min_foreground_area",
                "effect": "最小前景面积，范围 0–1000000；更小的孤立碎块被删除。",
                "default": 0,
                "recommended": "默认值：0（关闭）",
                "risk": "过大可能删除小道具或碎片特效。",
            },
            {
                "name": "fill_holes_max_size",
                "effect": "填充前景内部孔洞的面积上限，范围 0–1000000。",
                "default": 0,
                "recommended": "默认值：0（关闭）",
                "risk": "过大可能填掉主体内部的合理镂空。",
            },
            {
                "name": "edge_shrink_enabled",
                "effect": "开启缩减边缘。",
                "default": False,
                "recommended": "默认值：False",
                "risk": "仅在需要收紧轮廓时开启。",
            },
            {
                "name": "edge_shrink_px",
                "effect": "轮廓向内收缩的像素数，范围 0–100，须为整数。",
                "default": 0,
                "recommended": "默认值：0",
                "risk": "过大可能移除细小结构。",
            },
            {
                "name": "edge_feather_px",
                "effect": "新轮廓向内羽化的宽度，范围 0–100 像素。",
                "default": 0,
                "recommended": "默认值：0",
                "risk": "过大可能使轮廓变淡。",
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
