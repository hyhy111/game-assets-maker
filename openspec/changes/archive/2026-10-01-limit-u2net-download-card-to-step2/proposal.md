# Proposal

## Why

帧提取不依赖 U2Net，但步骤 1 当前预加载背景移除模型并无条件显示模型状态卡；当 U2Net 尚未安装时，用户会在错误的工作步骤看到首次下载提示。首次下载的决策与背景移除属于步骤 2。

## What Changes

- 移除步骤 1 对 U2Net 状态卡的渲染与模型预加载，不在帧提取阶段显示下载来源、下载或重试入口。
- 由步骤 2 独立检查和准备当前背景移除模型；仅当 U2Net 缺失、正在准备或准备失败时显示模型状态卡。
- 当 U2Net 已可用时，步骤 2 不显示首次下载卡，且背景移除的现有可执行性判定保持不变。
- 保留用户选择下载来源、进度、失败重试、后端模型状态 API 与模型文件持久化行为；下载来源选择器改用项目共享的非原生选择控件，并保持默认选择、键盘操作和重试来源传递。

## Capabilities

### New Capabilities

- `background-removal-model-readiness`: 定义 U2Net 缺失时的下载提示、步骤归属与背景移除前的模型就绪条件。

### Modified Capabilities

无。

## Impact

- `frontend/src/views/Editor/Step1Extract.vue`、`frontend/src/views/Editor/Step2Background.vue`、`frontend/src/components/editor/ModelStatusCard.vue` 和前端模型状态测试。
- 不修改模型下载来源、校验、存储路径或后端预加载 API；不引入自动下载。
