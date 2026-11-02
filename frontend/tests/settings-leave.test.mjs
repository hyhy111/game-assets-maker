import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';
import { computed, nextTick, reactive, ref } from 'vue';

const source = await readFile(new URL('../src/views/SeedanceSettings.vue', import.meta.url), 'utf8');
const script = source.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1].replace(/^import[\s\S]*?;\r?\n/gm, '');
const javascript = ts.transpileModule(script, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;

function settings() {
  const calls = [];
  let guard;
  const store = { settings: {}, error: null, async saveSettings() { calls.push('video'); return {}; } };
  const seedreamStore = { settings: {}, error: null, async saveSettings() { calls.push('image'); return {}; } };
  const configStore = { config: {}, error: null, async saveConfig() { calls.push('app'); return true; } };
  const projectStore = { setCurrentProject(value) { calls.push(['project', value]); } };
  const router = { async push(path) { assert.equal(guard({ fullPath: path }), true); calls.push(['route', path]); } };
  const api = { storage: { async saveSettings() { throw Error('unexpected storage save'); } } };
  const dependencies = {
    computed, nextTick, reactive, ref, watch() {}, onMounted() {}, onBeforeUnmount() {},
    onBeforeRouteLeave(callback) { guard = callback; },
    useI18n: () => ({ t: key => key }), useRouter: () => router,
    useSeedanceStore: () => store, useSeedreamStore: () => seedreamStore,
    useConfigStore: () => configStore, useProjectStore: () => projectStore,
    ALLOWED_COUNTS: [1, 2, 3, 4], ALLOWED_RATIOS: ['16:9'], DEFAULT_COUNT: 1, api,
    document: { activeElement: { focus() {} } },
    validationIssueForApiError: () => ({ code: 'SAVE_FAILED', key: 'seedance.validation.generic' }),
  };
  const setup = new Function(...Object.keys(dependencies), `${javascript}\nreturn {
    appDraft, storageDraft, storageSettings, confirmLeave, pendingRoute, saving, leaveError,
    migrationSummary, restartRequired, hasUnsavedChanges, markSettingsSaved,
    saveAndLeave, continueEditing, discardAndLeave, onLeaveKeydown,
  };`);
  const state = setup(...Object.values(dependencies));
  state.markSettingsSaved();
  state.appDraft.logger_enabled = true;
  assert.equal(guard({ fullPath: '/' }), false);
  return { ...state, calls, guard, store, seedreamStore, configStore, api };
}

test('saving all settings from the leave dialog returns home even when another route was requested', async () => {
  const state = settings();
  assert.equal(state.guard({ fullPath: '/login' }), false);
  await state.saveAndLeave();
  assert.deepEqual(state.calls, ['app', 'video', 'image', ['route', '/'], ['project', null]]);
  assert.equal(state.confirmLeave.value, false);
  assert.equal(state.hasUnsavedChanges.value, false);
  assert.equal(state.saving.value, false);
});

for (const stage of ['app', 'video', 'image']) {
  test(`${stage} save failure keeps the dialog and draft without navigating`, async () => {
    const state = settings();
    const target = stage === 'app' ? state.configStore : stage === 'video' ? state.store : state.seedreamStore;
    target[stage === 'app' ? 'saveConfig' : 'saveSettings'] = async () => false;
    await state.saveAndLeave();
    assert.equal(state.confirmLeave.value, true);
    assert.equal(state.hasUnsavedChanges.value, true);
    assert.equal(state.leaveError.value, 'seedance.settings.saveFailed');
    assert.equal(state.saving.value, false);
    assert.ok(!state.calls.some(Array.isArray));
  });
}

test('a thrown save error releases the busy state and allows a successful retry', async () => {
  const state = settings();
  state.configStore.saveConfig = async () => { throw Error('bridge disconnected'); };
  await state.saveAndLeave();
  assert.equal(state.confirmLeave.value, true);
  assert.equal(state.saving.value, false);
  assert.equal(state.leaveError.value, 'seedance.settings.saveFailed');
  state.configStore.saveConfig = async () => true;
  await state.saveAndLeave();
  assert.equal(state.confirmLeave.value, false);
  assert.equal(state.leaveError.value, '');
  assert.deepEqual(state.calls.at(-2), ['route', '/']);
});

test('pending saves block duplicate submissions, dismissal, discard and other navigation', async () => {
  const state = settings();
  let finish;
  state.configStore.saveConfig = () => new Promise(resolve => { finish = resolve; state.calls.push('app'); });
  const saved = state.saveAndLeave();
  assert.equal(state.saving.value, true);
  await state.saveAndLeave();
  state.continueEditing();
  state.onLeaveKeydown({ key: 'Escape' });
  await state.discardAndLeave();
  assert.equal(state.guard({ fullPath: '/login' }), false);
  assert.equal(state.confirmLeave.value, true);
  assert.deepEqual(state.calls, ['app']);
  finish(true);
  await saved;
  assert.deepEqual(state.calls.at(-2), ['route', '/']);
});

test('storage migration confirmation takes over without navigating or clearing the dirty draft', async () => {
  const state = settings();
  state.storageSettings.value = { project_dir: 'project', cache_dir: 'cache' };
  state.storageDraft.project_dir = '/new-projects';
  state.api.storage.saveSettings = async () => ({ success: true, migration_required: true, migration: { token: 'migration' } });
  await state.saveAndLeave();
  assert.equal(state.confirmLeave.value, false);
  assert.equal(state.migrationSummary.value.token, 'migration');
  assert.equal(state.hasUnsavedChanges.value, true);
  assert.deepEqual(state.calls, []);
});

test('a failed migration precheck stays in the leave dialog and shows its error', async () => {
  const state = settings();
  state.storageSettings.value = { project_dir: 'project', cache_dir: 'cache' };
  state.storageDraft.project_dir = '/new-projects';
  state.api.storage.saveSettings = async () => ({ success: false, error: { message: 'Destination is unavailable' } });
  await state.saveAndLeave();
  assert.equal(state.confirmLeave.value, true);
  assert.equal(state.leaveError.value, 'Destination is unavailable');
  assert.equal(state.hasUnsavedChanges.value, true);
  assert.deepEqual(state.calls, []);
});

test('continue editing and discard preserve the existing navigation choices', async () => {
  const state = settings();
  state.continueEditing();
  assert.equal(state.confirmLeave.value, false);
  assert.equal(state.hasUnsavedChanges.value, true);
  assert.equal(state.guard({ fullPath: '/login' }), false);
  await state.discardAndLeave();
  assert.deepEqual(state.calls, [['route', '/login']]);
});
