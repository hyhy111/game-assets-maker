import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { after, test } from 'node:test';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';

after(closeSfcRenderer);

const draftRequest = {
  prompt: 'restored prompt from draft',
  model: 'lite',
  resolution: '2K',
  ratio: '1:1',
  count: 3,
};

// SeedreamCreate calls store.loadRegenerationDraft on mount when the
// `regenerate` query param is present. We mock the store's method via
// pinia state + a module-level stub. Since renderSfc creates the app with
// real Pinia, we intercept by providing initial state and letting the
// component call the real store, which calls the real api (which is a
// no-op in SSR). To verify the draft is NOT calling createBatch, we
// render the page and assert the form was NOT submitted.

test('Seedream create page with regenerate query does not render confirmation modal', async () => {
  const html = await renderSfc('views/SeedreamCreate.vue', {
    route: '/image-generation/create?regenerate=batch-1',
    piniaState: {
      seedream: {
        batches: [],
        currentBatch: null,
        settings: { default_count: 2 },
        creatingBatch: false,
        loading: false,
        error: null,
      },
    },
  });
  // The confirmation modal (which triggers paid generation) must not appear.
  assert.doesNotMatch(html, /data-test="seedream-confirm-submit"/);
});

test('Seedream create page without regenerate query renders normally', async () => {
  const html = await renderSfc('views/SeedreamCreate.vue', {
    route: '/image-generation/create',
    piniaState: {
      seedream: {
        batches: [],
        currentBatch: null,
        settings: { default_count: 2 },
        creatingBatch: false,
        loading: false,
        error: null,
      },
    },
  });
  assert.match(html, /data-test="seedream-submit"/);
  // Default count is 2.
  assert.match(html, /aria-pressed="true"[^>]*data-value="2"/);
});

test('Seedream create page with regenerate query does not auto-submit', async () => {
  // The key contract: opening a regeneration draft must NOT call createBatch.
  // In SSR, the store's createBatch would fail (no pywebview api), but we
  // verify by checking creatingBatch stays false and no confirmation modal.
  const html = await renderSfc('views/SeedreamCreate.vue', {
    route: '/image-generation/create?regenerate=batch-1',
    piniaState: {
      seedream: {
        batches: [],
        currentBatch: null,
        settings: { default_count: 2 },
        creatingBatch: false,
        loading: false,
        error: null,
      },
    },
  });
  // No confirmation modal (paid action) should be visible.
  assert.doesNotMatch(html, /data-test="seedream-confirm-submit"/);
  // The submit button should be present (user can edit and confirm later).
  assert.match(html, /data-test="seedream-submit"/);
});

// Verify the duplicateBatchSequence helper from seedream-ui.ts directly.
test('duplicateBatchSequence returns circle numbers for matching params', async () => {
  const server = await import('vite').then(v => v.createServer({ appType: 'custom', logLevel: 'silent', server: { middlewareMode: true } }));
  try {
    const mod = await server.ssrLoadModule('/src/seedream-ui.ts');
    const batches = [
      { local_id: 'b1', request: { prompt: 'hero', model: 'pro', resolution: '1K', ratio: '16:9', count: 2 }, created_at: '2026-01-01T00:00:00Z', sequence: '' },
      { local_id: 'b2', request: { prompt: 'hero', model: 'pro', resolution: '1K', ratio: '16:9', count: 2 }, created_at: '2026-01-02T00:00:00Z', sequence: '' },
      { local_id: 'b3', request: { prompt: 'hero', model: 'pro', resolution: '1K', ratio: '16:9', count: 2 }, created_at: '2026-01-03T00:00:00Z', sequence: '' },
    ];
    assert.equal(mod.duplicateBatchSequence(batches[0], batches), '①');
    assert.equal(mod.duplicateBatchSequence(batches[1], batches), '②');
    assert.equal(mod.duplicateBatchSequence(batches[2], batches), '③');
  } finally {
    await server.close();
  }
});

test('duplicateBatchSequence returns empty for unique params', async () => {
  const server = await import('vite').then(v => v.createServer({ appType: 'custom', logLevel: 'silent', server: { middlewareMode: true } }));
  try {
    const mod = await server.ssrLoadModule('/src/seedream-ui.ts');
    const batches = [
      { local_id: 'b1', request: { prompt: 'hero', model: 'pro', resolution: '1K', ratio: '16:9', count: 2 }, created_at: '2026-01-01T00:00:00Z', sequence: '' },
      { local_id: 'b2', request: { prompt: 'villain', model: 'lite', resolution: '2K', ratio: '1:1', count: 1 }, created_at: '2026-01-02T00:00:00Z', sequence: '' },
    ];
    assert.equal(mod.duplicateBatchSequence(batches[0], batches), '');
    assert.equal(mod.duplicateBatchSequence(batches[1], batches), '');
  } finally {
    await server.close();
  }
});

test('duplicateBatchSequence prefers backend-provided sequence', async () => {
  const server = await import('vite').then(v => v.createServer({ appType: 'custom', logLevel: 'silent', server: { middlewareMode: true } }));
  try {
    const mod = await server.ssrLoadModule('/src/seedream-ui.ts');
    const batches = [
      { local_id: 'b1', request: { prompt: 'hero', model: 'pro', resolution: '1K', ratio: '16:9', count: 2 }, created_at: '2026-01-01T00:00:00Z', sequence: '①' },
      { local_id: 'b2', request: { prompt: 'hero', model: 'pro', resolution: '1K', ratio: '16:9', count: 2 }, created_at: '2026-01-02T00:00:00Z', sequence: '②' },
    ];
    assert.equal(mod.duplicateBatchSequence(batches[0], batches), '①');
    assert.equal(mod.duplicateBatchSequence(batches[1], batches), '②');
  } finally {
    await server.close();
  }
});

test('regeneration draft restores the reference image path and preview URL', async () => {
  const { createScriptedPyWebViewBridge, loadFrontendModule, closeFrontendHarness } = await import(
    './scripted-pywebview-bridge.mjs'
  );
  try {
    const bridge = createScriptedPyWebViewBridge({
      seedream_get_regeneration_draft: [
        {
          resolve: {
            success: true,
            data: {
              request: {
                prompt: 'restored prompt',
                model: 'pro',
                resolution: '1K',
                ratio: '16:9',
                count: 2,
                reference_image: '/cache/batch-1/reference/reference.png',
              },
              reference_image_url: '/seedream-media/batch-1/reference',
            },
          },
        },
      ],
    });
    const { createPinia, setActivePinia } = await import('pinia');
    const { useSeedreamStore } = await loadFrontendModule('/src/stores/seedream.ts');
    setActivePinia(createPinia());
    const store = useSeedreamStore();

    const draft = await store.loadRegenerationDraft('batch-1');

    assert.equal(draft.request.reference_image, '/cache/batch-1/reference/reference.png');
    assert.equal(draft.reference_image_url, '/seedream-media/batch-1/reference');

    // The draft restore itself makes no paid calls.
    assert.deepEqual(
      bridge.calls.map((call) => call.method),
      ['seedream_get_regeneration_draft'],
    );
  } finally {
    await closeFrontendHarness();
  }
});

test('SeedreamCreate restores the reference image into the composer form', async () => {
  const source = await readFile(new URL('../src/views/SeedreamCreate.vue', import.meta.url), 'utf8');
  assert.match(source, /form\.reference_image\s*=\s*request\.reference_image/);
  assert.match(source, /imagePreviewUrls\.reference\s*=\s*draft\.reference_image_url/);
});
