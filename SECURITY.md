# Security Policy

## Reporting a Vulnerability

If you discover a security issue, please do **not** open a public issue.
Instead, report it privately via GitHub's private vulnerability reporting
("Security" tab → "Report a vulnerability") or by contacting the maintainer
directly.

## Repository Hygiene

Please never commit any of the following:

- API keys, access tokens, passwords, or other credentials
  （API Key、访问令牌、密码等凭证）
- Downloaded model files under `models/`（下载的模型文件）
- Local project data: `project/`, `cache/`, `output/`, `logs/`
  （本地项目数据、缓存、输出、日志）
- Runtime configuration files such as `config.json` or `.env`
  （运行时配置文件）

These paths are covered by `.gitignore`; if you find a way they can slip
through, treat it as a bug and report it.
