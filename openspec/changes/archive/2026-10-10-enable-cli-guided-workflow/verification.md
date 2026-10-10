# CLI 引导流程交付与验证记录

验证日期：2026-10-10。范围：`enable-cli-guided-workflow`，按 Matt to-tickets、implement／TDD／code-review 流程完成。未提交或推送 Git；混合工作区的其他修改保持原状。

## 已交付行为

CLI 支持图片／视频草稿字段补丁、参考图及首尾帧、历史草稿恢复、三步参数保存及显式执行、页面导航、角色／动画精确多选、两种裁剪方式、过程文件及 AI 缓存安全读取和素材复用。运行中复用应用 API；回执区分持久化、界面同步和任务状态。离线保存明确返回未同步；有效根不一致或迁移要求重启时拒绝操作。

生成授权默认关闭。设置中尝试开启时说明并确认，取消保持关闭；确认后即时保存，重启读取、不出现启动确认，关闭立即生效。普通设置草稿和 CLI 不能开启授权。每次远端提交检查最新状态；重复请求保留既有回执，未知提交不自动重试。技能另要求当前对话首次提交取得用户确认；隔离开关验收的允许不代表付费生成授权。

首次抽帧遗漏完成标识已补齐，真实新项目抽取 6 帧后能够导航第二步；处理参数仅更新当前步骤的预览 FPS。取消开关的原生复选框状态漂移已修复。裁剪部分失败或音频错误不会被投影为完整可导出结果。

## 真实桌面证据

使用独立 `GAM CLI 验收` 窗口、控制端口 9876、`.scratch/enable-cli-guided-workflow/desktop-data` 数据根和空 API Key。原用户应用未被操作。用户明确允许隔离开关确认；取消、确认开启、重启保持开启、关闭及关闭提交拒绝均完成，最终开关关闭。

真实桌面与共享控制 API 完成草稿填入／清空／非法补丁拒绝、历史恢复、缓存图复用、三步保存与执行、不同页面导航、多角色两种裁剪模式、素材分页读取、非默认 FPS 显示及首次抽帧到第二步。步骤 2 使用本机已有模型，无下载；步骤 1／2／3 均有实际输出。角色的音频清单随两种裁剪结果生成。

证据保留在 `.scratch/enable-cli-guided-workflow/`：`navigation-desktop-results.json`、`live-control-results.json`、`processing-desktop-results.json`、`permission-enabled-evidence.json`、`draft-desktop-results.json`、`trim-desktop-results.json`、`fresh-project-desktop-results.json`。曾因验收脚本显式传入仓库根误建测试项目；改为隔离根后验收通过，误建目录已清理。

## 验证结果与限制

| 检查 | 结果 |
| --- | --- |
| 后端全量 pytest | 730 passed，2 skipped |
| 前端全量 npm test | 380 passed，0 failed |
| 前端 typecheck | 通过 |
| 前端 build | 通过 |
| 前端全仓 lint | 未通过：1 个已有 `select-repro.ts` 组件命名错误、1112 warnings；本次修改无新增错误 |
| 全仓 Ruff | 未通过：固定基线 48 项，当前 47 项，新增 0 项；比较证据 `ruff-baseline-comparison.json` |
| 本次独立新文件／修改范围 Ruff 与 format | 通过；既有文件问题按固定基线另记 |
| 五项技能 quick_validate | 全部通过；有效资源源目录与共享库逐文件一致，排除 macOS 元数据 |
| gam-export 生成器测试 | 6 passed |
| Godot 4.6.3 官方 headless 导入／运行 | 通过，`godot-runtime.log` 返回 failures=[]、passed=true |
| git diff --check | 通过 |
| 媒体 full 标记套件 | 未运行：未修改去背／挖空／对齐算法；实际隔离三步处理已执行 |
| 真实付费 AI 提交 | 未执行；请求边界、关闭零调用、重复和未知状态用隔离测试验证 |
| Godot 人工视觉／听觉 | 编辑器已打开并看到导出精灵；实际动画帧序、锚点观感及音效听感尚未人工验收 |

Godot 从实际全局／逐角色裁剪目录生成四个场景，涵盖普通／偏移帧、12／20 FPS、最终零基触发帧 0／2、循环触发、反向静音、暂停／停止清理播放和原速 pitch=1。生成器测试覆盖偏移与索引；无界面运行结果不代表人工听感通过。

两名独立复核者分别按规格与代码规范审查最后改动，未发现未解决阻断项；其最后复核为只读源码和文档复核，测试与桌面结果采用主线程证据。

## 规格覆盖

### cli-generation-permission

