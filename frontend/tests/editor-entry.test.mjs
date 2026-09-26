import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

test('opening an editor resets its step and ignores stale frame-load results', async () => {
  const editor = await readFile(
    new URL('../src/views/Editor/EditorLayout.vue', import.meta.url),
    'utf8',
  );

  assert.match(editor, /processStore\.goToStep\(1\);/);
  assert.match(editor, /const requestId = \+\+frameLoadRequestId;/);
  assert.match(editor, /currentProject\.value\?\.id === project\.id/);
  assert.match(editor, /await loadFramesForStep\(currentStep\.value\);/);
});
