# Proposal

## Why

Game Assets Maker 已有桌面与 Agent CLI 打包入口，但应用版本、包元数据和发行包名称存在不同版本号，尚未形成可复现的安装包发布及应用更新流程。首次公开版本已确定为 `1.0.0`，需要把版本来源、平台打包、GitHub Releases 与用户更新连成完整链路。

## What Changes

本次只记录方案，不实施以下功能；其中已确认的产品方向与建议的技术选择在 `design.md` 中分别标明。

- 首次公开版本为 `1.0.0`，对应 Git tag `v1.0.0`；统一应用显示、GUI/CLI 版本、Windows 文件属性、macOS Bundle 元数据及安装包名称。
- 使用当前 `hyhy111/game-assets-maker` 仓库；开发期间保持私有，首次公开发布时由维护者将仓库转为公开，发行包与更新说明托管在 GitHub Releases。
- 第一阶段支持检查最新正式 Release、展示更新说明、按系统与架构下载安装包、显示进度、取消、重试和校验；用户退出应用后手动覆盖安装。
- 建议 Windows 使用 PyInstaller 的现有目录产物，再由 Inno Setup 生成安装程序；macOS 使用现有 `.app` Bundle 生成 DMG，首版暂不配置 Developer ID 分发签名与 Apple 公证，随包提供手动允许打开说明。
- 建议 GitHub Actions 在各目标操作系统的 runner 上构建、验证、汇总附件并创建 Release 草稿；维护者完成真实安装验收后正式发布。
- 私有阶段复用本机 GitHub 授权或仅限该仓库的短期只读凭证开展真实测试；公开发行版匿名查询与下载公开附件。
- 安装、升级和卸载保持稳定用户数据目录及已配置的自定义存储位置，不将模型权重、凭证或个人素材放入发行包。

## Capabilities

### New Capabilities

以下是后续规范阶段需要定义的能力，本次尚未创建 delta specs：

- `application-version`: 单一版本来源、构建元数据和 GUI/CLI/安装包版本一致性。
- `desktop-release-packaging`: Windows 安装程序、macOS DMG、架构标识和真实覆盖安装验收。
- `github-release-delivery`: 固定提交构建、各平台产物汇总、校验文件、Release 草稿与正式发布。
- `application-update-download`: 正式 Release 检测、版本比较、平台附件选择、更新说明与可校验的下载流程。

### Modified Capabilities

暂无。保留现有 `storage-location-management`、`cli-workspace-control` 和 `background-removal-model-readiness` 的行为与数据安全边界，后续规范不应重复定义或削弱这些能力。

## Impact

- 后续实现预计涉及 `pyproject.toml`、`uv.lock`、前端包版本及锁文件、`build.py`、`GameAssetsMaker.spec`、版本 API、设置页、类型与本地化。
- 后续新增平台封装脚本、Inno Setup 安装描述、GitHub Actions 工作流及更新检测/下载模块；本次不创建这些实现文件。
- Inno Setup 是 Windows 构建工具；GitHub CLI 可用于 CI 发布及本机私有测试，正式用户无需安装 GitHub CLI、Python 或 uv。
- 首版不引入 macOS Developer ID 签名或公证凭证；将来接入时仅进入受控 CI secrets 或维护者本机，不进入源码和发行包。
- 现有混合工作区保持原样；本次只新增该 OpenSpec change 的方案文档和脚手架元数据。
- 本次交付为 `proposal.md` 与 `design.md`。规范和任务清单留待 `/openspec-propose` 补齐，实施留待 `/openspec-apply-change`。
