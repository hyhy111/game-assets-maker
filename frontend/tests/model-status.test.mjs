import assert from 'node:assert/strict';
import test from 'node:test';

import {
  canStartStep2,
  modelApproximateSizeMb,
  modelProgressPercent,
  modelStatusPresentation,
} from '../src/model-status.ts';

const status = (phase, overrides = {}) => ({
  model: 'u2net',
  phase,
  downloaded_bytes: null,
  total_bytes: null,
  error: null,
  ...overrides,
});

test('model phases map to stable UI presentation', () => {
  assert.deepEqual(modelStatusPresentation(status('needs_download')), {
    messageKey: 'modelStatus.needsDownload',
    busy: false,
    retryable: false,
    tone: 'info',
  });
  assert.equal(modelStatusPresentation(status('downloading')).messageKey, 'modelStatus.downloading');
  assert.equal(modelStatusPresentation(status('initializing')).messageKey, 'modelStatus.initializing');
  assert.equal(modelStatusPresentation(status('ready')).messageKey, 'modelStatus.ready');
  assert.deepEqual(modelStatusPresentation(status('failed')).retryable, true);
});

test('download progress is only shown when total size is reliable', () => {
  assert.equal(modelProgressPercent(status('downloading', { downloaded_bytes: 5 })), null);
  assert.equal(modelProgressPercent(status('downloading', { downloaded_bytes: 25, total_bytes: 100 })), 25);
  assert.equal(modelProgressPercent(status('initializing', { downloaded_bytes: 100, total_bytes: 100 })), null);
});

test('step 2 is unavailable until step 1 and the model are ready', () => {
  assert.equal(canStartStep2(false, status('ready'), 'u2net'), false);
  assert.equal(canStartStep2(true, status('initializing'), 'u2net'), false);
  assert.equal(canStartStep2(true, status('failed'), 'u2net'), false);
  assert.equal(canStartStep2(true, status('ready'), 'isnet-anime'), false);
  assert.equal(canStartStep2(true, status('ready'), 'u2net'), true);
});

test('supported models expose an honest approximate first-download size', () => {
  assert.equal(modelApproximateSizeMb('u2net'), 176);
  assert.equal(modelApproximateSizeMb('isnet-general-use'), null);
  assert.equal(modelApproximateSizeMb('isnet-anime'), null);
  assert.equal(modelApproximateSizeMb('unknown'), null);
});
