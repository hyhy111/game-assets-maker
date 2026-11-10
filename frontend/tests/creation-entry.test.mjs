import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { createRenderer, nextTick, ssrContextKey } from 'vue';
import { createPinia, setActivePinia } from 'pinia';
import { createI18n } from 'vue-i18n';
import { createMemoryHistory, createRouter } from 'vue-router';
import { closeFrontendHarness, createScriptedPyWebViewBridge, loadFrontendModule } from './scripted-pywebview-bridge.mjs';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';
import zhCN from '../src/locales/zh-CN.ts';

after(closeFrontendHarness);
after(closeSfcRenderer);
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
const availability = {
  asOf: '2026-01-01T00:00:00Z', refreshAt: '2026-01-01T00:01:00Z',
  account: { generalAvailable: 10000, bonusAvailable: 0, totalAvailable: 10000, buckets: [] },
  combinations: [
    { context: { platform: 'forfuner-ai', mediaType: 'image', model: imageId, resolution: null, durationSec: null, sizeLabel: '2K' }, quote: 60, generalAvailable: 10000, bonusAvailable: 0, message: '', canSubmit: true },
    { context: { platform: 'forfuner-ai', mediaType: 'video', model: videoId, resolution: '720p', durationSec: 4, sizeLabel: null }, quote: 199, generalAvailable: 10000, bonusAvailable: 0, message: '', canSubmit: true },
  ],
};
const jsonResponse = data => new Response(JSON.stringify({ code: 200, data }), {
  status: 200, headers: { 'Content-Type': 'application/json' },
});
const renderer = createRenderer({
  createElement: () => ({ children: [] }), createText: () => ({}), createComment: () => ({}),
  insert() {}, remove() {}, setText() {}, setElementText() {}, patchProp() {},
  parentNode: () => null, nextSibling: () => null,
});
const settle = async () => { for (let i = 0; i < 10; i++) await nextTick(); };
const composerSource = kind => readFile(new URL(`../src/views/${kind === 'image' ? 'SeedreamCreate' : 'SeedanceCreate'}.vue`, import.meta.url), 'utf8');
async function primarySubmitDisabled(kind, state) {
  const source = await composerSource(kind);
  const expression = source.match(new RegExp(`:disabled="([^"]+)"[^>]*data-test="${kind === 'image' ? 'seedream' : 'seedance'}-submit"`))?.[1];
  assert.ok(expression, 'evaluate the primary button binding against the mounted component state');
  return new Function('state', `with (state) { return (${expression}); }`)(state);
}

