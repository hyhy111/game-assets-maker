import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { after, test } from 'node:test';
import { createPinia, setActivePinia } from 'pinia';
import { closeFrontendHarness, loadFrontendModule } from './scripted-pywebview-bridge.mjs';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';

after(async () => {
  await closeSfcRenderer();
  await closeFrontendHarness();
});

const source = (path) => readFile(new URL(`../src/${path}`, import.meta.url), 'utf8');

const attempt = (index, status = 'succeeded') => ({
  local_id: `attempt-${index}`,
  index,
  status,
  request: {},
  response: {},
  usage: {},
  total_tokens: null,
  image_url: status === 'succeeded' ? `/seedream-media/batch/image/${index}` : '',
  image_width: 1024,
  image_height: 576,
  local_path: status === 'succeeded' ? `images/${index}.jpg` : null,
  url_expired: false,
  created_at: '2026-08-13T10:00:00Z',
  updated_at: '2026-08-13T10:00:42Z',
  finished_at: status === 'generating' ? null : '2026-08-13T10:00:42Z',
  elapsed_seconds: 42,
  error: null,
});

const batch = (index, overrides = {}) => ({
  local_id: `batch-${index}`,
  request: { prompt: 'hero', model: 'pro', resolution: '1K', ratio: '16:9', count: 2 },
  status: 'completed',
  sequence: '',
  attempts: [attempt(0), attempt(1)],
  created_at: `2026-08-13T${String(index).padStart(2, '0')}:00:00Z`,
  updated_at: `2026-08-13T${String(index).padStart(2, '0')}:00:42Z`,
  ...overrides,
});

const task = (index, overrides = {}) => ({
  local_id: `task-${index}`,
  remote_id: `remote-${index}`,
  remote_status: 'succeeded',
  sync_status: {},
  download_status: 'downloaded',
  cache_status: 'complete',
  protected: false,
  request: {
    prompt: 'move', model: 'standard', resolution: '720p', ratio: '16:9', duration: 4,
    generate_audio: false, return_last_frame: false, priority: 0, execution_expires_after: 3600,
  },
  input_urls: {},
  output_urls: { thumbnail: `/seedance-media/task-${index}/thumbnail` },
  created_at: `2026-08-13T${String(index).padStart(2, '0')}:00:00Z`,
  updated_at: `2026-08-13T${String(index).padStart(2, '0')}:01:05Z`,
  finished_at: `2026-08-13T${String(index).padStart(2, '0')}:01:05Z`,
  elapsed_seconds: 65,
  remote: {}, error: null, retry_of: null, handoffs: [],
  ...overrides,
});

const uniqueBatch = (index) => batch(index, {
  request: { prompt: `hero-${index}`, model: 'pro', resolution: '1K', ratio: '16:9', count: 2 },
});

const uniqueTask = (index) => task(index, {
  request: {
    prompt: `move-${index}`, model: 'standard', resolution: '720p', ratio: '16:9', duration: 4,
    generate_audio: false, return_last_frame: false, priority: 0, execution_expires_after: 3600,
  },
});

const renderRecent = ({ batches = [], tasks = [], workspace = {} } = {}) => renderSfc(
  'components/ai-creation/RecentGenerations.vue',
  {
    route: '/ai-creation',
    piniaState: {
      'ai-creation': {
        activeMode: 'image',
        recentFilter: 'image',
        recentLoaded: { image: 12, video: 12 },
        ...workspace,
      },
      seedream: { batches, loading: false, error: null },
      seedance: { tasks, loading: false, error: null },
    },
  },
);

test('recent generations defaults to images and shows the newest twelve in a responsive four-column grid', async () => {
  const html = await renderRecent({ batches: Array.from({ length: 13 }, (_, index) => uniqueBatch(index)) });

  assert.match(html, /aria-pressed="true"[^>]*data-test="recent-filter-image"/);
  assert.match(html, /data-test="recent-image-batch-12"/);
  assert.match(html, /data-test="recent-image-batch-1"/);
  assert.doesNotMatch(html, /data-test="recent-image-batch-0"/);
  assert.match(html, /class="[^"]*grid-cols-1[^"]*md:grid-cols-2[^"]*xl:grid-cols-4" data-test="recent-generations-grid"/);
  assert.match(html, /data-test="recent-load-more"/);
});

