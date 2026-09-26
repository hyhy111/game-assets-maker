import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  computeFrameAlignedPeaks,
  computePeaks,
  detectSoundSegments,
  sliceFrameAlignedPeaks,
} from '../src/composables/audioPeaks.ts';

test('computePeaks returns empty array for empty input', () => {
  assert.deepEqual(computePeaks(new Float32Array(0), 10), []);
});

test('computePeaks returns empty array for zero buckets', () => {
  assert.deepEqual(computePeaks(new Float32Array([0.1, 0.2]), 0), []);
});

test('computePeaks computes max absolute amplitude per bucket', () => {
  // 4 samples, 2 buckets -> bucket 0 = [0.1, -0.5], bucket 1 = [0.3, -0.2]
  const samples = new Float32Array([0.1, -0.5, 0.3, -0.2]);
  const peaks = computePeaks(samples, 2);
  assert.equal(peaks.length, 2);
  assert.ok(Math.abs(peaks[0] - 0.5) < 1e-6, `expected 0.5, got ${peaks[0]}`);
  assert.ok(Math.abs(peaks[1] - 0.3) < 1e-6, `expected 0.3, got ${peaks[1]}`);
});

test('computePeaks handles single sample per bucket', () => {
  const samples = new Float32Array([0.1, 0.5, 0.3, 0.9]);
  const peaks = computePeaks(samples, 4);
  assert.equal(peaks.length, 4);
  // Float32 精度：用近似比较
  assert.ok(Math.abs(peaks[0] - 0.1) < 1e-6, `expected ~0.1, got ${peaks[0]}`);
  assert.ok(Math.abs(peaks[1] - 0.5) < 1e-6, `expected ~0.5, got ${peaks[1]}`);
  assert.ok(Math.abs(peaks[2] - 0.3) < 1e-6, `expected ~0.3, got ${peaks[2]}`);
  assert.ok(Math.abs(peaks[3] - 0.9) < 1e-6, `expected ~0.9, got ${peaks[3]}`);
});

test('computePeaks handles more buckets than samples', () => {
  // 2 samples, 4 buckets -> bucketSize=0.5
  // bucket 0: empty, bucket 1: [0.4], bucket 2: empty, bucket 3: [-0.7]
  const samples = new Float32Array([0.4, -0.7]);
  const peaks = computePeaks(samples, 4);
  assert.equal(peaks.length, 4);
  // 空桶峰值为 0
  assert.equal(peaks[0], 0);
  assert.equal(peaks[2], 0);
  // 非空桶取对应样本的绝对值
  assert.ok(Math.abs(peaks[1] - 0.4) < 1e-6, `expected ~0.4, got ${peaks[1]}`);
  assert.ok(Math.abs(peaks[3] - 0.7) < 1e-6, `expected ~0.7, got ${peaks[3]}`);
});

test('computePeaks returns all zeros for silent input', () => {
  const samples = new Float32Array([0, 0, 0, 0, 0, 0]);
  const peaks = computePeaks(samples, 3);
  assert.deepEqual(peaks, [0, 0, 0]);
});

test('computePeaks clamps values to 0..1 range', () => {
  // PCM 值应在 -1..1，但防御性地 clamp
  const samples = new Float32Array([1.5, -2.0]);
  const peaks = computePeaks(samples, 1);
  assert.ok(peaks[0] <= 1, `expected <= 1, got ${peaks[0]}`);
});

test('frame-aligned clip peaks exactly match the same region of the full waveform', () => {
  const samples = Float32Array.from({ length: 100 }, (_, i) => (i % 10) / 10);
  const fullPeaks = computeFrameAlignedPeaks(samples, {
    sampleRate: 100,
    sourceFps: 10,
    timelineFrames: 10,
    bucketsPerFrame: 2,
  });
  const clipPeaks = sliceFrameAlignedPeaks(fullPeaks, 2, 5, 2);
  const independentlyComputed = computePeaks(samples.subarray(20, 50), 6);

  assert.deepEqual(clipPeaks, independentlyComputed);
});

// --- detectSoundSegments ---

/** 按段构造采样：每段给定长度与幅值（静音用 0）。 */
function samplesFromSegments(spec) {
  const total = spec.reduce((s, p) => s + p.len, 0);
  const out = new Float32Array(total);
  let i = 0;
  for (const p of spec) {
    for (let k = 0; k < p.len; k++) out[i++] = p.amp;
  }
  return out;
}

test('detectSoundSegments returns empty for empty input', () => {
  assert.deepEqual(detectSoundSegments(new Float32Array(0), { sampleRate: 1000 }), []);
});

test('detectSoundSegments returns empty for silence', () => {
  const s = samplesFromSegments([{ len: 200, amp: 0 }]);
  assert.equal(detectSoundSegments(s, { sampleRate: 1000 }).length, 0);
});

test('detectSoundSegments ignores amp below the 0.05 floor', () => {
  const s = samplesFromSegments([
    { len: 40, amp: 0 },
    { len: 100, amp: 0.03 },
    { len: 40, amp: 0 },
  ]);
  assert.equal(detectSoundSegments(s, { sampleRate: 1000 }).length, 0);
});

test('detectSoundSegments uses 10 percent of the range peak as the adaptive threshold', () => {
  const s = samplesFromSegments([
    { len: 100, amp: 1 },
    { len: 100, amp: 0 },
    { len: 100, amp: 0.12 },
  ]);
  assert.equal(detectSoundSegments(s, { sampleRate: 1000 }).length, 2);
});

test('detectSoundSegments detects a single loud segment', () => {
  // sampleRate=1000 => 1 sample = 1ms；windowMs=20 => 20 样本/窗
  const s = samplesFromSegments([
    { len: 40, amp: 0 },
    { len: 100, amp: 0.5 },
    { len: 60, amp: 0 },
  ]);
  const segs = detectSoundSegments(s, { sampleRate: 1000 });
  assert.equal(segs.length, 1);
  assert.ok(segs[0].startSample <= 40, `start ${segs[0].startSample}`);
  assert.ok(segs[0].endSample >= 140, `end ${segs[0].endSample}`);
});

test('detectSoundSegments keeps two segments when gap > mergeGapMs', () => {
  const s = samplesFromSegments([
    { len: 40, amp: 0 },
    { len: 60, amp: 0.5 },
    { len: 100, amp: 0 }, // 100ms gap > 80
    { len: 60, amp: 0.5 },
    { len: 40, amp: 0 },
  ]);
  assert.equal(detectSoundSegments(s, { sampleRate: 1000 }).length, 2);
});

test('detectSoundSegments merges two segments when gap < mergeGapMs', () => {
  const s = samplesFromSegments([
    { len: 40, amp: 0 },
    { len: 60, amp: 0.5 },
    { len: 40, amp: 0 }, // 40ms gap < 80
    { len: 60, amp: 0.5 },
    { len: 40, amp: 0 },
  ]);
  assert.equal(detectSoundSegments(s, { sampleRate: 1000 }).length, 1);
});

test('detectSoundSegments keeps strong short peaks but drops weak short segments', () => {
  const s = samplesFromSegments([
    { len: 20, amp: 0.8 }, // strong peak: keep even though 20ms < 50ms
    { len: 100, amp: 0 },
    { len: 20, amp: 0.2 }, // weak short segment: still drop
    { len: 100, amp: 0 },
    { len: 100, amp: 1 }, // establishes the range maximum
  ]);
  const segs = detectSoundSegments(s, { sampleRate: 1000, minSegmentMs: 50 });
  assert.equal(segs.length, 2);
  assert.deepEqual(segs[0], { startSample: 0, endSample: 20 });
});
