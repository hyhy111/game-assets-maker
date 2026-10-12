import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { createPinia, setActivePinia } from 'pinia';
import {
  closeFrontendHarness,
  createScriptedPyWebViewBridge,
  loadFrontendModule,
} from './scripted-pywebview-bridge.mjs';

after(closeFrontendHarness);

const seedanceTask = (overrides = {}) => ({
  local_id: 'task-1',
  remote_id: 'remote-1',
  remote_status: 'queued',
  sync_status: {},
  download_status: 'pending',
  cache_status: 'complete',
  protected: false,
  request: {
    prompt: 'Hero idle',
    model: 'standard',
    resolution: '720p',
    ratio: '16:9',
    duration: 5,
    generate_audio: false,
    return_last_frame: true,
    priority: 0,
    execution_expires_after: 3600,
  },
  input_urls: { first_frame: 'local://first.png' },
  output_urls: {},
  created_at: '2026-07-30T10:00:00Z',
  updated_at: '2026-07-30T10:00:00Z',
  finished_at: null,
  elapsed_seconds: 0,
  remote: {},
  error: null,
  retry_of: null,
  handoffs: [],
  ...overrides,
});

test('public project API observes scripted PyWebView results and errors', async () => {
  const bridge = createScriptedPyWebViewBridge({
    get_projects: [
      { resolve: [{ id: 'hero/idle' }] },
      { reject: new Error('project bridge failed') },
    ],
  });
  const { projectApi } = await loadFrontendModule('/src/api/index.ts');

  assert.deepEqual(await projectApi.getProjects(), [{ id: 'hero/idle' }]);
  await assert.rejects(projectApi.getProjects(), /project bridge failed/);
  assert.deepEqual(bridge.calls, [
    { method: 'get_projects', args: [] },
    { method: 'get_projects', args: [] },
  ]);
});

test('public frame API persists and restores hidden preview frames through PyWebView', async () => {
  const bridge = createScriptedPyWebViewBridge({
    get_hidden_frames: [{ resolve: ['frame_000002.png'] }],
    set_frame_hidden: [
      { resolve: { success: true, hidden_frames: ['frame_000002.png'] } },
      { resolve: { success: true, hidden_frames: [] } },
    ],
    restore_hidden_frames: [{ resolve: { success: true, hidden_frames: [] } }],
  });
  const { frameApi } = await loadFrontendModule('/src/api/index.ts');

  assert.deepEqual(await frameApi.getHiddenFrames('hero/idle'), ['frame_000002.png']);
  assert.deepEqual(
    await frameApi.setFrameHidden('hero/idle', 'frame_000002.png', true),
    { success: true, hidden_frames: ['frame_000002.png'] },
  );
  assert.deepEqual(
    await frameApi.setFrameHidden('hero/idle', 'frame_000002.png', false),
    { success: true, hidden_frames: [] },
  );
  assert.deepEqual(await frameApi.restoreHiddenFrames('hero/idle'), { success: true, hidden_frames: [] });
  assert.deepEqual(bridge.calls.map((call) => call.method), [
    'get_hidden_frames',
    'set_frame_hidden',
    'set_frame_hidden',
    'restore_hidden_frames',
  ]);
});

test('project store exposes bridge-loaded projects, roles, and failures', async () => {
  createScriptedPyWebViewBridge({
    get_projects: [{ resolve: [
      { id: 'old', modified_at: '2026-01-01T00:00:00Z' },
      { id: 'new', modified_at: '2026-02-01T00:00:00Z' },
    ] }],
    get_roles: [{ resolve: [{ name: 'hero', projectCount: 2 }] }],
  });
  setActivePinia(createPinia());
  const { useProjectStore } = await loadFrontendModule('/src/stores/project.ts');
  const store = useProjectStore();

  await store.loadProjects();

  assert.deepEqual(store.projects.map((project) => project.id), ['new', 'old']);
  assert.deepEqual(store.roles, [{ name: 'hero', projectCount: 2 }]);
  assert.equal(store.loading, false);
  assert.equal(store.error, null);

  createScriptedPyWebViewBridge({
    get_projects: [{ reject: new Error('cannot load projects') }],
  });
  await store.loadProjects();
  assert.equal(store.loading, false);
  assert.equal(store.error, 'cannot load projects');
});

