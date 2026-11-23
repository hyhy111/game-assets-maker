import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { createPinia, setActivePinia } from 'pinia';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';
import { closeFrontendHarness, createScriptedPyWebViewBridge, loadFrontendModule } from './scripted-pywebview-bridge.mjs';

after(closeSfcRenderer);
after(closeFrontendHarness);

test('cancelling a model download preserves a completion event delivered before the bridge reply', async () => {
  const downloading = { model: 'u2net', phase: 'downloading', downloaded_bytes: 4, total_bytes: 10, error: null };
  const cancelled = { ...downloading, phase: 'needs_download', downloaded_bytes: null, total_bytes: null };
  const bridge = createScriptedPyWebViewBridge({
    cancel_model_download: [{
      resolve: () => {
        bridge.window.dispatchEvent(new CustomEvent('model-status', { detail: cancelled }));
        return downloading;
      },
    }],
  });
  setActivePinia(createPinia());
  const { useProcessStore } = await loadFrontendModule('/src/stores/process.ts');
  const store = useProcessStore();
  store.initProgressListeners();
  bridge.window.dispatchEvent(new CustomEvent('model-status', { detail: downloading }));

  await store.cancelModelDownload();

  assert.deepEqual(bridge.calls, [{ method: 'cancel_model_download', args: ['u2net'] }]);
  assert.deepEqual(store.modelStatus, cancelled);
});

test('Step 2 uses segmented model controls and shows only U2Net alpha-matting settings', async () => {
  const html = await renderSfc('views/Editor/Step2Background.vue');
  const u2net = html.match(/<button[^>]*data-test="background-model-u2net"[^>]*>/)?.[0];
  const birefnet = html.match(/<button[^>]*data-test="background-model-birefnet-comfy"[^>]*>/)?.[0];

  const modelGroup = html.match(/<div[^>]*role="group"[^>]*aria-label="抠图模型"[\s\S]*?<\/div>/)?.[0];

  assert.ok(modelGroup, 'models use a segmented control group');
  assert.ok(u2net, 'U2Net has a segmented model button');
  assert.ok(birefnet, 'BiRefNet has a segmented model button');
  assert.ok(modelGroup.indexOf(birefnet) < modelGroup.indexOf(u2net), 'BiRefNet appears first');
  assert.match(modelGroup, /data-test="background-model-birefnet-comfy"[^>]*>\s*BiRefNet\s*<\/button>/);
  assert.match(modelGroup, /data-test="background-model-u2net"[^>]*>\s*U²-Net\s*<\/button>/);
  assert.match(u2net, /aria-pressed="true"/);
  assert.match(birefnet, /aria-pressed="false"/);
  assert.doesNotMatch(modelGroup, /aria-haspopup="listbox"/);
  assert.match(html, /aria-label="Alpha Matting"/);
  for (const label of ['抠图微调', 'Alpha 对比度', 'Alpha 阈值', '最小前景面积', '填充内部孔洞', '边缘去色']) {
    assert.doesNotMatch(html, new RegExp(label));
  }
});

test('segmented model choices remain disabled during processing', async () => {
  const html = await renderSfc('views/Editor/Step2Background.vue', {
    configureSetup(value) {
      value.taskStatus.value = { status: 'running', step: 2 };
    },
  });
  for (const model of ['u2net', 'birefnet-comfy']) {
    const button = html.match(new RegExp(`<button[^>]*data-test="background-model-${model}"[^>]*>`))?.[0];
    assert.ok(button);
    assert.match(button, /\sdisabled(?:\s|>|=)/);
  }
});

for (const model of ['birefnet-comfy', 'birefnet-lite-onnx']) {
  test(`${model} submission keeps defringe settings and resets every hidden parameter`, async () => {
    const project = {
      id: 'hero/idle', role: 'hero', action: 'idle', name: 'idle', path: '/projects/hero/idle',
      video_path: '', frame_interval: 1, created_at: '', modified_at: '',
      steps: { '1': { completed: true, data_ready: true, count: 1 } },
    };
    const bridge = createScriptedPyWebViewBridge({
      preload_model: [
        { resolve: model => ({ model, phase: 'ready', downloaded_bytes: null, total_bytes: null, error: null }) },
        { resolve: model => ({ model, phase: 'ready', downloaded_bytes: null, total_bytes: null, error: null }) },
      ],
      start_processing: [{ resolve: 'background-task' }],
      get_task_status: [{ resolve: { task_id: 'background-task', status: 'completed', step: 2, progress: 100 } }],
      get_project: [{ resolve: project }],
    });
    let bindings;
    await renderSfc('views/Editor/Step2Background.vue', {
      piniaState: {
        project: { currentProject: project },
        process: {
          s2Params: {
            model,
            alpha_matting: false,
            alpha_matting_erode_size: 17,
            alpha_matting_background_threshold: 200,
            alpha_matting_foreground_threshold: 150,
            alpha_contrast: 3.5,
            alpha_threshold: 99,
            defringe_enabled: true,
            defringe_px: 7,
            defringe_amount: 0.75,
            min_foreground_area: 250,
            fill_holes_max_size: 500,
            fps: 12,
            processed: false,
            processing_time: 0,
          },
        },
      },
      configureSetup(value) { bindings = value; },
    });
    await bindings.processStore.preloadModel(model);
    assert.equal(bindings.canProcess.value, true);

    await bindings.startProcessing();

    const submission = bridge.calls.find(call => call.method === 'start_processing');
    assert.deepEqual(submission.args, ['hero/idle', 2, {
      model,
      alpha_matting: true,
      alpha_matting_erode_size: 5,
      alpha_matting_background_threshold: 120,
      alpha_matting_foreground_threshold: 240,
      alpha_contrast: 1,
      alpha_threshold: 0,
      defringe_enabled: true,
      defringe_px: 7,
      defringe_amount: 0.75,
      min_foreground_area: 0,
      fill_holes_max_size: 0,
      fps: 12,
      processed: true,
      processing_time: 0,
    }]);
  });

}

