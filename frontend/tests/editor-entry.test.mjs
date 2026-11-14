import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

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

test('the editor loads source frames beyond the first 500 and discards stale later pages', async () => {
  const source = await readFile(new URL('../src/views/Editor/EditorLayout.vue', import.meta.url), 'utf8');
  const method = source.slice(source.indexOf('async function loadFramesForStep('), source.indexOf('async function hideCurrentFrame('));
  const javascript = ts.transpileModule(method, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;
  for (const stale of [false, true]) {
    const project = { value: { id: 'hero/idle' } };
    const calls = [];
    let loaded = [];
    let range;
    const frames = Array.from({ length: 550 }, (_, index) => ({ index }));
    const load = new Function('api', 'playerStore', 'currentProject', 'currentStep', 'hiddenFrames',
      'timelineFrameCount', 's1Params', 'projectStore', 'logEvent',
      `let frameLoadRequestId = 0; ${javascript}; return loadFramesForStep;`)(
      { frame: { async getFrames(_id, _step, page) {
        calls.push(page);
        if (page === 2 && stale) project.value = { id: 'hero/run' };
        return { success: true, total: 550, total_pages: 2, frames: frames.slice((page - 1) * 500, page * 500) };
      } } },
      { loadFrames(value) { loaded = value; }, setPlaybackRange(...args) { range = args; } },
      project, { value: 1 }, { value: [] }, { value: 0 },
      { value: { start_frame: 0, end_frame: 549, frame_interval: 3 } }, {}, () => {},
    );
    assert.equal(await load(1), !stale);
    assert.deepEqual(calls, [1, 2]);
    assert.equal(loaded.length, stale ? 0 : 550);
    assert.deepEqual(range, stale ? undefined : [0, 549, 3]);
  }
});
