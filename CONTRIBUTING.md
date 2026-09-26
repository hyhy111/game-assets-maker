# Contributing

This project accepts focused, minimal changes that preserve the existing desktop pipeline and Vue UI behavior.

## Development Setup

Install Python dependencies with `uv`:

```bash
uv sync
```

Install frontend dependencies:

```bash
cd frontend
npm install
```

Run the WebView app in development mode:

```bash
uv run python dev_start.py
```

### Debugging in the app: the request/activation log panel

The WebView app deliberately runs with devtools disabled on Windows
(`backend/main.py`: `debug=True` can freeze WebView2), so the browser console is not
available. In development builds a log panel is rendered at the bottom-left of the
window instead, showing every HTTP request, every window-activation event, and why a
refresh was skipped (e.g. throttling). It is the intended way to observe payment,
session-recovery and refresh behaviour inside the real app.

To add your own entries, call `logEvent('...')` from `@/debug/request-log`. The panel
only exists in development builds: `logEvent` call sites are eliminated from production
bundles, and the panel component is bundled but never rendered.

## Code Standards

Python uses the Ruff configuration in `pyproject.toml`.

```bash
uv run ruff check .
uv run ruff format --check .
```

Frontend code uses ESLint, TypeScript, and Vite:

```bash
cd frontend
npm run lint
npm run typecheck
npm run build
```

Use auto-fix commands only for files related to your change:

```bash
uv run ruff check . --fix
uv run ruff format .
cd frontend
npm run lint:fix
npm run format
```

Do not reformat unrelated files or perform broad refactors as part of a small fix.

## Comments and UI Text

Code comments must be written in English. Existing non-English comments do not need to be rewritten in unrelated changes, but any comment you add or touch must be English.

Keep comments brief and useful:

- Explain why the code does something when the reason is not obvious.
- Do not restate what the next line of code already says.
- Prefer clear names and small functions over explanatory comments.
- Add comments before non-obvious processing steps, compatibility behavior, or external tool constraints.

The application UI may continue to use Chinese text. User-facing documentation for open-source release should be bilingual when practical.

## Tests

Run the default regression suite before submitting backend or processing changes:

```bash
.venv/bin/python -m pytest -q
```

Run the full processing pipeline before release or after changing background removal/post-processing logic:

```bash
.venv/bin/python -m pytest -q -m full
```

## Repository Hygiene

Do not commit local project data, generated output, logs, virtual environments, downloaded model files, or local agent/tool work directories.

Do not commit files under these local paths:

- `models/`
- `project/`
- `logs/`
- `input/`
- `output/`
- `frontend/dist/`
- `.venv/`
- `.mimocode/`

`pyproject.toml` and `uv.lock` are the Python dependency source of truth. `requirements.txt` is legacy compatibility information and should not be extended with new dependencies.

## Branches and Commits

Keep branches and commits focused on one purpose. Use clear commit messages that describe the behavior or repository policy changed.

Before opening a pull request, include the commands you ran and note any checks that could not be run.

# 贡献指南

本项目接受范围清晰、改动最小的贡献，避免在小修复中混入无关重构。

## 开发环境

Python 依赖使用 `uv` 安装：

```bash
uv sync
```

前端依赖：

```bash
cd frontend
npm install
```

开发模式启动：

```bash
uv run python dev_start.py
```

### 应用内调试：请求 / 激活日志面板

WebView 应用在 Windows 上刻意关闭了 devtools（`backend/main.py`：`debug=True` 会卡死
WebView2），所以浏览器控制台这条路不通。开发构建下，窗口左下角会渲染一个日志面板，
显示每一次 HTTP 请求、每一次窗口激活事件，以及刷新**为什么被跳过**（比如节流）。
观察支付、登录态恢复、刷新行为时，这是在实际应用里唯一可用的通道。

需要留痕时调 `@/debug/request-log` 的 `logEvent('...')`。该面板只存在于开发构建：
`logEvent` 的调用点会从生产产物中消除，面板组件虽会被打包但不会渲染。

## 代码规范

Python 使用 `pyproject.toml` 中的 Ruff 配置：

```bash
uv run ruff check .
uv run ruff format --check .
```

前端使用 ESLint、TypeScript 和 Vite：

```bash
cd frontend
npm run lint
npm run typecheck
npm run build
```

自动修复只应作用于本次修改相关文件，不要顺手格式化无关文件。

代码注释必须使用英文。无关改动不要求批量改写既有中文注释，但新增或修改任何注释时都必须改为英文。应用 UI 文案可以继续使用中文。

注释应简短且有实际价值：

- 说明“不明显的原因”，不要重复代码已经表达的内容。
- 优先通过清晰命名和拆分小函数减少注释需求。
- 对复杂处理步骤、兼容逻辑、外部工具限制添加必要说明。

不要提交本地项目数据、输出目录、日志、虚拟环境、下载的模型文件或本地代理工具目录。
