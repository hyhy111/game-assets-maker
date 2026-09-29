# 实施任务

## 1. 后端目录识别与数据保护

- [x] 1.1 在旧版项目导入边界实现有序候选解析：先检查所选目录，再检查其直接子目录 `project/`，返回实际来源和冻结后的有效项目列表；新增直接选择、选择父目录、候选优先级和禁止递归搜索测试，并运行 `.venv/bin/python -m pytest -q tests/test_new_ui_smoke.py -k "import_legacy_project_directory"` 验证通过。
- [x] 1.2 将当前项目目录保护移动到实际来源解析之后，保持严格元数据校验、暂存复制、同名跳过、源目录保留和单项目失败清理语义；扩充当前目录、无效元数据、同名冲突和部分失败覆盖，并运行同一后端聚焦测试验证通过。

## 2. 前端按需入口与反馈

- [x] 2.1 删除主页常驻导入卡片，在动画库标题刷新按钮旁增加 Headless UI“更多”菜单，并在空项目状态增加轻量文字入口；两个入口复用现有导入处理函数和 loading 状态，更新 `frontend/tests/project-manager-home.test.mjs` 后运行 `cd frontend && node --experimental-strip-types --test tests/project-manager-home.test.mjs` 验证入口结构与调用链。
- [x] 2.2 将导入反馈改为仅在尝试后渲染、可关闭且带 `aria-live="polite"` 的局部提示，显示实际来源及导入、跳过、失败数量；更新中英文文案和对应前端测试，并再次运行项目管理页聚焦测试验证成功、失败与取消选择行为。

## 3. 集成验证

- [x] 3.1 从仓库根目录运行 `.venv/bin/python -m pytest -q`、`uv run ruff check .` 和 `uv run ruff format --check .`，确认导入变更未破坏后端回归与代码规范；将环境限制与产品失败分开记录。
- [x] 3.2 从 `frontend/` 运行 `npm test`、`npm run lint`、`npm run typecheck` 和 `npm run build`，再从仓库根目录运行 `git diff --check`，确认入口、国际化、类型与生产构建完整通过。
