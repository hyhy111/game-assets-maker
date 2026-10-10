---
name: gam-guide
description: 解释 Game Assets Maker 的功能、处理参数、配置、数据目录和 CLI 命令。用于查阅说明书、理解调参效果或排查操作错误。
---

# Game Assets Maker 说明书

默认用户已安装软件。按当前问题查阅对应参考，结合实际界面、CLI help 和本地文件回答；版本差异先核对当前能力。需要补充信息时一次只问一个问题。

- 软件功能、三步参数、音频和配置：阅读 [references/manual.md](references/manual.md)。
- 准备草稿、查询素材、处理任务和裁剪命令：阅读 [references/cli.md](references/cli.md)。
- 用户希望从当前素材继续制作：使用 `gam-workflow`。
- 用户只要图像或动作提示词：使用 `gam-pic-prompt` 或 `gam-video-prompt`。
- 用户希望导入 Godot：使用 `gam-export`，输入以实际裁剪回执为准。

解释参数时给出作用、当前值、合法范围、调整方向和应观察的画面变化。读取用户当前动画保存参数，避免把默认值说成正在使用的值。区分命令执行成功、文件已保存、界面已同步和实际素材质量；质量结论需要查看具体图像或播放片段。
