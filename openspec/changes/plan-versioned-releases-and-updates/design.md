# Design

## Context

本文记录 2026-10-12 的探索结果，动机见 `proposal.md`。技术选择是建议稿；本次没有实现更新功能、安装脚本或 CI 工作流，也没有创建远端 tag/Release、改变仓库可见性或执行签名与公证。

### 已确认方向

- 首次公开版本 `1.0.0`，对应 `v1.0.0`。
- 同一个 GitHub 仓库开发期间私有，首次正式公开发布时开源；安装包与更新说明使用 GitHub Releases。
- 第一阶段检测新版本、展示说明、下载安装包，用户退出后手动覆盖安装。
- macOS 首版使用 DMG，暂不配置 Developer ID 分发签名和 Apple 公证；安装说明提供“隐私与安全性 → 仍要打开”的首次启动操作，后续签名与公证独立规划。
- 在私有阶段做真实的 Release 检测与下载测试，不以 mock 或配置存在代替测试成功。

### 当前证据与缺口

| 环节 | 当前证据 | 尚未证明的部分 |
|---|---|---|
| 版本 | `pyproject.toml` 为 `0.1.0`，前端包和 `get_app_version()` 为 `2.0.0` | 单一版本来源、冻结包版本读取 |
| 打包 | `build.py` 构建前端，调用 spec，执行隔离用户数据目录下的 packaged CLI doctor | Windows 安装程序、CI 构建、安装后的 GUI 行为 |
| macOS | spec 生成 `.app`；现有 `dist` 中有标记 `0.0.0` 的 DMG 和 Bundle | 现有 DMG 的可复现生成步骤、当前代码对应的 DMG、下载后手动允许打开的启动体验 |
| GitHub | 本次会话真实授权 API 请求确认仓库私有、Release 列表为空，latest 返回 404 | Release 附件下载与客户端完整更新流程 |
| 安装数据 | 现有稳定数据目录与自定义存储规范 | 实际覆盖安装、卸载保留数据 |

本地现有 DMG 只能证明曾产出过 DMG，不能证明当前工作区可复现同一产物。工作区有既有未提交修改；CI 只能构建选定 Git 提交，不能自动包含本机工作区修改。

## Goals / Non-Goals

**Goals:**

- 让一个版本对应固定代码提交、可识别的平台安装包、更新说明与下载校验信息。
- 沿用现有 PyInstaller GUI/CLI 共享运行库布局，降低打包改造范围。
- 使安装包生成、Release 发布与客户端更新可以分阶段实测并分别报告结果。
- 升级只替换应用程序文件，用户数据与本地处理能力持续可用。

**Non-Goals:**

- 第一阶段不做自动安装、自动重启、后台静默更新、差分补丁或多渠道更新服务。
- 不自动开源仓库、不将首次公开发布绑定为 CI 的隐式副作用。
- 不将模型权重、用户数据或测试 Token 分发给正式用户，不要求正式用户安装 GitHub CLI。

## Decisions

### 1. 建议以 pyproject.toml 作为唯一手工维护的版本来源

公开版本从 `1.0.0` 起。构建时生成包含版本、提交 SHA、系统和架构的只读构建信息，并显式放入 GUI/CLI 发行包；冻结程序读取该信息，源码运行读取相同版本来源。前端包版本、相关锁文件、Windows 版本资源、安装器 AppVersion 和 macOS `CFBundleShortVersionString` / `CFBundleVersion` 由同一版本派生并检查一致性。

正式 tag 必须与版本一致；信息缺失、版本不匹配或构建目标不明时构建失败，不默默退回 `0.0.0`。版本比较按主、次、修订号解析，不能使用字符串字典序；稳定更新忽略预发布版本，且不自动降级。内部测试使用独立的低版本真实构建，保持测试 tag、程序元数据和文件名一致。

单独新增一份可手工修改的 VERSION 文件容易制造第二个版本来源，故优先使用现有 Python 项目元数据。版本统一会结束旧代码中硬编码的 `2.0.0`；这些旧包目前没有实现更新检测，不应伪造其升级验证结果。

### 2. Windows：现有目录产物 + Inno Setup 安装程序

