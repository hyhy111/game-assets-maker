import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';

const playerControlsUrl = new URL('../src/components/player/PlayerControls.vue', import.meta.url);
const audioTimelineUrl = new URL('../src/components/player/AudioTimeline.vue', import.meta.url);
const audioTimelineStoreUrl = new URL('../src/stores/audioTimeline.ts', import.meta.url);
const rangeSliderUrl = new URL('../src/components/player/RangeSlider.vue', import.meta.url);

test('audio playback runtime belongs to persistent player controls, not the collapsible editor', async () => {
  const [controls, timeline] = await Promise.all([
    readFile(playerControlsUrl, 'utf8'),
    readFile(audioTimelineUrl, 'utf8'),
  ]);

  assert.match(controls, /createAudioPlaybackEngine/);
  assert.match(controls, /setFrameAdvanceHook/);
  assert.doesNotMatch(timeline, /setFrameAdvanceHook/);
});

test('range track background click only updates the playhead', async () => {
  const source = await readFile(rangeSliderUrl, 'utf8');
  const handler = source.match(/function onTrackClick\(e: MouseEvent\) \{([\s\S]*?)\n\}/)?.[1] ?? '';

  assert.match(handler, /update:currentFrame/);
  assert.doesNotMatch(handler, /update:startFrame/);
  assert.doesNotMatch(handler, /update:endFrame/);
});

test('audio editor exposes an explicit selection audition action', async () => {
  const timeline = await readFile(audioTimelineUrl, 'utf8');
  assert.match(timeline, /试听选区/);
  assert.match(timeline, /previewSelection/);
});

test('source and clip waveform tracks use the same height and shared peak data', async () => {
  const timeline = await readFile(audioTimelineUrl, 'utf8');

  assert.match(timeline, /ref="waveformRef"[\s\S]*?class="[^"]*h-20/);
  assert.match(timeline, /ref="clipTrackRef"[\s\S]*?class="[^"]*h-20/);
  assert.match(timeline, /sliceFrameAlignedPeaks/);
});

test('opening the audio editor does not snap frame selection to frame_interval', async () => {
  const timeline = await readFile(audioTimelineUrl, 'utf8');

  assert.doesNotMatch(timeline, /setAudioSnap\(true\)/);
  assert.match(timeline, /frameFromTimelineRatio/);
});

test('all steps expose audio playback control while only step 1 exposes the audio editor', async () => {
  const [controls, store] = await Promise.all([
    readFile(playerControlsUrl, 'utf8'),
    readFile(audioTimelineStoreUrl, 'utf8'),
  ]);

  assert.match(controls, /data-test="audio-track-toggle"/);
  assert.match(controls, /:aria-expanded="showAudioTimeline"/);
  assert.match(controls, /audio-track-wave--active/);
  assert.match(controls, /@keyframes audio-track-wave/);
  assert.equal((controls.match(/data-test="audio-mute-toggle"/g) ?? []).length, 1);
  assert.match(controls, /:aria-pressed="!audioPlaybackEnabled"/);
  assert.match(controls, /:audio-muted="!audioPlaybackEnabled"/);
  assert.match(controls, /const audioPlaybackActive = computed\(\(\) => audioPlaybackEnabled\.value\)/);
  assert.match(controls, /playbackEnabled: audioPlaybackEnabled/);
  assert.doesNotMatch(controls, /const audioPlaybackEnabled = ref\(true\)/);
  assert.doesNotMatch(controls, /音效开|音效关/);
  assert.match(controls, /VolumeX/);
  assert.match(controls, /audioPlaybackEnabled/);
  assert.match(controls, /v-if="processStore\.currentStep === 1 && showAudioTimeline"/);
  assert.doesNotMatch(controls, /:clip-only=/);
  assert.match(controls, /timelineFrameForVisibleIndex\(playerStore\.frames, frame\)/);
  assert.match(controls, /nearestVisibleFrameIndex\(playerStore\.frames, value\)/);
  assert.match(store, /const playbackEnabled = ref\(true\)/);
  assert.match(store, /playbackEnabled\.value = true/);
  assert.match(store, /playbackEnabled,/);

  const timeline = await readFile(audioTimelineUrl, 'utf8');
  assert.match(timeline, /audioMuted\?: boolean/);
  assert.match(timeline, /if \(muted\) selectionPreviewEngine\.stopAll\(\)/);
  assert.match(timeline, /props\.audioMuted \|\| !hasValidSelection\.value/);
});
