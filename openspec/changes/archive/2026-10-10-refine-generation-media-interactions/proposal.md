# Proposal

## Why

2026-10-01 的需求访谈已确认：图片参考复用、参考图显示、素材目录入口、图片拖拽及编辑百分比输入存在交互缺口，API 调用详情日志也需要明确开发模式边界。本变更把六项需求转为中文约束与可验收场景，供后续独立实施。

## What Changes

- 图片详情新增“作为参考图生图”：返回图片输入页，填入或替换唯一参考图，保留输入页已有提示词及参数；优先使用已保存的编辑结果。
- 图片详情顶部删除任务左侧依次放置“另存为图片”和“打开目录”两个图标按钮，移动已有另存按钮而不重复添加；图标浅灰、具有悬停过渡和提示。视频详情在另存视频后增加“打开目录”。
- 图片编辑的角色高度和底部留白统一四舍五入为整数，允许 0% 底部留白，约束二者之和不超过 100%。
- 修复图片详情生成配置中的参考图，以及图生图任务创建后输入区域参考图缩略图的显示。
- 图片输入区域、视频首帧及尾帧区域接收单张本地文件或应用内生成图片拖拽；多张拒绝，替换时保留提示词和参数。
- **BREAKING（行为兼容性变化）**：自定义 Key 的 `ark-custom-key.jsonl` 从默认记录改为仅开发模式下可手动开启，默认关闭、切换立即生效；普通运行与安装版强制关闭，保留旧日志。

## Capabilities

### New Capabilities

- `generation-media-interactions`：图片详情参考复用、详情素材操作栏、参考图预览和单图拖拽。
- `image-edit-layout-values`：图片编辑百分比整数归一化及布局有效性约束。

### Modified Capabilities

- `custom-key-generation-audit`：为生命周期记录和持久化意图要求增加开发模式与开关前提，新增默认关闭及即时切换要求；原有隐私边界与账号生成隔离继续有效。

## Impact

- 前端：`SeedreamBatchDetail.vue`、`SeedancePreview.vue`、`SeedreamCreate.vue`、`SeedanceCreate.vue`、`SeedreamImageEraser.vue`、`SeedanceImagePicker.vue`、统一设置页 `SeedanceSettings.vue`，相关 stores、API 类型、应用内拖拽协议和双语文案。
- 后端：Seedream/Seedance 媒体路径解析与详情 API、系统目录打开入口、参考图 URL 装饰、`ArkAudit`、应用配置和开发运行能力暴露。
- 验证：现有 Seedream/Seedance 测试、自定义 Key 审计测试、配置测试及前端交互测试；增加无付费 API 调用的验收证据。
- 无新增依赖、无缓存或项目数据迁移；保持 `.gam` 数据路径契约。原始需求清单保持原样，本变更及已确认访谈构成实施依据。
