import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';

after(closeSfcRenderer);

test('remaining balance fills the bar and exhausted credit has an empty bar', async () => {
  for (const [remain, percent] of [[100, 100], [40, 40], [0, 0]]) {
    const html = await renderSfc('components/layout/CreditBucketRow.vue', {
      props: { bucket: { bucketId: '1', totalAmount: 100, remainAmount: remain,
        effectiveFrom: '2025-01-01T00:00:00Z', expireTime: '2099-01-01T00:00:00Z', skuName: 'Test credits' } },
    });
    assert.match(html, new RegExp(`width:${percent}%`));
    assert.match(html, new RegExp(`剩余 ${remain} / 共 100`));
    if (remain > 0) assert.match(html, /bg-gradient-to-r/);
    else assert.match(html, /opacity-50/);
  }
});

test('model scope belongs to its card and expiry does not repeat the balance', async () => {
  const html = await renderSfc('components/layout/CreditBucketRow.vue', {
    props: { bucket: { bucketId: '1', totalAmount: 100, remainAmount: 100,
      effectiveFrom: '2025-01-01T00:00:00Z', expireTime: '2099-01-01T00:00:00Z' },
    scope: 'model-a · 720p / 5秒；model-b · 2K' },
  });
  assert.match(html, /data-test="bucket-model-scope"/);
  assert.match(html, /truncate[^>]*>可用模型：model-a/);
  assert.match(html, /查看完整可用模型及规格/);
  assert.doesNotMatch(html, /剩 100 ·/);
});
