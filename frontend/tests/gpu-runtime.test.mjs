import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';

after(closeSfcRenderer);

const total_bytes = 1298542822;

function renderCard(phase, { compatibility = { state: 'compatible', name: 'GeForce RTX 4060 Ti' }, modelReady = true, cpuRunning = false, downloaded_bytes = 0 } = {}) {
  return renderSfc('components/editor/GpuRuntimeCard.vue', {
    props: { model: 'birefnet-lite-onnx', modelReady, cpuRunning },
    configureSetup(value) {
      value.status.value = { phase, total_bytes, downloaded_bytes, error: null };
      value.device.value = compatibility;
    },
  });
}

test('a compatible GPU offers the three component sources and a size estimate before download', async () => {
  const html = await renderCard('needs_download');

  assert.match(html, /RTX 4060 Ti/);
  assert.match(html, /约 1\.3 GB/);
  assert.match(html, /下载并启用/);
  for (const label of ['阿里云', '华为云', '官方 PyPI']) assert.match(html, new RegExp(label));
  assert.doesNotMatch(html, /清华大学|中科大|魔搭|Hugging Face|0\.0 MB|progressbar/);
});

test('only compatible GPUs with a ready model show download controls', async () => {
  for (const state of ['no_nvidia', 'unsupported', 'driver', 'unknown']) {
    const html = await renderCard('needs_download', { compatibility: { state } });
    assert.doesNotMatch(html, /下载并启用|下载来源|1\.3 GB/);
    assert.match(html, /仍可使用 CPU 抠图/);
    if (state === 'driver' || state === 'unknown') assert.match(html, /重新检测/);
  }

  const html = await renderCard('needs_download', { modelReady: false });
  assert.match(html, /RTX 4060 Ti/);
  assert.doesNotMatch(html, /下载并启用|下载来源|先在上方|可使用 CPU/);
});

test('download and pause show progress while installation and readiness stay compact', async () => {
  const downloading = await renderCard('downloading', { downloaded_bytes: 500000000 });
  assert.match(downloading, /role="progressbar"/);
  assert.match(downloading, /500\.0 MB \/ 1298\.5 MB/);
  assert.doesNotMatch(downloading, /下载来源/);

  const paused = await renderCard('paused', { downloaded_bytes: 500000000 });
  assert.match(paused, /500\.0 MB \/ 1298\.5 MB/);
  assert.match(paused, /继续下载/);

  const installing = await renderCard('initializing', { downloaded_bytes: total_bytes });
  assert.match(installing, /正在安装并验证 cuda加速/);
  assert.doesNotMatch(installing, /MB|下载来源/);

  const ready = await renderCard('ready', { downloaded_bytes: total_bytes });
  assert.match(ready, /cuda加速已就绪/);
  assert.doesNotMatch(ready, /CPU|MB|下载来源/);
  assert.match(await renderCard('ready', { cpuRunning: true }), /当前使用CPU抠图/);
});

test('the desktop bridge receives the chosen mirror only after a compatible detection result', async () => {
  const calls = [];
  let hardware = { state: 'compatible' };
  const previous = globalThis.window;
  globalThis.window = { pywebview: { api: {
    get_app_version() {},
    async detect_gpu_compatibility() { return hardware; },
    async prepare_gpu_runtime(...args) {
      calls.push(args);
      return {
        phase: 'failed',
        source: 'aliyun',
        total_bytes,
        error: null,
        device: { state: 'driver' },
      };
    },
  } } };
  try {
    let controls;
    await renderSfc('components/editor/GpuRuntimeCard.vue', {
      props: { model: 'birefnet-lite-onnx', modelReady: true },
      configureSetup(value) {
        controls = value;
        value.status.value = { phase: 'needs_download', total_bytes, error: null };
      },
    });
    controls.source.value = 'huawei';
    await controls.prepare();
    assert.deepEqual(calls, []);

    await controls.detect();
    await controls.prepare();
    assert.deepEqual(calls, [['birefnet-lite-onnx', 'huawei']]);
    assert.equal(controls.source.value, 'huawei');
    assert.equal(controls.device.value.state, 'driver');

    hardware = { state: 'compatible' };
    await controls.detect();
    controls.source.value = 'pypi';
    await controls.prepare();
    assert.deepEqual(calls[1], ['birefnet-lite-onnx', 'pypi']);
  } finally {
    globalThis.window = previous;
  }
});