async function mountPage(t, kind, { loggedIn = true, capabilityResponse, quoteResponse, availabilityResponse = availability, regenerationResponse, generationSource = 'forfuner-ai', routeQuery, bridgeScript = {}, initialModel } = {}) {
  const bridge = createScriptedPyWebViewBridge({
    set_platform_config: [{ resolve: { success: true } }],
    get_platform_capabilities: [{ resolve: capabilityResponse ?? { success: true, data: capabilities } }],
    seedream_get_regeneration_draft: regenerationResponse ? [{ resolve: regenerationResponse }] : [],
    ...bridgeScript,
  });
  const httpCalls = [];
  t.mock.method(globalThis, 'fetch', async (input, init = {}) => {
    const path = new URL(String(input)).pathname;
    httpCalls.push({ path, method: init.method ?? 'GET', body: init.body ? JSON.parse(init.body) : null });
    if (path === '/app/credit/v2/availability') return jsonResponse(availabilityResponse);
    const quoteMatch = path.match(/^\/app\/credit\/v2\/quote\/(image|video)$/);
    if (quoteMatch) {
      const response = typeof quoteResponse === 'function' ? await quoteResponse(httpCalls.at(-1).body) : quoteResponse;
      if (response instanceof Response) return response;
      return jsonResponse({
        quote: response?.data?.quote ?? (quoteMatch[1] === 'image' ? 60 : 199),
        canSubmit: response?.data?.canSubmit ?? true,
        message: response?.data?.message ?? '',
      });
    }
    throw new Error(`No scripted HTTP response for ${path}`);
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
    workspace.generationSource = generationSource;
    workspace.imageDraft.model = imageId;
    workspace.videoDraft.model = videoId;
    workspace.videoDraft.return_last_frame = false;
    if (initialModel) workspace[kind === 'image' ? 'imageDraft' : 'videoDraft'].model = initialModel;
  }
  const filename = kind === 'image' ? 'SeedreamCreate' : kind === 'video' ? 'SeedanceCreate' : 'AICreationWorkspace';
  const { default: component } = await loadFrontendModule(`/src/views/${filename}.vue`);
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/ai-creation', component: { render: () => null } }] });
  await router.push({ path: '/ai-creation', query: routeQuery ?? (regenerationResponse ? { regenerate: 'batch-to-restore' } : {}) });
  await router.isReady();
  const app = renderer.createApp({ ...component, render: () => null }, { embedded: true, showTaskList: false, showBatchList: false });
  app.use(pinia).use(router).use(createI18n({ legacy: false, locale: 'zh-CN', missingWarn: false, fallbackWarn: false, messages: { 'zh-CN': zhCN } }));
  app.provide(ssrContextKey, { modules: new Set() });
  t.mock.timers.enable({ apis: ['setTimeout'] });
  app.mount({ children: [] });
  t.after(() => app.unmount());
  await settle();
  return { app, workspace, auth, bridge, httpCalls, tick: async () => { await settle(); t.mock.timers.tick(400); await settle(); } };
}

for (const catalogDelayed of [false, true]) {
  test(`image: restoring an API-key batch quotes the upstream model ID with ${catalogDelayed ? 'delayed' : 'ready'} capabilities`, async t => {
    let resolveCatalog;
    const catalog = new Promise(resolve => { resolveCatalog = resolve; });
    const request = { prompt: 'restored deer', model: 'pro', resolution: '2K', ratio: '16:9', count: 1, source: 'api-key', reference_image: null };
    const page = await mountPage(t, 'image', {
      capabilityResponse: catalogDelayed ? () => catalog : undefined,
      regenerationResponse: { success: true, data: { request, model_id: imageId } },
    });
    if (catalogDelayed) resolveCatalog({ success: true, data: capabilities });
    await page.tick();

    assert.equal(page.workspace.generationSource, 'forfuner-ai');
    assert.equal(page.workspace.imageDraft.model, imageId);
    assert.equal(page.workspace.imageDraft.prompt, request.prompt);
    assert.equal(page.workspace.imageDraft.resolution, '2K');
    const quotes = page.httpCalls.filter(call => call.path === '/app/credit/v2/quote/image');
    assert.ok(quotes.length);
    assert.ok(quotes.every(call => call.body.model === imageId));
    assert.equal(page.app._instance.setupState.platformConfirmBlocked, false);
    assert.equal(page.bridge.calls.some(call => call.method === 'seedream_create_batch'), false);
  });
}

test('image: restoring a custom-key draft keeps its local model and makes no platform quote', async t => {
  const page = await mountPage(t, 'image', {
    generationSource: 'api-key',
    regenerationResponse: {
      success: true,
      data: { request: { prompt: 'restored deer', model: 'pro', resolution: '2K', ratio: '16:9', count: 1 }, model_id: imageId },
    },
  });
  await page.tick();
  assert.equal(page.workspace.imageDraft.model, 'pro');
  assert.equal(page.httpCalls.some(call => call.path === '/app/credit/v2/quote/image'), false);
});

for (const kind of ['image', 'video']) {
  for (const requestFailed of [false, true]) {
    test(`${kind}: ${requestFailed ? 'a failed quote request keeps its failure explanation' : 'insufficient credits do not claim the quote request failed'}`, async t => {
      const message = requestFailed ? '积分服务暂不可用' : '当前模型和规格可用积分不足，还差 20 分';
      const page = await mountPage(t, kind, {
        quoteResponse: requestFailed
          ? new Response(JSON.stringify({ code: 500, msg: message }), { status: 500 })
          : { data: { quote: 199, canSubmit: false, message } },
      });
      await page.tick();
      const state = page.app._instance.setupState;
      assert.equal(state.platformConfirmBlocked, true);
      const html = await renderSfc(`views/${kind === 'image' ? 'SeedreamCreate' : 'SeedanceCreate'}.vue`, {
        props: { embedded: true, showTaskList: false, showBatchList: false },
        piniaState: { auth: { status: 'authenticated' }, 'ai-creation': { generationSource: 'forfuner-ai' } },
        configureSetup(bindings) {
          bindings.quoteError.value = state.quoteError;
          if (kind === 'video') bindings.paidConfirmModal.value = true;
        },
      });
      assert.ok(html.includes(requestFailed ? message : '预计消耗 199 积分，当前可用积分不足'));
      if (requestFailed) assert.match(html, /平台报价获取失败/);
      else assert.doesNotMatch(html, /平台报价获取失败/);
    });
  }

  test(`${kind}: first entry loads a quote when model and parameters already match`, async t => {
    const page = await mountPage(t, kind);
    await page.tick();
    const quotes = page.httpCalls.filter(call => call.path === `/app/credit/v2/quote/${kind}`);
    assert.equal(quotes.length, 1, 'first entry must request the credit estimate without editing parameters');
    assert.equal(page.app._instance.setupState[kind === 'image' ? 'quoteUnit' : 'quoteValue'], kind === 'image' ? 60 : 199);
  });

  test(`${kind}: delayed capabilities trigger a quote only after the catalog is ready`, async t => {
    let resolveCapabilities;
    const response = new Promise(resolve => { resolveCapabilities = resolve; });
    const page = await mountPage(t, kind, { capabilityResponse: () => response });
    const quotePath = `/app/credit/v2/quote/${kind}`;
    await page.tick();
    assert.equal(page.httpCalls.filter(call => call.path === quotePath).length, 0);
    resolveCapabilities({ success: true, data: capabilities });
    await page.tick();
    assert.equal(page.httpCalls.filter(call => call.path === quotePath).length, 1);
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
    assert.equal(page.httpCalls.filter(call => call.path === `/app/credit/v2/quote/${kind}`).length, 1);
  });

  test(`${kind}: logout keeps the primary login prompt reachable without allowing confirmation`, async t => {
    const page = await mountPage(t, kind);
    await page.tick();
    const state = page.app._instance.setupState;
    page.workspace.imageDraft.prompt = 'Create a character';
    page.workspace.videoDraft.prompt = 'Walk forward';
    page.workspace.videoDraft.first_frame = '/tmp/character.png';
    page.auth.status = 'guest';
    await page.tick();
    assert.equal(page.workspace.generationSource, 'forfuner-ai');
    assert.equal(await primarySubmitDisabled(kind, state), false);
    assert.equal(state.platformConfirmBlocked, true);
    await state.submit();
    assert.equal(state.accessDialogOpen, true);
  });
}

test('image insufficient-credit notice updates the total when the image count changes', async t => {
  const page = await mountPage(t, 'image', {
    quoteResponse: { data: { quote: 60, canSubmit: false, message: 'Insufficient credits' } },
  });
  await page.tick();
  assert.equal(page.app._instance.setupState.quoteError, '预计消耗 60 积分，当前可用积分不足');
  page.workspace.imageDraft.count = 2;
  await page.tick();
  assert.equal(page.app._instance.setupState.quoteError, '预计消耗 120 积分，当前可用积分不足');
  assert.equal(page.app._instance.setupState.platformConfirmBlocked, true);
});

test('video model scope guards model selection while insufficient credits only guard sending', async t => {
  const otherModel = 'doubao-seedance-2-0-standard';
  const videoModels = [
    { model: videoId, resolutions: ['480p', '720p'], durationsByResolution: { '480p': [4, 5], '720p': [6] } },
    { model: otherModel, resolutions: ['720p'], durationsByResolution: { '720p': [6] } },
  ];
  const combos = [['480p', 4, videoId, 0], ['480p', 5, videoId, 300], ['720p', 6, videoId, 300], ['720p', 6, otherModel, 0]];
  const page = await mountPage(t, 'video', {
    quoteResponse: request => ({ data: { quote: 199, canSubmit: combos.some(([resolution, duration, model, bonus]) => (
      request.resolution === resolution && request.duration === duration && request.model === model && bonus >= 199
    )) } }),
    capabilityResponse: { success: true, data: { ...capabilities, video: { ...capabilities.video, models: videoModels } } },
    availabilityResponse: {
      ...availability,
      account: { generalAvailable: 0, bonusAvailable: 300, totalAvailable: 300, buckets: [] },
      combinations: combos.map(([resolution, durationSec, model, bonusAvailable]) => ({
        context: { platform: 'volc_ark', mediaType: 'video', model, resolution, durationSec, sizeLabel: null },
        quote: 199, generalAvailable: 0, bonusAvailable, canSubmit: bonusAvailable >= 199, message: '',
      })),
    },
  });
  await page.tick();
  const state = page.app._instance.setupState;
  assert.equal(state.modelOptions.find(option => option.value === otherModel).disabled, true);
  assert.equal(state.modelOptions.find(option => option.value === otherModel).reason, '当前账户积分不适用于此模型');
  page.workspace.videoDraft.resolution = '720p';
  page.workspace.videoDraft.duration = 6;
  await page.tick();
  const source = await composerSource('video');
  const resolutionAction = source.match(/:data-value="resolution"\s+@click="([^"]+)"/)?.[1];
  assert.ok(resolutionAction);
  new Function('form', 'resolution', 'selectResolution', resolutionAction)(page.workspace.videoDraft, '480p', state.selectResolution);
  await page.tick();
  assert.equal(page.workspace.videoDraft.model, videoId);
  assert.equal(page.workspace.videoDraft.duration, 4, 'all server-supported durations remain selectable');
  assert.equal(state.platformConfirmBlocked, true);
  assert.equal(state.quoteError, '预计消耗 199 积分，当前可用积分不足');
  assert.equal(await primarySubmitDisabled('video', state), true);
  await state.submit();
  assert.equal(page.bridge.calls.some(call => call.method === 'seedance_create_task'), false);

  page.workspace.videoDraft.duration = 5;
  await page.tick();
  assert.equal(state.platformConfirmBlocked, false);

  state.selectModel(otherModel);
  await page.tick();
  assert.equal(page.workspace.videoDraft.model, videoId);
  assert.equal(state.platformConfirmBlocked, false);
  state.selectModel(videoId);
  state.selectResolution('480p');
  page.workspace.videoDraft.duration = 5;
  await page.tick();

  page.workspace.capabilities = { ...page.workspace.capabilities, video: { ...page.workspace.capabilities.video, models: [
    { ...videoModels[0], durationsByResolution: { '480p': [4], '720p': [6] } },
    videoModels[1],
  ] } };
  await page.tick();
  assert.equal(page.workspace.videoDraft.duration, 5, 'catalog refreshes must preserve the selected draft');
});

