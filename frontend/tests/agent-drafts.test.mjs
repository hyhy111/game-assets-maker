import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { createPinia, setActivePinia } from 'pinia';
import { closeFrontendHarness, createScriptedPyWebViewBridge, loadFrontendModule } from './scripted-pywebview-bridge.mjs';
after(closeFrontendHarness);

const platformCapabilities = {
  video: { models: [], ratios: ['adaptive', '16:9', '1:1', '4:3'] },
  image: { models: [
    { model: 'server-default', sizes: ['2K'] },
    { model: 'new-platform-model', sizes: ['1K', '2K'] },
  ] },
};

test('draft patch preserves fields, previews local images and survives first initialization', async () => {
  const bridge = createScriptedPyWebViewBridge({
    agent_validate_draft: [{ resolve: { success: true } }],
    get_frame_thumbnail: [{ resolve: 'preview' }],
  });
  setActivePinia(createPinia());
  const { useAICreationStore, defaultVideoDraft } = await loadFrontendModule('/src/stores/aiCreation.ts');
  const store = useAICreationStore();
  store.videoDraft.generate_audio = true;
  await store.patchAgentDraft('video', { prompt: 'walk', first_frame: '/first.png' });
  store.initializeVideoDraft(defaultVideoDraft());
  assert.equal(store.videoDraft.prompt, 'walk');
  assert.equal(store.videoDraft.generate_audio, true);
  assert.equal(store.videoPreviewUrls.first_frame, 'data:image/png;base64,preview');
  assert.equal(bridge.calls.length, 2);
});

test('invalid image leaves every draft field and preview unchanged', async () => {
  createScriptedPyWebViewBridge({ agent_validate_draft: [{ resolve: { success: true } }], get_frame_thumbnail: [{ resolve: null }] });
  setActivePinia(createPinia());
  const { useAICreationStore } = await loadFrontendModule('/src/stores/aiCreation.ts');
  const store = useAICreationStore();
  store.imageDraft.prompt = 'original';
  const original = JSON.stringify(store.imageDraft);
  await assert.rejects(store.patchAgentDraft('image', { prompt: 'changed', reference_image: '/bad.png' }));
  assert.equal(JSON.stringify(store.imageDraft), original);
  assert.equal(store.imagePreviewUrls.reference, '');
});

test('prompt patch applies the backend-normalized equivalent image model', async () => {
  const bridge = createScriptedPyWebViewBridge({
    agent_validate_draft: [{ resolve: { success: true, draft: { model: 'pro' } } }],
  });
  setActivePinia(createPinia());
  const { useAICreationStore } = await loadFrontendModule('/src/stores/aiCreation.ts');
  const store = useAICreationStore();
  store.imageDraft.model = 'doubao-seedream-5-0-pro-260628';
  store.imageDraft.ratio = '3:4';
  store.imageDraft.count = 3;
  const result = await store.patchAgentDraft('image', { prompt: 'updated' });
  assert.equal(store.imageDraft.model, 'pro');
  assert.equal(result.draft.model, 'pro');
  assert.equal(store.imageDraft.prompt, 'updated');
  assert.equal(store.imageDraft.ratio, '3:4');
  assert.equal(store.imageDraft.count, 3);
  assert.equal(bridge.calls[0].args[1].source, 'api-key');
  assert.equal('source' in store.imageDraft, false);
});

test('omitting the image model preserves the user-selected Flash model', async () => {
  const bridge = createScriptedPyWebViewBridge({
    agent_validate_draft: [{ resolve: { success: true } }],
  });
  setActivePinia(createPinia());
  const { useAICreationStore } = await loadFrontendModule('/src/stores/aiCreation.ts');
  const store = useAICreationStore();
  store.imageDraft.model = 'flash';
  const result = await store.patchAgentDraft('image', { prompt: 'updated' });
  assert.equal(store.imageDraft.model, 'flash');
  assert.equal(result.draft.model, 'flash');
  assert.equal(store.imageDraft.prompt, 'updated');
  assert.equal(bridge.calls[0].args[1].model, 'flash');
});

