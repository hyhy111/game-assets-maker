# 验收记录

日期：2026-10-01。之前 tasks.md 中的测试和实机记录为历史证据，以下单独列出本轮检查。

## 完整性、正确性与一致性

- 13/13 任务完成；3 条要求均存在对应实现。
- `backend/main.py` 的 `on_window_closing` 通过 daemon worker 延后警告派发并返回 False，空闲和确认退出保留正常路径。
- `on_window_closed` 尝试每个清理步骤并在 finally 发出信号；`_exit_after_cleanup` 有限等待，成功清理才重启，失败/超时以状态 1 退出。
- `tests/test_main_exit.py`、`tests/test_app_restart.py` 和关闭警告测试覆盖清理失败、成功退出、重启顺序、超时及关闭交互契约。
- `backend/seedream/manager.py` 保留已保存响应的下载恢复及未保存响应的 unknown 状态，不自动重新提交付费请求；相关 manager 测试覆盖恢复。
- `frontend/src/views/SeedreamBatchDetail.vue` 仅选择 download_failed 且未过期的图片，顺序调用已有 retryDownload；store 将失败转为 false，因此一张失败不会中止后续下载。单张时保留独立按钮，批量期间禁用删除和重复点击。

## 本轮检查与警告

后端 659 passed / 2 skipped，前端 347 passed；typecheck、build、相关 Python Ruff check、`git diff --check` 与 strict validation 通过。

- 批量重试 UI 没有新增专门的交互回归用例；其过滤、顺序重试和失败继续行为已做源码审查，但本轮实机点击仍未验证。
- 本轮未重新运行 macOS 窗口关闭。tasks.md 保留此前实机记录；本轮通过测试验证后续清理失败分支。
- 全量 frontend lint 仍被既有 `select-repro.ts:5` 阻挡；4 个 Python 文件格式检查未通过，详见 audit 记录。
- Jev gate 向 TypeSafe 发送实现和证据被自动审批拒绝，未运行。

本地检查未发现关键缺项；场景覆盖与实机验证的限制如上，归档保留警告。
