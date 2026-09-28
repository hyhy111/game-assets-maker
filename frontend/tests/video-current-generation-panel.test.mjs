import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { after, test } from 'node:test';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';

after(closeSfcRenderer);

const taskFixture = (overrides = {}) => ({
  local_id: 'video-1',
  remote_id: 'remote-1',
  remote_status: 'succeeded',
  sync_status: {},
  download_status: 'downloaded',
  cache_status: 'complete',
  protected: false,
  request: {
    prompt: 'A hero raises a sword',
    model: 'standard',
    resolution: '720p',
    ratio: '16:9',
    duration: 5,
    generate_audio: false,
    return_last_frame: false,
    priority: 0,
    execution_expires_after: 3600,
  },
  input_urls: { first_frame: 'http://localhost/first.png' },
  output_urls: { video: 'http://localhost/video.mp4' },
  created_at: '2026-08-13T10:00:00Z',
  updated_at: '2026-08-13T10:01:00Z',
  finished_at: '2026-08-13T10:01:00Z',
  download_url_received_at: '2026-08-13T10:01:00Z',
  elapsed_seconds: 60,
  remote: {},
  error: null,
  retry_of: null,
  handoffs: [],
  ...overrides,
});

test('current video generation panel matches the composer surface and keeps only the detail action', async () => {
  const workspaceSource = await readFile(
    new URL('../src/views/AICreationWorkspace.vue', import.meta.url),
    'utf8',
  );
  const html = await renderSfc('components/ai-creation/VideoCurrentGenerationPanel.vue', {
    props: { task: taskFixture() },
  });

  assert.match(html, /生成任务/);
  assert.match(html, /下载完成/);
  assert.match(html, /<video[^>]+src="http:\/\/localhost\/video\.mp4"/);
  assert.match(html, /查看详情/);
  assert.match(html, /bg-\[#1f1f1f\]/);
  assert.match(html, /flex h-full flex-col/);
  assert.match(html, /min-h-0 flex-1/);
  assert.match(html, /mt-4 flex h-11 flex-nowrap items-center/);
  assert.doesNotMatch(html, /Seedance 生成视频|另存视频|送入逐帧动画流水线|总 Token 数|删除任务/);
  assert.match(workspaceSource, /class="grid items-stretch gap-5"/);
});

test('current video generation panel presents recovery actions for active and failed downloads', async () => {
  const queued = await renderSfc('components/ai-creation/VideoCurrentGenerationPanel.vue', {
    props: {
      task: taskFixture({
        remote_status: 'queued',
        download_status: 'pending',
        cache_status: 'complete',
        output_urls: {},
      }),
    },
  });
  assert.match(queued, /排队中/);
  assert.match(queued, /取消任务/);
  assert.match(queued, /查看详情/);

  const downloadFailed = await renderSfc('components/ai-creation/VideoCurrentGenerationPanel.vue', {
    props: {
      task: taskFixture({
        remote_status: 'succeeded',
        download_status: 'failed',
        output_urls: {},
      }),
    },
  });
  assert.match(downloadFailed, /生成失败/);
  assert.match(downloadFailed, /重新下载/);
  assert.match(downloadFailed, /查看详情/);
});

test('current video generation panel has no collapse control and always shows its content', async () => {
  const source = await readFile(
    new URL('../src/components/ai-creation/VideoCurrentGenerationPanel.vue', import.meta.url),
    'utf8',
  );
  const html = await renderSfc('components/ai-creation/VideoCurrentGenerationPanel.vue', {
    props: { task: taskFixture() },
  });

  assert.match(html, /下载完成/);
  assert.match(html, /<video|查看详情/);
  assert.doesNotMatch(source, /collapsed|aria-expanded|ChevronDown|ChevronUp|emit\('toggle'\)/);
});

test('video composer keeps both frame controls visible in compact mode', async () => {
  const html = await renderSfc('views/SeedanceCreate.vue', {
    route: '/ai-creation?mode=video',
    props: { embedded: true, creationMode: 'video' },
  });

  assert.match(html, /首帧图片/);
  assert.match(html, /尾帧图片/);
  assert.match(html, /aria-required="true"/);
});

test('confirmed video submission stays in the workspace and preserves its draft', async () => {
  const source = await readFile(
    new URL('../src/views/SeedanceCreate.vue', import.meta.url),
    'utf8',
  );
  const confirmMatch = source.match(/async function confirmPaidAction\(\)\s*\{[\s\S]*?\n\}/);
  assert.ok(confirmMatch, 'confirmPaidAction function should exist');

  assert.match(confirmMatch[0], /createPendingTask\(\)/);
  assert.match(source, /store\.createTask\(request, source\)/);
  assert.match(source, /workspace\.setCurrentGeneration\(\{ kind: 'video', localId: task\.local_id \}\)/);
  assert.doesNotMatch(confirmMatch[0], /router\.push|resetVideoDraft|form\.prompt\s*=|clearDraft\(/);
});
