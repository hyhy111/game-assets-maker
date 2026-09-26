import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  frameFromTimelineRatio,
  nearestVisibleFrameIndex,
  sourceFrameFromTimelineFrame,
  timelineFrameForVisibleIndex,
  timelineFramePercent,
} from '../src/components/player/timelineMath.ts';

test('frameFromTimelineRatio snaps pointer positions to integer frame indices', () => {
  assert.equal(frameFromTimelineRatio(0, 100), 0);
  assert.equal(frameFromTimelineRatio(0.504, 100), 50);
  assert.equal(frameFromTimelineRatio(0.506, 100), 50);
  assert.equal(frameFromTimelineRatio(1, 100), 99);
});

test('frameFromTimelineRatio clamps positions outside the track', () => {
  assert.equal(frameFromTimelineRatio(-1, 10), 0);
  assert.equal(frameFromTimelineRatio(2, 10), 9);
  assert.equal(frameFromTimelineRatio(0.5, 0), 0);
});

test('timelineFramePercent uses the same frame axis as pointer conversion', () => {
  assert.equal(timelineFramePercent(0, 100), 0);
  assert.equal(timelineFramePercent(50, 100), (50 / 99) * 100);
  assert.equal(timelineFramePercent(99, 100), 100);
});

test('hidden output frames keep their original timeline slots', () => {
  const visibleFrames = [
    { timeline_index: 0 },
    { timeline_index: 2 },
    { timeline_index: 3 },
  ];

  assert.equal(timelineFrameForVisibleIndex(visibleFrames, 1), 2);
  assert.equal(nearestVisibleFrameIndex(visibleFrames, 1), 1);
  assert.equal(sourceFrameFromTimelineFrame(2, 47, 3), 53);
});
