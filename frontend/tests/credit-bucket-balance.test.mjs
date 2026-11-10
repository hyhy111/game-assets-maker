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
  assert.match(html, /2099-01-01 到期/);
  assert.doesNotMatch(html, /billing\.expiresAt/);
});

test('credit scope summary and expanded rows use the same model names as the creation catalog', async () => {
  const video = 'doubao-seedance-2-0-mini-260615';
  const image = 'doubao-seedream-5-0-pro-260628';
  const ssrContext = {};
  const html = await renderSfc('components/layout/CreditBucketRow.vue', {
    props: {
      bucket: { bucketId: 'bonus', totalAmount: 500, remainAmount: 340 },
      scope: `${video} · 480p / 4秒；${video} · 720p / 4秒；${image} · 2K；future-model · 1K`,
    },
    piniaState: { 'ai-creation': { capabilities: {
      video: { models: [{ model: video, displayName: 'Seedance2.0 Mini' }] },
      image: { models: [{ model: image, displayName: 'Seedream 5.0 Pro' }] },
    } } },
    configureSetup(bindings) { bindings.scopeOpen.value = true; },
    ssrContext,
  });
  const tooltip = ssrContext.teleports.body;
  for (const content of [html, tooltip]) {
    assert.match(content, /Seedance2\.0 Mini/);
    assert.match(content, /Seedream 5\.0 Pro/);
    assert.match(content, /480p \/ 4秒；720p \/ 4秒/);
    assert.match(content, /future-model/);
    assert.ok(!content.includes(video));
    assert.ok(!content.includes(image));
  }
});

test('credit scope can resolve local image and video model keys without a media kind', async () => {
  const html = await renderSfc('components/layout/CreditBucketRow.vue', {
    props: { bucket: { bucketId: 'legacy', totalAmount: 100, remainAmount: 100 }, scope: 'mini · 720p；pro · 2K' },
  });
  assert.match(html, /Seedance2\.0 Mini/);
  assert.match(html, /Seedream 5\.0 Pro/);
});