for (const kind of ['image', 'video']) {
  test(`${kind}: a selected model outside the bonus scope becomes disabled and falls back to an eligible model`, async t => {
    const eligible = kind === 'image' ? imageId : videoId;
    const excluded = 'outside-bonus-scope';
    const modelEntry = model => kind === 'image'
      ? { model, displayName: model, sizes: ['2K'] }
      : { model, displayName: model, resolutions: ['720p'], durationsByResolution: { '720p': [4] } };
    const page = await mountPage(t, kind, {
      initialModel: excluded,
      capabilityResponse: { success: true, data: { ...capabilities, [kind]: { models: [modelEntry(excluded), modelEntry(eligible)] } } },
      availabilityResponse: { ...availability,
        account: { generalAvailable: 0, bonusAvailable: 340, totalAvailable: 340, buckets: [] },
        combinations: [eligible, excluded].map(model => ({
          context: { mediaType: kind, model, resolution: kind === 'video' ? '720p' : null, durationSec: kind === 'video' ? 4 : null, sizeLabel: kind === 'image' ? '2K' : null },
          quote: 360, generalAvailable: 0, bonusAvailable: model === eligible ? 340 : 0,
        })),
      },
      quoteResponse: { data: { quote: 360, canSubmit: false } },
    });
    await page.tick();
    const state = page.app._instance.setupState;
    assert.equal(page.workspace[kind === 'image' ? 'imageDraft' : 'videoDraft'].model, eligible);
    assert.equal(state.modelOptions.find(option => option.value === excluded).disabled, true);
    assert.equal(state.modelOptions.find(option => option.value === eligible).disabled, false);
    assert.equal(state.quoteError, '预计消耗 360 积分，当前可用积分不足');
    state.selectModel(excluded);
    await page.tick();
    assert.equal(page.workspace[kind === 'image' ? 'imageDraft' : 'videoDraft'].model, eligible);
    assert.equal(page.httpCalls.some(call => call.body?.model === excluded), false);
    assert.equal(await primarySubmitDisabled(kind, state), true);
  });

  test(`${kind}: an unaffordable saved default is preserved even when a cheaper specification is payable`, async t => {
    const model = kind === 'image' ? imageId : videoId;
    const page = await mountPage(t, kind, {
      capabilityResponse: { success: true, data: {
        ...capabilities,
        [kind]: { models: [kind === 'image'
          ? { model, sizes: ['1K', '2K'] }
          : { model, resolutions: ['480p', '720p'], durationsByResolution: { '480p': [4], '720p': [4] } }] },
      } },
      quoteResponse: { data: { quote: 360, canSubmit: false } },
      availabilityResponse: { ...availability, combinations: [{
        context: { mediaType: kind, model, resolution: kind === 'video' ? '480p' : null, durationSec: kind === 'video' ? 4 : null, sizeLabel: kind === 'image' ? '1K' : null },
        quote: 60, generalAvailable: 100, bonusAvailable: 0,
      }] },
    });
    await page.tick();
    assert.equal(page.workspace[kind === 'image' ? 'imageDraft' : 'videoDraft'].resolution, kind === 'image' ? '2K' : '720p');
    assert.equal(page.app._instance.setupState.platformConfirmBlocked, true);
  });

  test(`${kind}: zero credits leave supported configuration controls enabled and block sending`, async t => {
    const page = await mountPage(t, kind, {
      quoteResponse: { data: { quote: 360, canSubmit: false } },
      availabilityResponse: { ...availability, account: {
        generalAvailable: 0, bonusAvailable: 0, totalAvailable: 0,
        buckets: [{ bucket: { bucketId: 'empty-bonus', remainAmount: 0, usageMode: 'RESTRICTED' },
          rules: availability.combinations.map(row => row.context), usageSummary: '' }],
      }, combinations: availability.combinations.map(row => ({
        ...row, generalAvailable: 0, bonusAvailable: 0, canSubmit: false,
      })) },
    });
    await page.tick();
    const state = page.app._instance.setupState;
    assert.ok(state.modelOptions.length);
    assert.ok(state.modelOptions.every(option => !option.disabled));
    const html = await renderSfc(`views/${kind === 'image' ? 'SeedreamCreate' : 'SeedanceCreate'}.vue`, {
      props: { embedded: true, showTaskList: false, showBatchList: false },
      piniaState: { auth: { status: 'authenticated' }, 'ai-creation': {
        generationSource: 'forfuner-ai', capabilities,
        [kind === 'image' ? 'imageDraft' : 'videoDraft']: { ...page.workspace[kind === 'image' ? 'imageDraft' : 'videoDraft'] },
      } },
    });
    const buttons = [...html.matchAll(/<button\b[^>]*data-value="([^"]+)"[^>]*>/g)];
    assert.ok(buttons.some(([, value]) => value === (kind === 'image' ? '2K' : '720p')));
    for (const [tag, value] of buttons) {
      if ((kind === 'image' ? ['1K', '1.5K', '2K'] : ['720p']).includes(value)) assert.doesNotMatch(tag, /\bdisabled(?:[=\s>])/);
      if (kind === 'video' && value === '1080p') assert.match(tag, /\bdisabled(?:[=\s>])/);
    }
    assert.match(state.quoteError, /预计消耗 360 积分，当前可用积分不足/);
    assert.equal(await primarySubmitDisabled(kind, state), true);
    await state.submit();
    assert.equal(page.bridge.calls.some(call => /seedream_create_batch|seedance_create_task/.test(call.method)), false);
  });
}