test('image and video lists only show load more when they contain over twelve items', async () => {
  const [twelveImages, thirteenImages, twelveVideos, thirteenVideos] = await Promise.all([
    renderRecent({ batches: Array.from({ length: 12 }, (_, index) => uniqueBatch(index)) }),
    renderRecent({ batches: Array.from({ length: 13 }, (_, index) => uniqueBatch(index)) }),
    renderRecent({
      tasks: Array.from({ length: 12 }, (_, index) => uniqueTask(index)),
      workspace: { recentFilter: 'video' },
    }),
    renderRecent({
      tasks: Array.from({ length: 13 }, (_, index) => uniqueTask(index)),
      workspace: { recentFilter: 'video' },
    }),
  ]);

  assert.doesNotMatch(twelveImages, /data-test="recent-load-more"/);
  assert.match(thirteenImages, /data-test="recent-load-more"/);
  assert.doesNotMatch(twelveVideos, /data-test="recent-load-more"/);
  assert.match(thirteenVideos, /data-test="recent-load-more"/);
});

test('same normalized prompt is stacked with the newest task as its cover', async () => {
  const html = await renderRecent({
    batches: [
      batch(1, { request: { prompt: '  hero   attack ', model: 'pro', resolution: '1K', ratio: '16:9', count: 2 } }),
      batch(2, { request: { prompt: 'hero\nattack', model: 'pro', resolution: '1K', ratio: '16:9', count: 2 } }),
      batch(3, { request: { prompt: 'Hero attack', model: 'pro', resolution: '1K', ratio: '16:9', count: 2 } }),
    ],
  });

  assert.match(html, /data-test="recent-prompt-group-image-hero%20attack"/);
  assert.match(html, /data-test="recent-image-batch-2"/);
  assert.doesNotMatch(html, /data-test="recent-image-batch-1"/);
  assert.match(html, /data-test="recent-prompt-expand-image-hero%20attack"/);
  assert.match(html, /data-test="recent-media-favorite-image:batch-3:attempt-0"/);
  assert.doesNotMatch(html, /data-test="recent-media-favorite-image:batch-2:attempt-0"/);
  assert.match(html, /data-test="recent-prompt-group-image-Hero%20attack"/);
  assert.doesNotMatch(html, />hero attack</);
  assert.match(html, /data-test="recent-image-batch-2"[\s\S]*data-test="recent-prompt-expand-image-hero%20attack"/);
});

