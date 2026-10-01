# Tasks

## 1. 步骤归属与模型状态显示

- [x] 1.1 为 U2Net 缺失、就绪、下载/初始化和失败状态补充步骤 1/步骤 2 卡片可见性测试，验证步骤 1 不调用模型预加载或下载入口。
- [x] 1.2 从步骤 1 移除模型状态卡和背景移除模型预加载，保留帧提取参数与处理流程；运行相关编辑器视图测试。
- [x] 1.3 收紧步骤 2 的模型状态卡可见性：仅在缺失、准备中或失败时显示，且模型就绪后隐藏；验证步骤 2 的处理按钮仍使用既有模型就绪门槛。

## 2. 下载交互回归

- [x] 2.1 将 `ModelStatusCard` 的下载来源原生选择器替换为项目共享的非原生选择控件，保持 `modelscope` 默认值、ModelScope/GitHub 选项及现有下载状态显示。
- [x] 2.2 更新模型状态组件/页面测试，验证缺失时步骤 2 仍提供 ModelScope/GitHub 来源、显式下载、进度和失败重试，且不触发自动下载；覆盖切换来源后下载或重试会传递当前来源，以及键盘聚焦、展开和选择。
- [x] 2.3 运行 `frontend/tests/model-status.test.mjs`、`frontend/tests/model-status-component.test.mjs` 和受影响编辑器测试，确认既有模型状态 API 绑定未改变。

## 3. 集成验证

- [x] 3.1 从 `frontend/` 运行受影响测试、`npm run lint`、`npm run typecheck` 与 `npm run build`，记录通过、产品失败和环境失败。
- [x] 3.2 检查最终 diff 仅涉及步骤 1、步骤 2、模型状态卡与相关测试，运行 `git diff --check`；如 Jev 可用，以最小 diff、完成声明和实际测试证据运行最终 gate。

验收记录（2026-10-01）：按步骤 1、步骤 2、模型状态卡与相关测试路径审查提交 `53a698e`，并核对当前实现。前端 347 passed，typecheck、build 与 `git diff --check` 通过。全量 lint 被既有 `frontend/src/select-repro.ts:5` 的保留组件名错误阻挡。Jev gate 未运行：自动审批拒绝向 TypeSafe 传输实现 diff 和证据，本地审查已完成。详见 `verification.md`。
