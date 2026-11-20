import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';
after(closeSfcRenderer);
test('paused model shows recovered progress, remembered source and a continue action', async () => {
  const html = await renderSfc('components/editor/ModelStatusCard.vue', {
    props: { status: { model: 'birefnet-lite-onnx', phase: 'paused', source: 'huggingface', downloaded_bytes: 1048576, total_bytes: 3145728, error: null } },
  });
  assert.match(html, /继续下载/);
  assert.match(html, /已下载 1.0 MB \/ 3.1 MB/);
  assert.match(html, /Hugging Face/);
  assert.doesNotMatch(html, /PyPI/);
});

test('continue and failure source changes emit the selected model source', async () => {
  for (const phase of ['paused', 'failed']) {
    const selected = [];
    let bindings;
    await renderSfc('components/editor/ModelStatusCard.vue', {
      props: { status: { model: 'birefnet-lite-onnx', phase, source: 'huggingface', downloaded_bytes: 1, total_bytes: 3, error: null }, onRetry: source => selected.push(source) },
      configureSetup(value) { bindings = value; },
    });
    bindings.requestDownload();
    bindings.source.value = 'modelscope';
    bindings.requestDownload();
    assert.deepEqual(selected, ['huggingface', 'modelscope']);
  }
});

test('Windows pause and verification text leave Mac download controls intact', async () => {
  for (const [model, phase, expected] of [['birefnet-lite-onnx', 'downloading', '暂停下载'], ['birefnet-lite-onnx', 'verifying', 'SHA-256'], ['birefnet-comfy', 'downloading', '取消下载']]) {
    const html = await renderSfc('components/editor/ModelStatusCard.vue', { props: { status: { model, phase, downloaded_bytes: 1, total_bytes: 3, error: null } } });
    assert.match(html, new RegExp(expected));
  }
});


test('Lite displays the same decimal download size before and during preparation', async () => {
  for (const phase of ['needs_download', 'downloading', 'paused']) {
    const html = await renderSfc('components/editor/ModelStatusCard.vue', {
      props: { status: { model: 'birefnet-lite-onnx', phase, source: 'huggingface', downloaded_bytes: 1000000, total_bytes: 114538221, error: null } },
    });
    assert.match(html, /114.5 MB/);
    if (phase !== 'downloading') assert.match(html, /Hugging Face/);
    assert.doesNotMatch(html, /PyPI/);
  }
});
