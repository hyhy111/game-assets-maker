import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';

after(closeSfcRenderer);

const batchFixture = (overrides = {}) => ({
  local_id: 'batch-1',
  request: {
    prompt: 'A pixel art hero',
    model: 'pro',
    resolution: '1K',
    ratio: '16:9',
    count: 2,
  },
  status: 'completed',
  sequence: '',
  attempts: [
    {
      local_id: 'attempt-1',
      index: 0,
      status: 'succeeded',
      request: {},
      response: {},
      usage: {},
      total_tokens: 42,
      image_url: '/seedream-media/batch-1/image/0',
      image_width: 1024,
      image_height: 576,
      local_path: 'images/0.jpg',
      url_expired: false,
      created_at: '2026-08-04T10:00:00Z',
      updated_at: '2026-08-04T10:02:00Z',
      finished_at: '2026-08-04T10:02:00Z',
      elapsed_seconds: 120,
      error: null,
    },
    {
      local_id: 'attempt-2',
      index: 1,
      status: 'succeeded',
      request: {},
      response: {},
      usage: {},
      total_tokens: 42,
      image_url: '/seedream-media/batch-1/image/1',
      image_width: 1024,
      image_height: 576,
      local_path: 'images/1.jpg',
      url_expired: false,
      created_at: '2026-08-04T10:00:00Z',
      updated_at: '2026-08-04T10:02:00Z',
      finished_at: '2026-08-04T10:02:00Z',
      elapsed_seconds: 130,
      error: null,
    },
  ],
  created_at: '2026-08-04T10:00:00Z',
  updated_at: '2026-08-04T10:02:00Z',
  ...overrides,
});

const renderBoard = (batches = []) =>
  renderSfc('components/seedream/SeedreamBatchList.vue', {
    route: '/image-generation/create',
    piniaState: {
      seedream: {
        batches,
        currentBatch: null,
        settings: null,
        creatingBatch: false,
        loading: false,
        error: null,
      },
    },
  });

test('Seedream batch board shows empty state when no batches', async () => {
  const html = await renderBoard([]);
  assert.match(html, /data-test="seedream-board-empty"/);
});

test('Seedream batch board shows batch card without prompt', async () => {
  const html = await renderBoard([batchFixture()]);
  assert.match(html, /data-test="seedream-board-card-batch-1"/);
  assert.doesNotMatch(html, /A pixel art hero/);
});

test('Seedream batch board shows model label', async () => {
  const html = await renderBoard([batchFixture()]);
  assert.match(html, /data-test="seedream-board-model-batch-1"/);
  assert.match(html, /Seedream 5\.0 Pro/);
});

test('Seedream batch board shows resolution', async () => {
  const html = await renderBoard([batchFixture()]);
  assert.match(html, /data-test="seedream-board-resolution-batch-1"/);
  assert.match(html, /1K/);
});

test('Seedream batch board shows aspect ratio', async () => {
  const html = await renderBoard([batchFixture()]);
  assert.match(html, /data-test="seedream-board-ratio-batch-1"/);
  assert.match(html, /16:9/);
});

test('Seedream batch board shows count from attempts length', async () => {
  const html = await renderBoard([batchFixture()]);
  assert.match(html, /data-test="seedream-board-count-batch-1"/);
  assert.match(html, /2/);
});

test('Seedream batch board shows aggregated status badge', async () => {
  const html = await renderBoard([batchFixture()]);
  assert.match(html, /data-test="seedream-board-status-batch-1"/);
  assert.match(html, /已完成/);
});

test('Seedream batch board shows creation time', async () => {
  const html = await renderBoard([batchFixture()]);
  assert.match(html, /data-test="seedream-board-created-batch-1"/);
});

test('Seedream batch board shows sequence number for duplicate-param batches', async () => {
  const b1 = batchFixture({ local_id: 'b1', created_at: '2026-08-04T10:00:00Z', sequence: '①' });
  const b2 = batchFixture({ local_id: 'b2', created_at: '2026-08-04T11:00:00Z', sequence: '②' });
  const html = await renderBoard([b1, b2]);
  assert.match(html, /data-test="seedream-board-sequence-b1"/);
  assert.match(html, /①/);
  assert.match(html, /data-test="seedream-board-sequence-b2"/);
  assert.match(html, /②/);
});

test('Seedream batch board does not show sequence for unique-param batches', async () => {
  const b1 = batchFixture({ local_id: 'b1', request: { prompt: 'hero', model: 'pro', resolution: '1K', ratio: '16:9', count: 2 } });
  const b2 = batchFixture({ local_id: 'b2', request: { prompt: 'villain', model: 'lite', resolution: '2K', ratio: '1:1', count: 1 } });
  const html = await renderBoard([b1, b2]);
  assert.doesNotMatch(html, /seedream-board-sequence-b1/);
  assert.doesNotMatch(html, /seedream-board-sequence-b2/);
});

test('Seedream batch board shows partially_complete status', async () => {
  const html = await renderBoard([batchFixture({
    status: 'partially_complete',
    attempts: [
      { ...batchFixture().attempts[0] },
      { ...batchFixture().attempts[1], status: 'failed', image_url: '', local_path: null, error: { code: 'RATE_LIMIT', message: 'rate limited', status: 429 } },
    ],
  })]);
  assert.match(html, /data-test="seedream-board-status-batch-1"/);
  assert.match(html, /部分完成/);
});
