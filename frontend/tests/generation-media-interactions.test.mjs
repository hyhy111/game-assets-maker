import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { createPinia, setActivePinia } from 'pinia';
import { closeFrontendHarness, createScriptedPyWebViewBridge, loadFrontendModule } from './scripted-pywebview-bridge.mjs';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';

after(closeFrontendHarness);
after(closeSfcRenderer);

async function workspace() {
  setActivePinia(createPinia());
  const { useAICreationStore } = await loadFrontendModule('/src/stores/aiCreation.ts');
  return useAICreationStore();
}

test('reference handoff uses the selected edited path and fresh preview without changing parameters or generating', async () => {
  const bridge = createScriptedPyWebViewBridge({
    seedream_get_handoff_image: [{ resolve: { success: true, data: { local_path: '/cache/edited.png' } } }],
    get_frame_thumbnail: [{ resolve: 'EDITED' }],
  });
  const state = await workspace();
  Object.assign(state.imageDraft, { reference_image: '/old.png', prompt: 'existing draft', model: 'flash', ratio: '1:1', count: 3 });
  const before = { ...state.imageDraft };
  assert.equal(await state.handoffCandidateToImage('batch-2', 2), true);
  assert.deepEqual({ ...state.imageDraft }, { ...before, reference_image: '/cache/edited.png' });
  assert.equal(state.imagePreviewUrls.reference, 'data:image/png;base64,EDITED');
  assert.deepEqual(bridge.calls.map(c => c.method), ['seedream_get_handoff_image', 'get_frame_thumbnail']);
  assert.deepEqual(bridge.calls[0].args, ['batch-2', 2]);
});

test('a missing candidate or failing preview preserves the previous reference and preview', async () => {
  createScriptedPyWebViewBridge({
    seedream_get_handoff_image: [
      { resolve: { success: false, error: { code: 'NOT_FOUND', message: 'missing' } } },
      { resolve: { success: true, data: { local_path: '/missing.png' } } },
    ],
    get_frame_thumbnail: [{ reject: new Error('unreadable') }],
  });
  const state = await workspace();
  state.imageDraft.reference_image = '/old.png';
  state.imagePreviewUrls.reference = 'old-preview';
  for (let i = 0; i < 2; i++) {
    assert.equal(await state.handoffCandidateToImage('missing', i), false);
    assert.equal(state.imageDraft.reference_image, '/old.png');
    assert.equal(state.imagePreviewUrls.reference, 'old-preview');
  }
});

test('frame replacement only updates its explicit target and keeps prompt and other frame', async () => {
  createScriptedPyWebViewBridge({ get_frame_thumbnail: [{ resolve: 'NEW' }] });
  const state = await workspace();
  Object.assign(state.videoDraft, { first_frame: '/first.png', last_frame: '/last.png', prompt: 'keep prompt', duration: 8 });
  const before = { ...state.videoDraft };
  await state.setImageInput('/new.png', 'last_frame');
  assert.deepEqual({ ...state.videoDraft }, { ...before, last_frame: '/new.png' });
  assert.equal(state.videoPreviewUrls.last_frame, 'data:image/png;base64,NEW');
});

test('file drop imports file contents and uses backend path, preserving old state on failure', async () => {
  const oldReader = globalThis.FileReader;
  globalThis.FileReader = class {
    readAsDataURL() { this.result = 'data:image/png;base64,FIXTURE'; this.onload(); }
  };
  try {
    const bridge = createScriptedPyWebViewBridge({
      seedream_import_reference_image: [
        { resolve: { success: true, path: '/cache/imported.png' } },
        { resolve: { success: false, error: { code: 'INVALID_IMAGE', message: 'invalid' } } },
      ],
      get_frame_thumbnail: [{ resolve: 'IMPORTED' }],
    });
    const state = await workspace();
    state.imageDraft.prompt = 'keep';
    const file = new File(['fixture'], 'hero.png', { type: 'image/png' });
    assert.equal(await state.importDroppedImage(file, 'reference'), true);
    assert.equal(state.imageDraft.reference_image, '/cache/imported.png');
    assert.equal(state.imagePreviewUrls.reference, 'data:image/png;base64,IMPORTED');
    assert.deepEqual(bridge.calls[0].args, ['data:image/png;base64,FIXTURE', 'hero.png']);
    assert.equal(await state.importDroppedImage(file, 'reference'), false);
    assert.equal(state.imageDraft.reference_image, '/cache/imported.png');
    assert.equal(state.imageDraft.prompt, 'keep');
  } finally {
    if (oldReader === undefined) delete globalThis.FileReader;
    else globalThis.FileReader = oldReader;
  }
});