test('process store exposes bridge task progress through its public state', async () => {
  createScriptedPyWebViewBridge({
    get_step_params: [{ resolve: { frame_interval: 2, fps: 12, processed: false } }],
    start_processing: [{ resolve: 'process-1' }],
    get_task_status: [{ resolve: {
      success: true,
      task_id: 'process-1',
      status: 'completed',
      progress: 100,
      current: 3,
      total: 3,
    } }],
  });
  setActivePinia(createPinia());
  const { useProcessStore } = await loadFrontendModule('/src/stores/process.ts');
  const store = useProcessStore();

  await store.loadStepParams('hero/idle', 1);
  assert.equal(store.s1Params.frame_interval, 2);
  assert.equal(store.s1Params.fps, 12);

  assert.equal(await store.startProcessing('hero/idle', 1), 'process-1');
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(store.currentTask, 'process-1');
  assert.equal(store.taskStatus?.status, 'completed');
  assert.equal(store.progress, 100);
  assert.equal(store.isPolling, false);
});

test('Seedance store loads and creates tasks through the public bridge', async () => {
  const queued = seedanceTask();
  const created = seedanceTask({ local_id: 'task-2', remote_id: 'remote-2' });
  createScriptedPyWebViewBridge({
    seedance_list_tasks: [{ resolve: { success: true, tasks: [queued] } }],
    seedance_create_task: [{ resolve: { success: true, task: created } }],
  });
  setActivePinia(createPinia());
  const { useSeedanceStore } = await loadFrontendModule('/src/stores/seedance.ts');
  const store = useSeedanceStore();

  assert.deepEqual(await store.loadTasks(), [queued]);
  assert.equal(store.loading, false);
  assert.equal(store.error, null);

  const request = { first_frame: '/tmp/first.png', prompt: 'Hero idle' };
  assert.deepEqual(await store.createTask(request), created);
  assert.deepEqual(store.currentTask, created);
  assert.deepEqual(store.tasks.map((task) => task.local_id), ['task-2', 'task-1']);
});

test('Seedance regeneration draft restores cached inputs without submitting a task', async () => {
  const draft = {
    request: {
      first_frame: '/cache/task/input/first.png',
      last_frame: null,
      prompt: 'Hero attack',
      model: 'mini',
      resolution: '720p',
      ratio: '16:9',
      duration: 4,
      generate_audio: false,
      return_last_frame: true,
      priority: 0,
      execution_expires_after: 3600,
    },
    preview_urls: { first_frame: 'http://localhost/seedance-media/task-1/first_frame' },
  };
  const bridge = createScriptedPyWebViewBridge({
    seedance_get_regeneration_draft: [{ resolve: { success: true, data: draft } }],
  });
  setActivePinia(createPinia());
  const { useSeedanceStore } = await loadFrontendModule('/src/stores/seedance.ts');
  const store = useSeedanceStore();

  assert.deepEqual(await store.loadRegenerationDraft('task-1'), draft);
  assert.deepEqual(bridge.calls.map((call) => call.method), ['seedance_get_regeneration_draft']);
});

test('Seedance continuation draft uses the returned last frame without submitting a task', async () => {
  const draft = {
    request: { first_frame: '/cache/task/output/returned_last_frame.png', last_frame: null, prompt: '' },
    preview_urls: { first_frame: 'http://localhost/seedance-media/task-1/returned_last_frame' },
  };
  const bridge = createScriptedPyWebViewBridge({
    seedance_get_continuation_draft: [{ resolve: { success: true, data: draft } }],
  });
  setActivePinia(createPinia());
  const { useSeedanceStore } = await loadFrontendModule('/src/stores/seedance.ts');
  const store = useSeedanceStore();

  assert.deepEqual(await store.loadContinuationDraft('task-1'), draft);
  assert.deepEqual(bridge.calls.map((call) => call.method), ['seedance_get_continuation_draft']);
});

