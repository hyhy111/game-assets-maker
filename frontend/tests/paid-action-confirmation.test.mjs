import assert from 'node:assert/strict';
import test from 'node:test';

import { runConfirmedPaidAction } from '../src/paid-action-confirmation.ts';

test('paid generation actions do not reach the bridge after cancellation', async () => {
  const calls = [];

  const result = await runConfirmedPaidAction(null, async (action) => {
    calls.push(action);
    return 'created-task';
  });

  assert.equal(result, null);
  assert.deepEqual(calls, []);
});

test('paid retry and continuation reach the bridge exactly once after confirmation', async () => {
  for (const action of ['retry', 'continue']) {
    const calls = [];

    const result = await runConfirmedPaidAction(action, async (confirmedAction) => {
      calls.push(confirmedAction);
      return `${confirmedAction}-task`;
    });

    assert.equal(result, `${action}-task`);
    assert.deepEqual(calls, [action]);
  }
});
