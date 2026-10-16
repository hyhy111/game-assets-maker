import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import ts from 'typescript';
import { createPinia, setActivePinia } from 'pinia';
import { closeFrontendHarness, createScriptedPyWebViewBridge, loadFrontendModule } from './scripted-pywebview-bridge.mjs';

after(closeFrontendHarness);
const IMAGE_DEFAULT = 'doubao-seedream-preferred';
const VIDEO_DEFAULT = 'doubao-seedance-preferred';

async function setup() {
  const bridge = createScriptedPyWebViewBridge();
  setActivePinia(createPinia());
  const { useAICreationStore, defaultVideoDraft } = await loadFrontendModule('/src/stores/aiCreation.ts');
  const { defaultForm, correctPlatformImageParameters } = await loadFrontendModule('/src/seedream-ui.ts');
  const workspace = useAICreationStore();
  return { workspace, bridge, image: { ...defaultForm(), model: 'flash' }, video: { ...defaultVideoDraft(), model: 'fast' }, correctPlatformImageParameters };
}

test('switching generation sources selects separate image/video defaults without changing input content', async () => {
  const { workspace, bridge, image, video } = await setup();
  workspace.initializeImageDraft(image, IMAGE_DEFAULT);
  workspace.initializeVideoDraft(video, VIDEO_DEFAULT);
  workspace.imageDraft.prompt = 'keep image';
  workspace.imageDraft.reference_image = '/reference.png';
  workspace.videoDraft.prompt = 'keep video';
  workspace.videoDraft.first_frame = '/first.png';
  workspace.setGenerationSource('forfuner-ai');
  assert.equal(workspace.imageDraft.model, IMAGE_DEFAULT);
  assert.equal(workspace.videoDraft.model, VIDEO_DEFAULT);
  workspace.imageDraft.model = 'another-platform-image';
  workspace.videoDraft.model = 'another-platform-video';
  workspace.setGenerationSource('forfuner-ai');
  assert.equal(workspace.imageDraft.model, 'another-platform-image');
  workspace.setGenerationSource('api-key');
  assert.equal(workspace.imageDraft.model, 'flash');
  assert.equal(workspace.videoDraft.model, 'fast');
  assert.equal(workspace.imageDraft.prompt, 'keep image');
  assert.equal(workspace.imageDraft.reference_image, '/reference.png');
  assert.equal(workspace.videoDraft.prompt, 'keep video');
  assert.equal(workspace.videoDraft.first_frame, '/first.png');
  assert.deepEqual(bridge.calls, []);
});

test('asynchronously loaded settings initialize the platform preference instead of the first model', async () => {
  const { workspace, image, video } = await setup();
  workspace.setGenerationSource('forfuner-ai');
  workspace.initializeImageDraft(image, IMAGE_DEFAULT);
  workspace.initializeVideoDraft(video, VIDEO_DEFAULT);
  assert.equal(workspace.imageDraft.model, IMAGE_DEFAULT);
  assert.equal(workspace.videoDraft.model, VIDEO_DEFAULT);
  workspace.imageDraft.model = 'manual-image';
  workspace.videoDraft.model = 'manual-video';
  workspace.initializeImageDraft(image, 'new-default');
  workspace.initializeVideoDraft(video, 'new-video-default');
  assert.equal(workspace.imageDraft.model, 'manual-image');
  assert.equal(workspace.videoDraft.model, 'manual-video');
});

test('clearing a draft uses defaults from the active source', async () => {
  const { workspace, image, video } = await setup();
  workspace.initializeImageDraft(image, IMAGE_DEFAULT);
  workspace.initializeVideoDraft(video, VIDEO_DEFAULT);
  workspace.setGenerationSource('forfuner-ai');
  workspace.imageDraft.model = 'manual';
  workspace.videoDraft.model = 'manual';
  workspace.resetImageDraft();
  workspace.resetVideoDraft();
  assert.equal(workspace.imageDraft.model, IMAGE_DEFAULT);
  assert.equal(workspace.videoDraft.model, VIDEO_DEFAULT);
  workspace.setGenerationSource('api-key');
  workspace.resetImageDraft();
  workspace.resetVideoDraft();
  assert.equal(workspace.imageDraft.model, 'flash');
  assert.equal(workspace.videoDraft.model, 'fast');
});

