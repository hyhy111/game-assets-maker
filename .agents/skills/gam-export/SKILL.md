---
name: gam-export
description: 将 gam 的普通 PNG 序列、逐帧裁剪偏移和按帧触发音频导入 Godot 4，生成动画资源与可播放预览场景。
---

# gam 导出

将 gam 已处理好的素材导入 Godot 4，生成动画配置和可播放的预览场景。此 skill 负责导出与 Godot 验证，可作为制作指导 skill 的最后一步。

## 引导流程

1. 确定素材目录与目标 `project.godot`。读取实际目录，判断输入是单个动作还是包含多个动作的目录。面向新用户，每次说明一个当前步骤；需要补充信息时一次只问一个问题。
2. 有 `_frame_data.json` 时，读取 `output_name`、帧序与 offset；没有时，按文件名的数字自然顺序读取 PNG，偏移为零。普通序列应使用统一画布和对齐位置；不同尺寸但没有偏移数据时，先说明可能抖动并让用户确认对齐方式。
3. 有 `_audio_timeline.json` 时，使用其 `animation_fps` 和 `clips[].placement_frame`，关联同目录的 `file`。这些触发帧已经映射到最终导出序列，索引从 0 开始；向用户说明时换算为第几张图片。`source_placement_frame` 仅用于溯源，不再次换算。没有音频清单时仅导出动画，不猜测 WAV 的触发位置。
4. 没有 FPS 元数据时询问播放速度，通过 `--fps` 指定。默认 10 FPS 仅是 CLI 回退值，不代表源视频帧率。默认 idle/walk/run 循环，其他动作不循环；按用户意图用 `--loop` 增加循环动作。
5. 运行本 skill 内的 `scripts/generate.py`。素材在 Godot 项目之外时，复制到 `ArtAssets/<prefix>/`，保留源文件。输出已存在时先检查差异，再根据用户授权使用 `--yes`；该参数也会替换支持脚本。不要默认覆盖用户修改过的脚本。`--skip-scripts` 仅用于目标脚本已经兼容 `audio_events` 的项目。
6. 在 Godot 中打开生成场景：选择动作，检查帧顺序、速度、透明背景、锚点与音效位置，再运行场景。检查首帧音效、循环、动作切换与停止。记录实际完成的验证；无界面的导入和运行不证明画面质量或扬声器出声。

## 运行方式

从此 SKILL.md 所在目录解析脚本路径，避免绑定某个 agent 的安装路径。

```bash
python3 <skill-dir>/scripts/generate.py <素材目录> <资源前缀> --project <Godot项目目录>
python3 <skill-dir>/scripts/generate.py <素材目录> <资源前缀> --project <Godot项目目录> --fps 12 --loop 怒吼
```

输入可以是直接包含 PNG 的动作目录，也可以包含若干动作子目录。仅复制被使用的 PNG、音效和两种元数据，不复制工程缓存或源视频。缺失帧、缺失音频、越界触发帧或重复动作名会报错，修复后再运行。

## Godot 输出与控制

- `ArtAssets/<prefix>/`：项目外素材的副本。
- `Resources/Animations/<prefix>/<prefix>_<action>_config.tres`：偏移与音效事件。
- `Scenes/Animator/<prefix>.tscn`：含 SpriteFrames 的 AnimatedSprite2D 预览场景，自动播放首个动作。
- `Scripts/animation_config.gd` 与 `Scripts/sprite_animator.gd`：配置和播放支持。

运行时用 `play_with_offset(动作名)` 播放，`stop_with_offset()` 停止，`pause_with_audio()` 暂停。停止、暂停、切换动作或播放结束时停止当前音效；循环时每轮按帧触发，同帧多音效可重叠。直接调用原生 pause/stop 的状态会在下一次 process 检测；需要同步停止音效时用上述包装方法。反向播放只应用偏移，不触发音效。

编辑器预览使用 preview_animation、preview_frame、preview_playing、playback_fps。手动逐帧检查保持静音，启用播放时触发音效。导入已有项目后确认导出的 AnimationConfig 支持 audio_events。