建议第一阶段使用 Windows x64 的原生构建，再将完整 `dist/game-assets-maker/` 封装成单个 Setup EXE。安装源包含 GUI、`gam-agent.exe` 和 `_internal` 等整个运行库树，不能只取 GUI EXE。[PyInstaller 布局说明](https://pyinstaller.org/en/stable/usage.html)

建议安装行为：

- 使用固定 AppId，版本更新时不修改；采用 `UsePreviousAppDir=yes` 识别并沿用原安装目录。[AppId](https://jrsoftware.org/ishelp/topic_setup_appid.htm)、[安装目录复用](https://jrsoftware.org/ishelp/topic_setup_usepreviousappdir.htm)
- 默认按当前用户安装到用户程序目录；桌面和开始菜单快捷方式指向 GUI，CLI 与 GUI 共同交付，第一阶段不自动修改 PATH。
- 更新前提示正常退出 GUI 和仍在使用程序文件的 CLI；使用应用占用检测并处理取消，不强制结束处理/生成任务，不默认自动重启。[CloseApplications](https://jrsoftware.org/ishelp/topic_setup_closeapplications.htm)
- 仅安装和替换程序自有文件。旧运行库文件如需清理，按受控文件清单处理，不通配删除用户选择的整个目录。
- 卸载默认保留 `~/.gam` 与用户选择的项目/缓存目录；不在安装目录创建可写配置或模型。
- 检查 WebView2 Runtime；缺失时提供官方 Evergreen Runtime 安装入口，已就绪时避免再次安装。联网引导安装与离线 Runtime 是不同交付方式，普通安装包建议先使用联网引导；验证目标机器无 Runtime 时的体验。[Microsoft 分发说明](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)

现有打包入口之后还需新增 `.iss` 安装描述，使用 Inno Setup 的 `ISCC.exe` 命令行编译；这使本地和 CI 使用同一安装定义。[编译器说明](https://jrsoftware.org/ishelp/topic_compilercmdline.htm)

MSI/MSIX 可用于后续企业部署或商店交付；当前是普通桌面程序目录，Inno Setup 对现有布局改动更小。Setup EXE 产出不代表签名、安装和升级都已验证，Windows 代码签名状态应独立记录。

### 3. macOS：.app 放入 DMG 即可承担第一阶段安装分发

DMG 内放置 `Game Assets Maker.app` 与指向 `/Applications` 的快捷入口，用户拖入 Applications 安装；升级时正常退出应用后替换整个 `.app`。GUI 与 CLI 继续在同一 Bundle 内共享运行库。

建议把生成 DMG 的步骤纳入构建入口或专用封装脚本，使用 macOS 自带 `hdiutil` 完成基本镜像生成；窗口背景与布局可后续改善。DMG staging 中仅保留要交付的 Bundle 与 Applications 入口，不将其他 `dist` 产物和本机用户数据顺带打入。

首版已确认暂不配置 Developer ID 分发签名与 Apple 公证，DMG 和 Release 说明均明确这一状态。用户首次安装后的操作说明为：

1. 将 `.app` 拖入 Applications，尝试打开一次。
2. 如果系统因身份不明的开发者或未公证而阻止，进入“系统设置 → 隐私与安全性”，找到该应用并点击“仍要打开”。
3. 再次确认“打开”，按系统提示完成认证。

这与 Apple 提供的逐应用例外操作一致；系统通常会记住该应用的例外许可。安装说明链接到官方操作页，不要求全局关闭 Gatekeeper。损坏包、错误架构或实际运行故障须另行排查，不能归结为尚未点击允许。[Apple 手动打开说明](https://support.apple.com/zh-cn/102445)

此处“暂不签名”指不配置 Developer ID 分发身份，不是删除构建工具的所有签名。Apple Silicon 二进制仍需有效签名，保留 PyInstaller 默认生成的 ad-hoc 签名；默认签名不等于 Developer ID 或 Apple 公证。[PyInstaller 签名说明](https://pyinstaller.org/en/stable/feature-notes.html#macos-binary-code-signing)

发布验收使用从 GitHub 实际下载、保留正常下载隔离属性的 DMG，验证以上操作后 GUI 与 CLI 可启动并运行；源码启动和本机构建目录启动不能替代此验收。后续如接入 Developer ID、hardened runtime 和公证，另行增加凭证、签名/票据步骤及无需手动例外的分发验证。[Apple 分发说明](https://help.apple.com/xcode/mac/current/en.lproj/dev033e997ca.html)

建议先验证 macOS arm64。Intel x64 需单独构建和验收，不能将 arm64 文件重命名为 x64，也不直接承诺 universal2；Python、ONNX Runtime 等二进制依赖会影响多架构支持。

### 4. 发行包命名固定包含版本、平台与架构

建议命名：

| 平台 | 文件名示例 | 当前规划地位 |
|---|---|---|
| Windows x64 | `GameAssetsMaker-1.0.0-windows-x64-setup.exe` | 建议首批验收目标 |
| macOS arm64 | `GameAssetsMaker-1.0.0-macos-arm64.dmg` | 建议首批验收目标 |
| macOS x64 | `GameAssetsMaker-1.0.0-macos-x64.dmg` | 可扩展目标，独立验证后加入 |
| 校验文件 | `SHA256SUMS` | 建议与安装包同一 Release 上传 |

`SHA256SUMS` 按最终要上传的附件生成，首版在 DMG/Setup 封装完成后计算；后续启用签名、公证或票据附加时，必须在这些步骤完成后再计算，避免发布与下载校验使用不同字节。GitHub 自动生成的源码归档不作为客户端安装包。

### 5. GitHub Actions 可以承担构建及 Release 附件交付

PyInstaller 不是跨操作系统编译器，Windows 包在 Windows runner 构建，macOS 包在 macOS runner 构建。[PyInstaller 官方说明](https://pyinstaller.org/en/stable/index.html)

建议的构建矩阵如下；标签按 2026-10-12 官方清单核对，实际落地时再次确认可用性并固定环境，不依赖 `latest` 的隐式架构变化。

| 构建任务 | runner 示例 | 封装步骤 |
|---|---|---|
| Windows x64 | `windows-2022` | PyInstaller + Inno Setup |
| macOS arm64 | `macos-15` | PyInstaller Bundle + DMG |
| macOS x64（扩展） | `macos-15-intel` | 独立 Bundle + DMG |

公开和私有仓库都有相应托管 runner。标准公开仓库 runner 与私有仓库额度/计费规则不同；签名证书、存储等也应单独评估，不能笼统承诺整个发布过程免费。[GitHub runner 清单与规则](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)

建议触发与权限：

- 手动触发用于首次调试；正式版本使用已存在的版本 tag，所有平台解析到同一不可变提交 SHA。
- `uv sync --frozen` 使用锁定 Python 依赖，前端使用 `npm ci`，按项目约束选择 Python 3.12 和兼容的 Node；构建前检查 tag/元数据一致。
- 构建 job 只读仓库；附件汇总/发布 job 单独授予 `contents: write`，通过该仓库的 `GITHUB_TOKEN` 发布，无须把维护者 PAT 放进普通工作流。[GITHUB_TOKEN](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token)、[工作流权限](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#permissions)
- 所有必需平台成功后才汇总安装包和校验文件，建立关联已有 tag 的 Release 草稿。可使用 `gh release create` 的 draft 与 verify-tag 能力；工作流不生成未经检查的 tag。[GitHub CLI Release 创建](https://cli.github.com/manual/gh_release_create)
- 同一 tag 重跑不得悄悄覆盖已发布附件；仅草稿可显式重试，正式版本修复通过新版本交付。
- 首版 macOS 构建无需 Developer ID 或公证 secrets；后续接入签名时凭证进入 CI secrets，仅受信任的发布流程可用，普通 PR 构建不接触发布凭证。

概念流程如下，属于设计示意，不是已存在的 workflow：

```text
Existing tag / selected immutable commit
                    |
              Version checks
                    |
          +---------+---------+
          |                   |
     Windows build       macOS build
     CLI smoke check     CLI smoke check
     Setup EXE           DMG
          |                   |
          +---------+---------+
                    |
          Collect final artifacts
          Generate SHA256SUMS
                    |
             Draft Release
                    |
          Real installation checks
                    |
           Maintainer publishes
                    |
          Client checks and downloads
```

### 6. 更新检测优先使用 GitHub 原生 Release 元数据

后端查询 `GET /repos/hyhy111/game-assets-maker/releases/latest`，读取 `tag_name`、`body` 和 `assets`；设置页显示当前版本、新版本、发布时间、更新说明与操作状态。优先复用现有设置、API、类型和本地化模式，更新说明按文本显示，避免直接插入未经处理的 HTML。[Release 接口](https://docs.github.com/en/rest/releases/releases#get-the-latest-release)

建议首版从用户手动“检查更新”开始。启动时的后台检查属于后续产品选择，不视为本次已确认项。正式检查只接受已发布的稳定版本，并确认其版本高于本地版本；如果 GitHub 将旧版本设为 latest，也不自动降级。

附件按操作系统、进程/构建架构、版本与文件扩展名严格匹配。无匹配附件时显示“当前平台暂无安装包”并提供 Release 页面入口，不能选另一架构的包。网络失败、限流、版本格式错误分别报告，不冒充“已经是最新版”。公开仓库已确认可访问但无正式 Release 时显示“尚未发布正式版本”；私有阶段的 404 还可能与访问权限有关。

### 7. 建议应用内下载到稳定数据目录并校验

首次下载由用户点击触发，后端异步流式下载，前端展示进度、取消和失败重试。下载目录通过现有数据路径助手解析到稳定用户数据根下的专用目录，遵守数据根覆盖设置，不能写入应用包或仓库。

建议使用受控文件名和 `.part` 临时文件；成功完成并通过大小、SHA-256 检查后再改为正式文件。取消或失败不能留下看似完整的安装包；第一阶段重试重新下载，不承诺断点续传。缺少可用校验信息或校验失败时不显示“可安装”。

公开附件使用 `browser_download_url`。私有测试通过 asset ID 请求 `GET /repos/{owner}/{repo}/releases/assets/{asset_id}`，授权请求加 `Accept: application/octet-stream`，处理直接返回二进制及跳转两种情况。[附件下载接口](https://docs.github.com/en/rest/releases/assets#get-a-release-asset)

只允许 HTTPS；下载跳转到 GitHub 附件存储后不向其他主机继续转发 Authorization。认证值及含签名参数的临时 URL 不写入日志。下载完成提供打开所在文件夹，并按平台说明退出后运行 Setup 或拖动替换 `.app`；第一阶段不自动运行安装器或重启。

### 8. 私有测试与公开客户端使用同一更新逻辑、不同授权来源

本次会话已验证本机现有 `gh` 授权可访问仓库，无需重登或向聊天提供 Token。受限环境曾错误报告登录不可用，放开网络后真实只读 API 调用成功；授权状态必须以成功访问目标仓库为依据。

建议测试程序在本机测试入口内部复用 `gh` 凭证，或从测试进程环境读取仅限该仓库、短期且 `Contents: Read-only` 的细粒度 Token。凭证不得回显、写进项目配置、前端代码或构建信息。测试入口的授权只用于传输层，版本比较、资产匹配和校验复用正式客户端逻辑。正式公开版使用匿名访问，不依赖 `gh`，不保留私有 Token。[Token 管理](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)

测试 latest 接口必须有非 draft、非 prerelease 的已发布 Release。建议在仍私有的仓库建立版本一致的内部测试构建，例如本地 `0.0.1` 对应远端 `v0.0.2`；两者都来自真实打包流程，并明确标为内部测试。预发布包可通过按 tag 查询测试其他环节，但不能冒充正式 latest 测试。内部发布仍是独立远端操作，本次只记录方案。

首次公开前清理或明确标识内部测试 Release；源码开放检查覆盖 Git 历史、发行包和附件。由维护者手动改变可见性及正式发布 `v1.0.0`，随后在无凭证环境重新验证匿名检查、下载和安装。

### 9. 安装、更新、卸载与回退保护用户数据

安装器和 macOS 替换 Bundle 仅管理程序文件，`~/.gam`、自定义项目/缓存目录、凭证、模型与历史记录不参与覆盖。数据根和配置路径继续遵守现有 `GAM_DATA_ROOT`、`GAM_DATA_MODE`、`GAM_CONFIG` 解析；更新本身不触发存储迁移，不重置用户已经配置的位置。

旧程序回退由用户手动安装明确版本完成。首版版本/更新改造不主动改变历史数据格式；以后如引入格式升级，需单独定义向后兼容与备份策略，不能仅凭保存旧安装包就承诺数据一定能回退。

### 10. 验证按证据层次分开报告

| 层次 | 需要完成的验证 | 能说明什么 |
|---|---|---|
| 本地逻辑 | 版本解析、附件匹配、错误分类、校验和取消；采用有效反例 | 更新逻辑是否正确 |
| CI 原生产物 | 指定提交的原生构建、版本资源、GUI/CLI 完整性、隔离目录 doctor | 产物布局和 CLI 可运行 |
| 实际安装 | 无开发环境机器安装并启动 GUI、CLI，本地媒体流程、WebView2 缺失处理 | 用户是否能安装使用 |
| 真实 Release | 已授权私有 latest 与二进制附件完整下载、SHA-256 一致 | 实际 GitHub 检测与传输 |
| 覆盖升级 | 旧版检查新版、下载、退出、覆盖、重开并核对数据 | 第一阶段用户流程成立 |
| 公开发行 | 无凭证检查下载；macOS 按说明手动允许后启动，Windows 验证实际启动 | 公开用户可访问与启动 |

现有 packaged CLI doctor 是应保留的构建检查，不能替代上述 GUI 或安装验收。CI 对全套媒体测试所需 fixtures/模型应使用隔离测试数据准备，构建附件不包含模型；不调用付费 AI。正式发布遵守贡献指南的默认回归和 full 媒体流程要求；本次仅写文档，未执行这些测试。

## Risks / Trade-offs

- [runner、依赖与架构兼容变化] -> 固定环境、锁定依赖，扩展平台逐一实际构建和验收，不以重命名产物宣称兼容。
- [私有阶段额度与网络可用性] -> 手动触发优先，独立记录构建成本和客户端网络失败，失败不影响本地处理。
- [首版无 Developer ID / 公证带来首次手动允许操作] -> 提供准确安装说明，并用真实下载包验证操作后启动；后续可独立接入签名与公证改善体验。
- [程序运行时覆盖或残留旧库] -> 正常退出后安装，以程序文件清单管理更新，不删除用户数据目录。
- [发布部分平台或校验值不一致] -> 所有必需产物齐备后才创建草稿，最终字节计算校验值，正式附件不原地替换。
- [凭证或临时下载链接进入发行包/日志] -> 开发测试传输授权与正式匿名访问分离，重定向去除跨主机授权，输出脱敏。

## Migration Plan

1. 后续 `/openspec-propose` 将本探索的拟定能力补成规范与任务；确认建议的首批平台后再实施。
2. 统一版本读取与构建信息，验证源码和冻结包显示一致，再接入两种平台封装。
3. 使用固定提交在原生 runner 上构建，先交付 CI artifacts；验证后再接入 Release 草稿。
4. 实现检测和下载，共用逻辑接入本机私有授权，创建真实内部测试版本并完成旧版到新版的覆盖验收。
5. 首次公开前检查源码历史和包内容，按已确认的首版 macOS 策略保留默认 ad-hoc 签名、提供手动允许打开说明并完成真实下载启动验收；维护者将仓库公开并正式发布 `v1.0.0`。
6. 无凭证真实验证公开检测与下载；失败时保留旧程序可用，停止发布后续版本并按明确版本手动恢复程序。

版本统一与本地 macOS 封装已按用户后续确认的范围实施：`pyproject.toml` 版本为 `1.0.0`；运行时、CLI、前端包与 macOS bundle 版本同步；`build.py` 支持独立输出目录，完成 CLI 自检后自动生成 DMG 与 `.dmg.sha256`。本地测试产物位于 `dist/local-1.0.0/`，原有产物保留。

Windows EXE 安装器、GitHub Actions、更新检测与下载仍待实施。没有新增 `.iss`、workflow、更新 API 或下载代码，没有提交、推送、远端 Release、仓库开源或 CI 运行。该探索变更尚未补齐规范与任务，不能视为整个发布更新方案已经完成。
