import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { createPinia, setActivePinia } from 'pinia';
import {
  closeFrontendHarness,
  createScriptedPyWebViewBridge,
  loadFrontendModule,
} from './scripted-pywebview-bridge.mjs';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';

after(async () => {
  await closeFrontendHarness();
  await closeSfcRenderer();
});

const succeededAttempt = {
  local_id: 'attempt-1',
  index: 1,
  status: 'succeeded',
  request: {},
  response: {},
  usage: {},
  total_tokens: null,
  image_url: '/seedream-media/batch-1/image/1',
  image_width: 1024,
  image_height: 1024,
  local_path: 'images/1.jpg',
  url_expired: false,
  created_at: '2026-08-13T10:00:00Z',
  updated_at: '2026-08-13T10:01:00Z',
  finished_at: '2026-08-13T10:01:00Z',
  elapsed_seconds: 60,
  error: null,
};

const imageBatch = {
  local_id: 'batch-1',
  request: { prompt: 'image prompt', model: 'pro', resolution: '1K', ratio: '1:1', count: 2 },
  status: 'generating',
  sequence: '',
  attempts: [
    { ...succeededAttempt, index: 0, local_id: 'attempt-0', image_url: '/seedream-media/batch-1/image/0' },
    succeededAttempt,
  ],
  created_at: '2026-08-13T10:00:00Z',
  updated_at: '2026-08-13T10:01:00Z',
};

test('a successful candidate exposes the video-draft action in the current image panel', async () => {
  const html = await renderSfc('components/ai-creation/ImageCurrentGenerationPanel.vue', {
    route: '/ai-creation',
    props: { batch: imageBatch },
  });

  assert.match(html, /data-test="image-current-create-video"/);
  assert.match(html, /用这张图生成视频/);
});

test('candidate handoff replaces only the video first frame and does not submit a paid task', async () => {
  const bridge = createScriptedPyWebViewBridge({
    seedream_get_handoff_image: [
      { resolve: { success: true, data: { local_path: '/cache/candidate-1.png' } } },
      { resolve: { success: true, data: { local_path: '/cache/candidate-2.png' } } },
    ],
    get_frame_thumbnail: [
      { resolve: 'candidate-thumbnail' },
      { resolve: 'replacement-thumbnail' },
    ],
  });
  setActivePinia(createPinia());
  const { useAICreationStore } = await loadFrontendModule('/src/stores/aiCreation.ts');
  const workspace = useAICreationStore();
  workspace.initializeVideoDraft({
    first_frame: '', last_frame: null, prompt: '', model: 'standard', resolution: '720p', ratio: 'adaptive', duration: -1,
    generate_audio: false, return_last_frame: false, priority: 0, execution_expires_after: 3600,
  });
  Object.assign(workspace.videoDraft, {
    prompt: 'keep this motion prompt',
    model: 'mini',
    resolution: '1080p',
    ratio: '16:9',
    duration: 8,
  });
  workspace.setCurrentGeneration({ kind: 'image', localId: 'batch-1' });

  assert.equal(await workspace.handoffCandidateToVideo('batch-1', 1), true);

  assert.equal(workspace.activeMode, 'video');
  assert.equal(workspace.videoDraft.first_frame, '/cache/candidate-1.png');
  assert.equal(workspace.videoPreviewUrls.first_frame, 'data:image/png;base64,candidate-thumbnail');
  assert.equal(workspace.videoDraft.prompt, 'keep this motion prompt');
  assert.equal(workspace.videoDraft.model, 'mini');
  assert.equal(workspace.videoDraft.resolution, '1080p');
  assert.equal(workspace.videoDraft.ratio, '16:9');
  assert.equal(workspace.videoDraft.duration, 8);
  assert.deepEqual(workspace.currentGeneration, { kind: 'image', localId: 'batch-1' });

  assert.equal(await workspace.handoffCandidateToVideo('batch-1', 0), true);
  assert.equal(workspace.videoDraft.first_frame, '/cache/candidate-2.png');
  assert.equal(workspace.videoPreviewUrls.first_frame, 'data:image/png;base64,replacement-thumbnail');
  assert.equal(workspace.videoDraft.prompt, 'keep this motion prompt');
  assert.deepEqual(workspace.currentGeneration, { kind: 'image', localId: 'batch-1' });
  assert.deepEqual(bridge.calls, [
    { method: 'seedream_get_handoff_image', args: ['batch-1', 1] },
    { method: 'get_frame_thumbnail', args: ['/cache/candidate-1.png', 320] },
    { method: 'seedream_get_handoff_image', args: ['batch-1', 0] },
    { method: 'get_frame_thumbnail', args: ['/cache/candidate-2.png', 320] },
  ]);
  assert.equal(bridge.calls.some(({ method }) => method === 'seedance_create_task'), false);
});

