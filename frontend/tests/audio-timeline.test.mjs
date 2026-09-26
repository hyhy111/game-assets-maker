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

// ---------------------------------------------------------------------------
// Store + scripted bridge：模拟选区 -> 建片段 -> 持久化
// ---------------------------------------------------------------------------

test('createClip persists the clip via save_timeline and enters the store', async () => {
  const bridge = createScriptedPyWebViewBridge({
    extract_source_audio: [
      {
        resolve: {
          success: true,
          source_wav: 'http://localhost:8080/cache/01_audio/source.wav?t=1',
          source_fps: 10,
          total_frames: 30,
        },
      },
    ],
    load_timeline: [
      {
        resolve: {
          source_fps: 10,
          total_frames: 30,
          source_wav: 'http://localhost:8080/cache/01_audio/source.wav?t=1',
          clips: [],
        },
      },
    ],
    save_timeline: [{ resolve: { success: true } }],
  });

  const { useAudioTimelineStore } = await loadFrontendModule('/src/stores/audioTimeline.ts');
  setActivePinia(createPinia());
  const store = useAudioTimelineStore();

  // 加载源音频 + 已保存时间线
  await store.load('hero/attack');
  assert.equal(store.loaded, true);
  assert.equal(store.clips.length, 0);

  // 模拟选区 -> 建片段（placementFrame 默认 = 选区起始帧）
  await store.createClip({
    name: '片段 1',
    srcStartFrame: 4,
    srcEndFrame: 9,
    placementFrame: 4,
  });

  // 片段入 store
  assert.equal(store.clips.length, 1);
  assert.deepEqual(store.clips[0], {
    name: '片段 1',
    srcStartFrame: 4,
    srcEndFrame: 9,
    placementFrame: 4,
  });

  // save_timeline API 被触发，且携带完整 AudioTimeline 对象
  const saveCall = bridge.calls.find((c) => c.method === 'save_timeline');
  assert.ok(saveCall, 'save_timeline should be called');
  assert.equal(saveCall.args[0], 'hero/attack');
  assert.deepEqual(saveCall.args[1].clips, [
    { name: '片段 1', srcStartFrame: 4, srcEndFrame: 9, placementFrame: 4 },
  ]);
  assert.equal(saveCall.args[1].source_fps, 10);
  assert.equal(saveCall.args[1].total_frames, 30);
});

test('createClip defaults placementFrame to srcStartFrame when omitted', async () => {
  const bridge = createScriptedPyWebViewBridge({
    extract_source_audio: [
      { resolve: { success: true, source_wav: 'http://localhost/w.wav', source_fps: 24, total_frames: 60 } },
    ],
    load_timeline: [{ resolve: { source_fps: 24, total_frames: 60, source_wav: 'http://localhost/w.wav', clips: [] } }],
    save_timeline: [{ resolve: { success: true } }],
  });

  const { useAudioTimelineStore } = await loadFrontendModule('/src/stores/audioTimeline.ts');
  setActivePinia(createPinia());
  const store = useAudioTimelineStore();

  await store.load('hero/idle');
  await store.createClip({ name: 'step', srcStartFrame: 10, srcEndFrame: 20 });

  assert.equal(store.clips[0].placementFrame, 10, 'placementFrame defaults to srcStartFrame');
});

test('load reads saved clips from load_timeline', async () => {
  const savedClip = { name: 'hit', srcStartFrame: 5, srcEndFrame: 8, placementFrame: 12 };
  const bridge = createScriptedPyWebViewBridge({
    extract_source_audio: [
      { resolve: { success: true, source_wav: 'http://localhost/w.wav', source_fps: 10, total_frames: 30 } },
    ],
    load_timeline: [
      { resolve: { source_fps: 10, total_frames: 30, source_wav: 'http://localhost/w.wav', clips: [savedClip] } },
    ],
  });

  const { useAudioTimelineStore } = await loadFrontendModule('/src/stores/audioTimeline.ts');
  setActivePinia(createPinia());
  const store = useAudioTimelineStore();

  await store.load('hero/attack');
  assert.equal(store.clips.length, 1);
  assert.deepEqual(store.clips[0], savedClip);
});

