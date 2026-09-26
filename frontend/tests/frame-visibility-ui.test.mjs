import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

test('Step 2 and Step 3 expose reversible non-destructive frame hiding', async () => {
  const editor = await readFile(
    new URL('../src/views/Editor/EditorLayout.vue', import.meta.url),
    'utf8',
  );

  assert.match(editor, /currentStep\.value === 2 \|\| currentStep\.value === 3/);
  assert.match(editor, /api\.frame\.setFrameHidden\(project\.id, frame\.filename, true\)/);
  assert.match(editor, /api\.frame\.setFrameHidden\(project\.id, filename, false\)/);
  assert.match(editor, /api\.frame\.restoreHiddenFrames\(project\.id\)/);
  assert.match(editor, /frameVisibility\.hint/);
});