test('BiRefNet exposes only edge-defringe controls after model switching', async () => {
  let bindings;
  const html = await renderSfc('views/Editor/Step2Background.vue', {
    configureSetup(value) {
      bindings = value;
      value.setModel('birefnet-comfy');
      value.s2Params.value.defringe_enabled = true;
    },
  });
  const visibleHtml = html.replace(/<!--[\s\S]*?-->/g, '');
  const u2net = html.match(/<button[^>]*data-test="background-model-u2net"[^>]*>/)?.[0];
  const birefnet = html.match(/<button[^>]*data-test="background-model-birefnet-comfy"[^>]*>/)?.[0];

  assert.equal(bindings.s2Params.value.model, 'birefnet-comfy');
  assert.match(u2net, /aria-pressed="false"/);
  assert.match(birefnet, /aria-pressed="true"/);
  for (const label of ['边缘去色', '去色宽度（px）', '去色强度']) {
    assert.match(visibleHtml, new RegExp(label));
  }
  for (const label of ['Alpha Matting', '腐蚀大小', '背景阈值', '前景阈值', '抠图微调', 'Alpha 对比度', 'Alpha 阈值', '最小前景面积', '填充内部孔洞']) {
    assert.doesNotMatch(visibleHtml, new RegExp(label));
  }
});

test('U2Net submission keeps alpha-matting settings and resets every hidden parameter', async () => {
  const project = {
    id: 'hero/idle', role: 'hero', action: 'idle', name: 'idle', path: '/projects/hero/idle',
    video_path: '', frame_interval: 1, created_at: '', modified_at: '',
    steps: { '1': { completed: true, data_ready: true, count: 1 } },
  };
  const bridge = createScriptedPyWebViewBridge({
    preload_model: [
      { resolve: model => ({ model, phase: 'ready', downloaded_bytes: null, total_bytes: null, error: null }) },
      { resolve: model => ({ model, phase: 'ready', downloaded_bytes: null, total_bytes: null, error: null }) },
    ],
    start_processing: [{ resolve: 'background-task' }],
    get_task_status: [{ resolve: { task_id: 'background-task', status: 'completed', step: 2, progress: 100 } }],
    get_project: [{ resolve: project }],
  });
  let bindings;
  await renderSfc('views/Editor/Step2Background.vue', {
    piniaState: {
      project: { currentProject: project },
      process: {
        s2Params: {
          model: 'u2net',
          alpha_matting: true,
          alpha_matting_erode_size: 9,
          alpha_matting_background_threshold: 110,
          alpha_matting_foreground_threshold: 220,
          alpha_contrast: 2,
          alpha_threshold: 100,
          defringe_enabled: true,
          defringe_px: 8,
          defringe_amount: 0.9,
          min_foreground_area: 100,
          fill_holes_max_size: 200,
          fps: 15,
          processed: false,
          processing_time: 0,
        },
      },
    },
    configureSetup(value) { bindings = value; },
  });
  await bindings.processStore.preloadModel('u2net');
  assert.equal(bindings.canProcess.value, true);

  await bindings.startProcessing();

  const submission = bridge.calls.find(call => call.method === 'start_processing');
  assert.deepEqual(submission.args, ['hero/idle', 2, {
    model: 'u2net',
    alpha_matting: true,
    alpha_matting_erode_size: 9,
    alpha_matting_background_threshold: 110,
    alpha_matting_foreground_threshold: 220,
    alpha_contrast: 1,
    alpha_threshold: 0,
    defringe_enabled: false,
    defringe_px: 2,
    defringe_amount: 0.5,
    min_foreground_area: 0,
    fill_holes_max_size: 0,
    fps: 15,
    processed: true,
    processing_time: 0,
  }]);
});


test('Windows offers Lite FP16 and U2-Net and rejects the removed model', async () => {
  let bindings;
  const html = await renderSfc('views/Editor/Step2Background.vue', {
    piniaState: {
      config: { config: { background_models: ['u2net', 'birefnet-lite-onnx'], processing: { background_model: 'birefnet-lite-onnx' } } },
      process: { s2Params: { model: 'birefnet-lite-onnx', defringe_enabled: false } },
    },
    configureSetup(value) { bindings = value; },
  });
  assert.match(html, /background-model-birefnet-lite-onnx/);
  assert.match(html, /background-model-u2net/);
  assert.doesNotMatch(html, /background-model-birefnet-standard-onnx|BiRefNet Standard FP16/);
  assert.doesNotMatch(html, /background-model-birefnet-comfy/);
  assert.match(html, /边缘去色/);
  bindings.setModel('birefnet-standard-onnx');
  assert.equal(bindings.selectedModel.value, 'birefnet-lite-onnx');
  bindings.setModel('u2net');
  assert.equal(bindings.selectedModel.value, 'u2net');
  bindings.setModel('birefnet-lite-onnx');
  assert.equal(bindings.selectedModel.value, 'birefnet-lite-onnx');
});


test('Lite download card shows pinned decimal size before explicit download', async () => {
  const html = await renderSfc('components/editor/ModelStatusCard.vue', {
    props: { status: { model: 'birefnet-lite-onnx', phase: 'needs_download', downloaded_bytes: null, total_bytes: null, error: null } },
  });
  assert.match(html, /114.5 MB/);
  assert.match(html, /下载模型/);
});