test('platform image patch validates with the current source and preserves the model ID', async () => {
  const bridge = createScriptedPyWebViewBridge({
    get_platform_capabilities: [{ resolve: { success: true, data: platformCapabilities } }],
    agent_validate_draft: [{ resolve: (_kind, values) => (
      values.source === 'forfuner-ai'
        ? { success: true, draft: values }
        : { success: false, error: 'Unsupported Seedream model' }
    ) }],
  });
  setActivePinia(createPinia());
  const { useAICreationStore } = await loadFrontendModule('/src/stores/aiCreation.ts');
  const store = useAICreationStore();
  store.setGenerationSource('forfuner-ai');
  store.imageDraft.model = 'new-platform-model';
  await store.patchAgentDraft('image', { prompt: 'updated' });
  assert.equal(store.imageDraft.model, 'new-platform-model');
  assert.equal(store.imageDraft.prompt, 'updated');
  assert.equal(bridge.calls.find(call => call.method === 'agent_validate_draft').args[1].source, 'forfuner-ai');
  assert.equal('source' in store.imageDraft, false);
});

test('platform image patch waits for capabilities and fixes only unavailable implicit parameters', async () => {
  const bridge = createScriptedPyWebViewBridge({
    get_platform_capabilities: [{ resolve: { success: true, data: platformCapabilities } }],
    agent_validate_draft: [{ resolve: (_kind, values) => ({ success: true, draft: values }) }],
  });
  setActivePinia(createPinia());
  const { useAICreationStore } = await loadFrontendModule('/src/stores/aiCreation.ts');
  const store = useAICreationStore();
  store.setGenerationSource('forfuner-ai');
  store.imageDraft.model = 'removed-platform-model';
  store.imageDraft.resolution = '1.5K';
  store.imageDraft.count = 3;
  store.imageDraft.ratio = '3:4';
  const result = await store.patchAgentDraft('image', { prompt: 'updated' });
  assert.equal(result.draft.model, 'server-default');
  assert.equal(result.draft.resolution, '2K');
  assert.equal(result.draft.prompt, 'updated');
  assert.equal(result.draft.count, 3);
  assert.equal(result.draft.ratio, '3:4');
  assert.deepEqual(bridge.calls.map(call => call.method), ['get_platform_capabilities', 'agent_validate_draft']);
  assert.equal(bridge.calls[1].args[1].model, 'server-default');
  assert.equal(bridge.calls[1].args[1].resolution, '2K');
});

test('cached capabilities preserve the selected platform model without another fetch', async () => {
  const bridge = createScriptedPyWebViewBridge({
    agent_validate_draft: [{ resolve: { success: true } }],
  });
  setActivePinia(createPinia());
  const { useAICreationStore } = await loadFrontendModule('/src/stores/aiCreation.ts');
  const store = useAICreationStore();
  store.setGenerationSource('forfuner-ai');
  store.capabilities = platformCapabilities;
  store.imageDraft.model = 'new-platform-model';
  store.imageDraft.resolution = '1K';
  await store.patchAgentDraft('image', { prompt: 'updated' });
  assert.equal(store.imageDraft.model, 'new-platform-model');
  assert.equal(store.imageDraft.resolution, '1K');
  assert.deepEqual(bridge.calls.map(call => call.method), ['agent_validate_draft']);
});

test('an unavailable explicit platform model refreshes capabilities before rejecting the patch', async () => {
  const bridge = createScriptedPyWebViewBridge({
    get_platform_capabilities: [{ resolve: { success: true, data: platformCapabilities } }],
  });
  setActivePinia(createPinia());
  const { useAICreationStore } = await loadFrontendModule('/src/stores/aiCreation.ts');
  const store = useAICreationStore();
  store.setGenerationSource('forfuner-ai');
  store.capabilities = platformCapabilities;
  store.imageDraft.prompt = 'original';
  store.imageDraft.model = 'new-platform-model';
  const original = JSON.stringify(store.imageDraft);
  await assert.rejects(store.patchAgentDraft('image', { prompt: 'changed', model: 'unavailable' }), /UNSUPPORTED_MODEL/);
  assert.equal(JSON.stringify(store.imageDraft), original);
  assert.deepEqual(bridge.calls.map(call => call.method), ['get_platform_capabilities']);
});