test('image fallback respects saved preferences, manual choices and missing model availability', async () => {
  const { correctPlatformImageParameters } = await setup();
  const models = [{ model: 'first', sizes: ['1K'] }, { model: IMAGE_DEFAULT, sizes: ['2K'] }];
  assert.deepEqual(correctPlatformImageParameters('pro', '1K', models, IMAGE_DEFAULT), { model: IMAGE_DEFAULT, resolution: '2K' });
  assert.deepEqual(correctPlatformImageParameters('first', '1K', models, IMAGE_DEFAULT), { model: 'first', resolution: '1K' });
  assert.deepEqual(correctPlatformImageParameters('missing', '2K', models, 'delisted'), { model: 'first', resolution: '1K' });
  assert.deepEqual(correctPlatformImageParameters('pro', '2K', [], IMAGE_DEFAULT), { model: 'pro', resolution: '2K' });
});

const videoSource = await readFile(new URL('../src/views/SeedanceCreate.vue', import.meta.url), 'utf8');
const clampSource = videoSource.match(/function clampToPlatformModel\(\) \{[\s\S]*?\n\}/)?.[0];
assert.ok(clampSource);

function clampVideo(model, ready = true) {
  const context = {
    form: { model, resolution: '1080p', duration: 6 },
    modelDefaultsReady: { value: ready },
    platformVideoModels: { value: [
      { model: 'first', resolutions: ['480p'], durationsByResolution: { '480p': [4] } },
      { model: VIDEO_DEFAULT, resolutions: ['720p'], durationsByResolution: { '720p': [5] } },
    ] },
    store: { settings: { platform_default_model: VIDEO_DEFAULT } },
  };
  vm.runInNewContext(ts.transpileModule(`${clampSource}\nclampToPlatformModel();`, {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  }).outputText, context);
  return context.form;
}

test('video fallback waits for settings and then uses preferred model with compatible parameters', () => {
  assert.deepEqual(clampVideo('mini', false), { model: 'mini', resolution: '1080p', duration: 6 });
  assert.deepEqual(clampVideo('mini'), { model: VIDEO_DEFAULT, resolution: '720p', duration: 5 });
  assert.deepEqual(clampVideo('first'), { model: 'first', resolution: '480p', duration: 4 });
});


test('switching image source corrects resolution even after the store selects a valid API-key model', async () => {
  const source = await readFile(new URL('../src/views/SeedreamCreate.vue', import.meta.url), 'utf8');
  const selectSource = source.match(/function selectGenerationSource\(source: string\) \{[\s\S]*?\n\}/)?.[0];
  assert.ok(selectSource);
  const { correctResolution, localModelResolutions } = await loadFrontendModule('/src/seedream-ui.ts');
  const form = { model: IMAGE_DEFAULT, resolution: '4K' };
  const context = {
    form,
    workspace: { setGenerationSource: () => { form.model = 'flash'; } },
    store: { settings: { default_model: 'flash' } },
    localModelResolutions,
    fixResolution: () => { form.resolution = correctResolution(form.model, form.resolution); },
    scheduleQuoteRefresh() {},
  };
  vm.runInNewContext(ts.transpileModule(`${selectSource}\nselectGenerationSource('api-key');`, {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  }).outputText, context);
  assert.deepEqual(form, { model: 'flash', resolution: '1K' });
});


test('switching API-key Mini to ForFuner AI follows the configured model when no platform override is saved', async () => {
  const { workspace, video } = await setup();
  workspace.initializeVideoDraft({ ...video, model: 'mini' }, '');
  assert.equal(workspace.videoDraft.model, 'mini');
  workspace.setGenerationSource('forfuner-ai');
  const mini = 'doubao-seedance-2-0-mini-260615';
  const context = {
    form: workspace.videoDraft,
    modelDefaultsReady: { value: true },
    platformVideoModels: { value: [
      { model: 'doubao-seedance-2-0-260128', resolutions: ['720p'], durationsByResolution: { '720p': [4] } },
      { model: mini, resolutions: ['720p'], durationsByResolution: { '720p': [4] } },
    ] },
    store: { settings: { default_model: 'mini', default_model_id: mini, platform_default_model: '' } },
  };
  vm.runInNewContext(ts.transpileModule(`${clampSource}\nclampToPlatformModel();`, {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  }).outputText, context);
  assert.equal(workspace.videoDraft.model, mini);
});
