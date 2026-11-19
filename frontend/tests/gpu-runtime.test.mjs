import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';

after(closeSfcRenderer);

test('GPU preparation offers independent package sources, exact total and resumable progress', async () => {
  const html = await renderSfc('components/editor/GpuRuntimeCard.vue', {
    props: { model: 'birefnet-lite-onnx', modelReady: true },
    configureSetup(value) {
      value.status.value = { phase: 'paused', source: 'pypi', downloaded_bytes: 500000000, total_bytes: 1298542822, error: null };
    },
  });
  assert.match(html, /PyPI/);
  assert.match(html, /阿里云/);
  assert.match(html, /500.0 MB \/ 1298.5 MB/);
  assert.match(html, /继续准备/);
  assert.doesNotMatch(html, /ModelScope|魔搭|Hugging Face/);
});

test('explicit prepare and retry send the chosen component source through the desktop bridge', async () => {
  const calls = [];
  const previous = globalThis.window;
  globalThis.window = { pywebview: { api: {
    get_app_version() {},
    async prepare_gpu_runtime(...args) { calls.push(args); },
    async get_gpu_runtime_status() { return { phase: 'failed', source: 'aliyun', total_bytes: 6, error: null }; },
  } } };
  try {
    let controls;
    await renderSfc('components/editor/GpuRuntimeCard.vue', {
      props: { model: 'birefnet-standard-onnx', modelReady: true },
      configureSetup(value) { controls = value; },
    });
    assert.deepEqual(calls, []);
    controls.source.value = 'pypi';
    await controls.prepare();
    assert.deepEqual(calls, [['birefnet-standard-onnx', 'pypi']]);
    assert.equal(controls.source.value, 'pypi');
    controls.source.value = 'aliyun';
    await controls.prepare();
    assert.deepEqual(calls[1], ['birefnet-standard-onnx', 'aliyun']);
  } finally {
    globalThis.window = previous;
  }
});

for (const [phase, message] of [
  ['needs_download', 'NVIDIA 加速尚未准备'],
  ['initializing', '正在校验和验证 NVIDIA 加速'],
  ['ready', 'NVIDIA 加速可用，将用于下一次任务'],
  ['failed', 'NVIDIA 加速准备失败'],
]) {
  test(`GPU ${phase} keeps CPU availability visible`, async () => {
    const html = await renderSfc('components/editor/GpuRuntimeCard.vue', {
      props: { model: 'birefnet-lite-onnx', modelReady: true },
      configureSetup(value) {
        value.status.value = { phase, error: null, total_bytes: 1298542822 };
      },
    });
    assert.match(html, new RegExp(message));
    assert.match(html, /模型就绪后可继续使用 CPU/);
    if (phase === 'ready') assert.doesNotMatch(html, /从完整本地组件缓存启用/);
  });
}
