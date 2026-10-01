# Game Assets Maker

[English](#english) | [中文](#中文)

---

## 中文

Game Assets Maker 是一款桌面应用，把视频一键转换为**透明背景的游戏动画帧序列**，并内置 AI 图像 / 视频生成能力（Seedream / Seedance）。基于 PyWebView + Vue 3 + TailwindCSS。

### 核心功能

- **三步流水线**：视频抽帧 → rembg 背景移除（alpha matting）→ 绿幕打孔与精灵对齐
- **批量裁剪**：跨项目裁掉透明边缘，支持全局统一包围盒或逐帧紧致裁剪（含偏移 JSON）
- **AI 生成**：Seedream 文生图 / 图生图，Seedance 视频生成，本地缓存与历史记录
- **项目管理**：角色 / 动作两级项目结构，每步参数独立保存
- **像素后处理滤镜**：描边、孤立像素清理、边缘优化、颜色替换

### 技术栈

- 后端：Python 3.12、PyWebView、OpenCV、Pillow、rembg
- 前端：Vue 3 + TypeScript + Vite + Pinia + TailwindCSS
- 打包：PyInstaller（`GameAssetsMaker.spec`）

### 快速开始

```bash
# Python 依赖（需要 uv）
uv sync

# 前端依赖
cd frontend && npm install && cd ..

# 开发模式（Vite 热更新 + PyWebView）
uv run python dev_start.py

# 生产模式（先构建前端）
cd frontend && npm run build && cd ..
uv run python -m backend.main
```

### 模型准备

背景移除依赖 rembg 模型（不随仓库分发）。首次使用时会自动下载，也可以提前手动下载：

```bash
python scripts/download_models.py        # 全部模型（约 530MB）
python scripts/download_models.py u2net  # 仅默认模型
```

详见 [MODELS.md](MODELS.md)。

### 自定义 Key 调用日志

使用自定义 Ark API Key 生成图片或视频时，应用会在数据目录的 `logs/ark-custom-key.jsonl` 记录调用过程。开发模式默认为当前工作区的 `logs/`，安装版默认为 `~/.gam/logs/`；`GAM_DATA_ROOT` 会改变数据目录。该日志独立于设置中的“启用错误日志”。

同一 `call_id` 对应一次 Ark 调用。`intent` 表示客户端准备发起请求，`http_response` 表示收到 HTTP 响应，`parsed_response` 表示响应已解析，`response_persisted` 或 `task_persisted` 表示可恢复信息已保存。`elapsed_ms` 是截至该事件的毫秒数。视频的 `video.get` 是任务状态查询；图片的 `download_*` 表示本地下载阶段。日志只记录模型、时间、HTTP 状态、可用的请求 ID、用量和 URL 是否存在，不包含 Key、提示词原文、图片数据或下载 URL。

如果日志只有 `intent` 而没有响应事件，远端是否收到请求、是否生成或计费仍无法由客户端确定，需要以火山控制台记录为准。登录账号使用的云端生成逻辑不写入这份自定义 Key 日志。日志按大小轮转，最多保留 5 个归档文件；旧任务不会被追溯补记。

### 测试

```bash
uv run python scripts/run_tests.py            # 默认回归套件（无需 API Key）
uv run python scripts/run_tests.py full-local # 完整本地媒体流水线
uv run python scripts/run_tests.py all-free   # 全部免费测试 + JSON 报告
```

部分测试依赖视频 fixtures，可用 `python scripts/generate_test_fixtures.py` 重新生成。

### 打包发行

```bash
uv run python build.py
```

### 说明

应用内的登录 / 积分等云端功能为可选扩展，依赖自建后端服务；本地素材处理能力不依赖任何账号。

### 许可证

[MIT](LICENSE) © ForFuner

---

## English

Game Assets Maker is a desktop application that converts videos into **transparent game animation frame sequences**, with built-in AI image / video generation (Seedream / Seedance). Built with PyWebView + Vue 3 + TailwindCSS.

### Features

- **3-step pipeline**: frame extraction → rembg background removal (alpha matting) → green-screen hole punching & sprite alignment
- **Batch trim**: crop transparent margins across projects, with a unified bounding box or per-frame tight crops (offset JSON included)
- **AI generation**: Seedream text-to-image / image-to-image, Seedance video generation, local cache and history
- **Project management**: role/action project hierarchy with per-step settings
- **Pixel post-processing filters**: outline, isolated-pixel cleanup, edge optimization, color replacement

### Tech Stack

- Backend: Python 3.12, PyWebView, OpenCV, Pillow, rembg
- Frontend: Vue 3 + TypeScript + Vite + Pinia + TailwindCSS
- Packaging: PyInstaller (`GameAssetsMaker.spec`)

### Quick Start

```bash
# Python dependencies (requires uv)
uv sync

# Frontend dependencies
cd frontend && npm install && cd ..

# Development mode (Vite HMR + PyWebView)
uv run python dev_start.py

# Production mode (build the frontend first)
cd frontend && npm run build && cd ..
uv run python -m backend.main
```

### Custom-key Ark audit log

Image and video calls made with a user-supplied Ark API key are recorded in `logs/ark-custom-key.jsonl` under the application data root (the workspace in development, `~/.gam` when installed, or `GAM_DATA_ROOT` when set). This audit is independent of the optional error logger. Events sharing a `call_id` describe one provider call: `intent` precedes transport, `http_response` records receipt, `parsed_response` records a usable payload, and `response_persisted` / `task_persisted` records local recovery data. The log contains safe timing, status, usage, and URL-presence metadata, never keys, prompt text, media bytes, or signed URLs. An `intent` without a response does not prove provider acceptance or billing; check the Ark console for that. Account-backed generation is separate. The file rotates by size with up to five archives.

### Models

Background removal needs rembg models (not shipped in this repo). They download automatically on first use, or you can fetch them upfront:

```bash
python scripts/download_models.py        # all models (~530MB)
python scripts/download_models.py u2net  # default model only
```

See [MODELS.md](MODELS.md).

### Testing

```bash
uv run python scripts/run_tests.py            # default regression suite (no API key needed)
uv run python scripts/run_tests.py full-local # full local media pipeline
uv run python scripts/run_tests.py all-free   # all zero-cost tests + JSON report
```

Some tests need video fixtures; regenerate them with `python scripts/generate_test_fixtures.py`.

### Packaging

```bash
uv run python build.py
```

### Note

The in-app login / credit features are optional extensions backed by a self-hosted service; all local asset-processing capabilities work without any account.

### License

[MIT](LICENSE) © ForFuner