test('candidate handoff can target the video last frame without replacing the first frame', async () => {
  createScriptedPyWebViewBridge({
    seedream_get_handoff_image: [{ resolve: { success: true, data: { local_path: '/cache/last-frame.png' } } }],
    get_frame_thumbnail: [{ resolve: 'last-frame-thumbnail' }],
  });
  setActivePinia(createPinia());
  const { useAICreationStore } = await loadFrontendModule('/src/stores/aiCreation.ts');
  const workspace = useAICreationStore();
  workspace.videoDraft.first_frame = '/cache/first-frame.png';
  workspace.videoPreviewUrls.first_frame = 'data:image/png;base64,first-frame-thumbnail';

  assert.equal(await workspace.handoffCandidateToVideo('batch-1', 1, 'last_frame'), true);
  assert.equal(workspace.videoDraft.first_frame, '/cache/first-frame.png');
  assert.equal(workspace.videoPreviewUrls.first_frame, 'data:image/png;base64,first-frame-thumbnail');
  assert.equal(workspace.videoDraft.last_frame, '/cache/last-frame.png');
  assert.equal(workspace.videoPreviewUrls.last_frame, 'data:image/png;base64,last-frame-thumbnail');
});

test('first video initialization keeps a candidate handed off before the video composer mounts', async () => {
  createScriptedPyWebViewBridge({
    seedream_get_handoff_image: [{ resolve: { success: true, data: { local_path: '/cache/candidate.png' } } }],
    get_frame_thumbnail: [{ resolve: 'preview' }],
  });
  setActivePinia(createPinia());
  const { useAICreationStore } = await loadFrontendModule('/src/stores/aiCreation.ts');
  const workspace = useAICreationStore();

  await workspace.handoffCandidateToVideo('batch-1', 0);
  workspace.initializeVideoDraft({
    first_frame: '', last_frame: null, prompt: '', model: 'mini', resolution: '1080p', ratio: '16:9', duration: 8,
    generate_audio: false, return_last_frame: false, priority: 0, execution_expires_after: 3600,
  });

  assert.equal(workspace.videoDraft.first_frame, '/cache/candidate.png');
  assert.equal(workspace.videoPreviewUrls.first_frame, 'data:image/png;base64,preview');
  assert.equal(workspace.videoDraft.model, 'mini');
  assert.equal(workspace.videoDraft.resolution, '1080p');
  assert.equal(workspace.videoDraft.duration, 8);
});

test('video creation consumes the shared first-frame preview without source metadata', async () => {
  const html = await renderSfc('views/SeedanceCreate.vue', {
    route: '/ai-creation?mode=video',
    piniaState: {
      'ai-creation': {
        activeMode: 'video',
        videoDraft: { first_frame: '/cache/candidate.png', prompt: 'move', model: 'standard', resolution: '720p', ratio: 'adaptive', duration: -1, generate_audio: false, return_last_frame: false, priority: 0, execution_expires_after: 3600 },
        videoPreviewUrls: { first_frame: 'data:image/png;base64,preview', last_frame: '' },
      },
    },
  });

  assert.match(html, /src="data:image\/png;base64,preview"/);
  assert.doesNotMatch(html, /来自图片生成|候选 1|返回查看/);
});
