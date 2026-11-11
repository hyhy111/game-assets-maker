# 更新日志 / Changelog

## v1.0.4

### 新增

- 在设置中一键安装和更新 **GAM Skills**。首页会提示可用更新，安装检测支持 Agent 共享目录和 Claude Code 的独立安装。
- 登录页新增 **「忘记密码？」** 入口，支持通过邮箱验证码重置 ForFuner AI 账号密码。（loen 贡献）
- ForFuner AI 视频任务支持 **「返回尾帧」**。续生成时优先使用服务返回的尾帧，缺失时从已下载的视频提取。（loen 贡献）

### 修复与改进

- 修正图片和视频生成时模型、规格的可用性判断和预计消耗提示。切换模型时保留仍适用的参数，修复部分图片重新生成失败的问题。
- 优化积分明细中剩余积分、有效期和适用范围的展示。
- 修复部分安装环境中的 HTTPS 证书验证失败。增加脱敏日志，方便排查网络请求、生成和下载失败。
- 修复动画库滚动条样式、角色菜单关闭和订阅窗口关闭按钮对齐问题。

### What's new

- **GAM Skills** can now be installed and updated from Settings. The home page shows available updates. GAM recognizes both shared agent installs and standalone Claude Code installs.
- **Password reset** is available from the sign-in page. Use the email verification code to reset your ForFuner AI password. (Contributed by loen)
- **Video continuation** can use the last frame returned by ForFuner AI. If the frame is unavailable, GAM extracts it from the downloaded video. (Contributed by loen)

### Fixes and improvements

- **Image and video generation** shows more accurate model and setting availability and estimated costs. Compatible settings carry over when you switch models. Image regeneration works again for affected tasks.
- **Credit details** show remaining balances, expiry dates, and where credits can be used more clearly.
- **Connectivity and diagnostics** include a fix for HTTPS certificate errors in some installed environments and redacted logs for network, generation, and download failures.
- **Interface** fixes the animation library scrollbar, role menu dismissal, and subscription dialog close button alignment.
