import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';
import { computed, nextTick, reactive, ref } from 'vue';

const source = await readFile(new URL('../src/views/SeedanceSettings.vue', import.meta.url), 'utf8');
const script = source.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1].replace(/^import[\s\S]*?;\r?\n/gm, '');
const javascript = ts.transpileModule(script, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;

function settings() {
  const savedConfigs = [];
  const store = { settings: {}, error: null, async saveSettings() { return {}; } };
  const seedreamStore = { settings: {}, error: null, async saveSettings() { return {}; } };
  const configStore = {
    config: {
      logger_enabled: false,
      paid_generation_confirmation_enabled: true,
      processing: { background_model: 'birefnet-comfy' },
    },
    error: null,
    async saveConfig(update) { savedConfigs.push(update); return true; },
  };
  const projectStore = { setCurrentProject() {} };
  const router = { async push() {} };
  const api = { storage: { async saveSettings() { throw Error('unexpected storage save'); } } };
  const dependencies = {
    computed, nextTick, reactive, ref, watch() {}, onMounted() {}, onBeforeUnmount() {},
    onBeforeRouteLeave() {},
    useI18n: () => ({ t: key => key }), useRouter: () => router,
    useSeedanceStore: () => store, useSeedreamStore: () => seedreamStore,
    useConfigStore: () => configStore, useProjectStore: () => projectStore,
    ALLOWED_COUNTS: [1, 2, 3, 4], ALLOWED_RATIOS: ['16:9'], DEFAULT_COUNT: 1, api,
    document: { activeElement: { focus() {} } },
    validationIssueForApiError: () => ({ code: 'SAVE_FAILED', key: 'seedance.validation.generic' }),
  };
  const setup = new Function(...Object.keys(dependencies), `${javascript}\nreturn {
    processingDraft, syncAppDraft, savePlain, currentSnapshot, hasUnsavedChanges, markSettingsSaved,
  };`);
  return { ...setup(...Object.values(dependencies)), savedConfigs };
}

test('syncAppDraft applies the configured default background model', () => {
  const state = settings();
  assert.equal(state.processingDraft.background_model, 'u2net');
  state.syncAppDraft({
    logger_enabled: false,
    paid_generation_confirmation_enabled: true,
    processing: { background_model: 'birefnet-comfy' },
  });
  assert.equal(state.processingDraft.background_model, 'birefnet-comfy');
});

test('syncAppDraft keeps the draft when config predates the processing section', () => {
  const state = settings();
  state.processingDraft.background_model = 'birefnet-comfy';
  state.syncAppDraft({ logger_enabled: true, paid_generation_confirmation_enabled: true });
  assert.equal(state.processingDraft.background_model, 'birefnet-comfy');
});

test('savePlain persists the processing defaults with the app config', async () => {
  const state = settings();
  state.syncAppDraft({
    logger_enabled: false,
    paid_generation_confirmation_enabled: true,
    processing: { background_model: 'birefnet-comfy' },
  });
  const saved = await state.savePlain();
  assert.equal(saved, true);
  assert.deepEqual(state.savedConfigs, [{
    logger_enabled: false,
    paid_generation_confirmation_enabled: true,
    processing: { background_model: 'birefnet-comfy' },
  }]);
});

test('editing the default background model marks settings as unsaved', () => {
  const state = settings();
  state.syncAppDraft({
    logger_enabled: false,
    paid_generation_confirmation_enabled: true,
    processing: { background_model: 'u2net' },
  });
  state.markSettingsSaved();
  assert.equal(state.hasUnsavedChanges.value, false);
  state.processingDraft.background_model = 'birefnet-comfy';
  assert.equal(state.hasUnsavedChanges.value, true);
});
