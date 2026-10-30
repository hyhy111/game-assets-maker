import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { closeFrontendHarness, createScriptedPyWebViewBridge, loadFrontendModule } from './scripted-pywebview-bridge.mjs';

after(closeFrontendHarness);

test('manual frame edit bridge pins the requested step for open and save', async () => {
  const bridge = createScriptedPyWebViewBridge({
    get_editable_frame: [{resolve: {image_data_url: 'frame2', revision: 'r2'}}, {resolve: {image_data_url: 'frame3', revision: 'r3'}}],
    save_frame_edit: [{resolve: {success: true}}, {resolve: {success: true}}],
  });
  const {api} = await loadFrontendModule('/src/api/index.ts');
  const second = await api.frame.getEditableFrame('hero/idle', 'frame.png', 2);
  await api.frame.saveFrameEdit('hero/idle', 'frame.png', second.image_data_url, second.revision, 2);
  const third = await api.frame.getEditableFrame('hero/idle', 'frame.png');
  await api.frame.saveFrameEdit('hero/idle', 'frame.png', third.image_data_url, third.revision);
  assert.deepEqual(bridge.calls, [
    {method: 'get_editable_frame', args: ['hero/idle', 'frame.png', 2]},
    {method: 'save_frame_edit', args: ['hero/idle', 'frame.png', 'frame2', 'r2', 2]},
    {method: 'get_editable_frame', args: ['hero/idle', 'frame.png', 3]},
    {method: 'save_frame_edit', args: ['hero/idle', 'frame.png', 'frame3', 'r3', 3]},
  ]);
});
