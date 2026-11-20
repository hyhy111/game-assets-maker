import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { createPinia, setActivePinia } from 'pinia';
import {
  closeFrontendHarness,
  createScriptedPyWebViewBridge,
  loadFrontendModule,
} from './scripted-pywebview-bridge.mjs';

after(closeFrontendHarness);

test('step 2 params default to the configured background removal model', async () => {
  createScriptedPyWebViewBridge({
    get_step_params: [{ resolve: {} }],
  });
  setActivePinia(createPinia());
  const { useConfigStore } = await loadFrontendModule('/src/stores/config.ts');
  const { useProcessStore } = await loadFrontendModule('/src/stores/process.ts');
  useConfigStore().config = { processing: { background_model: 'birefnet-comfy' } };
  const store = useProcessStore();

  await store.loadStepParams('hero/idle', 2);

  assert.equal(store.s2Params.model, 'birefnet-comfy');
});

test('a project saved model overrides the configured default', async () => {
  createScriptedPyWebViewBridge({
    get_step_params: [{ resolve: { model: 'u2net' } }],
  });
  setActivePinia(createPinia());
  const { useConfigStore } = await loadFrontendModule('/src/stores/config.ts');
  const { useProcessStore } = await loadFrontendModule('/src/stores/process.ts');
  useConfigStore().config = { processing: { background_model: 'birefnet-comfy' } };
  const store = useProcessStore();

  await store.loadStepParams('hero/idle', 2);

  assert.equal(store.s2Params.model, 'u2net');
});

test('step 2 params fall back to u2net without a configured default', async () => {
  createScriptedPyWebViewBridge({
    get_step_params: [{ resolve: {} }],
  });
  setActivePinia(createPinia());
  const { useProcessStore } = await loadFrontendModule('/src/stores/process.ts');
  const store = useProcessStore();

  await store.loadStepParams('hero/idle', 2);

  assert.equal(store.s2Params.model, 'u2net');
});
