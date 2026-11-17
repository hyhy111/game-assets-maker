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

function editor(step = 3, completed = true, backgroundCompleted = true) {
  const currentProject = ref({ id: 'hero/idle', steps: { 2: { completed: backgroundCompleted }, 3: { completed } } });
  const currentStep = ref(step);
  const player = { setNavigationGuard() {}, replaceFrameImage() {}, pause() {} };
  const process = { setNavigationGuard() {}, applyStepParams() {}, isProcessing: false };
  const saves = [];
  const resets = [];
  const undos = [];
  const refreshes = [];
  const project = {
    isStepCompleted: step => currentProject.value.steps[step]?.completed ?? false,
    async loadProject(id) {
      refreshes.push(id);
      currentProject.value = { ...currentProject.value, steps: { ...currentProject.value.steps, 3: { completed: true } } };
    },
  };
  let fail = false;
  let failReset = false;
  const api = {
    frame: { async saveFrameEdit(...args) { saves.push(args); if (fail) throw Error('save failed'); return { revision: `r${saves.length}` }; } },
    process: {
      async resetPostProcessing(id) { resets.push(id); return !failReset; },
      async undoPostProcessing(id) { undos.push(id); return !failReset; },
    },
  };
  const names = ['computed', 'nextTick', 'onBeforeUnmount', 'onMounted', 'ref', 'watch', 'onBeforeRouteLeave',
    'useRouter', 'useRoute', 'useProjectStore', 'useProcessStore', 'usePlayerStore', 'useI18n', 'storeToRefs',
    'api', 'Step1Extract', 'Step2Background', 'Step3PostProcess'];
  const setup = new Function(...names, `${javascript}\nreturn { frameEditor, frameEditorRef, frameEditorTool, frameEditorError, frameEditorLoading, frameEditorSaving, navigationPending, beforeFrameNavigation, resolveFrameNavigation, saveCurrentFrameEdit, selectFrameTool, frameRetouchEnabled, frameVisibilityEnabled, onToolShortcut, openPostProcessingReset, closePostProcessingReset, resetPostProcessing, postProcessingResetOpen, postProcessingResetError };`);
  const state = setup(computed, nextTick, () => {}, () => {}, ref, () => {}, () => {},
    () => ({}), () => ({}), () => project, () => process, () => player,
    () => ({ t: key => key }), () => ({ currentProject, currentStep, s1Params: ref({}) }), api, null, null, null);
  state.frameEditor.value = { projectId: 'hero/idle', filename: '1.png', imageUrl: 'original', originalImageUrl: 'initial-frame', revision: 'r0', step };
  state.frameEditorTool.value = 'brush';
  state.frameEditorRef.value = { dirty: true, busy: false, markSaved() { this.dirty = false; }, getImageData: () => 'edited' };
  return { ...state, player, process, currentProject, currentStep, saves, resets, undos, refreshes, failSaving(value) { fail = value; }, failReset(value) { failReset = value; } };
}

test('resetting all Step 3 edits requires confirmation and preserves unsaved work on cancel or failure', async () => {
  const state = editor();
  state.openPostProcessingReset();
  assert.equal(state.postProcessingResetOpen.value, true);
  assert.equal(state.beforeFrameNavigation(), false);
  state.closePostProcessingReset();
  await state.resetPostProcessing();
  assert.deepEqual(state.resets, []);
  assert.equal(state.frameEditorRef.value.dirty, true);

  state.openPostProcessingReset();
  state.failReset(true);
  await state.resetPostProcessing();
  assert.equal(state.postProcessingResetOpen.value, true);
  assert.equal(state.postProcessingResetError.value, 'step3.resetAllFailed');
  assert.equal(state.frameEditorRef.value.dirty, true);
  state.failReset(false);
  await state.resetPostProcessing();
  assert.deepEqual(state.resets, ['hero/idle', 'hero/idle']);
  assert.deepEqual(state.refreshes, ['hero/idle']);
  assert.equal(state.frameEditor.value, null);
  assert.equal(state.postProcessingResetOpen.value, false);
  assert.deepEqual(state.saves, []);
});

