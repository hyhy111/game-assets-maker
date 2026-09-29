# Proposal

## Why

旧项目批量迁移卡片中的浏览器原生下拉框与目标动画输入框高度和项目控件风格不一致，且用户不能直接关闭这张临时工作卡片。资源库标题同时重复展示中英文品牌文本，设置页的九个下拉框也仍使用原生控件，造成体验割裂。

## What Changes

- 将旧项目批量迁移映射中的目标角色下拉框替换为项目共享的 Headless UI 下拉控件，匹配目标动画输入框高度、宽度和键盘可访问性。
- 在旧项目批量迁移卡片右上角增加关闭按钮；关闭仅隐藏当前页面会话中的映射工作区，不迁移、删除或修改项目数据。
- 移除资源库标题中的“游戏资产”，将保留的 `Game Assets` 提升为与右侧刷新/更多操作行对齐的唯一标题。
- 将 `SeedanceSettings.vue` 中所有原生下拉框（Seedance 默认值、Seedream 默认值与缓存保留时长）替换为同一项目共享下拉控件，保持原有选项、绑定类型、依赖修正逻辑与测试标识。

## Capabilities

### New Capabilities

- `legacy-migration-workspace`: 定义旧项目批量迁移映射卡片的可关闭工作区与资源库标题层级。
- `selection-control-consistency`: 定义迁移映射和统一设置页的非原生、键盘可访问选择控件及其尺寸一致性。

### Modified Capabilities

无。

## Impact

- `frontend/src/views/ProjectManager.vue`、`frontend/src/views/SeedanceSettings.vue` 及共享下拉组件。
- 对应的前端源代码与组件交互测试；不修改后端导入、迁移、设置持久化或 AI 缓存存储逻辑。
- 之前的 `merge-selected-storage-targets` 仍独立负责项目和 AI 缓存目录的非空目标迁移行为。