test('an image batch that costs more than its available credits shows the total and blocks sending', async t => {
  const page = await mountPage(t, 'image', {
    quoteResponse: { data: { quote: 60, canSubmit: true } },
    availabilityResponse: { ...availability, combinations: availability.combinations.map(row => ({
      ...row, generalAvailable: 100, bonusAvailable: 0,
    })) },
  });
  await page.tick();
  assert.equal(page.app._instance.setupState.platformConfirmBlocked, false);
  page.workspace.imageDraft.count = 2;
  await page.tick();
  const state = page.app._instance.setupState;
  assert.equal(state.quoteError, '预计消耗 120 积分，当前可用积分不足');
  assert.equal(await primarySubmitDisabled('image', state), true);
});

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

for (const returnLastFrame of [false, true]) {
  test(`video preserves return_last_frame=${returnLastFrame} through entry, source changes and submission`, async t => {
    const page = await mountPage(t, 'video', {
      bridgeScript: { seedance_validate_request: [{ resolve: { success: true, data: { valid: true } } }] },
    });
    await page.tick();
    assert.equal(page.workspace.videoDraft.return_last_frame, false, 'entry preserves the configured value');
    const state = page.app._instance.setupState;
    page.workspace.videoDraft.return_last_frame = returnLastFrame;
    state.selectGenerationSource('api-key');
    state.selectGenerationSource('forfuner-ai');
    await page.tick();
    assert.equal(page.workspace.videoDraft.return_last_frame, returnLastFrame);
    page.workspace.videoDraft.first_frame = '/cache/first.png';
    page.workspace.videoDraft.prompt = 'Walk forward';
    const previousDocument = globalThis.document;
    globalThis.document = new EventTarget();
    globalThis.document.activeElement = null;
    t.after(() => { if (previousDocument === undefined) delete globalThis.document; else globalThis.document = previousDocument; });
    await state.submit();
    const validation = page.bridge.calls.find(call => call.method === 'seedance_validate_request');
    assert.ok(validation);
    assert.equal(validation.args[0].return_last_frame, returnLastFrame);
    assert.equal(state.pendingRequest.return_last_frame, returnLastFrame);
    const html = await renderSfc('views/SeedanceCreate.vue', {
      props: { embedded: true, showTaskList: false },
      piniaState: { 'ai-creation': { generationSource: 'forfuner-ai' } },
    });
    const returnFrameInput = html.match(/<input\b[^>]*aria-label="返回尾帧"[^>]*>/)?.[0];
    assert.ok(returnFrameInput);
    assert.doesNotMatch(returnFrameInput, /\bdisabled(?:[=\s>])/);
  });
}

