import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { after, test } from 'node:test';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';
import { MODEL_LABELS, MODEL_RESOLUTIONS } from '../src/seedream-ui.ts';

after(closeSfcRenderer);

test('Seedream header keeps shared actions without the three page navigation links', async () => {
  const html = await renderSfc('components/seedream/SeedreamTopNav.vue', {
    route: '/image-generation/create',
  });
  assert.match(html, /title="返回项目列表"/);
  assert.match(html, /lucide-home-icon/);
  assert.doesNotMatch(html, /<nav/);
  assert.doesNotMatch(html, /任务列表/);
  assert.doesNotMatch(html, /任务详情/);
});

test('Seedream create page renders the supported Seedream 5.0 model options', async () => {
  const source = await readFile(new URL('../src/views/SeedreamCreate.vue', import.meta.url), 'utf8');
  const html = await renderSfc('views/SeedreamCreate.vue', {
    route: '/image-generation/create',
  });
  assert.match(source, /value: 'pro', label: t\('seedream\.models\.pro'\)/);
  assert.match(source, /value: 'flash', label: t\('seedream\.models\.flash'\)/);
  assert.doesNotMatch(source, /value: 'lite'/);
  const settings = await readFile(new URL('../src/views/SeedanceSettings.vue', import.meta.url), 'utf8');
  assert.doesNotMatch(settings, /value: 'lite'/);
  assert.doesNotMatch(source, /v45|v40|Seedream 4\.(?:5|0)/);
  assert.match(html, /Seedream 5\.0 Pro/);
});

test('Seedream create page renders resolution options 1K 1.5K 2K without 4K', async () => {
  const html = await renderSfc('views/SeedreamCreate.vue', {
    route: '/image-generation/create',
  });
  assert.match(html, /data-value="1K"/);
  assert.match(html, /data-value="1\.5K"/);
  assert.match(html, /data-value="2K"/);
  assert.doesNotMatch(html, /data-value="4K"/);
});

test('Seedream create page defaults to Pro 2K 16:9', async () => {
  const html = await renderSfc('views/SeedreamCreate.vue', {
    route: '/image-generation/create',
  });
  assert.match(html, /data-test="seedream-model"/);
  assert.match(html, /Seedream 5\.0 Pro/);
  assert.match(html, /data-test="seedream-parameter-summary"/);
  assert.match(html, /16:9/);
  assert.match(html, /2K/);
});

