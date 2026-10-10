import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';

after(closeSfcRenderer);

const attemptFixture = (overrides = {}) => ({
  local_id: 'attempt-1',
  index: 0,
  status: 'succeeded',
  request: { prompt: 'A pixel art hero', model: 'pro', resolution: '1K', ratio: '16:9', count: 1 },
  response: { created: 0, data: [{ url: 'https://example.com/img.jpg' }] },
  usage: { total_tokens: 42, generated_images: 1 },
  total_tokens: 42,
  image_url: '/seedream-media/batch-1/image/0',
  local_path: 'images/0.jpg',
  url_expired: false,
  created_at: '2026-08-04T10:00:00Z',
  updated_at: '2026-08-04T10:02:00Z',
  finished_at: '2026-08-04T10:02:00Z',
  elapsed_seconds: 120,
  error: null,
  ...overrides,
});

const batchFixture = (overrides = {}) => ({
  local_id: 'batch-1',
  request: {
    prompt: 'A pixel art hero',
    model: 'pro',
    resolution: '1K',
    ratio: '16:9',
    count: 1,
  },
  status: 'completed',
  attempts: [attemptFixture()],
  created_at: '2026-08-04T10:00:00Z',
  updated_at: '2026-08-04T10:02:00Z',
  ...overrides,
});

const renderDetail = (batchOverrides = {}) =>
  renderSfc('views/SeedreamBatchDetail.vue', {
    route: '/image-generation/batches/batch-1',
    piniaState: {
      seedream: {
        batches: [],
        currentBatch: batchFixture(batchOverrides),
        settings: null,
        creatingBatch: false,
        loading: false,
        error: null,
      },
    },
  });

test('Seedream batch detail shows loading placeholder when attempt is generating', async () => {
  const html = await renderDetail({
    status: 'generating',
    attempts: [attemptFixture({
      status: 'generating',
      image_url: '',
      local_path: null,
      total_tokens: null,
    })],
  });
  assert.match(html, /data-test="seedream-loading-0"/);
  assert.match(html, /animate-spin/);
});

test('Seedream batch detail shows local image and total_tokens on success', async () => {
  const html = await renderDetail();
  assert.match(html, /data-test="seedream-attempt-0"/);
  assert.match(html, /data-test="seedream-image-0"/);
  assert.match(html, /seedream-media\/batch-1\/image\/0/);
  assert.match(html, /data-test="seedream-total-tokens-summary"/);
  assert.match(html, /42/);
  assert.match(html, /data-test="seedream-download"/);
  assert.match(html, /data-test="seedream-edit-image-0"/);
  assert.match(html, /data-test="seedream-detail-favorite-attempt-1"/);
  assert.match(html, /图片编辑/);
  assert.doesNotMatch(html, /seedream-open-eraser-0/);
  assert.doesNotMatch(html, /seedream-resize-character-0/);
});

