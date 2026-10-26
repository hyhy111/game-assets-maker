# 开发与打包 / Development and packaging

[返回 README / Back to README](README.md) · [贡献指南 / Contributing](CONTRIBUTING.md)

## 中文

开发环境、测试和发行构建参考。直接使用应用请先看 [README 使用说明](README.md#使用说明)。

### 技术栈

- 后端：Python 3.12、PyWebView、OpenCV、Pillow、rembg
- 前端：Vue 3 + TypeScript + Vite + Pinia + TailwindCSS
- 打包：PyInstaller（`GameAssetsMaker.spec`）

### 源码启动

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

Agent 控制服务优先使用本机 `8765` 端口；被占用时自动分配空闲端口。CLI 从当前数据目录的 `cache/agent-control.json` 发现实际端口，退出时清理记录。源码开发时请在同一工作区调用 CLI；使用 `GAM_DATA_ROOT` 时，桌面程序与 CLI 应指向同一数据目录。

### 模型准备

背景移除当前仅支持 U2Net（约 176 MB），模型权重不随仓库或发布包分发。安装版在步骤 2 提示下载，由用户选择来源并点击下载；有效模型就绪后可离线处理。源码开发可在仓库根目录提前下载：

```bash
uv run python scripts/download_models.py u2net
```

详见 [MODELS.md](MODELS.md)。

### 自定义 Key 调用日志

仅通过 `dev_start.py` 启动的开发模式可在设置页开启“记录 API 调用详情”，默认关闭。开启后，自定义 Ark API Key 的图片与视频调用过程记录到数据目录的 `logs/ark-custom-key.jsonl`。开发模式默认为当前工作区的 `logs/`；`GAM_DATA_ROOT` 只改变数据目录，不授予日志资格。普通源码运行、安装数据模式与打包应用始终不记录该日志，即使配置残留开启值。该日志独立于设置中的“启用错误日志”和前端请求诊断。

开关独立即时保存，成功后影响后续事件，无需统一保存或重启。关闭保留已有文件，不记录后续事件，也不会在再次开启时补写关闭期间的事件；进行中的调用可能只有部分事件，因此缺少日志不能推断请求失败、未生成或未计费。

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

版本号统一来自 `pyproject.toml`；构建时自动同步前端包版本。macOS 构建会额外生成 `dist/GameAssetsMaker-<版本>-macos-<架构>.dmg` 和 `.dmg.sha256`，内含应用、Applications 快捷方式与安装说明。拖入 Applications 即可安装；覆盖更新前先退出应用。当前测试包没有 Developer ID 签名或 Apple 公证，受阻时按安装说明在“隐私与安全性”中选择“仍要打开”。

保留已有产物并在独立目录打包：

```bash
uv run python build.py --dist-dir dist/local-1.0.0 --work-dir build/local-1.0.0
```

可用 `--skip-dmg` 仅构建应用。Windows 可使用 Inno Setup 6.3+（含简体中文语言文件）和微软官方 WebView2 引导安装程序生成单个 EXE 安装包：

```powershell
uv run python build.py --windows-installer --iscc "C:/Tools/Inno Setup/ISCC.exe" --webview2-bootstrapper "C:/Tools/MicrosoftEdgeWebview2Setup.exe" --dist-dir dist/windows-setup --work-dir build/windows-setup
```

输出 `GameAssetsMaker-<版本>-windows-x64-Setup.exe` 和 `.exe.sha256`。安装器按当前用户安装，支持开始菜单、可选桌面快捷方式及卸载；升级沿用原安装目录。卸载保留 `.gam` 用户数据。缺少 WebView2 时联网安装微软运行库。重复构建请选新的输出目录，避免覆盖已有安装包。

可用 `--package-name` 自定义安装包文件名前缀，默认值为 `GameAssetsMaker`；版本号、系统和架构后缀自动保留。例如：

```bash
uv run python build.py --package-name "GAM" --dist-dir dist/gam --work-dir build/gam
```

在 Apple Silicon Mac 上生成 `GAM-<版本>-macos-arm64.dmg`。Windows 打包命令同样支持 `--package-name "GAM"`，生成 `GAM-<版本>-windows-x64-Setup.exe`；对应校验文件的名称和内容同步使用自定义名称。名称支持中文和空格（命令行中请加引号），不能包含路径分隔符、控制字符、`<>:"|?*{}`、首尾空白或结尾的点。该选项只修改安装包文件名，应用名称、安装目录及 CLI 入口保持不变。

GitHub Actions 工作流 [Build installers](.github/workflows/build-installers.yml) 支持手动同时构建 Windows x64 与 macOS Apple Silicon（ARM64），不生成 Intel Mac 安装包：

1. 将工作流、打包脚本及所需源码提交并推送到仓库默认分支；`dist/` 和 `build/` 不需要上传。
2. 打开仓库 **Actions → Build installers → Run workflow**，选择要打包的分支，填写 `package_name` 安装包前缀（默认 `GameAssetsMaker`）并运行。
3. 成功后打开该次运行，在 **Artifacts** 下载 `windows-x64-installer` 和 `macos-arm64-installer`，解压得到安装包及 `.sha256` 校验文件。
4. 安装验证后，可将 EXE、DMG 及对应校验文件上传到 GitHub Release。工作流只保存构建产物（14 天），不会自动发布 Release。

版本号来自 `pyproject.toml`，生产 API 地址沿用 `frontend/.env.production`。工作流调用现有打包脚本并执行包内 CLI 自检；Mac 安装包暂未配置 Developer ID 签名或 Apple 公证。

发行包同时包含 gam 桌面程序与 `gam-agent` CLI，共享运行库，用户无需安装 Python 或 uv。构建完成后自动在临时数据目录运行 CLI 自检；任一步失败都会使构建命令失败。

- macOS：`dist/Game Assets Maker.app/Contents/MacOS/gam-agent`
- Windows：`dist/game-assets-maker/gam-agent.exe`（与桌面程序及 `_internal` 一起交付）

安装版 gam 或随包 CLI 启动时，会在用户数据目录注册固定 CLI 入口：macOS 为 `~/.gam/gam-agent`，Windows 为 `%USERPROFILE%\.gam\gam-agent.cmd`（同目录的 `gam-agent.ps1` 为配套文件）。入口转发到安装包内的 CLI，保留共享运行库，无须配置 PATH；应用移动或升级后重新启动一次即可刷新。设置 `GAM_DATA_ROOT` 时，入口改为写入该目录。普通源码开发启动不会注册入口。

插件和 Agent 应优先通过上述绝对路径调用 CLI，入口缺失时再查安装目录。界面导航与草稿操作需要 gam 已启动；用户数据默认位于 `~/.gam`，模型及本地配置不包含在发行包中。

草稿填写支持按需传入独立参数，例如 `draft patch --kind video --prompt "原地行走" --first-frame "角色.png" --duration 5`；省略的参数保留界面原值。图片参考图使用 `--reference-image`，长提示词可用 `--prompt-file` 读取 UTF-8 纯文本。保留 `--patch-json` 兼容已有调用，与独立参数二选一。

### 维护 GAM Skills 子模块

六个 GAM Skills 在独立仓库 [hyhy111/gam-skills](https://github.com/hyhy111/gam-skills) 维护，以 Git 子模块放在 `.agents/skills/`。这里的修改直接属于 Skills 仓库；客户端记录使用的 Skills 提交版本。

```bash
# 新克隆时一起获取 Skills
git clone --recurse-submodules https://github.com/hyhy111/game-assets-maker.git

# 已有客户端检出：初始化记录的 Skills 版本
git submodule update --init -- .agents/skills

# 开始修改 Skills 前切换到维护分支
git -C .agents/skills switch main
```

先在 `.agents/skills/` 检查并验证改动，只提交本次所需的 Skills 文件并推送；再回到客户端更新 `.agents/skills` 指针。两个仓库分别提交，已有未提交改动应保留。其他本地 Skills 可继续放在该目录，但应保持 Git 忽略，不进入 GAM Skills 发布内容。

## English

Reference for source development, tests, and release builds. To use the app, start with the [README guide](README.md#usage).

### Tech Stack

- Backend: Python 3.12, PyWebView, OpenCV, Pillow, rembg
- Frontend: Vue 3 + TypeScript + Vite + Pinia + TailwindCSS
- Packaging: PyInstaller (`GameAssetsMaker.spec`)

### Run from source

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

The local agent control service prefers port `8765` and automatically selects a free port if occupied. The CLI discovers it through `cache/agent-control.json` in the active data root; shutdown removes the record. For source development, run the CLI from the same workspace. If using `GAM_DATA_ROOT`, point the desktop app and CLI to the same directory.

### Models

Background removal currently supports only U2Net (~176 MB). Model weights are not included in the repository or release package. In installed builds, step 2 prompts the user to select a source and download the model. Once ready, it supports offline processing. For source development, download it from the repository root:

```bash
uv run python scripts/download_models.py u2net
```

See [MODELS.md](MODELS.md).

### Custom-key Ark audit log

Development launched through `dev_start.py` offers a “Record API call details” setting, disabled by default. When enabled, calls made with a user-supplied Ark API key are recorded in `logs/ark-custom-key.jsonl` under the application data root (the development workspace, or `GAM_DATA_ROOT` when set). Ordinary source launches, installed data mode and packaged applications never record this log, even with a stale enabled setting. A data-root override does not grant logging permission. This audit is independent of the optional error logger and frontend request diagnostics.

The switch saves independently and, once saved, applies to subsequent events immediately without saving other settings or restarting. Disabling preserves existing files and stops recording new events; re-enabling never backfills disabled events. An in-flight call may have only partial events, so missing events do not prove failure, lack of generation, or lack of billing.

Events sharing a `call_id` describe one Ark call: `intent` precedes transport, `http_response` records receipt, `parsed_response` records a usable payload, and `response_persisted` / `task_persisted` records local recovery data. `elapsed_ms` is the elapsed time in milliseconds up to that event. For video, `video.get` is a task-status query; for images, `download_*` describes the local download stage. The log records only the model, timing, HTTP status, available request IDs, usage, and whether a URL exists. It excludes keys, prompt text, image data, and download URLs.

An `intent` without a response cannot establish whether the provider received the request, generated media, or charged for it; check the Ark console. Account-backed cloud generation does not write to this custom-key log. The file rotates by size with up to five archives, and existing tasks are never backfilled.

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

The canonical version is in `pyproject.toml`; the build synchronizes frontend package versions. On macOS it also creates `dist/GameAssetsMaker-<version>-macos-<architecture>.dmg` and `.dmg.sha256`, containing the app, an Applications shortcut, and installation instructions. Drag the app into Applications to install it; quit the old app before replacing it. Test builds have no Developer ID signature or Apple notarization; if blocked, follow the included Privacy & Security > Open Anyway instructions.

To preserve previous output, build in separate directories:

```bash
uv run python build.py --dist-dir dist/local-1.0.0 --work-dir build/local-1.0.0
```

Use `--skip-dmg` for the app bundle only. On Windows, use Inno Setup 6.3+ (including the Simplified Chinese language file) and Microsoft's official WebView2 bootstrapper to create a single EXE installer:

```powershell
uv run python build.py --windows-installer --iscc "C:/Tools/Inno Setup/ISCC.exe" --webview2-bootstrapper "C:/Tools/MicrosoftEdgeWebview2Setup.exe" --dist-dir dist/windows-setup --work-dir build/windows-setup
```

This produces `GameAssetsMaker-<version>-windows-x64-Setup.exe` and `.exe.sha256`. Setup installs for the current user, adds Start menu and optional desktop shortcuts, and reuses the previous installation directory on upgrade. Uninstall preserves `.gam` user data. A missing WebView2 runtime is installed online using Microsoft's installer. Use a fresh output directory to preserve existing installers.

Use `--package-name` to customize the installer filename prefix (default: `GameAssetsMaker`). The version, platform, and architecture suffixes are retained automatically. For example:

```bash
uv run python build.py --package-name "GAM" --dist-dir dist/gam --work-dir build/gam
```

This creates `GAM-<version>-macos-arm64.dmg` on an Apple Silicon Mac. The Windows build command also accepts `--package-name "GAM"`, producing `GAM-<version>-windows-x64-Setup.exe`. Checksum filenames and their contents use the custom name as well. Names may contain Chinese characters and spaces (quote them on the command line), but cannot contain path separators, control characters, `<>:"|?*{}`, leading/trailing whitespace, or trailing dots. This option changes only installer filenames; the application name, installation directory, and CLI entry paths remain unchanged.

The [Build installers](.github/workflows/build-installers.yml) GitHub Actions workflow manually builds Windows x64 and macOS Apple Silicon (ARM64) together. It does not produce Intel Mac installers:

1. Commit and push the workflow, packaging scripts, and required source to the repository's default branch. Do not upload `dist/` or `build/`.
2. Open **Actions → Build installers → Run workflow**, select the branch to package, enter the `package_name` installer prefix (default: `GameAssetsMaker`), and start the run.
3. After success, open the run and download `windows-x64-installer` and `macos-arm64-installer` from **Artifacts**. Extract the archives to obtain the installers and their `.sha256` files.
4. After installation testing, upload the EXE, DMG, and corresponding checksums to a GitHub Release. The workflow stores build artifacts for 14 days and does not publish releases automatically.

The version comes from `pyproject.toml`; the production API URL uses `frontend/.env.production`. The workflow calls the existing build script, including its bundled CLI checks. Mac installers currently have no Developer ID signing or Apple notarization.

The release includes both the gam desktop application and `gam-agent`, sharing runtime libraries. Users need neither Python nor uv. After packaging, the build runs the bundled CLI against temporary user data and fails if its smoke check fails.

- macOS: `dist/Game Assets Maker.app/Contents/MacOS/gam-agent`
- Windows: `dist/game-assets-maker/gam-agent.exe` (distribute it with the desktop executable and `_internal`)

Starting the packaged app or bundled CLI registers a stable entry in the user-data directory: `~/.gam/gam-agent` on macOS, or `%USERPROFILE%\.gam\gam-agent.cmd` on Windows (with its companion `gam-agent.ps1`). This entry forwards to the bundled CLI and retains its shared runtime libraries without changing PATH. Restart after moving or updating the app to refresh the entry. `GAM_DATA_ROOT` overrides its destination; ordinary source-development launches do not register it.

Plugins and agents should try this absolute path before searching the installation directory. Navigation and draft operations require the desktop application to be running. Writable data defaults to `~/.gam`; model weights and local configuration are excluded from the release.

Draft updates accept individual options, for example `draft patch --kind video --prompt "Walk in place" --first-frame "character.png" --duration 5`; omitted options preserve the current form values. Use `--reference-image` for image references or `--prompt-file` for long UTF-8 text. Existing `--patch-json` calls remain supported; choose JSON or individual options for each update.

### Maintain the GAM Skills submodule

The six GAM Skills live in the independent [hyhy111/gam-skills](https://github.com/hyhy111/gam-skills) repository, checked out at `.agents/skills/` as a Git submodule. Changes there belong to the Skills repository; the client records the Skills commit it uses.

```bash
# Clone the client with Skills
git clone --recurse-submodules https://github.com/hyhy111/game-assets-maker.git

# Initialize the Skills revision recorded by an existing client checkout
git submodule update --init -- .agents/skills

# Switch to the maintenance branch before editing Skills
git -C .agents/skills switch main
```

Inspect and validate changes inside `.agents/skills/`, commit only the intended Skills files, and push them first. Then update the client’s `.agents/skills` pointer. Commit the two repositories separately and preserve existing uncommitted changes. Other local skills may remain in that directory but should stay Git-ignored and out of GAM Skills releases.
