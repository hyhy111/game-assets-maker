import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import ts from 'typescript';
import { computed, ref } from 'vue';

const source = await readFile(new URL('../src/stores/updates.ts', import.meta.url), 'utf8');
const available = {
  current_version: '1.0.0', latest_version: '1.0.1', release_notes: 'Fixes',
  release_url: 'https://github.com/hyhy111/game-assets-maker/releases/tag/v1.0.1',
  status: 'available', error: '',
};

function createStore(overrides = {}) {
  const calls = { check: 0, version: 0, open: 0, ignore: [] };
  const system = {
    getAppVersion: async () => { calls.version++; return '1.0.0'; },
    checkAppUpdate: async () => { calls.check++; return { ...available }; },
    ignoreAppUpdate: async version => { calls.ignore.push(version); return true; },
    openAppUpdate: async () => { calls.open++; return true; },
    ...overrides,
  };
  const code = source.replace(/^import .*;$/gm, '').replace('export const useUpdateStore', 'const useUpdateStore');
  const compiled = ts.transpileModule(`${code}\nuseUpdateStore();`, {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const store = vm.runInNewContext(compiled, { ref, computed, defineStore: (_name, setup) => setup, api: { system } });
  return { store, calls };
}

test('startup checks once and exposes a notification only after a newer release arrives', async () => {
  let resolve;
  let count = 0;
  const { store } = createStore({ checkAppUpdate: () => { count++; return new Promise(done => { resolve = done; }); } });
  assert.equal(store.hasUpdate.value, false);
  const startup = store.initialize();
  assert.equal(store.checking.value, true);
  await store.initialize();
  assert.equal(count, 1);
  assert.equal(store.hasUpdate.value, false);
  resolve({ ...available });
  await startup;
  assert.equal(store.currentVersion.value, '1.0.0');
  assert.equal(store.hasUpdate.value, true);
  assert.equal(store.checking.value, false);
});

test('ignore hides the notification but retains manual update access', async () => {
  const { store, calls } = createStore();
  await store.initialize();
  await store.openUpdate();
  assert.equal(calls.open, 1);
  await store.ignoreCurrentVersion();
  assert.deepEqual(calls.ignore, ['1.0.1']);
  assert.equal(store.hasUpdate.value, false);
  assert.equal(store.state.value.status, 'ignored');
  assert.equal(store.canUpdate.value, true);
  assert.equal(store.currentVersion.value, '1.0.0');
  await store.openUpdate();
  await store.initialize();
  assert.equal(calls.open, 2);
  assert.equal(calls.check, 1);
});

for (const status of ['up_to_date', 'error']) {
  test(`${status} never exposes update actions`, async () => {
    const { store, calls } = createStore({ checkAppUpdate: async () => ({ ...available, status }) });
    await store.initialize();
    await store.openUpdate();
    await store.ignoreCurrentVersion();
    assert.equal(store.hasUpdate.value, false);
    assert.equal(calls.open, 0);
    assert.deepEqual(calls.ignore, []);
  });
}

test('network failure retains the local version and does not report up to date', async () => {
  const { store } = createStore({ checkAppUpdate: async () => { throw new Error('offline'); } });
  await store.initialize();
  assert.equal(store.currentVersion.value, '1.0.0');
  assert.equal(store.state.value.status, 'error');
  assert.equal(store.hasUpdate.value, false);
  assert.equal(store.checking.value, false);
});

for (const reject of [async () => false, async () => { throw new Error('failed'); }]) {
  test('ignore failure preserves the actionable notification', async () => {
    const { store } = createStore({ ignoreAppUpdate: reject });
    await store.initialize();
    await store.ignoreCurrentVersion();
    assert.equal(store.hasUpdate.value, true);
    assert.equal(store.actionError.value, 'ignoreFailed');
    assert.equal(store.actionPending.value, false);
  });
}

test('a blocked browser reports failure and keeps the update actionable', async () => {
  const { store } = createStore({ openAppUpdate: async () => false });
  await store.initialize();
  await store.openUpdate();
  assert.equal(store.actionError.value, 'openFailed');
  assert.equal(store.hasUpdate.value, true);
});


test('an ignored version loaded at startup still permits manual update without a notification', async () => {
  const { store, calls } = createStore({ checkAppUpdate: async () => ({ ...available, status: 'ignored' }) });
  await store.initialize();
  assert.equal(store.hasUpdate.value, false);
  assert.equal(store.canUpdate.value, true);
  await store.openUpdate();
  await store.ignoreCurrentVersion();
  assert.equal(calls.open, 1);
  assert.deepEqual(calls.ignore, []);
});
