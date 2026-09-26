import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';

after(closeSfcRenderer);

const settingsState = (defaultCount = 2) => ({
  seedream: {
    batches: [],
    currentBatch: null,
    settings: { default_count: defaultCount },
    creatingBatch: false,
    loading: false,
    error: null,
  },
});

test('Seedream settings page renders default count selector with options 1-4', async () => {
  const html = await renderSfc('views/SeedreamSettings.vue', {
    route: '/image-generation/settings',
    piniaState: settingsState(2),
  });
  assert.match(html, /data-test="seedream-settings-count"/);
  assert.match(html, /value="1"/);
  assert.match(html, /value="2"/);
  assert.match(html, /value="3"/);
  assert.match(html, /value="4"/);
});

test('Seedream settings page shows saved default count value', async () => {
  const html = await renderSfc('views/SeedreamSettings.vue', {
    route: '/image-generation/settings',
    piniaState: settingsState(3),
  });
  assert.match(html, /<option value="3" selected>/);
});

test('Seedream settings page has save button', async () => {
  const html = await renderSfc('views/SeedreamSettings.vue', {
    route: '/image-generation/settings',
    piniaState: settingsState(2),
  });
  assert.match(html, /type="submit"/);
  assert.match(html, /form="seedream-settings-form"/);
});

test('Seedream settings page renders defaults panel', async () => {
  const html = await renderSfc('views/SeedreamSettings.vue', {
    route: '/image-generation/settings',
    piniaState: settingsState(2),
  });
  assert.match(html, /data-test="seedream-settings-count"/);
});