test('switching to video after restoring an image draft does not show a video draft error', async t => {
  const page = await mountPage(t, 'video', {
    routeQuery: { mode: 'image', regenerate: 'image-batch' },
  });
  await page.tick();
  assert.equal(page.app._instance.setupState.draftLoadFailed, false);
  assert.equal(page.bridge.calls.some(call => call.method === 'seedance_get_regeneration_draft'), false);
});

test('switching to image after restoring a video draft does not load it as an image batch', async t => {
  const page = await mountPage(t, 'image', {
    routeQuery: { mode: 'video', regenerate: 'video-task' },
  });
  await page.tick();
  assert.equal(page.bridge.calls.some(call => call.method === 'seedream_get_regeneration_draft'), false);
});

for (const mode of [undefined, 'video']) {
  for (const action of ['regenerate', 'continue']) {
    const method = action === 'regenerate' ? 'seedance_get_regeneration_draft' : 'seedance_get_continuation_draft';
    test(`video ${action} restores its own draft with ${mode ?? 'legacy'} entry mode`, async t => {
      const page = await mountPage(t, 'video', {
        routeQuery: { mode, [action]: 'video-task' },
        bridgeScript: { [method]: [{ resolve: { success: true, data: {
          request: { first_frame: '/cache/first.png', prompt: 'Walk forward', return_last_frame: false },
          preview_urls: { first_frame: '/media/first.png' },
        } } }] },
      });
      await page.tick();
      assert.equal(page.app._instance.setupState.draftLoadFailed, false);
      assert.equal(page.workspace.videoDraft.first_frame, '/cache/first.png');
      assert.equal(page.workspace.videoDraft.prompt, 'Walk forward');
      assert.equal(page.workspace.videoDraft.return_last_frame, false);
      assert.equal(page.bridge.calls.filter(call => call.method === method).length, 1);
    });
  }
}

test('video still reports an actual continuation draft load failure', async t => {
  const page = await mountPage(t, 'video', {
    routeQuery: { mode: 'video', continue: 'missing-video' },
    bridgeScript: { seedance_get_continuation_draft: [{ resolve: {
      success: false, error: { code: 'NOT_FOUND', message: 'Missing video task' },
    } }] },
  });
  await page.tick();
  assert.equal(page.app._instance.setupState.draftLoadFailed, true);
  assert.equal(page.app._instance.setupState.handoffLoadFailed, false);
});
