import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import ts from 'typescript';

const storeSource = await readFile(new URL('../src/stores/config.ts', import.meta.url), 'utf8');
const viewSource = await readFile(new URL('../src/views/SeedanceSettings.vue', import.meta.url), 'utf8');

function createStore(save) {
  const source = storeSource.replace(/^import .*;$/gm, '').replace('export const useConfigStore', 'const useConfigStore');
  const compiled = ts.transpileModule(`${source}\nuseConfigStore();`, {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const context = {
    defineStore: (_name, setup) => setup,
    ref: value => ({ value }),
    api: { config: { setArkAuditEnabled: save } },
  };
  return vm.runInNewContext(compiled, context);
}

test('immediate audit save updates only its field and preserves config identity and draft values', async () => {
  const calls = [];
  const store = createStore(async value => { calls.push(value); return true; });
  const previous = { ark_audit_enabled: false, logger_enabled: false, seedance: { default_duration: 4 } };
  store.config.value = previous;
  assert.equal(await store.setArkAuditEnabled(true), true);
  assert.deepEqual(calls, [true]);
  assert.equal(store.config.value, previous);
  assert.equal(store.config.value.ark_audit_enabled, true);
  assert.equal(store.config.value.logger_enabled, false);
  assert.equal(store.config.value.seedance.default_duration, 4);
});

test('save rejection and transport failure leave persisted UI state unchanged', async () => {
  for (const save of [async () => false, async () => { throw new Error('offline'); }]) {
    const store = createStore(save);
    store.config.value = { ark_audit_enabled: true };
    assert.equal(await store.setArkAuditEnabled(false), false);
    assert.equal(store.config.value.ark_audit_enabled, true);
  }
});

test('settings audit toggle is qualified by the backend and does not enter unified-save drafts', () => {
  assert.match(viewSource, /v-if="configStore\.config\?\.ark_audit_available"/);
  assert.match(viewSource, /:model-value="configStore\.config\.ark_audit_enabled === true"/);
  const appDraft = viewSource.match(/const appDraft = reactive\(\{[\s\S]*?\}\);/)?.[0];
  const snapshot = viewSource.match(/const currentSnapshot = computed\([\s\S]*?\}\)\);/)?.[0];
  const unifiedSave = viewSource.match(/async function saveWithMigrationCheck\(\) \{[\s\S]*?\n\}/)?.[0];
  for (const source of [appDraft, snapshot, unifiedSave]) {
    assert.ok(source);
    assert.doesNotMatch(source, /ark_audit_enabled/);
  }
});

test('settings handler saves immediately and reports failure without changing other drafts or snapshots', async () => {
  const source = viewSource.match(/async function setArkAuditEnabled\(enabled: boolean\) \{[\s\S]*?\n\}/)?.[0];
  assert.ok(source);
  const context = {
    configStore: { config: { ark_audit_available: true }, setArkAuditEnabled: async () => false },
    auditSaving: { value: false },
    auditError: { value: '' },
    t: key => key,
  };
  const compiled = ts.transpileModule(`${source}\nsetArkAuditEnabled(true);`, {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  }).outputText;
  await vm.runInNewContext(compiled, context);
  assert.equal(context.auditError.value, 'settings.arkAuditSaveFailed');
  assert.equal(context.auditSaving.value, false);
  assert.doesNotMatch(source, /appDraft|markSettingsSaved|saveConfig|saveSettings/);
});