test('Seedance store sends only one create request while a submission is pending', async () => {
  const created = seedanceTask({ local_id: 'task-2', remote_id: 'remote-2' });
  let resolveCreate;
  const bridge = createScriptedPyWebViewBridge({
    seedance_create_task: [{ resolve: () => new Promise((resolve) => { resolveCreate = resolve; }) }],
  });
  setActivePinia(createPinia());
  const { useSeedanceStore } = await loadFrontendModule('/src/stores/seedance.ts');
  const store = useSeedanceStore();
  const request = { first_frame: '/tmp/first.png', prompt: 'Hero idle' };

  const first = store.createTask(request);
  const second = await store.createTask(request);
  assert.equal(second, null);
  assert.deepEqual(bridge.calls.map((call) => call.method), ['seedance_create_task']);

  resolveCreate({ success: true, task: created });
  assert.deepEqual(await first, created);
});

test('Seedance store exposes structured and thrown bridge failures', async () => {
  createScriptedPyWebViewBridge({
    seedance_list_tasks: [{ resolve: {
      success: false,
      error: { code: 'AUTH_FAILED', message: 'Authentication failed', field: null },
    } }],
  });
  setActivePinia(createPinia());
  const { useSeedanceStore } = await loadFrontendModule('/src/stores/seedance.ts');
  const store = useSeedanceStore();

  assert.deepEqual(await store.loadTasks(), []);
  assert.equal(store.error?.code, 'AUTH_FAILED');
  assert.equal(store.loading, false);

  createScriptedPyWebViewBridge({
    seedance_list_tasks: [{ reject: new Error('bridge unavailable') }],
  });
  assert.deepEqual(await store.loadTasks(), []);
  assert.equal(store.error?.code, 'REQUEST_FAILED');
  assert.equal(store.error?.message, 'bridge unavailable');
});

test('Seedance store exposes cancel, retry, continuation, deletion, and handoff results', async () => {
  const queued = seedanceTask();
  const cancelled = seedanceTask({ remote_status: 'cancelled' });
  const retried = seedanceTask({ local_id: 'task-retry', retry_of: 'task-1' });
  const continued = seedanceTask({ local_id: 'task-continue', retry_of: 'task-1' });
  const downloaded = seedanceTask({
    local_id: 'task-download',
    remote_status: 'succeeded',
    download_status: 'downloaded',
    output_urls: { video: 'local://video.mp4' },
  });
  const handedOff = seedanceTask({
    local_id: 'task-continue',
    protected: true,
    handoffs: [{ project_id: 'hero/idle', role: 'hero', action: 'idle', created_at: '2026-07-30T10:10:00Z' }],
  });
  const bridge = createScriptedPyWebViewBridge({
    seedance_cancel_task: [{ resolve: { success: true, task: cancelled } }],
    seedance_retry_task: [{ resolve: { success: true, task: retried } }],
    seedance_retry_download: [{ resolve: { success: true, task: downloaded } }],
    seedance_continue_task: [{ resolve: { success: true, task: continued } }],
    seedance_delete_task: [{ resolve: { success: true } }],
    seedance_handoff: [{ resolve: { success: true, project_id: 'hero/idle', task: handedOff } }],
  });
  setActivePinia(createPinia());
  const { useSeedanceStore } = await loadFrontendModule('/src/stores/seedance.ts');
  const store = useSeedanceStore();
  store.upsertTask(queued);

  assert.deepEqual(await store.cancelTask('task-1'), cancelled);
  assert.deepEqual(await store.retryTask('task-1'), retried);
  assert.deepEqual(await store.retryDownload('task-download'), downloaded);
  assert.deepEqual(await store.continueTask('task-1'), continued);
  assert.equal(await store.deleteTask('task-retry'), true);
  const handoff = await store.handoff('task-continue', 'hero', 'idle');

  assert.equal(handoff?.project_id, 'hero/idle');
  assert.deepEqual(store.currentTask, handedOff);
  assert.equal(store.tasks.some((task) => task.local_id === 'task-retry'), false);
  assert.equal(store.tasks.find((task) => task.local_id === 'task-continue')?.protected, true);
  assert.deepEqual(bridge.calls.map((call) => call.method), [
    'seedance_cancel_task',
    'seedance_retry_task',
    'seedance_retry_download',
    'seedance_continue_task',
    'seedance_delete_task',
    'seedance_handoff',
  ]);
});

