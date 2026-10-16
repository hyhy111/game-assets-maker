---
name: gam-cli
description: 使用 gam-agent CLI 操作 gam。用于填入图片或视频提示词与参考图、打开页面、查询任务和素材、执行本地处理与裁剪，以及按授权提交 AI 生成任务。
---

# gam CLI

直接使用 `gam-agent` 完成用户要求的gam操作，无须先调用 `gam-guide` 或 `gam-workflow`。用户要求“填入提示词框”时，优先通过 CLI 更新草稿；只要求写提示词时，保持为文本输出。

向用户说明界面选项、草稿状态或操作结果时，务必使用界面当前语言的显示名称；先查阅 [字段与界面名称映射](references/ui-field-names.md)。

## 执行与验证

1. 先按 [固定 CLI 入口](references/cli.md#固定-cli-入口) 查找用户数据目录下的启动入口：macOS 为 `~/.gam/gam-agent`，Windows 为 `%USERPROFILE%\.gam\gam-agent.cmd`；明确设置 `GAM_DATA_ROOT` 时先查该目录。直接使用入口的绝对路径执行 `doctor` 和目标子命令的 `--help`，无需先检查 PATH。固定入口缺失或失效时再查已知安装目录，具体回退见参考文档。源码开发环境使用仓库内的 Python：Windows 为 `.venv/Scripts/python.exe -m src.cli.agent`，macOS 为 `.venv/bin/python -m src.cli.agent`。按当前运行环境选择入口，沿用明确的 `GAM_DATA_ROOT`、`GAM_DATA_MODE` 和 `GAM_CONFIG`，核对 CLI 与应用的数据及项目根一致。
2. 执行前阅读 [references/cli.md](references/cli.md) 中对应操作的说明。界面导航、草稿和直接生成需要运行中的应用；连接或项目根不匹配时先诊断，再执行目标操作。
3. 根据用户意图选择图片或视频草稿，读取当前草稿后，优先用 `draft patch --kind image|video` 的独立参数按需填写：提示词用 `--prompt`，参考图用 `--reference-image`，视频首帧／尾帧用 `--first-frame`／`--last-frame`，推荐时长可用 `--duration`。仅传本次需要修改的参数，其他参数保持原值；按当前 shell 的规则安全引用提示词和路径，长文本或不便安全引用的多行内容可用 `--prompt-file` 读取 UTF-8 纯文本。参数与清空／开关用法见参考文档。旧 CLI 的 help 未提供独立参数时才回退到 `--patch-json`。填写后读取草稿，核对提示词及所改字段，并确认 `data.ui_sync=applied`；用过临时文本／JSON 文件时在完成后清理。
4. 对其他操作检查实际回执。异步处理跟踪 `task_id` 到终态；超时或无回执时用原 `request_id` 查询，再决定下一步。请求、持久化、界面同步与素材质量分别报告，画面质量需要查看真实媒体。

视频草稿和生成请求的 `duration` 只能配置为 4、5、6 秒。用户要求填入视频提示词草稿时，若该提示词附有具体建议时长，可同时将建议写入 `duration`，仅将提示词正文写入 `prompt`；用户明确指定的时长优先。没有建议或明确指定时保持已有合法时长，需要设置且缺少可用值时采用 5 秒。已有草稿或历史任务使用其他时长时，先说明限制并确认改为哪个合法时长，再继续；智能时长不能保证 4～6 秒，因此不使用。

填写草稿完成后让用户在gam中检查和发送。只有用户要求直接提交生成时，才进入参考文档的“CLI 生成授权”流程；填写草稿本身不代表提交授权。

## 生成前的账号与 Key 配置

用户询问 ForFuner AI 登录、积分购买、自定义 Key 配置，或生成因鉴权／余额／模型权限受阻时，阅读 [AI 生成方式与配置](../gam-guide/references/ai-generation-setup.md)。新用户优先推荐登录 ForFuner AI；自定义 Key 按参考指导用户在火山引擎完成充值门槛、模型开通和本机配置。沿用用户已选方式，不把草稿补丁当作切换生成方式的接口。登录、验证码、付款和密钥输入由用户在对应界面完成；CLI 仅执行当前 help 支持且已授权的操作。

## 按需衔接

- 只需gam功能、参数或配置说明：使用 `gam-guide`。
- 需要写图像或动作提示词：使用 `gam-pic-prompt` 或 `gam-video-prompt`，已有提示词直接使用。
- 需要连续制作、调参和结果检查：使用 `gam-workflow`。
- 需要将裁剪结果导入 Godot：使用 `gam-export`。