test('AI creation model dropdown uses the prompt composer palette', async () => {
  const [modelSelect, create] = await Promise.all([
    readFile(new URL('../src/components/ai-creation/CreationModelSelect.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/views/SeedreamCreate.vue', import.meta.url), 'utf8'),
  ]);
  assert.match(modelSelect, /ListboxOptions/);
  assert.match(modelSelect, /border-\[#3b3b3b\] bg-\[#1f1f1f\]/);
  assert.match(modelSelect, /bg-primary\/20 text-primary-200/);
  assert.equal((create.match(/bg-primary\/20 text-primary-200 shadow-sm/g) ?? []).length, 3);
});

test('Seedream create page renders count selector with options 1-4', async () => {
  const html = await renderSfc('views/SeedreamCreate.vue', {
    route: '/image-generation/create',
  });
  assert.match(html, /data-test="seedream-count"/);
  assert.match(html, /data-value="1"/);
  assert.match(html, /data-value="2"/);
  assert.match(html, /data-value="3"/);
  assert.match(html, /data-value="4"/);
});

test('Seedream create page defaults count to 1', async () => {
  const html = await renderSfc('views/SeedreamCreate.vue', {
    route: '/image-generation/create',
  });
  assert.match(html, /aria-pressed="true"[^>]*data-value="1"/);
});

test('Seedream create page shows prompt suggestion on hover over the word counter', async () => {
  const html = await renderSfc('views/SeedreamCreate.vue', {
    route: '/image-generation/create',
  });
  assert.match(html, /data-test="seedream-prompt-count"/);
  // The suggestion lives in a hover-only tooltip anchored to the counter.
  assert.match(html, /data-test="seedream-prompt-suggestion"/);
  assert.match(html, /class="[^"]*hidden[^"]*group-hover:block/);
  assert.match(html, /seedream-prompt-suggestion"[^>]*>\s*官方建议不超过 300 个汉字/);
});

test('Seedream create page renders all five allowed aspect ratios', async () => {
  const html = await renderSfc('views/SeedreamCreate.vue', {
    route: '/image-generation/create',
  });
  assert.match(html, /data-value="1:1"/);
  assert.match(html, /data-value="16:9"/);
  assert.match(html, /data-value="9:16"/);
  assert.match(html, /data-value="4:3"/);
  assert.match(html, /data-value="3:4"/);
});

test('Seedream create page renders submit button', async () => {
  const html = await renderSfc('views/SeedreamCreate.vue', {
    route: '/image-generation/create',
  });
  assert.match(html, /data-test="seedream-submit"/);
});

test('Seedream create page keeps the composer at the same height as the video composer', async () => {
  const html = await renderSfc('views/SeedreamCreate.vue', {
    route: '/image-generation/create',
  });
  // rows matches the video composer (rows="3") so the textarea's intrinsic
  // height can never overflow the shared 282px composer and shift the layout.
  assert.match(html, /rows="3"/);
  assert.match(html, /min-h-\[282px\]/);
  assert.doesNotMatch(html, /min-h-\[224px\]/);
});

test('Seedream create page presents prompt and parameters in one composer without reference image upload', async () => {
  const html = await renderSfc('views/SeedreamCreate.vue', {
    route: '/image-generation/create',
  });
  assert.match(html, /data-test="seedream-composer"/);
  assert.match(html, /class="[^"]*seedream-prompt-surface[^"]*border-\[#3b3b3b\][^"]*bg-\[#1f1f1f\][^"]*"[^>]*data-test="seedream-composer"/);
  assert.match(html, /data-test="seedream-prompt"/);
  assert.match(html, /data-test="seedream-model"/);
  assert.doesNotMatch(html, /<select[^>]*data-test="seedream-model"/);
  assert.match(html, /data-test="seedream-parameter-summary"/);
  assert.match(html, /class="[^"]*border-\[#3b3b3b\][^"]*bg-\[#1f1f1f\][^"]*"[^>]*data-test="seedream-parameter-panel"/);
  assert.match(html, /aria-expanded="false"/);
  assert.match(html, /data-test="seedream-parameter-panel"[^>]*style="display:none;"/);
  assert.match(html, /data-test="seedream-resolution"/);
  assert.match(html, /data-test="seedream-ratio"/);
  assert.match(html, /data-test="seedream-count"/);
  assert.match(html, /图片生成/);
  assert.doesNotMatch(html, /data-test="seedream-reference-image"/);
});

test('Seedream create page does not render confirmation modal initially', async () => {
  const html = await renderSfc('views/SeedreamCreate.vue', {
    route: '/image-generation/create',
  });
  assert.doesNotMatch(html, /data-test="seedream-confirm-submit"/);
});

test('Seedream create page renders the task list below the full-width composer', async () => {
  const html = await renderSfc('views/SeedreamCreate.vue', {
    route: '/image-generation/create',
  });
  const composerIndex = html.indexOf('data-test="seedream-composer"');
  const taskListIndex = html.indexOf('data-test="seedream-board-empty"');
  assert.ok(composerIndex >= 0);
  assert.ok(taskListIndex > composerIndex);
  assert.doesNotMatch(html, /max-w-4xl/);
});

// ---------------------------------------------------------------------------
// Reference image (single-image reference generation)
// ---------------------------------------------------------------------------

test('image composer renders an optional single reference image card', async () => {
  const html = await renderSfc('views/SeedreamCreate.vue', {
    route: '/image-generation/create',
  });
  assert.match(html, /data-test="seedream-reference-card"/);
  assert.match(html, /参考图/);
  assert.match(html, /data-test="seedance-frame-optional"/);
});

test('reference image card shows the draft preview and remove control when a reference is attached', async () => {
  const html = await renderSfc('views/SeedreamCreate.vue', {
    route: '/image-generation/create',
    piniaState: {
      'ai-creation': {
        activeMode: 'image',
        imageInitialized: true,
        imageDraft: {
          prompt: 'keep the pose',
          model: 'pro',
          resolution: '1K',
          ratio: '16:9',
          count: 2,
          reference_image: '/tmp/reference.png',
        },
        imagePreviewUrls: { reference: 'data:image/png;base64,cmVm' },
        videoInitialized: true,
      },
    },
  });
  assert.match(html, /data:image\/png;base64,cmVm/);
  assert.doesNotMatch(html, /data-test="seedream-reference-card"[^>]*>\s*<fieldset[^>]*>\s*<button[^>]*title="选择参考图"/);
});

test('creating a batch submits the reference image path from the image draft', async () => {
  const { createScriptedPyWebViewBridge, loadFrontendModule, closeFrontendHarness } = await import(
    './scripted-pywebview-bridge.mjs'
  );
  try {
    const bridge = createScriptedPyWebViewBridge({
      seedream_create_batch: [
        {
          resolve: {
            success: true,
            batch: {
              local_id: 'batch-1',
              request: {},
              status: 'completed',
              sequence: '',
              reference_image_url: '/seedream-media/batch-1/reference',
              attempts: [],
              created_at: '2026-08-13T10:00:00Z',
              updated_at: '2026-08-13T10:00:00Z',
            },
          },
        },
      ],
    });
    const { createPinia, setActivePinia } = await import('pinia');
    const { useAICreationStore } = await loadFrontendModule('/src/stores/aiCreation.ts');
    const { useSeedreamStore } = await loadFrontendModule('/src/stores/seedream.ts');
    const { createRequest } = await loadFrontendModule('/src/seedream-ui.ts');
    setActivePinia(createPinia());
    const workspace = useAICreationStore();
    const store = useSeedreamStore();

    workspace.imageDraft.reference_image = '/tmp/reference.png';
    await store.createBatch(createRequest(workspace.imageDraft));
    const createCall = bridge.calls.find((call) => call.method === 'seedream_create_batch');
    assert.equal(createCall.args[0].reference_image, '/tmp/reference.png');

    workspace.imageDraft.reference_image = '';
    await store.createBatch(createRequest(workspace.imageDraft));
    const secondCall = bridge.calls.filter((call) => call.method === 'seedream_create_batch')[1];
    assert.equal(secondCall.args[0].reference_image, null);
  } finally {
    await closeFrontendHarness();
  }
});

test('clearing the image draft removes the reference image and its preview', async () => {
  const { loadFrontendModule, closeFrontendHarness } = await import('./scripted-pywebview-bridge.mjs');
  try {
    const { createPinia, setActivePinia } = await import('pinia');
    const { useAICreationStore } = await loadFrontendModule('/src/stores/aiCreation.ts');
    setActivePinia(createPinia());
    const workspace = useAICreationStore();

    workspace.imageDraft.reference_image = '/tmp/reference.png';
    workspace.imagePreviewUrls.reference = 'data:image/png;base64,cmVm';
    assert.equal(workspace.imageDraftChanged(), true);

    workspace.resetImageDraft();

    assert.equal(workspace.imageDraft.reference_image, '');
    assert.equal(workspace.imagePreviewUrls.reference, '');
    assert.equal(workspace.imageDraftChanged(), false);
  } finally {
    await closeFrontendHarness();
  }
});

test('selecting a reference image stores the picked path and a thumbnail preview', async () => {
  const { createScriptedPyWebViewBridge, loadFrontendModule, closeFrontendHarness } = await import(
    './scripted-pywebview-bridge.mjs'
  );
  try {
    const bridge = createScriptedPyWebViewBridge({
      seedream_select_image_file: [{ resolve: '/tmp/picked.png' }],
      get_frame_thumbnail: [{ resolve: 'dGh1bWI=' }],
    });
    const { createPinia, setActivePinia } = await import('pinia');
    const { useSeedreamStore } = await loadFrontendModule('/src/stores/seedream.ts');
    setActivePinia(createPinia());
    const store = useSeedreamStore();

    const selection = await store.selectReferenceImage();

    assert.deepEqual(selection, { path: '/tmp/picked.png', previewUrl: 'data:image/png;base64,dGh1bWI=' });
    assert.deepEqual(
      bridge.calls.map((call) => call.method),
      ['seedream_select_image_file', 'get_frame_thumbnail'],
    );
  } finally {
    await closeFrontendHarness();
  }
});

test('paid confirmation mentions the reference image when one is attached', async () => {
  const source = await readFile(new URL('../src/views/SeedreamCreate.vue', import.meta.url), 'utf8');
  assert.match(source, /data-test="seedream-confirm-reference"/);
  const [zh, en] = await Promise.all([
    readFile(new URL('../src/locales/zh-CN.ts', import.meta.url), 'utf8'),
    readFile(new URL('../src/locales/en.ts', import.meta.url), 'utf8'),
  ]);
  assert.match(zh, /reference:/);
  assert.match(en, /reference:/);
});

test('switching creation mode keeps the reference image in the image draft', async () => {
  const { loadFrontendModule, closeFrontendHarness } = await import('./scripted-pywebview-bridge.mjs');
  try {
    const { createPinia, setActivePinia } = await import('pinia');
    const { useAICreationStore } = await loadFrontendModule('/src/stores/aiCreation.ts');
    setActivePinia(createPinia());
    const workspace = useAICreationStore();

    workspace.imageDraft.reference_image = '/tmp/reference.png';
    workspace.imagePreviewUrls.reference = 'data:image/png;base64,cmVm';

    workspace.activeMode = 'video';
    workspace.activeMode = 'image';

    assert.equal(workspace.imageDraft.reference_image, '/tmp/reference.png');
    assert.equal(workspace.imagePreviewUrls.reference, 'data:image/png;base64,cmVm');
  } finally {
    await closeFrontendHarness();
  }
});


test('retired Lite remains named in history but is unavailable for new generation', () => {
  assert.deepEqual(Object.keys(MODEL_RESOLUTIONS), ['pro', 'flash']);
  assert.equal(MODEL_LABELS.lite, 'Seedream 5.0 Lite');
});
