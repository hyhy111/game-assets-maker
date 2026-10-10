import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { imageGenerationCredits, videoGenerationCredits } from '../src/generation-credits.ts';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';

after(closeSfcRenderer);

test('image estimates match the supplied prices and multiply by requested count', () => {
  for (const [model, resolution, credits] of [
    ['pro', '1K', 30], ['pro', '1.5K', 30], ['pro', '2K', 60],
  ]) {
    for (const count of [1, 2, 3, 4]) {
      assert.equal(imageGenerationCredits(model, resolution, count), credits * count);
    }
  }
});

test('video estimates use every supplied table cell without linear extrapolation', () => {
  for (const [model, resolution, prices] of [
    ['standard', '480p', [185, 231, 277]],
    ['standard', '720p', [397, 497, 596]],
    ['standard', '1080p', [991, 1239, 1487]],
    ['fast', '480p', [149, 186, 223]],
    ['fast', '720p', [320, 400, 480]],
    ['mini', '480p', [92, 112, 139]],
    ['mini', '720p', [199, 248, 298]],
  ]) {
    prices.forEach((credits, index) => {
      assert.equal(videoGenerationCredits(model, resolution, index + 4), credits);
    });
  }
});

test('unpriced combinations are unknown rather than free or extrapolated', () => {
  assert.equal(videoGenerationCredits('fast', '1080p', 4), null);
  assert.equal(videoGenerationCredits('mini', '1080p', 4), null);
  for (const duration of [-1, 0, 4.5, 7, 15]) {
    assert.equal(videoGenerationCredits('standard', '720p', duration), null);
  }
  assert.equal(imageGenerationCredits('lite', '2K', 1), null);
  for (const resolution of ['1K', '1.5K', '2K']) {
    assert.equal(imageGenerationCredits('flash', resolution, 1), null);
  }
  for (const count of [0, -1, 1.5, 5]) {
    assert.equal(imageGenerationCredits('pro', '1K', count), null);
  }
});

test('image composer shows credits only for a logged-in account without a custom key', async () => {
  const html = await renderSfc('views/SeedreamCreate.vue', {
    route: '/image-generation/create',
    piniaState: {
      auth: { status: 'authenticated' },
      'ai-creation': { imageDraft: {
        model: 'pro', resolution: '2K', count: 3, prompt: '', ratio: '16:9', reference_image: '',
      } },
    },
  });
  assert.match(html, /预计消耗 180 积分/);
  assert.doesNotMatch(html, /1 元|100 积分|¥/);
});

test('custom key hides the image credit estimate even when the account is logged in', async () => {
  const html = await renderSfc('views/SeedreamCreate.vue', {
    route: '/image-generation/create',
    piniaState: {
      auth: { status: 'authenticated' },
      seedance: { settings: { api_key_configured: true } },
    },
  });
  assert.doesNotMatch(html, /data-test="generation-credits"/);
});

test('video composer shows the selected price only for a logged-in account without a custom key', async () => {
  const html = await renderSfc('views/SeedanceCreate.vue', {
    route: '/video-generation/create',
    props: { showTaskList: false },
    piniaState: {
      auth: { status: 'authenticated' },
      'ai-creation': { videoDraft: {
        model: 'mini', resolution: '480p', duration: 5, prompt: '', ratio: 'adaptive',
        first_frame: '', last_frame: null, generate_audio: false, return_last_frame: false,
      } },
    },
  });
  assert.match(html, /预计消耗 112 积分/);
});

test('custom key hides the video credit estimate', async () => {
  const html = await renderSfc('views/SeedanceCreate.vue', {
    route: '/video-generation/create',
    props: { showTaskList: false },
    piniaState: {
      auth: { status: 'authenticated' },
      seedance: { settings: { api_key_configured: true } },
    },
  });
  assert.doesNotMatch(html, /data-test="generation-credits"/);
});
