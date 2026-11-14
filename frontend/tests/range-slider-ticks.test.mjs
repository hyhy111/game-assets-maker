import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';

after(closeSfcRenderer);

const rangeProps = { totalFrames: 95, startFrame: 14, endFrame: 94, currentFrame: 50 };

function selectedFrames(html) {
  return Array.from(html.matchAll(/data-frame="(\d+)"/g), (match) => Number(match[1]));
}

test('extraction ticks start at the selected start frame and stop at the last sampled frame', async () => {
  const html = await renderSfc('components/player/RangeSlider.vue', {
    props: { ...rangeProps, frameInterval: 3 },
  });

  assert.deepEqual(selectedFrames(html), Array.from({ length: 27 }, (_, index) => 14 + index * 3));
  assert.match(html, /data-test="extraction-ticks"/);
  for (const frame of [14, 50, 92]) {
    assert.ok(html.includes(`style="left:${(frame / 94) * 100}%;" data-frame="${frame}"`));
  }
});

test('custom ticks move on the source axis while keeping their original slot', async () => {
  const html = await renderSfc('components/player/RangeSlider.vue', {
    props: { ...rangeProps, frameInterval: 3, frameOverrides: { 50: 51 }, editable: true },
  });
  const frames = selectedFrames(html);
  assert.equal(frames.length, 27);
  assert.ok(frames.includes(51));
  assert.ok(!frames.includes(50));
  assert.match(html, /aria-label="预览并替换第 51 帧"/);
  assert.ok(html.includes(`style="left:${(51 / 94) * 100}%;" data-frame="51"`));
});

test('automatic interval calculation rebuilds regular ticks after a manual replacement even when the interval stays the same', async () => {
  let extraction;
  await renderSfc('views/Editor/Step1Extract.vue', {
    piniaState: {
      player: {
        frames: Array.from({ length: 95 }, (_, index) => ({ path: `f${index}`, url: `frame-${index}.png` })),
        startFrame: 14, endFrame: 94, currentIndex: 23, frameInterval: 9,
      },
      process: { currentStep: 1, s1Params: {
        start_frame: 14, end_frame: 94, frame_interval: 9, frame_overrides: { 23: 24 },
      } },
    },
    configureSetup(bindings) {
      extraction = bindings;
      bindings.autoCalculateInterval();
    },
  });
  assert.equal(extraction.s1Params.value.frame_interval, 9);
  assert.deepEqual(extraction.s1Params.value.frame_overrides, {});
  assert.deepEqual(extraction.playerStore.playbackFrameIndices, [14, 23, 32, 41, 50, 59, 68, 77, 86]);
});

test('selecting a neighboring frame changes the extraction, playback and reopened picker', async () => {
  let controls;
  const html = await renderSfc('components/player/PlayerControls.vue', {
    piniaState: {
      player: {
        frames: Array.from({ length: 95 }, (_, index) => ({ path: `f${index}`, url: `frame-${index}.png` })),
        startFrame: 14, endFrame: 94, currentIndex: 50, frameInterval: 3,
      },
      process: { currentStep: 1, s1Params: { frame_interval: 3 } },
    },
    configureSetup(bindings) {
      controls = bindings;
      bindings.openFramePicker(50);
    },
  });
  assert.match(html, /data-test="frame-picker"/);
  assert.match(html, /data-candidate="48"/);
  assert.match(html, /data-candidate="52"/);
  assert.match(html, /src="frame-50.png"/);
  assert.equal(controls.playerStore.isPlaying, false);
  controls.selectReplacementFrame(53);
  assert.equal(controls.s1Params.value.frame_overrides, undefined, 'the neighboring selected tick cannot be duplicated');
  controls.selectReplacementFrame(51);
  assert.deepEqual(controls.s1Params.value.frame_overrides, { 50: 51 });
  assert.equal(controls.playerStore.currentIndex, 51);
  assert.equal(controls.playerStore.playbackFrameIndices[12], 51);
  assert.equal(controls.editingBaseFrame.value, null);
  controls.openFramePicker(50);
  assert.equal(controls.framePicker.value.currentFrame, 51);
  controls.selectReplacementFrame(50);
  assert.deepEqual(controls.s1Params.value.frame_overrides, {});
});

test('extraction ticks reflect changed intervals, range bounds and short videos', async () => {
  const cases = [
    [{ frameInterval: 2 }, Array.from({ length: 41 }, (_, index) => 14 + index * 2)],
    [{ startFrame: 15, endFrame: 23, frameInterval: 3 }, [15, 18, 21]],
    [{ startFrame: 20, endFrame: 23, frameInterval: 10 }, [20]],
    [{ startFrame: 23, endFrame: 23, frameInterval: 3 }, [23]],
    [{ totalFrames: 1, startFrame: 0, endFrame: 0, frameInterval: 2 }, [0]],
  ];
  for (const [overrides, expected] of cases) {
    const html = await renderSfc('components/player/RangeSlider.vue', {
      props: { ...rangeProps, ...overrides },
    });
    assert.deepEqual(selectedFrames(html), expected);
  }
});

test('default, every-frame, simple and unloaded timelines omit extraction ticks', async () => {
  for (const overrides of [{}, { frameInterval: 1 }, { simple: true, frameInterval: 3 },
    { totalFrames: 0, frameInterval: 3 }, { frameInterval: 0 }, { frameInterval: 2.5 }]) {
    const html = await renderSfc('components/player/RangeSlider.vue', {
      props: { ...rangeProps, ...overrides },
    });
    assert.doesNotMatch(html, /data-test="extraction-ticks"/);
  }
});

test('player controls supply extraction ticks with the audio track collapsed and expanded', async () => {
  for (const expanded of [false, true]) {
    const html = await renderSfc('components/player/PlayerControls.vue', {
      piniaState: {
        player: {
          frames: Array.from({ length: 95 }, (_, index) => ({ url: `frame-${index}.png` })),
          startFrame: 14,
          endFrame: 94,
          currentIndex: 50,
        },
        process: { currentStep: 1, s1Params: { frame_interval: 3 } },
      },
      configureSetup(bindings) {
        bindings.showAudioTimeline.value = expanded;
      },
    });
    assert.equal((html.match(/data-test="extraction-ticks"/g) ?? []).length, 1);
    assert.deepEqual(selectedFrames(html), Array.from({ length: 27 }, (_, index) => 14 + index * 3));
  }
});
