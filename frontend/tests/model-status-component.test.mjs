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

test('step 1 and step 2 use the same card and step 2 uses the readiness guard', async () => {
  const source = async (name) => readFile(new URL(`../src/${name}`, import.meta.url), 'utf8');
  const [step1, step2] = await Promise.all([
    source('views/Editor/Step1Extract.vue'),
    source('views/Editor/Step2Background.vue'),
  ]);
  assert.match(step1, /<ModelStatusCard/);
  assert.match(step2, /<ModelStatusCard/);
  assert.match(step2, /canStartStep2\(step1Completed\.value, modelStatus\.value, selectedModel\.value\)/);
  assert.match(step2, /watch\(selectedModel/);
  assert.match(step2, /modelStatus\.step2Blocked/);
});