// ---------------------------------------------------------------------------
// 组件渲染：选区 UI + 片段轨道
// ---------------------------------------------------------------------------

test('AudioTimeline renders the create-clip button and saved clips on the clip track', async () => {
  const html = await renderSfc('components/player/AudioTimeline.vue', {
    props: { totalFrames: 100, currentFrame: 10 },
    piniaState: {
      audioTimeline: {
        sourceWav: 'http://localhost:8080/cache/01_audio/source.wav?t=1',
        sourceFps: 10,
        totalFrames: 100,
        clips: [
          { name: 'step', srcStartFrame: 0, srcEndFrame: 5, placementFrame: 10 },
          { name: 'hit', srcStartFrame: 20, srcEndFrame: 28, placementFrame: 40 },
        ],
        currentProjectId: 'hero/attack',
        loading: false,
        error: null,
        loaded: true,
        selectedClipIndices: [],
      },
    },
  });

  // 创建按钮存在（默认禁用，因无选区）
  assert.match(html, /data-test="create-audio-clip"/);
  assert.match(html, /disabled/);
  // 片段轨道渲染两个已保存片段
  assert.match(html, /data-test="audio-clip-track"/);
  assert.match(html, /step/);
  assert.match(html, /hit/);
  // 提示文案
  assert.match(html, /在波形上拖动以选择 Source Region/);
});

// ---------------------------------------------------------------------------
// 票 03：拖动改 placementFrame（live + clamp）、选中、删除、多片段共存
// ---------------------------------------------------------------------------

test('moveClip updates placementFrame live without triggering save', async () => {
  // save_timeline 故意不入队：moveClip 不得在拖动中持久化
  const bridge = createScriptedPyWebViewBridge({
    extract_source_audio: [
      { resolve: { success: true, source_wav: 'http://localhost/w.wav', source_fps: 10, total_frames: 30 } },
    ],
    load_timeline: [
      {
        resolve: {
          source_fps: 10, total_frames: 30, source_wav: 'http://localhost/w.wav',
          clips: [{ name: '片段 1', srcStartFrame: 4, srcEndFrame: 9, placementFrame: 4 }],
        },
      },
    ],
  });

  const { useAudioTimelineStore } = await loadFrontendModule('/src/stores/audioTimeline.ts');
  setActivePinia(createPinia());
  const store = useAudioTimelineStore();

  await store.load('hero/attack');
  assert.equal(store.clips[0].placementFrame, 4);

  // 模拟拖动中：moveClip 实时改 placementFrame，不触发 save
  store.moveClip(0, 15);
  assert.equal(store.clips[0].placementFrame, 15, 'placementFrame updates live');
  assert.equal(
    bridge.calls.filter((c) => c.method === 'save_timeline').length,
    0,
    'moveClip must not call save_timeline mid-drag',
  );
});

test('moveClip clamps placementFrame to [0, totalFrames - span]', async () => {
  const bridge = createScriptedPyWebViewBridge({
    extract_source_audio: [
      { resolve: { success: true, source_wav: 'http://localhost/w.wav', source_fps: 10, total_frames: 30 } },
    ],
    load_timeline: [
      {
        resolve: {
          source_fps: 10, total_frames: 30, source_wav: 'http://localhost/w.wav',
          clips: [{ name: '片段 1', srcStartFrame: 4, srcEndFrame: 9, placementFrame: 4 }],
        },
      },
    ],
  });
  const { useAudioTimelineStore } = await loadFrontendModule('/src/stores/audioTimeline.ts');
  setActivePinia(createPinia());
  const store = useAudioTimelineStore();
  await store.load('hero/attack');

  const span = 9 - 4; // 5
  const maxPlacement = 30 - span; // 25

  store.moveClip(0, 999);
  assert.equal(store.clips[0].placementFrame, maxPlacement, 'clamped to upper bound');
  store.moveClip(0, -10);
  assert.equal(store.clips[0].placementFrame, 0, 'clamped to lower bound');
});

