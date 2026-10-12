import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';

after(closeSfcRenderer);

const attempt = (index, status, overrides = {}) => ({
  local_id: `attempt-${index}`,
  index,
  status,
  request: {},
  response: {},
  usage: {},
  total_tokens: null,
  image_url: '',
  image_width: null,
  image_height: null,
  local_path: null,
  url_expired: false,
  created_at: '2026-08-13T10:00:00Z',
  updated_at: `2026-08-13T10:00:0${index}Z`,
  finished_at: null,
  elapsed_seconds: 0,
  error: null,
  ...overrides,
});

const batch = {
  local_id: 'batch-1',
  request: { prompt: 'hero', model: 'pro', resolution: '1K', ratio: '16:9', count: 4 },
  status: 'generating',
  sequence: '',
  attempts: [
    attempt(0, 'succeeded', {
      image_url: 'http://127.0.0.1:54321/seedream-media/batch-1/image/0',
      local_path: 'images/0.jpg',
      finished_at: '2026-08-13T10:00:03Z',
    }),
    attempt(1, 'generating'),
    attempt(2, 'downloading'),
    attempt(3, 'failed', { error: { code: 'FAILED', message: 'failed' } }),
  ],
  created_at: '2026-08-13T10:00:00Z',
  updated_at: '2026-08-13T10:00:03Z',
};

test('image current-generation panel shows every independent candidate state and selects a successful result', async () => {
  const html = await renderSfc('components/ai-creation/ImageCurrentGenerationPanel.vue', {
    route: '/ai-creation',
    props: { batch },
  });

  assert.match(html, /data-test="image-current-panel"/);
  assert.match(html, /data-test="image-current-attempt-0"/);
  assert.match(html, /data-test="image-current-attempt-1"/);
  assert.match(html, /data-test="image-current-attempt-2"/);
  assert.match(html, /data-test="image-current-attempt-3"/);
  assert.match(html, /aria-pressed="true"/);
  assert.match(html, /http:\/\/127\.0\.0\.1:54321\/seedream-media\/batch-1\/image\/0/);
  assert.match(html, /生成中/);
  assert.match(html, /下载中/);
  assert.match(html, /生成失败/);
  assert.match(html, /href="\/image-generation\/batches\/batch-1"/);
});

test('image current-generation panel stays expanded without a collapse control', async () => {
  const html = await renderSfc('components/ai-creation/ImageCurrentGenerationPanel.vue', {
    route: '/ai-creation',
    props: { batch },
  });

  assert.match(html, /data-test="image-current-summary"/);
  assert.match(html, /1\/4/);
  assert.match(html, /data-test="image-current-attempt-0"/);
  assert.match(html, /href="\/image-generation\/batches\/batch-1"/);
  assert.doesNotMatch(html, /data-test="image-current-panel-toggle"/);
});

test('workspace resolves the current image generation from the event-updated batch collection', async () => {
  const source = await readFile(
    new URL('../src/views/AICreationWorkspace.vue', import.meta.url),
    'utf8',
  );

  assert.match(source, /seedream\.batches\.find/);
  assert.match(source, /currentGeneration\?\.localId/);
  assert.match(source, /ImageCurrentGenerationPanel/);
});

test('image current-generation panel offers a close control', async () => {
  const html = await renderSfc('components/ai-creation/ImageCurrentGenerationPanel.vue', {
    route: '/ai-creation',
    props: { batch },
  });

  const button = html.match(/<button[^>]*data-test="image-current-close"[^>]*>/)?.[0] ?? '';
  assert.ok(button, 'close button should render');
  assert.match(button, /aria-label="关闭当前任务"/);
});

test('closing the current generation restores the single-column prompt layout', async () => {
  const [workspaceSource, storeSource] = await Promise.all([
    readFile(new URL('../src/views/AICreationWorkspace.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/stores/aiCreation.ts', import.meta.url), 'utf8'),
  ]);

  assert.match(workspaceSource, /@close="dismissCurrentGeneration"/);
  const dismiss = workspaceSource.match(/function dismissCurrentGeneration\(\) \{[\s\S]*?\n\}/)?.[0] ?? '';
  assert.ok(dismiss, 'workspace dismiss handler should exist');
  assert.match(dismiss, /workspace\.dismissCurrentGeneration\(\)/);
  // Without a current generation the work area returns to one column, so the
  // prompt composer regains its original full-width style.
  assert.match(workspaceSource, /if \(!currentGenerationAvailable\.value\) return 'grid-cols-1';/);

  const storeDismiss = storeSource.match(/function dismissCurrentGeneration\(\) \{[\s\S]*?\n\}/)?.[0] ?? '';
  assert.ok(storeDismiss, 'store dismiss action should exist');
  assert.match(storeDismiss, /currentGeneration\.value = null/);
});

test('paid image confirmation stays in the workspace and opens the returned batch panel', async () => {
  const source = await readFile(
    new URL('../src/views/SeedreamCreate.vue', import.meta.url),
    'utf8',
  );
  const confirmSubmit = source.match(/async function confirmSubmit\(\) \{([\s\S]*?)\n\}/);

  assert.ok(confirmSubmit, 'confirmSubmit should exist');
  assert.match(confirmSubmit[0], /store\.createBatch\(request, source\)/);
  assert.match(confirmSubmit[0], /workspace\.setCurrentGeneration\(\{ kind: 'image', localId: batch\.local_id \}\)/);
  assert.doesNotMatch(confirmSubmit[0], /router\.push/);
  assert.doesNotMatch(confirmSubmit[0], /resetImageDraft|form\.prompt\s*=\s*['"]/);
});
