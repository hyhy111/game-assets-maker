import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

const viewUrl = new URL('../src/views/SeedanceSettings.vue', import.meta.url);
const apiUrl = new URL('../src/api/index.ts', import.meta.url);
const zhUrl = new URL('../src/locales/zh-CN.ts', import.meta.url);
const enUrl = new URL('../src/locales/en.ts', import.meta.url);

async function sources() {
  const [view, api, zh, en] = await Promise.all([
    readFile(viewUrl, 'utf8'),
    readFile(apiUrl, 'utf8'),
    readFile(zhUrl, 'utf8'),
    readFile(enUrl, 'utf8'),
  ]);
  return { view, api, zh, en };
}

test('settings page shows selectable, copyable resolved paths for project and AI cache', async () => {
  const { view, zh, en } = await sources();

  // A dedicated storage panel renders both locations as readonly (selectable
  // and copyable) inputs showing the resolved absolute path.
  assert.match(view, /data-test="storage-project-dir"/);
  assert.match(view, /data-test="storage-cache-dir"/);
  const projectInput = view.match(/<input[^>]*data-test="storage-project-dir"[^>]*>/)?.[0] ?? '';
  const cacheInput = view.match(/<input[^>]*data-test="storage-cache-dir"[^>]*>/)?.[0] ?? '';
  assert.match(projectInput, /readonly/);
  assert.match(cacheInput, /readonly/);
  assert.match(projectInput, /:value="projectDisplayPath"/);
  assert.match(cacheInput, /:value="cacheDisplayPath"/);
  assert.match(view, /<div class="grid gap-4">[\s\S]*storage-project-dir[\s\S]*storage-cache-dir/);

  // Resolved display paths fall back to the backend-resolved roots while the
  // configured value stays relative.
  assert.match(view, /storageSettings\.value\?\.projects_root/);
  assert.match(view, /storageSettings\.value\?\.ai_cache_root/);

  // The page loads the storage settings on mount.
  assert.match(view, /api\.storage\.getSettings\(\)/);

  for (const locale of [zh, en]) {
    assert.match(locale, /projectDir:/);
    assert.match(locale, /aiCacheDir:/);
  }
});

test('choosing a directory only updates the draft', async () => {
  const { view } = await sources();

  const body = view.match(/async function selectStorageDirectory\(field: 'project_dir' \| 'cache_dir'\) \{[\s\S]*?\n\}/)?.[0] ?? '';
  assert.ok(body, 'selectStorageDirectory exists');
  assert.match(body, /api\.system\.selectDirectory\(\)/);
  assert.match(body, /storageDraft\[field\] = path/);
  assert.doesNotMatch(body, /saveSettings|saveConfig|executeMigration/);
  for (const field of ['project_dir', 'cache_dir']) {
    assert.ok(view.includes(`selectStorageDirectory('${field}')`), `chooser wired for ${field}`);
  }

  // Draft edits feed the unsaved-changes snapshot.
  assert.match(view, /storage:\s*\{ \.\.\.storageDraft \}/);
});

test('save routes through a plain save or a single migration confirmation', async () => {
  const { view } = await sources();

  // The save button branches on whether the configured path values changed.
  assert.match(view, /storagePathsChanged/);
  const branch = view.match(/async function saveWithMigrationCheck\(\) \{[\s\S]*?\n\}/)?.[0] ?? '';
  assert.ok(branch, 'migration-aware save branch exists');
  assert.match(branch, /api\.storage\.saveSettings\(combined\)/);
  assert.match(branch, /project_dir: storageDraft\.project_dir/);
  assert.match(branch, /cache_dir: storageDraft\.cache_dir/);
  // A newly entered API key rides inside the transactional draft instead of
  // being persisted before the precheck, so a failed migration saves nothing.
  assert.match(branch, /api_key: apiKey\.value/);

  // One confirmation dialog lists every entry of a multi-location change, so
  // a double-path migration asks exactly once.
  const dialog = view.match(/<div\s+v-if="migrationSummary"[\s\S]*?migrationConfirm/)?.[0] ?? '';
  assert.ok(dialog, 'migration confirmation dialog exists');
  assert.match(dialog, /v-for="entry in migrationSummary\.entries"/);
  assert.match(dialog, /entry\.source/);
  assert.match(dialog, /entry\.target/);
  assert.match(dialog, /keepOldNotice/);
  assert.match(dialog, /restartNotice/);

  // Rejecting the confirmation never executes the migration.
  const cancel = view.match(/function closeMigrationConfirmation\(\) \{[\s\S]*?\n\}/)?.[0] ?? '';
  assert.ok(cancel, 'cancel handler exists');
  assert.doesNotMatch(cancel, /executeMigration|saveSettings/);
});

test('migration progress and failure feedback keep the draft dirty', async () => {
  const { view } = await sources();

  const execute = view.match(/async function executeMigration\(\) \{[\s\S]*?\n\}/)?.[0] ?? '';
  assert.ok(execute, 'execute handler exists');
  assert.match(execute, /addEventListener\('storage-migration-progress'/);
  assert.match(execute, /removeEventListener\('storage-migration-progress'/);
  assert.match(execute, /api\.storage\.executeMigration\(migrationSummary\.value\.token\)/);

  // Failure path: surface the error and keep dirty state (no markSettingsSaved).
  const failure = execute.match(/if \(!result\.success\) \{[\s\S]*?\}/)?.[0] ?? '';
  assert.match(failure, /migrationError\.value = result\.error\.message/);
  assert.doesNotMatch(failure, /markSettingsSaved/);
  assert.match(view, /data-test="storage-migration-error"/);

  // Progress is rendered while copying.
  assert.match(view, /migrationProgress\.copied/);
  assert.match(view, /migrationProgress\.total/);
});

test('a committed migration forces a restart-only state', async () => {
  const { view, zh, en } = await sources();

  // The blocking overlay offers exactly the two allowed exits.
  assert.match(view, /v-if="restartRequired"/);
  assert.match(view, /data-test="storage-restart-required"/);
  assert.match(view, /data-test="storage-restart-now"/);

  // Navigation back into project processing or AI generation is blocked.
  const guard = view.match(/onBeforeRouteLeave\(\(to\) => \{[\s\S]*?\n\}\)/)?.[0] ?? '';
  assert.match(guard, /if \(restartRequired\.value\) return false;/);

  // One-click restart enters the close flow immediately without waiting for a
  // plain-save success message.
  const restart = view.match(/async function restartNow\(\) \{[\s\S]*?\n\}/)?.[0] ?? '';
  assert.match(restart, /api\.lifecycle\.requestAppRestart\(\)/);
  assert.doesNotMatch(restart, /markSettingsSaved|saveFeedback/);

  // Closing routes through the backend so the closed event runs the regular
  // cleanup; JS window.close() is not reliably routed by PyWebView.
  assert.match(view, /api\.lifecycle\.closeApp\(\)/);
  assert.doesNotMatch(view, /window\.close\(\)/);

  for (const locale of [zh, en]) {
    assert.match(locale, /restartRequiredTitle:/);
    assert.match(locale, /restartNow:/);
    assert.match(locale, /closeApp:/);
  }
});

test('frontend API wrappers expose the storage and lifecycle endpoints', async () => {
  const { api } = await sources();

  assert.match(api, /storage_get_settings/);
  assert.match(api, /storage_save_settings/);
  assert.match(api, /storage_execute_migration/);
  assert.match(api, /storage_migration_state/);
  assert.match(api, /request_app_restart/);
  assert.match(api, /close_app/);
  assert.match(api, /storage: storageApi/);
  assert.match(api, /lifecycle: lifecycleApi/);
});
