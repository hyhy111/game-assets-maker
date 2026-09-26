import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import {
  computePeaks,
  getTriggeredClips,
  createAudioPlaybackEngine,
  createAudioSyncController,
} from '../src/composables/audioPeaks.ts';
import {
  closeFrontendHarness,
  createScriptedPyWebViewBridge,
  loadFrontendModule,
} from './scripted-pywebview-bridge.mjs';

after(async () => {
  await closeFrontendHarness();
});

// ---------------------------------------------------------------------------
// 票 04：音画同步预览
// 纯函数 getTriggeredClips + 可注入 AudioContext 的播放引擎 + 同步控制器
// ---------------------------------------------------------------------------

// --- getTriggeredClips（纯函数：判定帧前进跨越了哪些片段）---

test('getTriggeredClips returns clips whose placementFrame is crossed forward', () => {
  const clips = [
    { name: 'a', srcStartFrame: 0, srcEndFrame: 4, placementFrame: 7 }, // 5 < 7 <= 10
    { name: 'b', srcStartFrame: 0, srcEndFrame: 4, placementFrame: 5 }, // == prev, 未跨越
    { name: 'c', srcStartFrame: 0, srcEndFrame: 4, placementFrame: 10 }, // == curr, 跨越
    { name: 'd', srcStartFrame: 0, srcEndFrame: 4, placementFrame: 11 }, // > curr, 未跨越
  ];
  const triggered = getTriggeredClips(5, 10, clips);
  assert.deepEqual(
    triggered.map((c) => c.name),
    ['a', 'c'],
  );
});

test('getTriggeredClips returns empty when frame does not advance', () => {
  const clips = [{ name: 'a', srcStartFrame: 0, srcEndFrame: 4, placementFrame: 5 }];
  assert.deepEqual(getTriggeredClips(10, 10, clips), []);
});

test('getTriggeredClips returns empty on backward transition (scrub / loop wrap)', () => {
  const clips = [{ name: 'a', srcStartFrame: 0, srcEndFrame: 4, placementFrame: 5 }];
  assert.deepEqual(getTriggeredClips(10, 3, clips), []);
});

test('getTriggeredClips handles empty clips', () => {
  assert.deepEqual(getTriggeredClips(0, 10, []), []);
});

test('getTriggeredClips triggers each of multiple crossed clips independently', () => {
  const clips = [
    { name: 'a', srcStartFrame: 0, srcEndFrame: 2, placementFrame: 8 },
    { name: 'b', srcStartFrame: 0, srcEndFrame: 2, placementFrame: 12 },
    { name: 'c', srcStartFrame: 0, srcEndFrame: 2, placementFrame: 15 }, // > curr(14)
  ];
  const triggered = getTriggeredClips(5, 14, clips);
  assert.deepEqual(
    triggered.map((c) => c.name),
    ['a', 'b'],
  );
});

// --- createAudioPlaybackEngine（mock AudioContext，断言 start 的 offset/duration）---

function mockAudioContext() {
  const sources = [];
  const ctx = {
    currentTime: 0,
    destination: { _dest: true },
    createBufferSource() {
      const src = {
        buffer: null,
        connect() {},
        when: null,
        offset: null,
        duration: null,
        _stopped: false,
        start(when, offset, duration) {
          src.when = when;
          src.offset = offset;
          src.duration = duration;
        },
        stop() {
          src._stopped = true;
        },
        onended: null,
      };
      sources.push(src);
      return src;
    },
    close() {},
  };
  ctx.__sources = sources;
  return ctx;
}

test('playClip calls AudioBufferSourceNode.start with offset/duration derived from sourceFps', () => {
  const ctx = mockAudioContext();
  const engine = createAudioPlaybackEngine(() => ctx);
  engine.setBuffer({ _fake: 'buffer' });
  // srcStartFrame=4, srcEndFrame=9, sourceFps=10 -> offset=0.4, duration=0.5
  engine.playClip({ name: 'x', srcStartFrame: 4, srcEndFrame: 9, placementFrame: 10 }, 10);
  assert.equal(ctx.__sources.length, 1);
  const src = ctx.__sources[0];
  assert.equal(src.when, 0);
  assert.ok(Math.abs(src.offset - 0.4) < 1e-9, `expected offset 0.4, got ${src.offset}`);
  assert.ok(Math.abs(src.duration - 0.5) < 1e-9, `expected duration 0.5, got ${src.duration}`);
});

test('playClip does nothing without a buffer', () => {
  const ctx = mockAudioContext();
  const engine = createAudioPlaybackEngine(() => ctx);
  engine.playClip({ name: 'x', srcStartFrame: 4, srcEndFrame: 9, placementFrame: 10 }, 10);
  assert.equal(ctx.__sources.length, 0);
});