test('undoing Step 3 requires an available batch and calls only the one-step restore', async () => {
  const state = editor();
  state.openPostProcessingReset('last');
  assert.equal(state.postProcessingResetOpen.value, false);
  state.currentProject.value.steps[3].can_undo_processing = true;
  state.openPostProcessingReset('last');
  assert.equal(state.postProcessingResetOpen.value, true);
  assert.deepEqual(state.undos, []);
  await state.resetPostProcessing();
  assert.deepEqual(state.resets, []);
  assert.deepEqual(state.undos, ['hero/idle']);
  assert.deepEqual(state.refreshes, ['hero/idle']);
  assert.equal(state.postProcessingResetOpen.value, false);
});

test('saving keeps the current frame and tool, resets the edit baseline, and uses the returned revision on the next save', async () => {
  const state = editor();
  assert.equal(await state.saveCurrentFrameEdit('first'), true);
  assert.equal(state.frameEditor.value.filename, '1.png');
  assert.equal(state.frameEditorTool.value, 'brush');
  assert.equal(state.frameEditorRef.value.dirty, false);
  assert.equal(state.frameEditor.value.revision, 'r1');
  assert.equal(state.frameEditor.value.originalImageUrl, 'initial-frame');
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

test('Cmd/Ctrl+S saves the selected wand or eraser frame without leaving the tool', async () => {
  for (const tool of ['wand', 'brush']) {
    for (const modifier of ['metaKey', 'ctrlKey']) {
      const state = editor();
      state.frameEditorTool.value = tool;
      const event = { key: 's', [modifier]: true, preventDefault() { this.defaultPrevented = true; } };
      assert.equal(await state.onToolShortcut(event), true);
      assert.equal(event.defaultPrevented, true);
      assert.deepEqual(state.saves, [['hero/idle', '1.png', 'edited', 'r0', 3]]);
      assert.equal(state.frameEditorRef.value.dirty, false);
      assert.equal(state.frameEditor.value.revision, 'r1');
      assert.equal(state.frameEditorTool.value, tool);
    }
  }
});

test('frame save shortcuts suppress browser saving but do not submit clean, busy or suspended edits twice', async () => {
  for (const configure of [
    state => { state.frameEditorRef.value.dirty = false; },
    state => { state.frameEditorRef.value.busy = true; },
    state => { state.frameEditorLoading.value = true; },
    state => { state.frameEditorSaving.value = true; },
    state => { state.navigationPending.value = true; },
    state => { state.process.isProcessing = true; },
  ]) {
    const state = editor();
    configure(state);
    const event = { key: 's', ctrlKey: true, preventDefault() { this.defaultPrevented = true; } };
    await state.onToolShortcut(event);
    assert.equal(event.defaultPrevented, true);
    assert.equal(state.saves.length, 0);
  }
  const state = editor();
  const event = () => ({ key: 'S', metaKey: true, preventDefault() { this.defaultPrevented = true; } });
  const saving = state.onToolShortcut(event());
  await state.onToolShortcut(event());
  await state.onToolShortcut({ ...event(), repeat: true });
  await saving;
  assert.equal(state.saves.length, 1);
});

test('save shortcuts stay scoped to step 3 retouch tools and preserve failed edits', async () => {
  for (const configure of [
    state => { state.currentStep.value = 2; },
    state => { state.frameEditorTool.value = 'browse'; },
    state => { state.frameEditor.value = null; },
  ]) {
    const state = editor();
    configure(state);
    const event = { key: 's', ctrlKey: true, preventDefault() { this.defaultPrevented = true; } };
    await state.onToolShortcut(event);
    assert.equal(event.defaultPrevented, undefined);
    assert.equal(state.saves.length, 0);
  }
  for (const options of [{ altKey: true }, { shiftKey: true }, { isComposing: true }, { defaultPrevented: true }]) {
    const state = editor();
    await state.onToolShortcut({ key: 's', ctrlKey: true, ...options, preventDefault() { throw Error('shortcut must be ignored'); } });
    assert.equal(state.saves.length, 0);
  }
  const incomplete = editor(3, false, false);
  await incomplete.onToolShortcut({ key: 's', metaKey: true, preventDefault() { throw Error('step 2 must be completed'); } });
  assert.equal(incomplete.saves.length, 0);
  const state = editor();
  state.failSaving(true);
  assert.equal(await state.onToolShortcut({ key: 's', metaKey: true, preventDefault() {} }), false);
  assert.equal(state.frameEditorRef.value.dirty, true);
  assert.equal(state.frameEditorError.value, 'magicWand.failed');
  assert.equal(state.frameEditorTool.value, 'brush');
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

test('step 3 retouch tools are available after step 2 without running step 3', () => {
  for (const step of [1, 2, 3]) {
    const state = editor(step);
    assert.equal(state.frameRetouchEnabled.value, step === 3);
    assert.equal(state.frameVisibilityEnabled.value, step === 2 || step === 3);
  }
  assert.equal(editor(3, false).frameRetouchEnabled.value, true);
  assert.equal(editor(3, false, false).frameRetouchEnabled.value, false);
  assert.equal(editor(3, true, false).frameRetouchEnabled.value, true, 'legacy final-only projects remain editable');
});

test('saving either retouch tool before step 3 processing refreshes the completed project status', async () => {
  for (const tool of ['wand', 'brush']) {
    const state = editor(3, false);
    state.frameEditorTool.value = tool;
    assert.equal(state.currentProject.value.steps[3].completed, false);
    assert.equal(await state.saveCurrentFrameEdit('edited'), true);
    assert.deepEqual(state.refreshes, ['hero/idle']);
    assert.equal(state.currentProject.value.steps[3].completed, true);
    assert.equal(state.frameEditorTool.value, tool);
  }
  const failed = editor(3, false);
  failed.failSaving(true);
  assert.equal(await failed.saveCurrentFrameEdit('edited'), false);
  assert.deepEqual(failed.refreshes, []);
  assert.equal(failed.currentProject.value.steps[3].completed, false);
});

test('V enters move-canvas mode in every step and preserves unsaved retouch edits', () => {
  const previousElement = globalThis.Element;
  class Target { constructor(editable = false) { this.editable = editable; } closest() { return this.editable; } }
  globalThis.Element = Target;
  const prepare = step => {
    const state = editor(step);
    if (step !== 3) {
      state.frameEditor.value = null;
      state.frameEditorRef.value = null;
      state.frameEditorTool.value = 'browse';
    } else {
      state.frameEditorTool.value = 'brush';
      state.frameEditorRef.value.dirty = true;
    }
    return state;
  };
  const press = (state, options = {}) => {
    const event = { key: 'v', target: new Target(), preventDefault() { this.defaultPrevented = true; }, ...options };
    state.onToolShortcut(event);
    return event;
  };
  try {
    for (const step of [1, 2, 3]) {
      const state = prepare(step);
      assert.equal(press(state).defaultPrevented, true, `V must be handled in step ${step}`);
      assert.equal(state.frameEditorTool.value, 'browse');
      assert.equal(state.saves.length, 0);
      if (step === 3) {
        assert.equal(state.frameEditor.value.filename, '1.png');
        assert.equal(state.frameEditorRef.value.dirty, true);
      } else {
        assert.equal(state.frameEditor.value, null, 'V must not open a retouch session');
      }

      for (const options of [
        { target: new Target(true) }, { ctrlKey: true }, { metaKey: true }, { altKey: true },
        { repeat: true }, { defaultPrevented: true },
      ]) {
        const guarded = prepare(step);
        press(guarded, options);
        assert.equal(guarded.frameEditorTool.value, step === 3 ? 'brush' : 'browse');
        if (step === 3) assert.equal(guarded.frameEditorRef.value.dirty, true);
      }
      for (const configure of [
        state => { state.frameEditorLoading.value = true; },
        state => { state.frameEditorSaving.value = true; },
        state => { state.navigationPending.value = true; },
        state => { state.process.isProcessing = true; },
        state => { if (state.frameEditorRef.value) state.frameEditorRef.value.busy = true; },
      ]) {
        const guarded = prepare(step);
        configure(guarded);
        press(guarded);
        assert.equal(guarded.frameEditorTool.value, step === 3 ? 'brush' : 'browse');
        if (step === 3) assert.equal(guarded.frameEditorRef.value.dirty, true);
      }
    }
  } finally {
    if (previousElement === undefined) delete globalThis.Element;
    else globalThis.Element = previousElement;
  }
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
