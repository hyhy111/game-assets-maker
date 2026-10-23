import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { createRenderer, nextTick, ssrContextKey } from 'vue';
import { createPinia, setActivePinia } from 'pinia';
import { createI18n } from 'vue-i18n';
import { createMemoryHistory, createRouter } from 'vue-router';
import { closeFrontendHarness, createScriptedPyWebViewBridge, loadFrontendModule } from './scripted-pywebview-bridge.mjs';

after(closeFrontendHarness);
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: { getItem: () => null, setItem() {}, removeItem() {} },
});
const imageId = 'doubao-seedream-5-0-pro-260628';
const videoId = 'doubao-seedance-2-0-mini-260615';
const capabilities = {
  image: { models: [{ model: imageId, sizes: ['1K', '1.5K', '2K'] }] },
  video: { models: [{ model: videoId, resolutions: ['720p'], durationsByResolution: { '720p': [4] } }], ratios: ['16:9'] },
};
const renderer = createRenderer({
  createElement: () => ({ children: [] }), createText: () => ({}), createComment: () => ({}),
  insert() {}, remove() {}, setText() {}, setElementText() {}, patchProp() {},
  parentNode: () => null, nextSibling: () => null,
});
const settle = async () => { for (let i = 0; i < 10; i++) await nextTick(); };

async function mountPage(t, kind, { loggedIn = true, capabilityResponse, quoteResponse } = {}) {
  const bridge = createScriptedPyWebViewBridge({
    set_platform_config: [{ resolve: { success: true } }],
    get_platform_capabilities: [{ resolve: capabilityResponse ?? { success: true, data: capabilities } }],
    seedream_quote_image: [{ resolve: quoteResponse ?? { success: true, data: { quote: 60 } } }],
    seedance_quote_video: [{ resolve: quoteResponse ?? { success: true, data: { quote: 199 } } }],
  });
  bridge.window.scrollTo = () => {};
  const pinia = createPinia();
  setActivePinia(pinia);
  const { useAICreationStore } = await loadFrontendModule('/src/stores/aiCreation.ts');
  const { useAuthStore } = await loadFrontendModule('/src/stores/auth.ts');
  const { useSeedreamStore } = await loadFrontendModule('/src/stores/seedream.ts');
  const { useSeedanceStore } = await loadFrontendModule('/src/stores/seedance.ts');
  const workspace = useAICreationStore();
  const auth = useAuthStore();
  auth.status = loggedIn ? 'authenticated' : 'unknown';
  useSeedreamStore().settings = { default_model: 'pro', default_model_id: imageId, default_count: 1, default_resolution: '2K', default_ratio: '16:9' };
  useSeedanceStore().settings = {
    default_model: 'mini', default_model_id: videoId, default_resolution: '720p', default_ratio: '16:9', default_duration: 4,
    default_generate_audio: true, default_return_last_frame: false, api_key_configured: true,
  };
  if (kind !== 'workspace') {
    workspace.generationSource = 'forfuner-ai';
    workspace.imageDraft.model = imageId;
    workspace.videoDraft.model = videoId;
    workspace.videoDraft.return_last_frame = false;
  }
  const filename = kind === 'image' ? 'SeedreamCreate' : kind === 'video' ? 'SeedanceCreate' : 'AICreationWorkspace';
  const { default: component } = await loadFrontendModule(`/src/views/${filename}.vue`);
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/ai-creation', component: { render: () => null } }] });
  await router.push('/ai-creation');
  await router.isReady();
  const app = renderer.createApp({ ...component, render: () => null }, { embedded: true, showTaskList: false, showBatchList: false });
  app.use(pinia).use(router).use(createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false, messages: { en: {} } }));
  app.provide(ssrContextKey, { modules: new Set() });
  t.mock.timers.enable({ apis: ['setTimeout'] });
  app.mount({ children: [] });
  t.after(() => app.unmount());
  await settle();
  return { app, workspace, auth, calls: bridge.calls, tick: async () => { await settle(); t.mock.timers.tick(400); await settle(); } };
}

for (const kind of ['image', 'video']) {
  test(`${kind}: first entry loads a quote when model and parameters already match`, async t => {
    const page = await mountPage(t, kind);
    await page.tick();
    const quotes = page.calls.filter(call => call.method === (kind === 'image' ? 'seedream_quote_image' : 'seedance_quote_video'));
    assert.equal(quotes.length, 1, 'first entry must request the credit estimate without editing parameters');
    assert.equal(page.app._instance.setupState[kind === 'image' ? 'quoteUnit' : 'quoteValue'], kind === 'image' ? 60 : 199);
  });

  test(`${kind}: delayed capabilities trigger a quote only after the catalog is ready`, async t => {
    let resolveCapabilities;
    const response = new Promise(resolve => { resolveCapabilities = resolve; });
    const page = await mountPage(t, kind, { capabilityResponse: () => response });
    const method = kind === 'image' ? 'seedream_quote_image' : 'seedance_quote_video';
    await page.tick();
    assert.equal(page.calls.filter(call => call.method === method).length, 0);
    resolveCapabilities({ success: true, data: capabilities });
    await page.tick();
    assert.equal(page.calls.filter(call => call.method === method).length, 1);
    assert.equal(page.app._instance.setupState[kind === 'image' ? 'quoteUnit' : 'quoteValue'], kind === 'image' ? 60 : 199);
  });

  test(`${kind}: a late quote cannot return after switching to a custom key`, async t => {
    let resolveQuote;
    const response = new Promise(resolve => { resolveQuote = resolve; });
    const page = await mountPage(t, kind, { quoteResponse: () => response });
    await page.tick();
    assert.equal(page.app._instance.setupState.quoteLoading, true);
    page.workspace.setGenerationSource('api-key');
    await settle();
    resolveQuote({ success: true, data: { quote: 999 } });
    await settle();
    assert.equal(page.app._instance.setupState[kind === 'image' ? 'quoteUnit' : 'quoteValue'], null);
    assert.equal(page.app._instance.setupState.quoteLoading, false);
  });

  test(`${kind}: late login restores the initial quote without a model change`, async t => {
    const page = await mountPage(t, kind, { loggedIn: false });
    await page.tick();
    page.auth.status = 'authenticated';
    await page.tick();
    assert.equal(page.calls.filter(call => call.method === (kind === 'image' ? 'seedream_quote_image' : 'seedance_quote_video')).length, 1);
  });
}

test('workspace entry defaults a signed-in account to ForFuner AI and permits a manual source change', async t => {
  const page = await mountPage(t, 'workspace');
  assert.equal(page.workspace.generationSource, 'forfuner-ai');
  page.workspace.setGenerationSource('api-key');
  await page.tick();
  assert.equal(page.workspace.generationSource, 'api-key');
});

test('workspace entry follows delayed login restoration', async t => {
  const page = await mountPage(t, 'workspace', { loggedIn: false });
  assert.equal(page.workspace.generationSource, 'api-key');
  page.auth.status = 'authenticated';
  await page.tick();
  assert.equal(page.workspace.generationSource, 'forfuner-ai');
});
