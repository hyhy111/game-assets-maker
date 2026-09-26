import assert from 'node:assert/strict';
import test from 'node:test';
import {
  downloadUrlMayBeExpired,
  duplicateTaskSequence,
  seedanceTaskActions,
  seedanceTaskPhase,
  taskTitle,
} from '../src/seedance-ui.ts';

const task = (overrides = {}) => ({
  local_id: 'local-1',
  remote_id: 'remote-1',
  remote_status: 'succeeded',
  sync_status: {},
  download_status: 'downloaded',
  cache_status: 'complete',
  protected: false,
  request: {
    prompt: 'A hero raises a sword',
    model: 'standard',
    resolution: '720p',
    ratio: '16:9',
    duration: 5,
    generate_audio: false,
    return_last_frame: true,
    priority: 0,
    execution_expires_after: 3600,
  },
  input_urls: { first_frame: 'http://localhost/first.png' },
  output_urls: {
    video: 'http://localhost/video.mp4',
    returned_last_frame: 'http://localhost/returned.png',
  },
  file_size_bytes: 1024,
  created_at: '2026-07-26T10:00:00Z',
  updated_at: '2026-07-26T10:05:00Z',
  finished_at: '2026-07-26T10:05:00Z',
  download_url_received_at: '2026-07-26T10:05:00Z',
  elapsed_seconds: 300,
  remote: {},
  error: null,
  retry_of: null,
  handoffs: [],
  ...overrides,
});

test('task presentation maps status to phase and legal actions', () => {
  assert.equal(seedanceTaskPhase(task({ remote_status: 'queued' })), 'queued');
  assert.equal(seedanceTaskPhase(task({ remote_status: 'cancelling' })), 'cancelling');
  assert.equal(seedanceTaskPhase(task({ download_status: 'pending' })), 'downloading');
  assert.deepEqual(seedanceTaskActions(task({ remote_status: 'queued' })), ['cancel', 'regenerate']);
  assert.deepEqual(seedanceTaskActions(task()), ['view', 'continue', 'regenerate', 'delete']);
  assert.deepEqual(
    seedanceTaskActions(task({ download_status: 'failed', output_urls: {} })),
    ['retry-download', 'regenerate', 'delete'],
  );
});

test('download link expiry warning starts after 24 hours without disabling retry', () => {
  const receivedAt = Date.parse('2026-07-26T10:05:00Z');
  assert.equal(downloadUrlMayBeExpired(task(), receivedAt + 24 * 60 * 60 * 1000 - 1), false);
  assert.equal(downloadUrlMayBeExpired(task(), receivedAt + 24 * 60 * 60 * 1000), true);
  assert.equal(downloadUrlMayBeExpired(task({ download_url_received_at: null }), receivedAt + 48 * 60 * 60 * 1000), false);
});

test('identical task requests receive stable chronological circled sequences', () => {
  const first = task({ local_id: 'first', created_at: '2026-07-26T10:00:00Z' });
  const second = task({ local_id: 'second', created_at: '2026-07-26T10:01:00Z' });
  const different = task({
    local_id: 'different',
    created_at: '2026-07-26T10:02:00Z',
    request: { ...task().request, duration: 6 },
  });
  assert.equal(duplicateTaskSequence(first, [second, different, first]), '①');
  assert.equal(duplicateTaskSequence(second, [second, different, first]), '②');
  assert.equal(duplicateTaskSequence(different, [second, different, first]), '');
});

test('task title trims whitespace and truncates safely', () => {
  assert.equal(taskTitle(task({ request: { ...task().request, prompt: '  hello  ' } }), 'Untitled'), 'hello');
  assert.equal(taskTitle(task({ request: { ...task().request, prompt: '' } }), 'Untitled'), 'Untitled');
  assert.equal(taskTitle(task(), 'Untitled', 8), 'A hero…');
});