test('playClip skips zero/negative duration clips', () => {
  const ctx = mockAudioContext();
  const engine = createAudioPlaybackEngine(() => ctx);
  engine.setBuffer({ _fake: 'buffer' });
  engine.playClip({ name: 'x', srcStartFrame: 5, srcEndFrame: 5, placementFrame: 10 }, 10);
  assert.equal(ctx.__sources.length, 0);
});

test('playClip ignores non-positive sourceFps', () => {
  const ctx = mockAudioContext();
  const engine = createAudioPlaybackEngine(() => ctx);
  engine.setBuffer({ _fake: 'buffer' });
  engine.playClip({ name: 'x', srcStartFrame: 4, srcEndFrame: 9, placementFrame: 10 }, 0);
  assert.equal(ctx.__sources.length, 0);
});

test('stopAll stops all active sources', () => {
  const ctx = mockAudioContext();
  const engine = createAudioPlaybackEngine(() => ctx);
  engine.setBuffer({ _fake: 'buffer' });
  engine.playClip({ name: 'a', srcStartFrame: 0, srcEndFrame: 4, placementFrame: 1 }, 10);
  engine.playClip({ name: 'b', srcStartFrame: 0, srcEndFrame: 4, placementFrame: 2 }, 10);
  assert.equal(ctx.__sources.length, 2);
  engine.stopAll();
  assert.ok(ctx.__sources.every((s) => s._stopped), 'all sources stopped');
  // 再 stopAll 幂等，不抛错
  engine.stopAll();
});

// --- createAudioSyncController（帧跨越 -> 播放；scrub/步进 -> 静音；多片段各触各的）---

function mockEngine() {
  const calls = [];
  return {
    calls,
    setBuffer() {},
    hasBuffer() {
      return true;
    },
    playClip(clip, fps) {
      calls.push({ type: 'play', clip, fps });
    },
    stopAll() {
      calls.push({ type: 'stop' });
    },
    dispose() {},
  };
}

test('controller plays crossed clips on forward frame advance with correct sourceFps', () => {
  const engine = mockEngine();
  const audioStore = {
    clips: [{ name: 'a', srcStartFrame: 0, srcEndFrame: 4, placementFrame: 10 }],
    sourceFps: 24,
    loaded: true,
  };
  const ctrl = createAudioSyncController({ audioStore, engine });
  ctrl.onFrameAdvance(5, 12); // 跨越 placementFrame 10
  assert.equal(engine.calls.length, 1);
  assert.equal(engine.calls[0].type, 'play');
  assert.equal(engine.calls[0].clip.placementFrame, 10);
  assert.equal(engine.calls[0].fps, 24);
});

test('controller does not trigger on backward / scrub transition', () => {
  const engine = mockEngine();
  const audioStore = {
    clips: [{ name: 'a', srcStartFrame: 0, srcEndFrame: 4, placementFrame: 10 }],
    sourceFps: 24,
    loaded: true,
  };
  const ctrl = createAudioSyncController({ audioStore, engine });
  ctrl.onFrameAdvance(12, 5); // 后退（scrub / wrap）
  assert.equal(engine.calls.length, 0);
});

test('controller triggers each of multiple clips independently', () => {
  const engine = mockEngine();
  const audioStore = {
    clips: [
      { name: 'a', srcStartFrame: 0, srcEndFrame: 2, placementFrame: 8 },
      { name: 'b', srcStartFrame: 0, srcEndFrame: 2, placementFrame: 12 },
      { name: 'c', srcStartFrame: 0, srcEndFrame: 2, placementFrame: 25 }, // 未跨越
    ],
    sourceFps: 10,
    loaded: true,
  };
  const ctrl = createAudioSyncController({ audioStore, engine });
  ctrl.onFrameAdvance(5, 20); // 跨越 8 与 12
  assert.deepEqual(
    engine.calls.filter((c) => c.type === 'play').map((c) => c.clip.name),
    ['a', 'b'],
  );
});

test('controller reads clips/sourceFps live (reflects store changes after creation)', () => {
  const engine = mockEngine();
  const audioStore = {
    clips: [],
    sourceFps: 10,
    loaded: true,
  };
  const ctrl = createAudioSyncController({ audioStore, engine });
  ctrl.onFrameAdvance(0, 10);
  assert.equal(engine.calls.length, 0, 'no clips initially');
  // 模拟 store 变化：新增片段
  audioStore.clips = [{ name: 'late', srcStartFrame: 0, srcEndFrame: 2, placementFrame: 5 }];
  ctrl.onFrameAdvance(0, 10);
  assert.equal(engine.calls.length, 1);
  assert.equal(engine.calls[0].clip.name, 'late');
});

