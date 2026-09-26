import assert from 'node:assert/strict';
import test from 'node:test';
import { nextFocusIndex, trapModalTab } from '../src/modal-focus.ts';

test('nextFocusIndex handles empty, single, forward, backward, and wrapping focus', () => {
  assert.equal(nextFocusIndex(0, 0, false), -1);
  assert.equal(nextFocusIndex(1, 0, false), 0);
  assert.equal(nextFocusIndex(3, 0, false), 1);
  assert.equal(nextFocusIndex(3, 0, true), 2);
  assert.equal(nextFocusIndex(3, 2, false), 0);
});

test('trapModalTab prevents default and focuses forward and backward targets', () => {
  const buttons = [0, 1, 2].map(() => ({ focusCalls: 0, focus() { this.focusCalls += 1; } }));
  const root = { querySelectorAll: () => buttons };
  globalThis.document = { activeElement: buttons[2] };
  const forward = { key: 'Tab', shiftKey: false, prevented: false, preventDefault() { this.prevented = true; } };
  trapModalTab(forward, root);
  assert.equal(forward.prevented, true); assert.equal(buttons[0].focusCalls, 1);
  globalThis.document.activeElement = buttons[0];
  const backward = { key: 'Tab', shiftKey: true, prevented: false, preventDefault() { this.prevented = true; } };
  trapModalTab(backward, root);
  assert.equal(backward.prevented, true); assert.equal(buttons[2].focusCalls, 1);
});
