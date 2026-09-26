import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { after, test } from 'node:test';
import {
  closeFrontendHarness,
  createScriptedPyWebViewBridge,
  loadFrontendModule,
} from './scripted-pywebview-bridge.mjs';

after(closeFrontendHarness);

test('seedream API getHandoffImage calls the backend handoff method with local id and attempt', async () => {
  const bridge = createScriptedPyWebViewBridge({
    seedream_get_handoff_image: [{ resolve: { success: true, data: { local_path: '/cache/img.jpg' } } }],
  });
  const { seedreamApi } = await loadFrontendModule('/src/api/index.ts');

  const result = await seedreamApi.getHandoffImage('batch-1', 2);

  assert.deepEqual(result, { success: true, data: { local_path: '/cache/img.jpg' } });
  assert.deepEqual(bridge.calls, [
    { method: 'seedream_get_handoff_image', args: ['batch-1', 2] },
  ]);
});

test('SeedanceCreate delegates a handoff query to the shared creation-session action', async () => {
  const [source, workspaceSource] = await Promise.all([
    readFile(new URL('../src/views/SeedanceCreate.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/stores/aiCreation.ts', import.meta.url), 'utf8'),
  ]);

  // Detects handoff query param.
  assert.match(source, /route\.query\.handoff/);
  assert.match(source, /workspace\.handoffCandidateToVideo\(handoffId, attemptIndex\)/);
  // The shared action keeps the safe local-path and thumbnail API boundary.
  assert.match(workspaceSource, /api\.seedream\.getHandoffImage/);
  assert.match(workspaceSource, /api\.frame\.getFrameThumbnail/);
  assert.match(workspaceSource, /field: VideoFrameField = 'first_frame'/);
  assert.match(workspaceSource, /videoDraft\[field\] = localPath/);
  assert.match(workspaceSource, /videoPreviewUrls\[field\] = `data:image\/png;base64,\$\{thumbnail\}`/);
});

test('SeedanceCreate handoff path does not submit a video task or copy the image prompt', async () => {
  const source = await readFile(
    new URL('../src/views/SeedanceCreate.vue', import.meta.url),
    'utf8',
  );

  // Extract the onMounted body to inspect the handoff block in isolation.
  const onMountedMatch = source.match(/onMounted\(async \(\) => \{([\s\S]*?)\n\}\);/);
  assert.ok(onMountedMatch, 'onMounted should exist');
  const onMountedBody = onMountedMatch[1];

  // The handoff block must not call store.createTask (only the paid confirmation does).
  assert.doesNotMatch(onMountedBody, /store\.createTask/);

  // Extract the handoff if-block to verify the prompt is not copied.
  const handoffBlockMatch = onMountedBody.match(/if \(handoffId\) \{([\s\S]*?)\n    \}/);
  assert.ok(handoffBlockMatch, 'handoff if-block should exist');
  const handoffBlock = handoffBlockMatch[1];

  // The video prompt stays empty: the handoff block must not assign form.prompt.
  assert.doesNotMatch(handoffBlock, /form\.prompt\s*=/);
  // The handoff block must not call any video-generation API.
  assert.doesNotMatch(handoffBlock, /api\.seedance\./);
});

test('SeedanceCreate handoff failure sets draftLoadFailed for a recoverable state', async () => {
  const source = await readFile(
    new URL('../src/views/SeedanceCreate.vue', import.meta.url),
    'utf8',
  );

  // draftLoadFailed is set on handoff failure, disabling submit and showing an error.
  assert.match(source, /draftLoadFailed\.value = true/);
  // handoffLoadFailed distinguishes the handoff failure message from continuation failures.
  assert.match(source, /handoffLoadFailed/);
  assert.match(source, /handoffLoadFailed \? t\('seedance\.create\.handoffLoadFailed'\)/);
});

test('SeedanceCreate submit remains guarded by paid confirmation, first_frame and prompt presence', async () => {
  const source = await readFile(
    new URL('../src/views/SeedanceCreate.vue', import.meta.url),
    'utf8',
  );

  // The submit button stays disabled when draftLoadFailed, first_frame, or prompt is missing.
  assert.match(source, /:disabled="submitting \|\| platformGenerationSelected \|\| draftLoadFailed \|\| !form\.first_frame \|\| !form\.prompt\.trim\(\)"/);
  // The paid confirmation action delegates to the single guarded task-creation helper.
  const confirmMatch = source.match(/async function confirmPaidAction\(\)\s*\{[\s\S]*?\n\}/);
  assert.ok(confirmMatch, 'confirmPaidAction function should exist');
  assert.match(confirmMatch[0], /await createPendingTask\(\)/);
  assert.match(source, /async function createPendingTask\(\)[\s\S]*const request = pendingRequest;[\s\S]*store\.createTask\(request\)/);
});