test('save after moveClip persists the new placementFrame (drag-end commit)', async () => {
  const bridge = createScriptedPyWebViewBridge({
    extract_source_audio: [
      { resolve: { success: true, source_wav: 'http://localhost/w.wav', source_fps: 10, total_frames: 30 } },
    ],
    load_timeline: [
      {
        resolve: {
          source_fps: 10, total_frames: 30, source_wav: 'http://localhost/w.wav',
          clips: [{ name: '片段 1', srcStartFrame: 4, srcEndFrame: 9, placementFrame: 4 }],
        },
      },
    ],
    save_timeline: [{ resolve: { success: true } }],
  });
  const { useAudioTimelineStore } = await loadFrontendModule('/src/stores/audioTimeline.ts');
  setActivePinia(createPinia());
  const store = useAudioTimelineStore();
  await store.load('hero/attack');

  // 模拟完整拖动：moveClip(实时) -> mouseup save(持久化)
  store.moveClip(0, 18);
  await store.save();

  const saveCall = bridge.calls.find((c) => c.method === 'save_timeline');
  assert.ok(saveCall, 'save_timeline called on drag end');
  assert.equal(saveCall.args[1].clips[0].placementFrame, 18, 'persisted placementFrame');
});

test('selectClip sets and clears selectedClipIndex', async () => {
  const bridge = createScriptedPyWebViewBridge({
    extract_source_audio: [
      { resolve: { success: true, source_wav: 'http://localhost/w.wav', source_fps: 10, total_frames: 30 } },
    ],
    load_timeline: [
      {
        resolve: {
          source_fps: 10, total_frames: 30, source_wav: 'http://localhost/w.wav',
          clips: [
            { name: 'a', srcStartFrame: 0, srcEndFrame: 3, placementFrame: 0 },
            { name: 'b', srcStartFrame: 5, srcEndFrame: 8, placementFrame: 10 },
          ],
        },
      },
    ],
  });
  const { useAudioTimelineStore } = await loadFrontendModule('/src/stores/audioTimeline.ts');
  setActivePinia(createPinia());
  const store = useAudioTimelineStore();
  await store.load('hero/attack');

  assert.deepEqual(store.selectedClipIndices, [], 'no selection initially');
  store.selectClip(1);
  assert.deepEqual(store.selectedClipIndices, [1], 'selected clip 1');
  store.clearSelection();
  assert.deepEqual(store.selectedClipIndices, [], 'cleared selection');
});

test('multiple clips coexist on the timeline', async () => {
  const bridge = createScriptedPyWebViewBridge({
    extract_source_audio: [
      { resolve: { success: true, source_wav: 'http://localhost/w.wav', source_fps: 10, total_frames: 60 } },
    ],
    load_timeline: [
      { resolve: { source_fps: 10, total_frames: 60, source_wav: 'http://localhost/w.wav', clips: [] } },
    ],
    save_timeline: [
      { resolve: { success: true } },
      { resolve: { success: true } },
      { resolve: { success: true } },
    ],
  });
  const { useAudioTimelineStore } = await loadFrontendModule('/src/stores/audioTimeline.ts');
  setActivePinia(createPinia());
  const store = useAudioTimelineStore();
  await store.load('hero/attack');

  await store.createClip({ name: 'step', srcStartFrame: 0, srcEndFrame: 4, placementFrame: 5 });
  await store.createClip({ name: 'hit', srcStartFrame: 10, srcEndFrame: 14, placementFrame: 20 });
  await store.createClip({ name: 'whoosh', srcStartFrame: 30, srcEndFrame: 35, placementFrame: 40 });

  assert.equal(store.clips.length, 3, 'three clips coexist');
  assert.deepEqual(
    store.clips.map((c) => c.name),
    ['step', 'hit', 'whoosh'],
  );
});

