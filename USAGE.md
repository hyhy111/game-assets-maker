# 使用参考 / Usage reference

[返回 README / Back to README](README.md)

首次安装与完整处理流程见 [README](README.md)。本页保留重命名、默认模型与版本更新的详细行为。

For installation and the first processing workflow, see the [README](README.md). This page documents renaming, default models, and update behavior.

## 中文

### 角色与动画重命名

在动画库中，点击角色行右侧的三点菜单，或动画卡片删除图标左侧的三点菜单，选择「重命名」。输入新名称后保存；角色名不能与已有角色重复，动画名不能与同角色下的其他动画重复。项目正在处理或裁剪时，请等待任务结束后再改名。动画卡片的删除图标始终显示，悬浮时变红，点击后仍需确认。

### 默认模型

设置页的图片与视频参数各提供一套默认模型配置，自定义 API Key 和 ForFuner AI 共用。平台来源会将所选模型匹配到可用模型清单中的完整 ID；不可用时选择其他可用模型，并按平台能力调整分辨率和时长。新草稿、清空草稿和切换生成来源时应用默认值；重新进入已有草稿时保留手动选择的有效模型。旧版单独保存的 ForFuner AI 默认模型不再使用。平台清单加载失败时可重试，不回退到 API Key 模型列表。

### 版本与更新

应用每次启动后在后台检查 GitHub 最新正式 Release。设置页显示当前版本；检测到更高版本后显示“更新”和“忽略当前版本”，顶部设置图标右上角同时出现黄点。更新会打开对应版本的 Release 下载页，下载后退出应用并手动覆盖安装。忽略操作立即保存到当前数据目录的配置中，只隐藏该版本的顶部黄点；设置页保留更新按钮和更新说明，下一个新版本仍会提示。检查失败不影响本地处理，也不会显示“已是最新版”。

私有仓库测试可在启动进程中设置 `GAM_UPDATE_GITHUB_TOKEN`，使用仅授权本仓库且具有 `Contents: read` 权限的 Token。该值只用于后端请求，不保存到配置、不返回前端，也不放入安装包。未设置时匿名查询，适用于公开发行仓库。`latest` 必须存在非草稿、非预发布的正式 Release；404 可能表示尚无正式版本或无访问权限。

### 错误诊断日志

安装版会自动将远程请求失败记录到 `~/.gam/logs/network.log`，包括连接、证书、超时、HTTP 错误、业务失败和失败任务状态。Seedream / Seedance 的 API 异常分别记录到同目录的 `seedream.log`、`seedance.log`，保留操作名、异常原因、调用堆栈及可用的任务标识。通用错误提示中的 `error_id` 可与日志对应。这些诊断记录不受“启用错误日志”设置控制，不记录请求正文、图片内容或凭证，URL 查询参数会被移除。每个文件最多 5 MB，保留 3 份轮转备份；写入失败不影响原操作。设置 `GAM_DATA_ROOT` 时日志随之移动，源码开发模式默认写入工作区 `logs/`。

## English

### Renaming roles and animations

In the animation library, open the three-dot menu on the right of a role row, or the three-dot menu to the left of an animation card’s delete icon, and choose Rename. Enter the new name and save. Role names must be unique; animation names must be unique within their role. Wait for active processing or trimming to finish before renaming. The animation card’s delete icon stays visible, turns red on hover, and still requires confirmation when clicked.

### Default models

Image and video settings each have one default model shared by Custom API Key and ForFuner AI. Platform generation maps that choice to a full ID in the available-model catalog, choosing another available model and adjusting resolution or duration when needed. New drafts, clearing drafts and source changes apply the shared defaults; reopening an existing draft retains a valid manually selected model. Legacy separate ForFuner AI defaults are ignored. Failed catalog loads can be retried and never fall back to the API-key model list.

### Version and updates

At each launch, the app checks the latest stable GitHub Release in the background. Settings shows the current version. A newer release reveals Update and Ignore this version, with a yellow dot on the header settings icon. Update opens that release page for download; quit the app and install manually. Ignoring persists immediately in the active data-root configuration and hides only that version’s header dot. Settings retains the Update button and release notes. Future releases remain eligible. Failed checks do not block local processing or claim the app is up to date.

For private-repository tests, set `GAM_UPDATE_GITHUB_TOKEN` in the launching process using a token restricted to this repository with `Contents: read`. It stays in the backend request, outside frontend responses, saved config and packaged artifacts. Without it, checks are anonymous for public releases. The latest endpoint requires a published stable release; 404 can mean no stable release or insufficient access.

### Error diagnostics

Installed builds automatically record remote connection, certificate, timeout, HTTP, business and failed-job errors in `~/.gam/logs/network.log`. Seedream and Seedance API exceptions are recorded separately in `seedream.log` and `seedance.log`, including the operation, cause, traceback and available task identifiers. Generic error messages include an `error_id` matching the log. These diagnostics are independent of the error-logging setting. Request bodies, image contents and credentials are omitted or redacted; URL query parameters are removed. Each file rotates at 5 MB with three backups, and logging failures do not affect the original operation. `GAM_DATA_ROOT` relocates the logs; source development defaults to the workspace's `logs/` directory.


## 本地去背与后处理

步骤 02 每个动作保留一套当前去背结果。切换模型可以继续查看上一轮结果。新一轮整批成功后替换去背帧并清除步骤 03 的结果，包含逐帧修整。失败或取消时保留上次成功的两步结果。

步骤 03 的批量工具按挖孔、缩减边缘、对齐的顺序执行。缩减边缘默认关闭，数值以原图像素为单位。缩减使外轮廓及透明孔洞周围的可见像素向内收，羽化从新轮廓向内逐渐恢复原始不透明度。魔棒和橡皮擦仍可用于逐帧修整。
