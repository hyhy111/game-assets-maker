import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { createPinia, setActivePinia } from 'pinia';
import { closeFrontendHarness, createScriptedPyWebViewBridge, loadFrontendModule } from './scripted-pywebview-bridge.mjs';
after(closeFrontendHarness);

test('confirmed permission save preserves config identity and unrelated draft fields', async () => {
  const bridge = createScriptedPyWebViewBridge({ save_cli_generation_enabled: [{ resolve: { success: true } }] });
  setActivePinia(createPinia());
  const { useConfigStore } = await loadFrontendModule('/src/stores/config.ts');
  const store = useConfigStore();
  store.config = { cli_generation_enabled: false, language: 'zh', logger_enabled: false };
  const original = store.config;
  assert.equal(await store.setCliGenerationEnabled(true, true), true);
  assert.equal(store.config, original);
  assert.equal(store.config.cli_generation_enabled, true);
  assert.equal(store.config.logger_enabled, false);
  assert.deepEqual(bridge.calls[0].args, [true, true]);
});


test('failed permission save preserves existing value and config identity', async () => {
  createScriptedPyWebViewBridge({ save_cli_generation_enabled: [{ resolve: { success: false } }] });
  setActivePinia(createPinia());
  const { useConfigStore } = await loadFrontendModule('/src/stores/config.ts');
  const store = useConfigStore();
  store.config = { cli_generation_enabled: false, language: 'zh' };
  const original = store.config;
  assert.equal(await store.setCliGenerationEnabled(true, true), false);
  assert.equal(store.config, original);
  assert.equal(store.config.cli_generation_enabled, false);
});