test('deleteClip removes the clip and persists', async () => {
  const bridge = createScriptedPyWebViewBridge({
    extract_source_audio: [
      { resolve: { success: true, source_wav: 'http://localhost/w.wav', source_fps: 10, total_frames: 30 } },
    ],
    load_timeline: [
      {
        resolve: {
          source_fps: 10, total_frames: 30, source_wav: 'http://localhost/w.wav',
          clips: [
            { name: 'keep', srcStartFrame: 0, srcEndFrame: 3, placementFrame: 0 },
            { name: 'delete-me', srcStartFrame: 5, srcEndFrame: 8, placementFrame: 10 },
          ],
        },
      },
    ],
    save_timeline: [{ resolve: { success: true } }],
  });
  const { useAudioTimelineStore } = await loadFrontendModule('/src/stores/audioTimeline.ts');
  setActivePinia(createPinia());
  const store = useAudioTimelineStore();
  await store.load('hero/attack');

  await store.deleteClip(1);

  assert.equal(store.clips.length, 1, 'one clip removed');
  assert.equal(store.clips[0].name, 'keep', 'remaining clip is the unselected one');

  const saveCall = bridge.calls.find((c) => c.method === 'save_timeline');
  assert.ok(saveCall, 'deleteClip persists');
  assert.equal(saveCall.args[1].clips.length, 1);
  assert.equal(saveCall.args[1].clips[0].name, 'keep');
});

test('deleteClip clears selection when deleting the active clip', async () => {
  const bridge = createScriptedPyWebViewBridge({
    extract_source_audio: [
      { resolve: { success: true, source_wav: 'http://localhost/w.wav', source_fps: 10, total_frames: 30 } },
    ],
    load_timeline: [
      {
        resolve: {
          source_fps: 10, total_frames: 30, source_wav: 'http://localhost/w.wav',
          clips: [
            { name: 'a', srcStartFrame: 0, srcEndFrame: 3, placementFrame: 0 },
            { name: 'b', srcStartFrame: 5, srcEndFrame: 8, placementFrame: 10 },
          ],
        },
      },
    ],
    save_timeline: [{ resolve: { success: true } }],
  });
  const { useAudioTimelineStore } = await loadFrontendModule('/src/stores/audioTimeline.ts');
  setActivePinia(createPinia());
  const store = useAudioTimelineStore();
  await store.load('hero/attack');

  store.selectClip(1);
  assert.deepEqual(store.selectedClipIndices, [1]);
  await store.deleteClip(1);
  assert.deepEqual(store.selectedClipIndices, [], 'selection cleared after deleting active clip');
});

// ---------------------------------------------------------------------------
// 票 03 组件渲染：选中高亮 + 删除按钮 + 拖动/选中交互挂载
// ---------------------------------------------------------------------------

test('AudioTimeline highlights the selected clip and shows a delete button', async () => {
  const html = await renderSfc('components/player/AudioTimeline.vue', {
    props: { totalFrames: 100, currentFrame: 10 },
    piniaState: {
      audioTimeline: {
        sourceWav: 'http://localhost:8080/cache/01_audio/source.wav?t=1',
        sourceFps: 10,
        totalFrames: 100,
        clips: [
          { name: 'step', srcStartFrame: 0, srcEndFrame: 5, placementFrame: 10 },
          { name: 'hit', srcStartFrame: 20, srcEndFrame: 28, placementFrame: 40 },
        ],
        selectedClipIndices: [1],
        currentProjectId: 'hero/attack',
        loading: false,
        error: null,
        loaded: true,
      },
    },
  });

  // 选中的片段带 data-selected="true"（顺序无关）
  assert.match(html, /data-selected="true"/);
  // 选中时出现删除按钮
  assert.match(html, /data-test="delete-audio-clip"/);
});

test('AudioTimeline shows no delete button when no clip is selected', async () => {
  const html = await renderSfc('components/player/AudioTimeline.vue', {
    props: { totalFrames: 100, currentFrame: 10 },
    piniaState: {
      audioTimeline: {
        sourceWav: 'http://localhost/w.wav',
        sourceFps: 10,
        totalFrames: 100,
        clips: [{ name: 'step', srcStartFrame: 0, srcEndFrame: 5, placementFrame: 10 }],
        selectedClipIndices: [],
        currentProjectId: 'hero/attack',
        loading: false,
        error: null,
        loaded: true,
      },
    },
  });

  assert.doesNotMatch(html, /data-test="delete-audio-clip"/);
  // 未选中片段不带 data-selected="true"
  assert.doesNotMatch(html, /data-selected="true"/);
});
