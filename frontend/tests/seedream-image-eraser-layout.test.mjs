import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import ts from 'typescript';
import { computed, ref } from 'vue';

const source = await readFile(new URL('../src/components/seedream/SeedreamImageEraser.vue', import.meta.url), 'utf8');
const script = source.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1]
  .replace(/^import .*;$/gm, '');
const javascript = ts.transpileModule(script, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.None },
}).outputText;

function editor(generationLayout = null, height = 1000) {
  const emitted = [];
  const setup = new Function(
    'ref', 'computed', 'onMounted', 'onBeforeUnmount', 'defineProps', 'withDefaults', 'defineEmits', 'useI18n',
    `${javascript}\nreturn {
      resizeTargetRatio, resizeBottomMarginRatio, imageHeight, sourceResizeTop, sourceResizeBottom,
      targetHeightPixels, bottomDistancePixels, canApplyResize, currentGenerationLayout,
      normalizeResizeRatios, updateResizeRatio, resetResizeGuides, applyResize, undo, redo, apply,
      initializeCanvas(canvas) { canvasRef.value = canvas; editSourceCanvas = canvas; }
    };`,
  );
  const state = setup(ref, computed, () => {}, () => {},
    () => ({ generationLayout }), (props) => props,
    () => (...args) => emitted.push(args), () => ({ t: (key) => key }));
  state.imageHeight.value = height;
  state.resetResizeGuides();
  const context = { fillRect() {}, clearRect() {}, drawImage() {} };
  state.initializeCanvas({ width: 1000, height, getContext: () => context, toDataURL: () => 'data:image/png;base64,fixture' });
  return { ...state, emitted };
}

function layout(heightRatio = 0.666, marginRatio = 0.054, height = 1000) {
  const target = Math.round(height * heightRatio);
  return {
    source_width: 1000, source_height: height, measured_top: 100, measured_bottom: 900,
    measured_height: 800, target_height: target, character_height_ratio: heightRatio,
    bottom_distance: Math.round(height * marginRatio), bottom_margin_ratio: marginRatio,
    scale: target / 800,
  };
}

test('historical decimals normalize before pixel calculation without mutating the saved layout', () => {
  const saved = layout();
  const state = editor(saved);
  assert.equal(state.resizeTargetRatio.value, 67);
  assert.equal(state.resizeBottomMarginRatio.value, 5);
  assert.equal(state.targetHeightPixels.value, 670);
  assert.equal(state.bottomDistancePixels.value, 50);
  assert.equal(saved.character_height_ratio, 0.666);
  assert.equal(saved.bottom_margin_ratio, 0.054);
  assert.equal(state.canApplyResize.value, true);
});

test('input rounds halves, preserves height on overflow, and normalizes the visible DOM value', () => {
  const state = editor();
  state.normalizeResizeRatios(42.5, 3.5);
  assert.equal(state.resizeTargetRatio.value, 43);
  assert.equal(state.resizeBottomMarginRatio.value, 4);
  state.normalizeResizeRatios(90.5, 20.5);
  assert.equal(state.resizeTargetRatio.value, 91);
  assert.equal(state.resizeBottomMarginRatio.value, 9);
  const input = { valueAsNumber: 90.6, value: '90.6' };
  state.updateResizeRatio({ target: input }, 'height');
  assert.equal(input.value, '91');
  assert.equal(state.targetHeightPixels.value + state.bottomDistancePixels.value, 1000);
});

test('full height and zero margin remain valid; bounds clamp with height taking priority', () => {
  const state = editor();
  state.normalizeResizeRatios(100, 0);
  assert.equal(state.canApplyResize.value, true);
  assert.equal(state.targetHeightPixels.value, 1000);
  assert.equal(state.bottomDistancePixels.value, 0);
  state.normalizeResizeRatios(-10, -5);
  assert.equal(state.resizeTargetRatio.value, 1);
  assert.equal(state.resizeBottomMarginRatio.value, 0);
  state.normalizeResizeRatios(150, 99);
  assert.equal(state.resizeTargetRatio.value, 100);
  assert.equal(state.resizeBottomMarginRatio.value, 0);
});

test('empty and non-finite inputs cannot apply a layout and preserve the other field', () => {
  const state = editor();
  state.normalizeResizeRatios(43, 4);
  for (const value of [NaN, Infinity, -Infinity]) {
    state.updateResizeRatio({ target: { valueAsNumber: value, value: '' } }, 'height');
    assert.equal(state.resizeTargetRatio.value, null);
    assert.equal(state.resizeBottomMarginRatio.value, 4);
    assert.equal(state.canApplyResize.value, false);
    state.applyResize();
    assert.equal(state.currentGenerationLayout.value, null);
  }
  state.normalizeResizeRatios(43, null);
  assert.equal(state.canApplyResize.value, false);
});

test('apply, undo, redo and saved reopen use the same integer inputs and submitted pixels', () => {
  const saved = layout();
  const state = editor(saved);
  state.applyResize();
  assert.equal(state.currentGenerationLayout.value.target_height, 670);
  assert.equal(state.currentGenerationLayout.value.bottom_distance, 50);
  state.undo();
  assert.equal(state.resizeTargetRatio.value, 67);
  assert.equal(state.resizeBottomMarginRatio.value, 5);
  state.redo();
  state.apply();
  assert.equal(state.emitted.length, 1);
  const submitted = state.emitted[0][3];
  assert.equal(submitted.character_height_ratio, 0.67);
  assert.equal(submitted.bottom_margin_ratio, 0.05);
  const reopened = editor(submitted);
  assert.equal(reopened.resizeTargetRatio.value, 67);
  assert.equal(reopened.resizeBottomMarginRatio.value, 5);
  assert.equal(reopened.targetHeightPixels.value, submitted.target_height);
  assert.equal(reopened.bottomDistancePixels.value, submitted.bottom_distance);
  assert.deepEqual(saved, layout());
});

test('pixel rounding on an odd canvas does not place the character outside the canvas', () => {
  const state = editor(null, 101);
  state.normalizeResizeRatios(50, 50);
  assert.equal(state.targetHeightPixels.value, 51);
  assert.equal(state.bottomDistancePixels.value, 50);
  assert.equal(state.canApplyResize.value, true);
  state.applyResize();
  assert.equal(state.resizeTargetRatio.value, 50);
  assert.equal(state.resizeBottomMarginRatio.value, 50);
  assert.equal(state.currentGenerationLayout.value.target_height + state.currentGenerationLayout.value.bottom_distance, 101);
});
