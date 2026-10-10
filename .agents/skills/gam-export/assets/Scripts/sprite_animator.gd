@tool
class_name SpriteAnimtor
extends AnimatedSprite2D

## ============================================================================
## Sprite Animator - 轻量化动画预览工具
## 专注于逐帧偏移调整和编辑器内的播放控制
## ============================================================================

# -----------------------------------------------------------------------------
# 动画配置
# -----------------------------------------------------------------------------
@export_group("动画配置")

## 动画配置列表 (键: 动画名称, 值: AnimationConfig 资源)
@export var animation_configs: Array[AnimationConfig] = []

# -----------------------------------------------------------------------------
# 播放控制 (通过编辑器面板操作)
# -----------------------------------------------------------------------------
@export_group("播放控制")

# 内部存储选中的动画名称
var _preview_animation: String = ""

## 当前预览的帧索引 (上限为当前动画最大帧数-1)
@export var preview_frame: int = 0:
	set(value):
		var max_frame = _get_max_frame_count()
		if max_frame > 0:
			preview_frame = clampi(value, 0, max_frame - 1)
		else:
			preview_frame = 0
		_preview_frame = preview_frame
		_update_preview()

## 播放速度 (每秒帧数)
@export_range(0.1, 60.0, 0.1) var playback_fps: float = 10.0

## 是否正在循环播放
@export var preview_playing: bool = false:
	set(value):
		preview_playing = value
		if preview_playing:
			_start_preview()
		else:
			_stop_preview()

# -----------------------------------------------------------------------------
# 动态属性列表 (实现下拉菜单的关键)
# -----------------------------------------------------------------------------

func _get_property_list() -> Array[Dictionary]:
	var properties: Array[Dictionary] = []

	# 获取当前 SpriteFrames 中所有的动画名称
	var anim_names: PackedStringArray = [""] # 默认留一个空选项
	if sprite_frames:
		anim_names.append_array(sprite_frames.get_animation_names())

	# 将数组转为逗号分隔的字符串，用于生成下拉列表
	var hint_string = ",".join(anim_names)

	# 动态添加 preview_animation 属性到面板
	properties.append({
		"name": "preview_animation",
		"type": TYPE_STRING,
		"usage": PROPERTY_USAGE_DEFAULT,
		"hint": PROPERTY_HINT_ENUM,
		"hint_string": hint_string
	})

	return properties

# Godot 属性系统回调：读取动态属性 preview_animation
func _get(property: StringName):
	if property == &"preview_animation":
		return _preview_animation
	return null

# Godot 属性系统回调：写入动态属性 preview_animation，切换动画后重置帧索引
func _set(property: StringName, value: Variant) -> bool:
	if property == &"preview_animation":
		_stop_audio()
		_preview_animation = value
		# 切换动画时的逻辑
		var max_frame = _get_max_frame_count()
		if _preview_frame >= max_frame:
			_preview_frame = 0
			preview_frame = 0
		_update_preview()
		# 强制刷新面板，确保 preview_frame 的范围或其他关联属性更新
		notify_property_list_changed()
		return true
	return false

# -----------------------------------------------------------------------------
# 运行时状态变量
# -----------------------------------------------------------------------------
var _frame_timer: float = 0.0
var _preview_frame: int = 0

# 运行时追踪用
var _last_animation: StringName = &""
var _last_frame: int = -1
var _audio_players: Array[AudioStreamPlayer] = []
var _audio_started: bool = false
signal audio_triggered(frame_index: int, stream: AudioStream)

# 用于检测 SpriteFrames 资源是否变化
var _cached_sprite_frames: SpriteFrames = null

# -----------------------------------------------------------------------------
# 生命周期回调
# -----------------------------------------------------------------------------
# 编辑器模式下自动启动预览；运行时连接帧变化信号并记录初始状态
func _ready():
	if Engine.is_editor_hint():
		_start_preview()
	if not frame_changed.is_connected(_on_frame_changed):
		frame_changed.connect(_on_frame_changed)
	animation_changed.connect(_on_animation_changed)
	animation_finished.connect(_stop_audio)
	_last_animation = animation
	_last_frame = frame
	_apply_frame_offset()

# 编辑器模式下检测 SpriteFrames 资源变化并刷新面板，运行时检测帧变化以应用偏移
func _process(delta: float):
	if Engine.is_editor_hint():
		if sprite_frames != _cached_sprite_frames:
			_cached_sprite_frames = sprite_frames
			notify_property_list_changed()
		_process_editor(delta)
	else:
		if not is_playing() or get_playing_speed() <= 0:
			_stop_audio()
		elif not _audio_started:
			_audio_started = true
			_trigger_audio(frame)
		if animation != _last_animation or frame != _last_frame:
			_apply_frame_offset()
			_last_animation = animation
			_last_frame = frame

# -----------------------------------------------------------------------------
# 编辑器预览方法
# -----------------------------------------------------------------------------
func _start_preview():
	_stop_audio()
	_frame_timer = 0.0
	_update_preview()
	if preview_playing:
		_trigger_audio(frame)

