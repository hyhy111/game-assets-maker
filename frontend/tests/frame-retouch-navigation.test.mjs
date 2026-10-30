import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { after, test } from 'node:test';
import ts from 'typescript';
import { computed, nextTick, ref } from 'vue';
import { createPinia, setActivePinia } from 'pinia';
import { closeFrontendHarness, createScriptedPyWebViewBridge, loadFrontendModule } from './scripted-pywebview-bridge.mjs';

after(closeFrontendHarness);

const source = await readFile(new URL('../src/views/Editor/EditorLayout.vue', import.meta.url), 'utf8');
const script = source.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1].replace(/^import .*;$/gm, '');
const javascript = ts.transpileModule(script, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;

function editor(step = 3, completed = true) {
  const currentProject = ref({ id: 'hero/idle', steps: { 2: { completed: true }, 3: { completed: true } } });
  const currentStep = ref(step);
  const player = { setNavigationGuard() {}, replaceFrameImage() {}, pause() {} };
  const process = { setNavigationGuard() {}, isProcessing: false };
  const saves = [];
  let fail = false;
  const api = { frame: { async saveFrameEdit(...args) { saves.push(args); if (fail) throw Error('save failed'); return { revision: `r${saves.length}` }; } } };
  const names = ['computed', 'nextTick', 'onBeforeUnmount', 'onMounted', 'ref', 'watch', 'onBeforeRouteLeave',
    'useRouter', 'useRoute', 'useProjectStore', 'useProcessStore', 'usePlayerStore', 'useI18n', 'storeToRefs',
    'api', 'Step1Extract', 'Step2Background', 'Step3PostProcess'];
  const setup = new Function(...names, `${javascript}\nreturn { frameEditor, frameEditorRef, frameEditorTool, frameEditorError, navigationPending, beforeFrameNavigation, resolveFrameNavigation, saveCurrentFrameEdit, selectFrameTool, frameRetouchEnabled, frameVisibilityEnabled, onToolShortcut };`);
  const state = setup(computed, nextTick, () => {}, () => {}, ref, () => {}, () => {},
    () => ({}), () => ({}), () => ({ isStepCompleted: () => completed }), () => process, () => player,
    () => ({ t: key => key }), () => ({ currentProject, currentStep, s1Params: ref({}) }), api, null, null, null);
  state.frameEditor.value = { projectId: 'hero/idle', filename: '1.png', imageUrl: 'original', revision: 'r0', step };
  state.frameEditorTool.value = 'brush';
  state.frameEditorRef.value = { dirty: true, busy: false, markSaved() { this.dirty = false; }, getImageData: () => 'edited' };
  return { ...state, player, process, currentStep, saves, failSaving(value) { fail = value; } };
}

test('saving keeps the current frame and tool, resets the edit baseline, and uses the returned revision on the next save', async () => {
  const state = editor();
  assert.equal(await state.saveCurrentFrameEdit('first'), true);
  assert.equal(state.frameEditor.value.filename, '1.png');
  assert.equal(state.frameEditorTool.value, 'brush');
  assert.equal(state.frameEditorRef.value.dirty, false);
  assert.equal(state.frameEditor.value.revision, 'r1');
  state.frameEditorRef.value.dirty = true;
  await state.saveCurrentFrameEdit('second');
  assert.deepEqual(state.saves.map(call => [call[2], call[3], call[4]]), [['first', 'r0', 3], ['second', 'r1', 3]]);
});

test('browse keeps the edit session and unsaved state; staying cancels only the requested navigation', async () => {
  const state = editor();
  state.selectFrameTool('browse');
  assert.equal(state.frameEditorTool.value, 'browse');
  assert.equal(state.frameEditorRef.value.dirty, true);
  const allowed = state.beforeFrameNavigation();
  assert.equal(state.navigationPending.value, true);
  assert.equal(state.beforeFrameNavigation(), false, 'repeated requests cannot replace the pending decision');
  await state.resolveFrameNavigation('stay');
  assert.equal(await allowed, false);
  assert.equal(state.navigationPending.value, false);
  assert.equal(state.frameEditor.value.filename, '1.png');
  assert.equal(state.frameEditorRef.value.dirty, true);
  assert.equal(state.saves.length, 0);
});

test('a failed save holds navigation and edits; retry saves before permitting the original action', async () => {
  const state = editor();
  state.failSaving(true);
  const allowed = state.beforeFrameNavigation();
  let resumed = false;
  allowed.then(value => { resumed = value; });
  await state.resolveFrameNavigation('save');
  assert.equal(resumed, false);
  assert.equal(state.navigationPending.value, true);
  assert.equal(state.frameEditorRef.value.dirty, true);
  assert.equal(state.frameEditorError.value, 'magicWand.failed');
  state.failSaving(false);
  await state.resolveFrameNavigation('save');
  assert.equal(await allowed, true);
  assert.equal(state.frameEditor.value, null);
  assert.equal(state.navigationPending.value, false);
});

test('discard permits navigation without saving; a clean session exits without prompting', async () => {
  const state = editor();
  const allowed = state.beforeFrameNavigation();
  await state.resolveFrameNavigation('discard');
  assert.equal(await allowed, true);
  assert.equal(state.frameEditor.value, null);
  assert.equal(state.saves.length, 0);
  const clean = editor();
  clean.frameEditorRef.value.dirty = false;
  assert.equal(clean.beforeFrameNavigation(), true);
  assert.equal(clean.navigationPending.value, false);
  assert.equal(clean.frameEditor.value, null);
});

test('player buttons, timeline seeking, playback and step navigation all honor the pending edit decision', async () => {
  createScriptedPyWebViewBridge({});
  const { usePlayerStore } = await loadFrontendModule('/src/stores/player.ts');
  const { useProcessStore } = await loadFrontendModule('/src/stores/process.ts');
  setActivePinia(createPinia());
  const player = usePlayerStore();
  const process = useProcessStore();
  player.frames = [0, 1, 2].map(index => ({ filename: `${index}.png`, path: `${index}.png`, url: `data:${index}` }));
  player.endFrame = 2;
  player.currentIndex = 1;
  player.setNavigationGuard(() => false);
  player.nextFrame(); player.prevFrame(); player.goToFrame(2);
  await player.play();
  assert.equal(player.currentIndex, 1);
  assert.equal(player.isPlaying, false);
  process.setNavigationGuard(() => false);
  process.goToStep(3);
  assert.equal(process.currentStep, 1);
  let allow;
  player.setNavigationGuard(() => new Promise(resolve => { allow = resolve; }));
  const navigating = player.goToFrame(2);
  assert.equal(player.currentIndex, 1);
  allow(true);
  await navigating;
  assert.equal(player.currentIndex, 2);
  process.setNavigationGuard(() => new Promise(resolve => { allow = resolve; }));
  const switching = process.goToStep(3);
  assert.equal(process.currentStep, 1);
  allow(true);
  await switching;
  assert.equal(process.currentStep, 3);
});

test('retouch tools require completed step 3 while frame hiding remains available in step 2', () => {
  for (const step of [1, 2, 3]) {
    const state = editor(step);
    assert.equal(state.frameRetouchEnabled.value, step === 3);
    assert.equal(state.frameVisibilityEnabled.value, step === 2 || step === 3);
  }
  assert.equal(editor(3, false).frameRetouchEnabled.value, false);
});

test('W/E/V switch frame tools and ignore text entry, modifiers, other steps and pending navigation', () => {
  const state = editor();
  const previousElement = globalThis.Element;
  class Target { constructor(editable = false) { this.editable = editable; } closest() { return this.editable; } }
  globalThis.Element = Target;
  try {
    function press(key, options = {}) {
      const event = { key, target: new Target(), preventDefault() { this.defaultPrevented = true; }, ...options };
      state.onToolShortcut(event);
      return event;
    }
    for (const [key, tool] of [['w','wand'], ['e','brush'], ['v','browse'], ['W','wand']]) {
      assert.equal(press(key).defaultPrevented, true);
      assert.equal(state.frameEditorTool.value, tool);
    }
    for (const options of [{target:new Target(true)}, {ctrlKey:true}, {metaKey:true}, {altKey:true}, {repeat:true}, {defaultPrevented:true}]) {
      press('e', options);
      assert.equal(state.frameEditorTool.value, 'wand');
    }
    state.currentStep.value = 2;
    press('e'); assert.equal(state.frameEditorTool.value, 'wand');
    state.currentStep.value = 3;
    state.navigationPending.value = true;
    press('e'); assert.equal(state.frameEditorTool.value, 'wand');
    state.navigationPending.value = false;
    state.process.isProcessing = true;
    press('e'); assert.equal(state.frameEditorTool.value, 'wand');
    state.process.isProcessing = false;
    state.frameEditorRef.value.busy = true;
    press('e'); assert.equal(state.frameEditorTool.value, 'wand');
  } finally {
    if (previousElement === undefined) delete globalThis.Element;
    else globalThis.Element = previousElement;
  }
});