test('duplicate animation handoff preserves the task and allows retry with another name', async () => {
  const downloaded = seedanceTask({
    remote_status: 'succeeded',
    download_status: 'downloaded',
    output_urls: { video: 'local://video.mp4' },
  });
  const duplicateError = {
    code: 'INVALID_REQUEST',
    message: "角色 'hero' 下的动作 'idle' 已存在，请使用其他名称",
    field: null,
  };
  const handedOff = seedanceTask({
    ...downloaded,
    handoffs: [{ project_id: 'hero/idle-2', role: 'hero', action: 'idle-2' }],
  });
  const bridge = createScriptedPyWebViewBridge({
    seedance_handoff: [
      { resolve: { success: false, error: duplicateError } },
      { resolve: { success: true, project_id: 'hero/idle-2', task: handedOff } },
    ],
  });
  setActivePinia(createPinia());
  const { useSeedanceStore } = await loadFrontendModule('/src/stores/seedance.ts');
  const store = useSeedanceStore();
  store.upsertTask(downloaded);
  store.currentTask = downloaded;

  assert.equal(await store.handoff('task-1', 'hero', 'idle'), null);
  assert.deepEqual(store.error, duplicateError);
  assert.deepEqual(store.currentTask, downloaded);
  assert.equal(store.loading, false);

  assert.equal((await store.handoff('task-1', 'hero', 'idle-2'))?.project_id, 'hero/idle-2');
  assert.equal(store.error, null);
  assert.deepEqual(store.currentTask, handedOff);
  assert.equal(store.loading, false);
  assert.deepEqual(bridge.calls, [
    { method: 'seedance_handoff', args: ['task-1', 'hero', 'idle'] },
    { method: 'seedance_handoff', args: ['task-1', 'hero', 'idle-2'] },
  ]);
});

test('Seedance image selection keeps the source path and builds a safe thumbnail preview', async () => {
  const bridge = createScriptedPyWebViewBridge({
    seedance_select_image_file: [{ resolve: '/tmp/rabbit.jpeg' }],
    get_frame_thumbnail: [{ resolve: 'thumbnail-base64' }],
  });
  setActivePinia(createPinia());
  const { useSeedanceStore } = await loadFrontendModule('/src/stores/seedance.ts');
  const store = useSeedanceStore();

  assert.deepEqual(await store.selectImageFile(), {
    path: '/tmp/rabbit.jpeg',
    previewUrl: 'data:image/png;base64,thumbnail-base64',
  });
  assert.deepEqual(bridge.calls, [
    { method: 'seedance_select_image_file', args: [] },
    { method: 'get_frame_thumbnail', args: ['/tmp/rabbit.jpeg', 320] },
  ]);
});

test('Seedance video save stays inside the app and reports the system-dialog result', async () => {
  const bridge = createScriptedPyWebViewBridge({
    seedance_save_video: [{ resolve: { success: true, data: { saved: true, path: '/tmp/video.mp4' } } }],
  });
  setActivePinia(createPinia());
  const { useSeedanceStore } = await loadFrontendModule('/src/stores/seedance.ts');
  const store = useSeedanceStore();

  assert.equal(await store.saveVideo('task-1'), true);
  assert.deepEqual(bridge.calls, [{ method: 'seedance_save_video', args: ['task-1'] }]);
});
