import assert from 'node:assert/strict';
import test from 'node:test';
import { correctDuration, createRequest, DURATION_OPTIONS, validateCreateForm, validationIssueForApiError } from '../src/seedance-ui.ts';

const validForm = {
  first_frame: '/tmp/first.png', last_frame: null, prompt: 'a hero raises a sword', model: 'standard',
  resolution: '720p', ratio: 'adaptive', duration: -1, generate_audio: false,
  return_last_frame: false, priority: 0, execution_expires_after: 3600,
};

test('local validation exposes stable localization keys instead of English sentences', () => {
  const errors = validateCreateForm({ ...validForm, first_frame: '', duration: 3 });
  assert.deepEqual(errors.first_frame, { field: 'first_frame', code: 'FIRST_FRAME_REQUIRED', key: 'seedance.validation.firstFrameRequired' });
  assert.deepEqual(errors.duration, { field: 'duration', code: 'INVALID_DURATION', key: 'seedance.validation.invalidDuration' });
});

test('video duration UI options are limited to four through six seconds', () => {
  assert.deepEqual(DURATION_OPTIONS, [4, 5, 6]);
  assert.equal(correctDuration(-1), 4);
  assert.equal(correctDuration(5), 5);
  assert.equal(correctDuration(15), 4);
});

test('empty or whitespace-only prompt is rejected before preflight with a localized required error', () => {
  assert.deepEqual(
    validateCreateForm({ ...validForm, prompt: '' }).prompt,
    { field: 'prompt', code: 'PROMPT_REQUIRED', key: 'seedance.validation.promptRequired' },
  );
  assert.deepEqual(
    validateCreateForm({ ...validForm, prompt: '   ' }).prompt,
    { field: 'prompt', code: 'PROMPT_REQUIRED', key: 'seedance.validation.promptRequired' },
  );
});

test('long prompts remain creatable despite exceeding the displayed recommendation', () => {
  const errors = validateCreateForm({ ...validForm, prompt: `中${'a'.repeat(500)}` });
  assert.equal(errors.prompt, undefined);
});

test('create request retains selected first and optional last frame paths exactly', () => {
  const request = createRequest({ ...validForm, first_frame: '/tmp/first.webp', last_frame: '/tmp/last.heic' });
  assert.equal(request.first_frame, '/tmp/first.webp');
  assert.equal(request.last_frame, '/tmp/last.heic');
  assert.equal(createRequest({ ...validForm, last_frame: '' }).last_frame, null);
});

test('API validation maps known codes and safely localizes unknown failures', () => {
  assert.deepEqual(
    validationIssueForApiError({ field: 'payload', code: 'PAYLOAD_TOO_LARGE' }),
    { field: 'body', code: 'PAYLOAD_TOO_LARGE', key: 'seedance.validation.payloadTooLarge' },
  );
  assert.deepEqual(
    validationIssueForApiError({ field: null, code: 'SOMETHING_NEW' }),
    { field: 'body', code: 'SOMETHING_NEW', key: 'seedance.validation.generic' },
  );
});

test('create request fixes priority and expiry to the application defaults', () => {
  const request = createRequest({ ...validForm, priority: 9, execution_expires_after: 3600 });
  assert.equal(request.priority, 0);
  assert.equal(request.execution_expires_after, 172800);
});

test('API priority and expiry fields remain localized inline issues', () => {
  assert.deepEqual(
    validationIssueForApiError({ field: 'priority', code: 'INVALID_PRIORITY' }),
    { field: 'priority', code: 'INVALID_PRIORITY', key: 'seedance.validation.invalidPriority' },
  );
  assert.deepEqual(
    validationIssueForApiError({ field: 'execution_expires_after', code: 'INVALID_EXPIRY' }),
    { field: 'execution_expires_after', code: 'INVALID_EXPIRY', key: 'seedance.validation.invalidExpiry' },
  );
});
