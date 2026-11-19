import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';
after(closeSfcRenderer);
for (const locale of ['zh-CN', 'en']) {
  test(`${locale} reports CPU fallback for the actual task`, async () => {
    const html = await renderSfc('views/Editor/Step2Background.vue', {
      locale,
      configureSetup(value) {
        value.taskStatus.value = { step: 2, status: 'completed', execution_device: 'cpu', gpu_fallback: { code: 'GPU_OUT_OF_MEMORY', message: 'fixture' } };
      }
    });
    assert.match(html, locale === 'en' ? /completed on CPU/ : /已使用 CPU 完成/);
    assert.match(html, locale === 'en' ? /GPU memory/ : /显存不足/);
    assert.match(html, locale === 'en' ? /selected model/ : /原模型/);
  });
}