test('drop protocol rejects multiple files, web links and non-images', async () => {
  const { readImageDrop, SEEDREAM_IMAGE_DRAG_TYPE } = await loadFrontendModule('/src/seedream-image-drag.ts');
  const file = new File(['fixture'], 'hero.png', { type: 'image/png' });
  const dt = (files, text = '') => ({ files, getData: type => type === SEEDREAM_IMAGE_DRAG_TYPE ? text : '' });
  assert.deepEqual(readImageDrop(dt([file, file])), { kind: 'error', key: 'aiCreation.dropSingleImage' });
  assert.deepEqual(readImageDrop(dt([])), { kind: 'error', key: 'aiCreation.dropInvalidImage' });
  assert.equal(readImageDrop(dt([new File(['text'], 'a.txt', { type: 'text/plain' })])).kind, 'error');
  assert.deepEqual(readImageDrop(dt([file])), { kind: 'file', file });
  assert.equal(readImageDrop(dt([], JSON.stringify({ localId: 'batch', attemptIndex: -1 }))).kind, 'error');
  assert.deepEqual(readImageDrop(dt([], JSON.stringify({ localId: 'batch', attemptIndex: 2 }))), { kind: 'candidate', candidate: { localId: 'batch', attemptIndex: 2 } });
});

test('file drops accept supported TIFF and HEIF formats plus empty MIME candidates, leaving content validation to the backend', async () => {
  const { readImageDrop } = await loadFrontendModule('/src/seedream-image-drag.ts');
  const drop = file => readImageDrop({ files: [file], getData: () => '' });
  for (const [name, type] of [
    ['hero.tif', 'image/tiff'], ['hero.tiff', 'image/tiff'],
    ['hero.heic', 'image/heic'], ['hero.heif', 'image/heif'],
    ['hero.PNG', ''], ['hero.jpeg', ''], ['hero.jpg', ''],
    ['hero.webp', ''], ['hero.bmp', ''], ['hero.gif', ''],
    ['hero.tif', ''], ['hero.tiff', ''], ['hero.heic', ''], ['hero.heif', ''],
  ]) {
    const file = new File(['unvalidated bytes'], name, { type });
    assert.deepEqual(drop(file), { kind: 'file', file });
  }
  for (const [name, type] of [
    ['hero.png', 'text/plain'], ['hero.heic', 'application/octet-stream'],
    ['hero.svg', 'image/svg+xml'], ['hero.txt', ''], ['hero', ''],
  ]) {
    assert.deepEqual(drop(new File(['unvalidated bytes'], name, { type })), {
      kind: 'error', key: 'aiCreation.dropInvalidImage',
    });
  }
});

test('selected reference preview survives task creation rather than switching to the task media URL', async () => {
  createScriptedPyWebViewBridge({
    seedream_create_batch: [{ resolve: { success: true, batch: { local_id: 'new', created_at: '', attempts: [], reference_image_url: 'http://localhost:8080/seedream-media/new/reference', request: {} } } }],
  });
  const state = await workspace();
  state.imageDraft.reference_image = '/cache/reference.png';
  state.imagePreviewUrls.reference = 'data:image/png;base64,LOCAL_FIXTURE';
  const { useSeedreamStore } = await loadFrontendModule('/src/stores/seedream.ts');
  const { createRequest } = await loadFrontendModule('/src/seedream-ui.ts');
  await useSeedreamStore().createBatch(createRequest(state.imageDraft));
  state.setCurrentGeneration({ kind: 'image', localId: 'new' });
  assert.equal(state.imageDraft.reference_image, '/cache/reference.png');
  assert.equal(state.imagePreviewUrls.reference, 'data:image/png;base64,LOCAL_FIXTURE');
});

test('image toolbar has a single accessible icon save followed by directory and delete', async () => {
  const batch = {
    local_id: 'batch-1', status: 'completed', created_at: '', updated_at: '',
    request: { prompt: 'fixture', model: 'pro', resolution: '1K', ratio: '16:9', count: 1 },
    attempts: [{ local_id: 'a', index: 0, status: 'succeeded', image_url: '/seedream-media/batch-1/image/0', local_path: 'images/0.png', absolute_path: '/cache/image.png', elapsed_seconds: 0 }],
  };
  const html = await renderSfc('views/SeedreamBatchDetail.vue', { route: '/image-generation/batches/batch-1', piniaState: { seedream: { currentBatch: batch, batches: [] } } });
  const ids = ['seedream-create-video', 'seedream-regenerate', 'seedream-use-reference', 'seedream-download', 'seedream-open-directory', 'seedream-delete'];
  const positions = ids.map(id => html.indexOf(`data-test="${id}"`));
  assert.ok(positions.every((position, i) => position >= 0 && (!i || position > positions[i - 1])));
  assert.equal((html.match(/data-test="seedream-download"/g) || []).length, 1);
  assert.match(html, /aria-label="另存为图片"/);
  assert.match(html, /aria-label="打开目录"/);
  assert.match(html, /draggable="true"/);
});
