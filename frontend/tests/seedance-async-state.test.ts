import assert from 'node:assert/strict';
import test from 'node:test';
import {
  SeedanceAsyncGuard,
  mergeTaskSnapshot,
  reconcileCurrentTask,
} from '../src/stores/seedance-async-state.ts';

type Task = {
  local_id: string;
  created_at: string;
  label: string;
};

const oldest: Task = { local_id: 'oldest', created_at: '2026-07-17T00:00:00Z', label: 'oldest' };
const changed: Task = { local_id: 'changed', created_at: '2026-07-17T01:00:00Z', label: 'snapshot' };
const createdByEvent: Task = { local_id: 'event', created_at: '2026-07-17T02:00:00Z', label: 'event' };

test('merges a list snapshot without losing event changes or resurrecting deletions', () => {
  const snapshotRevisions = new Map([
    ['oldest', 0],
    ['changed', 0],
  ]);
  const currentRevisions = new Map([
    ['oldest', 0],
    ['changed', 1],
    ['event', 1],
  ]);
  const merged = mergeTaskSnapshot(
    [changed],
    [
      { ...changed, label: 'event update' },
      createdByEvent,
    ],
    snapshotRevisions,
    currentRevisions
  );

  assert.deepEqual(merged, [
    createdByEvent,
    { ...changed, label: 'event update' },
  ]);
});

test('only the latest resource request may commit and only the latest operation may change errors', () => {
  const guard = new SeedanceAsyncGuard();
  const firstSettings = guard.begin('settings');
  const latestCache = guard.begin('cache');
  const secondSettings = guard.begin('settings');

  assert.equal(guard.isResourceCurrent(firstSettings), false);
  assert.equal(guard.isResourceCurrent(secondSettings), true);
  assert.equal(guard.isResourceCurrent(latestCache), true);
  assert.equal(guard.isLatestOperation(firstSettings), false);
  assert.equal(guard.isLatestOperation(latestCache), false);
  assert.equal(guard.isLatestOperation(secondSettings), true);
});

test('reconciles the selected task to the accepted snapshot object', () => {
  const selected = { ...changed, label: 'before refresh' };
  const snapshotTask = { ...changed, label: 'snapshot update' };

  assert.equal(
    reconcileCurrentTask(selected, [snapshotTask], new Map([['changed', 0]]), new Map([['changed', 0]])),
    snapshotTask
  );
});

test('clears a selected task only when its accepted snapshot safely omits it', () => {
  assert.equal(
    reconcileCurrentTask(changed, [], new Map([['changed', 0]]), new Map([['changed', 0]])),
    null
  );
});

test('keeps the selected task updated by an event after a list request started', () => {
  const eventTask = { ...changed, label: 'event update' };
  const merged = mergeTaskSnapshot(
    [changed],
    [eventTask],
    new Map([['changed', 0]]),
    new Map([['changed', 1]])
  );

  assert.equal(
    reconcileCurrentTask(eventTask, merged, new Map([['changed', 0]]), new Map([['changed', 1]])),
    eventTask
  );
});
