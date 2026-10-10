@tool
class_name AnimationConfig
extends Resource

## 该配置对应的动画名称
@export var animation_name: String = ""

## 逐帧精灵偏移量（帧索引 -> Vector2）
@export var frame_offsets: Dictionary = {}


## 获取指定帧的偏移量
func get_frame_offset(frame_idx: int) -> Vector2:
	if frame_offsets.has(frame_idx):
		var offset_data = frame_offsets[frame_idx]
		if offset_data is Vector2:
			return offset_data
		elif offset_data is Dictionary:
			return Vector2(
				offset_data.get("x", 0.0),
				offset_data.get("y", 0.0)
			)
	return Vector2.ZERO

## Frame-indexed sound events; indexes refer to exported SpriteFrames.
@export var audio_events: Array[Dictionary] = []