test('new platform models can be selected after a stale capability list is refreshed', async () => {
  const bridge = createScriptedPyWebViewBridge({
    get_platform_capabilities: [{ resolve: { success: true, data: platformCapabilities } }],
    agent_validate_draft: [{ resolve: { success: true } }],
  });
  setActivePinia(createPinia());
  const { useAICreationStore } = await loadFrontendModule('/src/stores/aiCreation.ts');
  const store = useAICreationStore();
  store.setGenerationSource('forfuner-ai');
  store.capabilities = { ...platformCapabilities, image: { models: [platformCapabilities.image.models[0]] } };
  await store.patchAgentDraft('image', { model: 'new-platform-model', resolution: '1K' });
  assert.equal(store.imageDraft.model, 'new-platform-model');
  assert.equal(store.imageDraft.resolution, '1K');
  assert.deepEqual(bridge.calls.map(call => call.method), ['get_platform_capabilities', 'agent_validate_draft']);
});

test('unsupported explicit platform resolution and an empty model list leave drafts unchanged', async () => {
  for (const capabilities of [platformCapabilities, { ...platformCapabilities, image: { models: [] } }]) {
    createScriptedPyWebViewBridge({
      get_platform_capabilities: [{ resolve: { success: true, data: capabilities } }],
    });
    setActivePinia(createPinia());
    const { useAICreationStore } = await loadFrontendModule('/src/stores/aiCreation.ts');
    const store = useAICreationStore();
    store.setGenerationSource('forfuner-ai');
    store.imageDraft.model = 'new-platform-model';
    const original = JSON.stringify(store.imageDraft);
    await assert.rejects(store.patchAgentDraft('image', { resolution: '1.5K' }), /UNSUPPORTED_RESOLUTION|NO_AVAILABLE_MODELS/);
    assert.equal(JSON.stringify(store.imageDraft), original);
  }
});

test('capability fetch failure preserves the image draft and previews', async () => {
  createScriptedPyWebViewBridge({
    get_platform_capabilities: [{ resolve: { success: false, error: { code: 'OFFLINE', message: 'service offline' } } }],
  });
  setActivePinia(createPinia());
  const { useAICreationStore } = await loadFrontendModule('/src/stores/aiCreation.ts');
  const store = useAICreationStore();
  store.setGenerationSource('forfuner-ai');
  store.imageDraft.prompt = 'original';
  store.imagePreviewUrls.reference = 'original-preview';
  const original = JSON.stringify(store.imageDraft);
  await assert.rejects(store.patchAgentDraft('image', { prompt: 'updated' }), /service offline/);
  assert.equal(JSON.stringify(store.imageDraft), original);
  assert.equal(store.imagePreviewUrls.reference, 'original-preview');
});

test('a platform patch waits for an ongoing refresh even when an older list is cached', async () => {
  let resolveCapabilities;
  const response = new Promise(resolve => { resolveCapabilities = resolve; });
  const bridge = createScriptedPyWebViewBridge({
    get_platform_capabilities: [{ resolve: () => response }],
    agent_validate_draft: [{ resolve: { success: true } }],
  });
  setActivePinia(createPinia());
  const { useAICreationStore } = await loadFrontendModule('/src/stores/aiCreation.ts');
  const store = useAICreationStore();
  store.setGenerationSource('forfuner-ai');
  store.capabilities = platformCapabilities;
  store.imageDraft.model = 'new-platform-model';
  store.imageDraft.prompt = 'original';
  const refresh = store.ensureCapabilities(true);
  const patch = store.patchAgentDraft('image', { prompt: 'updated' });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(store.imageDraft.prompt, 'original');
  assert.deepEqual(bridge.calls.map(call => call.method), ['get_platform_capabilities']);
  resolveCapabilities({ success: true, data: {
    ...platformCapabilities, image: { models: [platformCapabilities.image.models[0]] },
  } });
  await refresh;
  await patch;
  assert.equal(store.imageDraft.model, 'server-default');
  assert.equal(store.imageDraft.prompt, 'updated');
});

test('changing the generation source during capability loading cancels the patch', async () => {
  let resolveCapabilities;
  const response = new Promise(resolve => { resolveCapabilities = resolve; });
  createScriptedPyWebViewBridge({ get_platform_capabilities: [{ resolve: () => response }] });
  setActivePinia(createPinia());
  const { useAICreationStore } = await loadFrontendModule('/src/stores/aiCreation.ts');
  const store = useAICreationStore();
  store.setGenerationSource('forfuner-ai');
  const patch = store.patchAgentDraft('image', { prompt: 'updated' });
  store.setGenerationSource('api-key');
  const original = JSON.stringify(store.imageDraft);
  resolveCapabilities({ success: true, data: platformCapabilities });
  await assert.rejects(patch, /DRAFT_CHANGED/);
  assert.equal(JSON.stringify(store.imageDraft), original);
});