func _stop_preview():
	_stop_audio()

# 编辑器模式下按 playback_fps 推进预览帧
func _process_editor(delta: float):
	if not preview_playing:
		return

	_frame_timer += delta
	var frame_time = 1.0 / playback_fps

	if _frame_timer >= frame_time:
		_frame_timer -= frame_time
		_advance_frame()

# 编辑器预览：前进到下一帧并同步属性面板
func _advance_frame():
	if _preview_animation.is_empty() or not sprite_frames:
		return

	var frame_count = sprite_frames.get_frame_count(_preview_animation)
	if frame_count == 0:
		return

	_preview_frame = (_preview_frame + 1) % frame_count
	preview_frame = _preview_frame # 更新导出属性以同步面板
	_update_preview()
	if preview_playing:
		_trigger_audio(_preview_frame)

# 将当前预览的动画和帧同步到 AnimatedSprite2D，并应用偏移配置
func _update_preview():
	if not sprite_frames or _preview_animation.is_empty():
		return

	# 同步动画名称和帧
	animation = _preview_animation
	frame = _preview_frame

	# 应用偏移配置
	_apply_frame_offset()

# -----------------------------------------------------------------------------
# 帧偏移应用逻辑
# -----------------------------------------------------------------------------
func _apply_frame_offset():
	if not sprite_frames or animation.is_empty():
		return

	var config = _get_animation_config(animation)
	if not config:
		# 如果没有配置，重置偏移为零
		self.offset = Vector2.ZERO
		return

	var frame_offset = config.get_frame_offset(frame)
	# 应用时取反：让锚点对齐到节点位置
	# AnimationConfig 中存储的 offset 表示锚点相对于精灵中心的偏移
	# Godot offset 需要反向移动精灵，使锚点固定在节点位置
	self.offset = - frame_offset
	queue_redraw()

# 运行时帧变化回调：编辑器内不处理，避免与预览逻辑冲突
func _on_frame_changed() -> void:
	if Engine.is_editor_hint():
		return
	_apply_frame_offset()
	if is_playing() and get_playing_speed() > 0:
		_audio_started = true
		_trigger_audio(frame)
	else:
		_stop_audio()
	_last_frame = frame

# 运行时外部调用：播放指定动画并立即应用当前帧偏移
func play_with_offset(anim_name: StringName = &"", custom_speed: float = 1.0, from_end: bool = false) -> void:
	play(anim_name, custom_speed, from_end)
	_apply_frame_offset()
	_last_animation = animation
	_last_frame = frame

# 运行时外部调用：反向播放指定动画并立即应用当前帧偏移
func play_backwards_with_offset(anim_name: StringName = &"") -> void:
	play_backwards(anim_name)
	_apply_frame_offset()
	_last_animation = animation
	_last_frame = frame

func _get_max_frame_count() -> int:
	"""获取当前动画的总帧数"""
	if not sprite_frames or _preview_animation.is_empty():
		return 0
	if not sprite_frames.has_animation(_preview_animation):
		return 0
	return sprite_frames.get_frame_count(_preview_animation)

func _get_animation_config(anim_name: String) -> AnimationConfig:
	"""从数组中查找匹配动画名称的配置"""
	for config in animation_configs:
		if config and config.animation_name == anim_name:
			return config
	return null

# -----------------------------------------------------------------------------
# 公共控制方法 (可供外部或脚本调用)
# -----------------------------------------------------------------------------
func play_pause() -> void:
	"""切换播放/暂停状态"""
	preview_playing = not preview_playing

func next_frame() -> void:
	"""手动进入下一帧"""
	_advance_frame()

func previous_frame() -> void:
	"""手动返回上一帧"""
	if _preview_animation.is_empty() or not sprite_frames:
		return

	var frame_count = sprite_frames.get_frame_count(_preview_animation)
	if frame_count == 0:
		return

	_preview_frame = (_preview_frame - 1 + frame_count) % frame_count
	preview_frame = _preview_frame
	_update_preview()


func _stop_audio() -> void:
	for player in _audio_players:
		player.stop()
		player.queue_free()
	_audio_players.clear()
	_audio_started = false


func _trigger_audio(frame_index: int) -> void:
	var config = _get_animation_config(animation)
	if not config:
		return
	for event in config.audio_events:
		if event.get("frame", -1) != frame_index:
			continue
		var stream = event.get("stream") as AudioStream
		if not stream:
			continue
		var player := AudioStreamPlayer.new()
		player.stream = stream
		add_child(player)
		_audio_players.append(player)
		player.finished.connect(func():
			_audio_players.erase(player)
			player.queue_free()
		)
		player.play()
		audio_triggered.emit(frame_index, stream)


func _on_animation_changed() -> void:
	_stop_audio()
	_apply_frame_offset()


func stop_with_offset() -> void:
	_stop_audio()
	stop()
	_apply_frame_offset()


func pause_with_audio() -> void:
	_stop_audio()
	pause()