test('Seedream batch detail places a back action above the framed preview stage', async () => {
  const html = await renderDetail();
  const backIndex = html.indexOf('data-test="seedream-detail-back"');
  const stageIndex = html.indexOf('data-test="seedream-detail-stage"');
  assert.ok(backIndex >= 0);
  assert.ok(stageIndex > backIndex);
  assert.match(html, /class="[^"]*ml-auto[^"]*w-fit[^"]*"[^>]*data-test="seedream-detail-back"/);
  assert.match(html, /bg-\[#252525\]/);
});

test('Seedream detail routes erasing, resize, and original restore through one image editor', async () => {
  const source = await import('node:fs/promises').then(({ readFile }) =>
    readFile(new URL('../src/views/SeedreamBatchDetail.vue', import.meta.url), 'utf8'));
  assert.match(source, /seedream-edit-image-/);
  assert.match(source, /resize-enabled/);
  assert.match(source, /external-restore-available/);
  assert.match(source, /:key="attemptImageUrl\(currentImageEditorAttempt\)"/);
  assert.match(source, /@restore="restoreOriginalFromEditor"/);
  assert.match(source, /@apply="applyImageEditor"/);
  assert.match(source, /store\.applyEraser/);
  assert.match(source, /store\.restoreCharacter/);
  assert.doesNotMatch(source, /store\.resizeCharacter/);
  assert.doesNotMatch(source, /seedream-restore-character-/);
});

test('Seedream eraser provides background fill, adjustable brush, and local undo history', async () => {
  const source = await import('node:fs/promises').then(({ readFile }) =>
    readFile(new URL('../src/components/seedream/SeedreamImageEraser.vue', import.meta.url), 'utf8'));
  assert.match(source, /HISTORY_LIMIT = 20/);
  assert.match(source, /:min="5"/);
  assert.match(source, /:max="200"/);
  assert.match(source, /seedream-eraser-undo/);
  assert.match(source, /seedream-eraser-redo/);
  assert.match(source, /cropImageData/);
  assert.match(source, /sampleCornerColor/);
  assert.match(source, /context\.strokeStyle = backgroundCss\.value/);
  assert.match(source, /@wheel\.prevent="zoomCanvas"/);
  assert.match(source, /event\.button !== 1/);
  assert.match(source, /setPointerCapture/);
  assert.match(source, /MIN_ZOOM = 0\.25/);
  assert.match(source, /MAX_ZOOM = 8/);
  assert.match(source, /image-editor-top-guide/);
  assert.match(source, /image-editor-bottom-guide/);
  assert.match(source, /function applyResize\(\)/);
  assert.match(source, /editSourceCanvas/);
  assert.match(source, /function renderFromSource\(\)/);
  assert.match(source, /targetBottom - layout\.measured_bottom \* layout\.scale/);
  assert.match(source, /targetHeight \/ sourceMeasuredHeight\.value/);
  const startStroke = source.slice(source.indexOf('function startStroke'), source.indexOf('function moveStroke'));
  assert.match(startStroke, /setPointerCapture[\s\S]*drawing\.value = true[\s\S]*displayToSourcePoint[\s\S]*if \(!point\) return/);
  const moveStroke = source.slice(source.indexOf('function moveStroke'), source.indexOf('function finishStroke'));
  assert.match(moveStroke, /if \(!point\) \{[\s\S]*lastPoint = null[\s\S]*else drawPoint/);
  assert.doesNotMatch(source, /image-editor-resize-toggle/);
  assert.match(source, /data-test="image-editor-resize-controls"/);
  assert.match(source, /image-editor-measured-height-px/);
  assert.doesNotMatch(source, /seedream\.detail\.eraserHint/);
  assert.doesNotMatch(source, /seedream\.detail\.eraserHistoryHint/);
  assert.match(source, /data-test="image-editor-restore-original"/);
  assert.match(source, /bg-success/);
  assert.match(source, /function restoreOriginal\(\)/);
  assert.match(source, /emit\('cancel'\)[\s\S]*image-editor-restore-original[\s\S]*seedream-eraser-apply/);
  assert.doesNotMatch(source, /CHARACTER_HEIGHT_PRESETS|image-editor-height-preset-/);
  assert.match(source, /resizeTargetRatio = ref<number \| null>\(null\)/);
  assert.match(source, /resizeBottomMarginRatio = ref<number \| null>\(null\)/);
  assert.match(source, /data-test="image-editor-original-resolution"/);
  assert.match(source, /const guideMeasuredHeight = computed\(\(\) => Math\.max\(0, resizeBottom\.value - resizeTop\.value\)\)/);
  const setGuide = source.slice(source.indexOf('function setGuide'), source.indexOf('function displayToSourceY'));
  assert.doesNotMatch(setGuide, /resizeBottomMarginRatio\.value\s*=/);
  const canApplyResize = source.slice(source.indexOf('const canApplyResize'), source.indexOf('onMounted(() =>'));
  assert.match(canApplyResize, /sourceResizeTop\.value !== \(currentGenerationLayout\.value\?\.measured_top/);
  assert.match(canApplyResize, /sourceResizeBottom\.value !== \(currentGenerationLayout\.value\?\.measured_bottom/);
  assert.match(source, /normalizeResizeRatios\(saved\.character_height_ratio \* 100, saved\.bottom_margin_ratio \* 100\)/);
  assert.match(source, /const estimatedVideoHeights = computed/);
  assert.match(source, /v-if="targetHeightPixels > 0"/);
  assert.match(source, /\[480, 720, 1080\]/);
  assert.match(source, /Math\.round\(videoHeight \* targetHeightPixels\.value \/ imageHeight\.value\)/);
  assert.match(source, /character_height_ratio: targetHeight \/ canvas\.height/);
  assert.match(source, /bottom_margin_ratio: bottomDistance \/ canvas\.height/);
});

test('restoring the original refreshes the open image editor instead of closing it', async () => {
  const source = await import('node:fs/promises').then(({ readFile }) =>
    readFile(new URL('../src/views/SeedreamBatchDetail.vue', import.meta.url), 'utf8'));
  const restoreHandler = source.match(/async function restoreOriginalFromEditor[\s\S]*?\n}\n\nfunction attemptLoadingMessage/)?.[0] ?? '';
  assert.match(restoreHandler, /generation_layout = null/);
  assert.match(restoreHandler, /imageRevisions\.value\[attemptIndex\] = Date\.now\(\)/);
  assert.doesNotMatch(restoreHandler, /imageEditorAttemptIndex\.value = null/);
});

test('saving an edited image keeps its layout available for the next editor open', async () => {
  const source = await import('node:fs/promises').then(({ readFile }) =>
    readFile(new URL('../src/views/SeedreamBatchDetail.vue', import.meta.url), 'utf8'));
  const applyHandler = source.match(/async function applyImageEditor[\s\S]*?\n}\n\nasync function restoreOriginalFromEditor/)?.[0] ?? '';
  assert.match(applyHandler, /const result = await store\.applyEraser/);
  assert.match(applyHandler, /currentImageEditorAttempt\.value\.generation_layout = result\.generation_layout/);
  assert.match(applyHandler, /imageEditorAttemptIndex\.value = null/);
  const editorSource = await import('node:fs/promises').then(({ readFile }) =>
    readFile(new URL('../src/components/seedream/SeedreamImageEraser.vue', import.meta.url), 'utf8'));
  assert.match(editorSource, /normalizeResizeRatios\(saved\.character_height_ratio \* 100, saved\.bottom_margin_ratio \* 100\)/);
  assert.match(editorSource, /resizeTop\.value = height - saved\.bottom_distance - saved\.target_height/);
  assert.match(editorSource, /resizeBottom\.value = height - saved\.bottom_distance/);
});

test('Seedream batch detail shows API unavailable when total_tokens is missing', async () => {
  const html = await renderDetail({
    attempts: [attemptFixture({
      total_tokens: null,
      usage: { generated_images: 1 },
    })],
  });
  assert.match(html, /data-test="seedream-total-tokens-summary"/);
  assert.match(html, /API 未返回/);
});

test('Seedream batch detail shows failed state with error message', async () => {
  const html = await renderDetail({
    status: 'failed',
    attempts: [attemptFixture({
      status: 'failed',
      image_url: '',
      local_path: null,
      error: { code: 'RATE_LIMIT', message: 'rate limited', status: 429 },
    })],
  });
  assert.match(html, /data-test="seedream-failed-0"/);
  assert.match(html, /rate limited/);
});

test('Seedream batch detail displays batch configuration', async () => {
  const html = await renderDetail();
  assert.match(html, /A pixel art hero/);
  assert.match(html, /1K/);
  assert.match(html, /16:9/);
  assert.match(html, /Seedream 5\.0 Pro/);
});

test('Seedream batch detail shows aggregated batch status badge', async () => {
  const html = await renderDetail();
  assert.match(html, /data-test="seedream-batch-status"/);
});

test('Seedream batch detail shows multiple attempts independently', async () => {
  const html = await renderDetail({
    status: 'partially_complete',
    request: { prompt: 'hero', model: 'pro', resolution: '1K', ratio: '16:9', count: 2 },
    attempts: [
      attemptFixture({ index: 0, local_id: 'a-0', image_url: '/seedream-media/batch-1/image/0' }),
      attemptFixture({
        index: 1,
        local_id: 'a-1',
        status: 'failed',
        image_url: '',
        local_path: null,
        error: { code: 'RATE_LIMIT', message: 'rate limited', status: 429 },
      }),
    ],
  });
  // First attempt succeeded.
  assert.match(html, /data-test="seedream-image-0"/);
  // Second attempt failed.
  assert.match(html, /data-test="seedream-failed-1"/);
  assert.match(html, /rate limited/);
});

test('Seedream batch detail shows count from attempts length', async () => {
  const html = await renderDetail({
    request: { prompt: 'hero', model: 'pro', resolution: '1K', ratio: '16:9', count: 3 },
    attempts: [
      attemptFixture({ index: 0, local_id: 'a-0' }),
      attemptFixture({ index: 1, local_id: 'a-1', status: 'generating', image_url: '', local_path: null, total_tokens: null }),
      attemptFixture({ index: 2, local_id: 'a-2', status: 'generating', image_url: '', local_path: null, total_tokens: null }),
    ],
  });
  assert.match(html, /data-test="seedream-loading-1"/);
  assert.match(html, /data-test="seedream-loading-2"/);
});

test('Seedream batch detail shows create video button for succeeded candidate image', async () => {
  const html = await renderDetail();
  assert.match(html, /data-test="seedream-create-video"/);
  assert.match(html, /创建视频/);
});

test('Seedream batch detail renders one main image with selectable thumbnails for multiple results', async () => {
  const html = await renderDetail({
    request: { prompt: 'hero', model: 'pro', resolution: '1K', ratio: '16:9', count: 2 },
    attempts: [
      attemptFixture({ index: 0, local_id: 'a-0' }),
      attemptFixture({ index: 1, local_id: 'a-1', image_url: '/seedream-media/batch-1/image/1' }),
    ],
  });
  assert.match(html, /data-test="seedream-image-0"/);
  assert.doesNotMatch(html, /data-test="seedream-image-1"/);
  assert.match(html, /data-test="seedream-image-thumbnails"/);
  assert.match(html, /data-test="seedream-thumbnail-0"/);
  assert.match(html, /data-test="seedream-thumbnail-1"/);
  assert.match(html, /seedream-edit-image-0/);
});

test('Seedream batch detail uses the selected image for video creation and editing', async () => {
  const source = await import('node:fs/promises').then(({ readFile }) =>
    readFile(new URL('../src/views/SeedreamBatchDetail.vue', import.meta.url), 'utf8'));
  assert.match(source, /@click="createVideo\(selectedSucceededAttempt\.index\)"/);
  assert.match(source, /@click="openImageEditor\(selectedSucceededAttempt\.index\)"/);
  assert.match(source, /function selectSucceededAttempt\(attemptIndex: number\)/);
});

test('Seedream batch detail hides create video button for generating attempt', async () => {
  const html = await renderDetail({
    status: 'generating',
    attempts: [attemptFixture({
      status: 'generating',
      image_url: '',
      local_path: null,
      total_tokens: null,
    })],
  });
  assert.doesNotMatch(html, /seedream-create-video/);
});

test('Seedream batch detail hides create video button for failed attempt', async () => {
  const html = await renderDetail({
    status: 'failed',
    attempts: [attemptFixture({
      status: 'failed',
      image_url: '',
      local_path: null,
      error: { code: 'RATE_LIMIT', message: 'rate limited', status: 429 },
    })],
  });
  assert.doesNotMatch(html, /seedream-create-video/);
});

test('Seedream batch detail shows unknown state with may-have-been-billed hint', async () => {
  const html = await renderDetail({
    status: 'unknown',
    attempts: [attemptFixture({
      status: 'unknown',
      image_url: '',
      local_path: null,
      error: { code: 'SUBMISSION_UNKNOWN', message: 'outcome is unknown' },
    })],
  });
  assert.match(html, /data-test="seedream-unknown-0"/);
  assert.match(html, /data-test="seedream-unknown-hint"/);
  // unknownHint key already exists in locale: '此请求结果无法确定，可能已经计费。'
  assert.match(html, /可能已经计费/);
});

test('Seedream batch detail shows 429 rate limit hint for rate-limited failure', async () => {
  const html = await renderDetail({
    status: 'failed',
    attempts: [attemptFixture({
      status: 'failed',
      image_url: '',
      local_path: null,
      error: { code: 'RATE_LIMIT', message: 'rate limited', status: 429 },
    })],
  });
  assert.match(html, /data-test="seedream-failed-0"/);
  assert.match(html, /data-test="seedream-rate-limit-hint"/);
});

test('Seedream batch detail shows download_failed state with retry download button', async () => {
  const html = await renderDetail({
    status: 'failed',
    attempts: [attemptFixture({
      status: 'download_failed',
      image_url: '',
      local_path: null,
      url_expired: false,
      error: { code: 'OSError', message: 'download network error' },
    })],
  });
  assert.match(html, /data-test="seedream-download-failed-0"/);
  assert.match(html, /data-test="seedream-retry-download-0"/);
});

test('Seedream batch detail shows URL expired message when url_expired is true', async () => {
  const html = await renderDetail({
    status: 'failed',
    attempts: [attemptFixture({
      status: 'download_failed',
      image_url: '',
      local_path: null,
      url_expired: true,
      error: { code: 'OSError', message: 'download failed' },
    })],
  });
  assert.match(html, /data-test="seedream-download-failed-0"/);
  assert.match(html, /data-test="seedream-url-expired"/);
  assert.doesNotMatch(html, /seedream-retry-download/);
});

test('Seedream batch detail does not show rate limit hint for non-429 failure', async () => {
  const html = await renderDetail({
    status: 'failed',
    attempts: [attemptFixture({
      status: 'failed',
      image_url: '',
      local_path: null,
      error: { code: 'INTERNAL', message: 'server error', status: 500 },
    })],
  });
  assert.match(html, /data-test="seedream-failed-0"/);
  assert.doesNotMatch(html, /seedream-rate-limit-hint/);
});

// ---------------------------------------------------------------------------
// Issue #7: Regenerate, safe delete, actual dimensions
// ---------------------------------------------------------------------------

test('Seedream batch detail shows regenerate button for completed batch', async () => {
  const html = await renderDetail({ status: 'completed' });
  assert.match(html, /data-test="seedream-regenerate"/);
  assert.match(html, /再次生成/);
});

test('Seedream batch detail shows regenerate button for partially_complete batch', async () => {
  const html = await renderDetail({
    status: 'partially_complete',
    attempts: [
      attemptFixture({ index: 0, local_id: 'a-0' }),
      attemptFixture({ index: 1, local_id: 'a-1', status: 'failed', image_url: '', local_path: null, error: { code: 'RATE_LIMIT', message: 'rate limited', status: 429 } }),
    ],
  });
  assert.match(html, /data-test="seedream-regenerate"/);
});

test('Seedream batch detail hides regenerate button while generating', async () => {
  const html = await renderDetail({
    status: 'generating',
    attempts: [attemptFixture({ status: 'generating', image_url: '', local_path: null, total_tokens: null })],
  });
  assert.doesNotMatch(html, /seedream-regenerate/);
});

test('Seedream batch detail shows delete button disabled while generating', async () => {
  const html = await renderDetail({
    status: 'generating',
    attempts: [attemptFixture({ status: 'generating', image_url: '', local_path: null, total_tokens: null })],
  });
  assert.match(html, /data-test="seedream-delete"/);
  // The HTML disabled attribute (space-delimited, not the CSS class disabled:opacity-50).
  assert.match(html, / disabled [^>]*data-test="seedream-delete"/);
});

test('Seedream batch detail shows delete button enabled for terminal batch', async () => {
  const html = await renderDetail({ status: 'completed' });
  assert.match(html, /data-test="seedream-delete"/);
  // The button should NOT have the HTML disabled attribute (CSS classes disabled:opacity-50 are fine).
  assert.doesNotMatch(html, / disabled [^>]*data-test="seedream-delete"/);
});

test('Seedream batch detail shows actual image dimensions for succeeded attempt', async () => {
  const html = await renderDetail({
    attempts: [attemptFixture({ image_width: 1024, image_height: 576 })],
  });
  assert.match(html, /data-test="seedream-dimensions-0"/);
  assert.match(html, /1024/);
  assert.match(html, /576/);
});

test('Seedream batch detail hides dimensions when not available', async () => {
  const html = await renderDetail({
    attempts: [attemptFixture({ image_width: null, image_height: null })],
  });
  assert.doesNotMatch(html, /seedream-dimensions-0/);
});

test('batch detail shows the reference image thumbnail when the batch has one', async () => {
  const html = await renderDetail({ reference_image_url: '/seedream-media/batch-1/reference' });
  assert.match(html, /data-test="seedream-reference-thumbnail"/);
  assert.match(html, /src="\/seedream-media\/batch-1\/reference"/);
  assert.match(html, /参考图/);
});

test('batch detail omits the reference thumbnail for plain text-to-image batches', async () => {
  const html = await renderDetail();
  assert.doesNotMatch(html, /data-test="seedream-reference-thumbnail"/);
});
