## Why

新用户需要 Agent 连贯指导 Game Assets Maker 的素材生成、三步处理和 Godot 导入；现有 CLI 虽能执行部分流程，却不能把生成草稿、保存参数和运行中的界面可靠衔接。补足可查询、可同步、受用户授权约束的接口，并提供中文操作教练与说明书，让用户能检查每一步结果后继续制作。

## What Changes

- CLI 可查询并按字段更新图片／视频草稿，包括提示词、唯一参考图、首／尾帧和现有生成参数；复用“再次生成”恢复草稿，不自动提交。
- CLI 支持用户指定的步骤 1／2／3 参数读取、修改、保存、执行，并同步运行中界面；支持现有功能页面跳转。
- 查询角色及其动画，多选执行统一包围盒或逐帧紧致裁剪，返回帧目录、偏移及音频清单供 `gam-export` 使用。
- 提供过程文件与 AI 缓存的列表、元数据和受控读取，供 Agent 判断结果、选择参考素材与复用历史提示词风格。
- 设置增加默认关闭的“允许 CLI 提交 AI 生成任务”；用户尝试开启时弹窗说明并确认，取消不启用，关闭立即阻止后续 CLI 提交。读取、草稿和本地处理不受此开关限制。
- **BREAKING**：现有 `gam-agent seedance create` 不能继续绕过开关直接提交；图片和视频 CLI 提交统一受该开关约束。已有查询、本地处理命令和桌面手动发送保留。
- 新增中文主流程教练 `gam-workflow` 和说明书 `gam-guide`，复用 `gam-pic-prompt`、`gam-video-prompt` 与 `gam-export`；gam 系列说明与指引统一中文。主流程在当前对话首次提交生成前要求确认，确认后本对话后续任务不重复确认，新对话重新确认。

## Capabilities

### New Capabilities

- `cli-workspace-control`：生成草稿、处理参数、执行回执与页面跳转。
- `cli-local-artifacts`：角色／动画查询、多选裁剪及过程文件、AI 缓存发现和读取。
- `cli-generation-permission`：设置授权、实时提交校验与对话首次确认的边界。
- `gam-guidance-skills`：中文教练、说明书、提示词与 Godot 导出衔接。

### Modified Capabilities

无。沿用存储路径及现有素材复用规格；不修改其需求。

## Impact

- `src/cli/agent.py`、`src/agent_tools/`、`backend/agent_control/`、`backend/main.py`：扩展 JSON 命令契约和运行时调用。
- 项目、处理、裁剪、图片／视频 API 与现有缓存仓库：复用处理及校验逻辑，补齐稳定投影和权限边界。
- `frontend/src/composables/useAgentControl.ts`、`stores/aiCreation.ts`、`stores/process.ts`、统一设置页及类型、本地化：草稿／参数同步、回执和授权弹窗。
- `src/utils/app_config.py`：新增缺省关闭配置，通过现有数据路径持久化；遵循自定义项目和 AI 缓存根。
- `.agents/skills/gam-*/`：规划中文技能及参考文档；既有共享 `gam-export` 的来源与部署在实施时先核对，不在本方案阶段更新共享库。
- 现有 CLI／控制接口／存储／生成测试及真实桌面交互验收。不新增依赖、账户／积分规则或媒体处理算法。
