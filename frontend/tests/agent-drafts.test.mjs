import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { createPinia, setActivePinia } from 'pinia';
import { closeFrontendHarness, createScriptedPyWebViewBridge, loadFrontendModule } from './scripted-pywebview-bridge.mjs';
after(closeFrontendHarness);

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