| 需求 | 验证证据 |
| --- | --- |
| CLI 生成授权默认关闭且只能在设置中确认开启 | tests/test_cli_generation_permission.py、test_agent_navigation.py；前端权限测试；真实取消／确认／重启／关闭证据；未知远端隔离测试 |
| 程序在每次 CLI 远端提交前校验有效开关 | tests/test_cli_generation_permission.py、test_agent_navigation.py；前端权限测试；真实取消／确认／重启／关闭证据；未知远端隔离测试 |
| Agent 每个新对话首次提交前取得确认 | tests/test_cli_generation_permission.py、test_agent_navigation.py；前端权限测试；真实取消／确认／重启／关闭证据；未知远端隔离测试 |
| 生成状态与再次生成和下载语义可区分 | tests/test_cli_generation_permission.py、test_agent_navigation.py；前端权限测试；真实取消／确认／重启／关闭证据；未知远端隔离测试 |

### cli-local-artifacts

| 需求 | 验证证据 |
| --- | --- |
| 角色与动画列表支持精确多选 | tests/test_agent_artifacts.py、test_agent_cli.py；实际素材复用和两种裁剪目录／音频证据 |
| 多选裁剪支持两种模式和导出交接 | tests/test_agent_artifacts.py、test_agent_cli.py；实际素材复用和两种裁剪目录／音频证据 |
| 可发现过程文件和 AI 生成缓存 | tests/test_agent_artifacts.py、test_agent_cli.py；实际素材复用和两种裁剪目录／音频证据 |
| 文件读取保留可用溯源并控制内容边界 | tests/test_agent_artifacts.py、test_agent_cli.py；实际素材复用和两种裁剪目录／音频证据 |
| 本地素材可用于继续创建草稿 | tests/test_agent_artifacts.py、test_agent_cli.py；实际素材复用和两种裁剪目录／音频证据 |

### cli-workspace-control

| 需求 | 验证证据 |
| --- | --- |
| CLI 按字段更新生成草稿并保留其他内容 | tests/test_agent_drafts.py、test_agent_navigation.py、test_agent_steps.py；前端草稿／导航测试；真实桌面草稿、三步与页面证据 |
| 再次生成恢复草稿而非提交任务 | tests/test_agent_drafts.py、test_agent_navigation.py、test_agent_steps.py；前端草稿／导航测试；真实桌面草稿、三步与页面证据 |
| 三步处理参数具有明确的 CLI 支持范围 | tests/test_agent_drafts.py、test_agent_navigation.py、test_agent_steps.py；前端草稿／导航测试；真实桌面草稿、三步与页面证据 |
| 参数保存与界面同步具有可验证回执 | tests/test_agent_drafts.py、test_agent_navigation.py、test_agent_steps.py；前端草稿／导航测试；真实桌面草稿、三步与页面证据 |
| 三步处理复用同一项目的实际参数 | tests/test_agent_drafts.py、test_agent_navigation.py、test_agent_steps.py；前端草稿／导航测试；真实桌面草稿、三步与页面证据 |
| CLI 可导航现有功能界面 | tests/test_agent_drafts.py、test_agent_navigation.py、test_agent_steps.py；前端草稿／导航测试；真实桌面草稿、三步与页面证据 |

### gam-guidance-skills

| 需求 | 验证证据 |
| --- | --- |
| gam 系列技能使用中文书写 | 五技能结构／资源核验；三种起点及授权情境文档走查；6 项导出测试与 Godot 运行证据（人工听感待验收） |
| 主流程支持三种起点和逐步反馈 | 五技能结构／资源核验；三种起点及授权情境文档走查；6 项导出测试与 Godot 运行证据（人工听感待验收） |
| 教练遵守草稿和生成授权边界 | 五技能结构／资源核验；三种起点及授权情境文档走查；6 项导出测试与 Godot 运行证据（人工听感待验收） |
| gam-guide 提供参数功能与配置说明 | 五技能结构／资源核验；三种起点及授权情境文档走查；6 项导出测试与 Godot 运行证据（人工听感待验收） |
| 裁剪结果交接到 Godot 并明确音频帧规则 | 五技能结构／资源核验；三种起点及授权情境文档走查；6 项导出测试与 Godot 运行证据（人工听感待验收） |

## 技能源与部署

- `gam-guide`、`gam-workflow`、`gam-pic-prompt`、`gam-video-prompt`：本仓库 `.agents/skills/<名称>` 为源。
- `gam-export`：`/Users/hy/.local/share/gam-export/gam-export` 为源，保留既有生成器。
- 共享库：`/Users/hy/.skills-manager/skills/<名称>`；已部署至 Claude Code、Codex、Kimi、TRAE CN。部署清单见 `skill-deployment-results.json`。
- `.agents/`、`docs/` 和 scratch 被当前忽略规则排除，技能源、说明和本地 tickets 不会自动进入 Git；未改忽略规则或强制暂存。归档内本记录提供可追踪交付边界。

## 同步与归档

四项增量均为新增需求，共 20 项；同步时创建对应主规格，保留 Purpose、所有需求和场景，仅将 ADDED Requirements 转为 Requirements。归档前核对主规格正文完全一致，执行严格校验。人工观感／听感及付费生成属于明确未执行的验收项，不被计作通过。
