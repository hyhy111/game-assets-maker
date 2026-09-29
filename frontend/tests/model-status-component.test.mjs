import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';

after(closeSfcRenderer);

const status = (phase, overrides = {}) => ({
  model: 'u2net',
  phase,
  downloaded_bytes: null,
  total_bytes: null,
  error: null,
  ...overrides,
});

test('shared model card renders download, failure recovery, and ready states', async () => {
  const needed = await renderSfc('components/editor/ModelStatusCard.vue', {
    props: { status: status('needs_download') },
  });
  assert.match(needed, /u2net 模型需要首次下载/);
  assert.match(needed, /安装包不含模型。请选择来源下载约 176 MB 的模型文件，完成后保存在本机，无需重复下载。/);
  assert.match(needed, /<button[^>]*aria-haspopup="listbox"/);
  assert.doesNotMatch(needed, /<select/);
  const source = await readFile(new URL('../src/components/editor/ModelStatusCard.vue', import.meta.url), 'utf8');
  assert.doesNotMatch(source, /\bDownload\b/);

  const failed = await renderSfc('components/editor/ModelStatusCard.vue', {
    props: {
      status: status('failed', {
        error: { code: 'MODEL_DOWNLOAD_FAILED', message: 'Model download failed' },
      }),
    },
  });
  assert.match(failed, /模型下载失败，请检查网络连接后重试/);
  assert.match(failed, /重试模型准备/);

  const ready = await renderSfc('components/editor/ModelStatusCard.vue', {
    props: { status: status('ready') },
  });
  assert.match(ready, /u2net 模型已就绪/);
});

test('only step 2 owns the model card and model preparation', async () => {
  const source = async (name) => readFile(new URL(`../src/${name}`, import.meta.url), 'utf8');
  const [step1, step2] = await Promise.all([
    source('views/Editor/Step1Extract.vue'),
    source('views/Editor/Step2Background.vue'),
  ]);
  assert.doesNotMatch(step1, /ModelStatusCard/);
  assert.doesNotMatch(step1, /preloadModel/);
  assert.match(step2, /<ModelStatusCard/);
  assert.match(step2, /shouldShowModelStatus/);
  assert.ok(
    step2.indexOf('<ModelStatusCard') < step2.indexOf('Canvas Background Color Selector'),
    'the model card is shown above the preview background color control',
  );
  assert.match(step2, /canStartStep2\(step1Completed\.value, modelStatus\.value, selectedModel\.value\)/);
  assert.match(step2, /watch\(selectedModel/);
  assert.match(step2, /modelStatus\.step2Blocked/);
});

test('model card keeps the selected source for download and retry', async () => {
  const source = await readFile(new URL('../src/components/editor/ModelStatusCard.vue', import.meta.url), 'utf8');
  assert.match(source, /<Select\s+v-model="source"/);
  assert.match(source, /@click="\$emit\('retry', source\)"/);
});