test('prompt group adds no separate summary card and renders all tasks only when expanded', async () => {
  const collapsed = await renderSfc('components/ai-creation/RecentPromptGroup.vue', {
    props: {
      groupId: 'image-hero', prompt: 'hidden prompt', count: 2, expanded: false,
    },
    slots: { default: () => 'latest task' },
  });
  const html = await renderSfc('components/ai-creation/RecentPromptGroup.vue', {
    props: {
      groupId: 'image-hero', prompt: 'hero', count: 2, expanded: true,
    },
    slots: {
      default: () => 'latest task',
      expanded: () => ['task one', 'task two'],
    },
  });

  assert.doesNotMatch(collapsed, /hidden prompt/);
  assert.match(collapsed, /bg-\[#242424\]/);
  assert.doesNotMatch(collapsed, /bg-\[#181b24\]/);
  assert.match(html, /data-test="recent-prompt-expanded-image-hero"/);
  assert.match(html, /class="[^"]*fixed inset-0[^"]*bg-black\/75/);
  assert.match(html, /role="dialog" aria-modal="true"/);
  assert.doesNotMatch(html, /这条提示词的 2 个任务/);
  assert.match(html, />hero</);
  assert.match(html, /task one/);
  assert.match(html, /task two/);
});

test('prompt grouping preserves case while normalizing surrounding and repeated whitespace', async () => {
  const { groupRecentByPrompt, listRecentIndividually } = await loadFrontendModule('/src/recent-prompt-groups.ts');
  const items = [
    { local_id: 'old', created_at: '2026-08-13T10:00:00Z', request: { prompt: ' hero   attack ' } },
    { local_id: 'new', created_at: '2026-08-13T12:00:00Z', request: { prompt: 'hero\nattack' } },
    { local_id: 'case', created_at: '2026-08-13T11:00:00Z', request: { prompt: 'Hero attack' } },
  ];
  const grouped = groupRecentByPrompt([
    ...items,
  ]);

  assert.deepEqual(grouped.map((group) => ({
    key: group.key,
    ids: group.items.map((item) => item.local_id),
  })), [
    { key: 'hero attack', ids: ['new', 'old'] },
    { key: 'Hero attack', ids: ['case'] },
  ]);
  assert.deepEqual(listRecentIndividually(items).map((group) => ({
    key: group.key,
    ids: group.items.map((item) => item.local_id),
  })), [
    { key: '__item__:new', ids: ['new'] },
    { key: '__item__:case', ids: ['case'] },
    { key: '__item__:old', ids: ['old'] },
  ]);
});

test('favorites belong to individual media and stacked covers do not show a favorite button', async () => {
  const [singleImage, stackedImages, singleVideo, recentSource, imageCardSource] = await Promise.all([
    renderRecent({ batches: [batch(1)] }),
    renderRecent({ batches: [batch(1), batch(2)] }),
    renderRecent({ tasks: [task(1)], workspace: { recentFilter: 'video' } }),
    source('components/ai-creation/RecentGenerations.vue'),
    source('components/ai-creation/RecentImageGenerationCard.vue'),
  ]);

  assert.match(singleImage, /data-test="recent-media-favorite-image:batch-1:attempt-0"/);
  assert.doesNotMatch(stackedImages, /data-test="recent-media-favorite-/);
  assert.match(singleVideo, /data-test="recent-media-favorite-video:task-1"/);
  assert.match(imageCardSource, /<slot name="top-right" :attempt="selectedAttempt"/);
  assert.match(recentSource, /imageMediaKey\(group\.items\[0\]\.local_id, attempt\.local_id\)/);
  assert.match(recentSource, /useRecentMediaFavorites\(\)/);
  assert.doesNotMatch(recentSource, /recent-prompt-favorites|favoritePromptKeys/);
});

test('same-prompt stacking can be switched off and the preference is persisted', async () => {
  const recent = await source('components/ai-creation/RecentGenerations.vue');

  assert.match(recent, /<Switch\s+v-model="stackSamePrompts"/);
  assert.match(recent, /stackSamePrompts\.value\s*\?\s*groupRecentByPrompt\(seedream\.batches\)\s*:\s*listRecentIndividually\(seedream\.batches\)/s);
  assert.match(recent, /const STACK_STORAGE_KEY = 'gam:stack-same-prompts'/);
  assert.match(recent, /localStorage\.setItem\(STACK_STORAGE_KEY, String\(enabled\)\)/);
});

test('video cards loop through at most 20 sampled frames from the first 80 frames on hover', async () => {
  const card = await source('components/ai-creation/RecentVideoGenerationCard.vue');

  assert.match(card, /const SOURCE_FRAME_INTERVAL = 4;/);
  assert.match(card, /const SOURCE_FRAME_LIMIT = 80;/);
  assert.match(card, /const PREVIEW_FRAME_LIMIT = 20;/);
  assert.match(card, /previewFrameIndex = \(previewFrameIndex \+ 1\) % previewFrameCount;/);
  assert.match(card, /const targetFrame = previewFrameIndex \* SOURCE_FRAME_INTERVAL;/);
  assert.match(card, /@mouseenter="startPreview"/);
  assert.match(card, /@mouseleave="stopPreview"/);
  assert.match(card, /onBeforeUnmount\(stopPreview\);/);
});

test('video filter is independent from creation mode and renders video metadata', async () => {
  const html = await renderRecent({
    tasks: [task(1)],
    workspace: { activeMode: 'image', recentFilter: 'video' },
  });

  assert.match(html, /aria-pressed="true"[^>]*data-test="recent-filter-video"/);
  assert.match(html, /data-test="recent-video-task-1"/);
  assert.match(html, /720p/);
  assert.match(html, /16:9/);
  assert.match(html, />4s</);
  assert.match(html, /01:05/);
});

test('video metadata chips stay on one row without shrinking their font', async () => {
  const [card, zhLocale, enLocale] = await Promise.all([
    source('components/ai-creation/RecentVideoGenerationCard.vue'),
    source('locales/zh-CN.ts'),
    source('locales/en.ts'),
  ]);

  assert.match(card, /flex-nowrap[^"\n]*overflow-hidden[^"\n]*whitespace-nowrap[^"\n]*text-xs/);
  assert.doesNotMatch(card, /container-type|cqw|text-\[clamp/);
  assert.match(zhLocale, /models: \{ standard: 'Seedance2\.0', fast: 'Seedance2\.0 Fast', mini: 'Seedance2\.0 Mini' \}/);
  assert.match(enLocale, /models: \{ standard: 'Seedance2\.0', fast: 'Seedance2\.0 Fast', mini: 'Seedance2\.0 Mini' \}/);
  assert.doesNotMatch(card, /flex flex-wrap gap-1\.5 text-xs text-gray-400/);
});

test('active cards show generating instead of elapsed time and terminal image batches show one total elapsed time', async () => {
  const activeHtml = await renderRecent({
    batches: [batch(1, { status: 'generating', attempts: [attempt(0), attempt(1, 'generating')] })],
  });
  assert.match(activeHtml, /生成中/);
  assert.doesNotMatch(activeHtml, /00:42/);

  const terminalHtml = await renderRecent({ batches: [batch(1)] });
  assert.match(terminalHtml, /创建时间/);
  assert.match(terminalHtml, /总耗时/);
  assert.match(terminalHtml, /00:42/);
  assert.doesNotMatch(terminalHtml, /2\/2/);
});

test('recent generation cards right-align total elapsed metadata', async () => {
  const [imageCard, videoCard] = await Promise.all([
    source('components/ai-creation/RecentImageGenerationCard.vue'),
    source('components/ai-creation/RecentVideoGenerationCard.vue'),
  ]);

  assert.match(imageCard, /<div class="text-right">\s*<dt class="text-gray-500">\{\{ t\('aiCreation\.recent\.elapsed'\) \}\}/s);
  assert.match(videoCard, /<div class="text-right">\s*<dt class="text-gray-500">\{\{ t\('aiCreation\.recent\.elapsed'\) \}\}/s);
});

test('active recent video cards use white status text over the preview', async () => {
  const videoCard = await source('components/ai-creation/RecentVideoGenerationCard.vue');

  assert.match(videoCard, /if \(active\.value\) return 'bg-primary\/20 text-white'/);
});

test('image task cards use one main preview with a selectable thumbnail strip', async () => {
  const html = await renderRecent({
    batches: [batch(1, { attempts: [attempt(0), attempt(1), attempt(2)] })],
  });

  assert.match(html, /data-test="recent-image-main-preview"/);
  assert.match(html, /data-test="recent-image-thumbnails"/);
  assert.match(html, /data-test="recent-image-thumbnail-0"/);
  assert.match(html, /data-test="recent-image-thumbnail-1"/);
  assert.match(html, /data-test="recent-image-thumbnail-2"/);
  assert.match(html, /draggable="true"/);
  assert.match(html, /拖到视频生成的首帧或尾帧/);
  assert.match(html, /aria-pressed="true"[^>]*data-test="recent-image-thumbnail-0"/);
  assert.doesNotMatch(html, /3\/3/);
  assert.doesNotMatch(html, /gridTemplateRows|thumbnailGridStyle|thumbnailItemClass/);
});

test('image previews fill the card top edge like video previews', async () => {
  const card = await source('components/ai-creation/RecentImageGenerationCard.vue');

  assert.match(card, /class="group\/preview relative block aspect-video w-full overflow-hidden bg-black\/25/);
  assert.match(card, /class="h-full w-full object-cover transition/);
  assert.match(card, /class="absolute right-3 top-3 z-\[2\]"/);
  assert.doesNotMatch(card, /bg-\[#18191c\] p-3|overflow-hidden rounded-lg bg-black\/25|object-contain/);
});

test('recent filter and loaded extents are window-session state with per-media reset and load more', async () => {
  setActivePinia(createPinia());
  const { useAICreationStore } = await loadFrontendModule('/src/stores/aiCreation.ts');
  const workspace = useAICreationStore();

  assert.equal(workspace.recentFilter, 'image');
  assert.deepEqual(workspace.recentLoaded, { image: 12, video: 12 });
  workspace.loadMoreRecent('image');
  workspace.setRecentFilter('video');
  workspace.loadMoreRecent('video');
  workspace.resetRecentLoaded('video');

  assert.equal(workspace.recentFilter, 'video');
  assert.deepEqual(workspace.recentLoaded, { image: 24, video: 12 });
});

test('workspace uses the unified recent-generations component instead of mode-coupled legacy lists', async () => {
  const workspace = await source('views/AICreationWorkspace.vue');
  assert.match(workspace, /<RecentGenerations\s*\/>/);
  assert.doesNotMatch(workspace, /<SeedreamBatchList|<SeedanceTaskList/);
});

test('refresh reloads only the selected list and cards route directly to full detail', async () => {
  const recent = await source('components/ai-creation/RecentGenerations.vue');

  assert.match(recent, /workspace\.recentFilter === 'image' \? seedream\.loadBatches\(\) : seedance\.loadTasks\(\)/);
  assert.match(recent, /workspace\.resetRecentLoaded\(workspace\.recentFilter\)/);
  assert.match(recent, /router\.push\(`\/image-generation\/batches\/\$\{encodeURIComponent\(localId\)\}`\)/);
  assert.match(recent, /router\.push\(`\/video-generation\/tasks\/\$\{encodeURIComponent\(localId\)\}`\)/);
});