test('controller does not trigger when audio is not loaded', () => {
  const engine = mockEngine();
  const audioStore = {
    clips: [{ name: 'a', srcStartFrame: 0, srcEndFrame: 2, placementFrame: 5 }],
    sourceFps: 10,
    loaded: false,
  };
  const ctrl = createAudioSyncController({ audioStore, engine });
  ctrl.onFrameAdvance(0, 10);
  assert.equal(engine.calls.length, 0, 'no trigger when timeline not loaded');
});

test('controller stopAll on manual frame change, but not on tick advance', () => {
  const engine = mockEngine();
  const audioStore = {
    clips: [{ name: 'a', srcStartFrame: 0, srcEndFrame: 2, placementFrame: 10 }],
    sourceFps: 10,
    loaded: true,
  };
  const ctrl = createAudioSyncController({ audioStore, engine });

  // tick 推进到 12（onFrameAdvance 设置 lastTickFrame=12）
  ctrl.onFrameAdvance(5, 12);
  ctrl.onFrameChanged(12); // 与 lastTickFrame 一致 -> 非手动 -> 不 stop
  assert.equal(engine.calls.some((c) => c.type === 'stop'), false);

  // 手动 scrub 到 7（无 onFrameAdvance，lastTickFrame 仍为 12）-> stop
  engine.calls.length = 0;
  ctrl.onFrameChanged(7);
  assert.equal(engine.calls.some((c) => c.type === 'stop'), true);
});

// --- 端到端链路：帧跨越 placementFrame -> AudioBufferSourceNode.start 正确 offset/duration ---

test('frame advance crossing a placementFrame triggers start with correct offset/duration', () => {
  const ctx = mockAudioContext();
  const engine = createAudioPlaybackEngine(() => ctx);
  engine.setBuffer({ _fake: 'buffer' });
  const audioStore = {
    clips: [{ name: 'step', srcStartFrame: 6, srcEndFrame: 12, placementFrame: 10 }],
    sourceFps: 30,
    loaded: true,
  };
  const ctrl = createAudioSyncController({ audioStore, engine });
  ctrl.onFrameAdvance(8, 11); // 跨越 placementFrame 10
  assert.equal(ctx.__sources.length, 1);
  // offset = 6/30 = 0.2；duration = (12-6)/30 = 0.2
  assert.ok(Math.abs(ctx.__sources[0].offset - 0.2) < 1e-9, `offset ${ctx.__sources[0].offset}`);
  assert.ok(Math.abs(ctx.__sources[0].duration - 0.2) < 1e-9, `duration ${ctx.__sources[0].duration}`);
});

// ---------------------------------------------------------------------------
// Player store：frame-advance hook 仅在 tick() 连续播放时触发，scrub/步进不触发
// ---------------------------------------------------------------------------

async function setupPlayerStore() {
  createScriptedPyWebViewBridge({});
  const { usePlayerStore } = await loadFrontendModule('/src/stores/player.ts');
  const { setActivePinia } = await import('pinia');
  const { createPinia } = await import('pinia');
  setActivePinia(createPinia());
  const store = usePlayerStore();
  // 填充 frames 与播放区间，使导航函数无需 api 即可工作
  store.$patch({
    frames: Array.from({ length: 20 }, (_, i) => ({ path: `f${i}`, url: `u${i}` })),
    startFrame: 0,
    endFrame: 19,
    currentIndex: 5,
  });
  return { store };
}

test('goToFrame (scrub) does NOT fire the frame-advance hook', async () => {
  const { store } = await setupPlayerStore();
  let calls = 0;
  store.setFrameAdvanceHook(() => {
    calls += 1;
  });
  store.goToFrame(10);
  assert.equal(calls, 0, 'goToFrame must not fire the continuous-play frame-advance hook');
});

test('nextFrame and prevFrame do NOT fire the frame-advance hook', async () => {
  const { store } = await setupPlayerStore();
  let calls = 0;
  store.setFrameAdvanceHook(() => {
    calls += 1;
  });
  store.nextFrame();
  store.prevFrame();
  assert.equal(calls, 0, 'single-frame stepping must not fire the frame-advance hook');
});

test('manual frame stepping stays at one frame when frame_interval is greater than one', async () => {
  const { store } = await setupPlayerStore();
  store.frameInterval = 5;

  store.nextFrame();
  assert.equal(store.currentIndex, 6);
  store.prevFrame();
  assert.equal(store.currentIndex, 5);
});

test('setFrameAdvanceHook(null) unregisters without throwing', async () => {
  const { store } = await setupPlayerStore();
  store.setFrameAdvanceHook(() => {});
  assert.doesNotThrow(() => store.setFrameAdvanceHook(null));
});

// 防御：computePeaks 仍可用（回归守卫）
test('computePeaks still works (regression guard)', () => {
  assert.deepEqual(computePeaks(new Float32Array([0.1, -0.5]), 1)[0] - 0.5 < 1e-6, true);
});
