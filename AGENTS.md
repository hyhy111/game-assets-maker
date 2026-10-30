# AGENTS.md

These instructions apply to the entire repository.

## Read Before Acting

- Read `README.md` for product scope, setup, and entrypoints.
- Read `CONTRIBUTING.md` before changing code, tests, dependencies, build behavior, or release behavior.
- Treat source code, tests, `pyproject.toml`, and `frontend/package.json` as the current source of truth when documentation disagrees.
- Inspect `git status` before editing. Preserve unrelated user changes and local-only files.

## Change Workflow

- Use the smallest change that fully solves the requested problem. Avoid broad refactors, mechanical rewrites, and unrelated formatting.
- Implement clear, scoped requests directly with proportionate validation.
- OpenSpec is optional. Use it when the user requests it or when its planning artifacts would materially help a complex change; follow the user's preferred workflow.
- When working on an existing OpenSpec change, read `openspec/config.yaml` and its relevant artifacts, and verify the implementation before syncing specifications or archiving.

## Repository Boundaries

- `backend/` contains the PyWebView application and Python APIs exposed to the frontend.
- `src/` contains shared Python utilities, processing code, and CLI entrypoints.
- `frontend/` is the Vue 3 and TypeScript application. Reuse its existing components, stores, styling tokens, and interaction patterns.
- `tests/` contains Python tests; `frontend/tests/` contains frontend tests.
- Keep UI, settings, types, validation, persistence fallback, localization, and tests consistent when changing a user-visible model or capability.

## GAM Skills Submodule

- `.agents/skills` is the separate `hyhy111/gam-skills` Git repository. Read its `AGENTS.md` before editing Skills. Keep local non-GAM skills ignored within that directory.
- Initialize the recorded Skills version with `git submodule update --init -- .agents/skills`. Commit and push intended Skills changes in the submodule before updating the client pointer; preserve pending edits in both repositories.

## Persistent Data Safety

- Installed applications store writable user state under `~/.gam` by default. Resolve paths through the existing data-path helpers and honor `GAM_DATA_ROOT`, `GAM_DATA_MODE`, and `GAM_CONFIG`.
- Keep installed user state outside the replaceable application package, including projects, configuration, credentials, cache, logs, WebView state, and downloaded models.
- Legacy project migration is copy-only: import valid project directories, preserve the source, and never overwrite an existing destination.
- Never use repository-local sample or development paths as proof that installed-mode isolation works. Cover real installed entrypoints when changing path behavior.

## Implementation Rules

- Add or modify code comments in English. UI copy may remain localized.
- Prefer existing abstractions over parallel implementations. Keep backend validation authoritative even when the frontend also guards an action.
- Preserve local-first behavior. Do not make local asset processing depend on login, credits, or a remote service.
- Do not store API keys, credentials, tokens, personal project data, generated media, or downloaded models in the repository.
- Add dependencies through `pyproject.toml` and `uv.lock`; do not extend legacy `requirements.txt` for new dependencies.

## Upgrade Compatibility

- Preserve older saved projects, configuration, and PyWebView bridge calls. Give new fields safe defaults and keep existing argument defaults and persisted names compatible; test legacy data when changing these contracts.
- For frontend delivery or release changes, verify that a persistent WebView cache loads the current UI after an upgrade. Tie the packaged entry URL to the application version and frontend build content, including same-version rebuilds, while preserving the storage origin and user state. Cover invalidation in `tests/test_frontend_entry_url.py`.
- Before release, perform a packaged upgrade smoke test using an existing WebView profile and confirm the updated UI appears. Report checks that were not performed; source or development-mode checks alone do not verify installed upgrades.

## Validation

- Run backend commands from the repository root and frontend commands from `frontend/`.
- Start with focused tests for the changed behavior, then expand checks in proportion to risk.
- Typical backend checks:

  ```bash
  .venv/bin/python -m pytest -q
  uv run ruff check .
  uv run ruff format --check .
  ```

- Typical frontend checks:

  ```bash
  cd frontend
  npm test
  npm run lint
  npm run typecheck
  npm run build
  ```

- Run the full media-processing suite after changing background removal or post-processing behavior:

  ```bash
  .venv/bin/python -m pytest -q -m full
  ```

- Report exactly which checks passed, failed, or were not run. Separate sandbox, network, socket, fixture, and dependency failures from confirmed product regressions.

## Git Hygiene

- Do not discard, rewrite, stage, or commit unrelated changes.
- Stage explicit paths in a mixed worktree.
- Treat commit, push, release, and publication as separate actions; perform only the actions the user requested.
- Before handoff, inspect the diff and run `git diff --check`.
