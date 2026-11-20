import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

test('Step 2 and Step 3 expose reversible non-destructive frame hiding', async () => {
  const editor = await readFile(
    new URL('../src/views/Editor/EditorLayout.vue', import.meta.url),
    'utf8',
  );

  assert.match(editor, /currentStep\.value === 2 \|\| currentStep\.value === 3/);
  assert.match(editor, /api\.frame\.setFrameHidden\(projectId, frame\.filename, true\)/);
  assert.match(editor, /api\.frame\.setFrameHidden\(projectId, filename, false\)/);
  assert.match(editor, /api\.frame\.restoreHiddenFrames\(projectId\)/);
  assert.match(editor, /@restore="restoreHiddenFrame"/);
  const panel = await readFile(
    new URL('../src/components/player/HiddenFramesPanel.vue', import.meta.url),
    'utf8',
  );
  assert.match(panel, /frameVisibility\.hint/);
  assert.match(panel, /\$emit\('restore', card\.filename\)/);
});
