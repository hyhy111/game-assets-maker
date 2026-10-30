import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import ts from 'typescript';
import { computed, ref, watch } from 'vue';
import { eraseBrushSegment } from '../src/utils/magic-wand.ts';

const source = await readFile(new URL('../src/components/seedream/SeedreamImageEraser.vue', import.meta.url), 'utf8');
const script = source.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1]
  .replace(/^import .*;$/gm, '');
const javascript = ts.transpileModule(script, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.None },
}).outputText;

function editor(generationLayout = null, height = 1000, options = {}) {
  const emitted = [];
  const setup = new Function(
    'defineExpose', 'ref', 'computed', 'watch', 'onMounted', 'onBeforeUnmount', 'defineProps', 'withDefaults', 'defineEmits', 'useI18n', 'eraseBrushSegment',
    `${javascript}\nreturn {
      resizeTargetRatio, resizeBottomMarginRatio, imageHeight, sourceResizeTop, sourceResizeBottom,
      targetHeightPixels, bottomDistancePixels, canApplyResize, currentGenerationLayout,
      normalizeResizeRatios, updateResizeRatio, resetResizeGuides, applyResize, undo, redo, apply,
      drawPoint, drawLine, finishStroke, brushSize, brushFeather, dirty, onKeydown, tool, wandTolerance,
      initializeStroke(view, source, before, bounds) {
        canvasRef.value = view; editSourceCanvas = source; strokeBefore = before;
        strokeAfter = { ...before, data: new Uint8ClampedArray(before.data) };
        strokeBounds = bounds; drawing.value = true;
      },
      initializeCanvas(canvas) { loading.value = false; canvasRef.value = canvas; editSourceCanvas = canvas; }
    };`,
  );
  const state = setup(() => {}, ref, computed, watch, () => {}, () => {},
    () => ({ generationLayout, ...options }), (props) => props,
    () => (...args) => emitted.push(args), () => ({ t: (key) => key }), eraseBrushSegment);
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

test('component soft eraser records the complete stroke and restores all feather pixels on undo and redo', () => {
  const state = editor(null, 11, { magicWandEnabled: true });
  assert.equal(state.brushSize.value, 5);
  assert.equal(state.brushFeather.value, 0);
  state.brushFeather.value = 2;
  let pixels = new Uint8ClampedArray(11 * 11 * 4);
  for (let i = 0; i < 121; i++) pixels.set([120, 130, 140, 200], i * 4);
  const original = new Uint8ClampedArray(pixels);
  const context = {
    createImageData(width, height) { return { width, height, data: new Uint8ClampedArray(width * height * 4) }; },
    getImageData(x, y, width, height) {
      const result = this.createImageData(width, height);
      for (let row = 0; row < height; row++) {
        result.data.set(pixels.slice(((y + row) * 11 + x) * 4, ((y + row) * 11 + x + width) * 4), row * width * 4);
      }
      return result;
    },
    putImageData(image, dx, dy, x = 0, y = 0, width = image.width, height = image.height) {
      for (let row = y; row < y + height; row++) {
        pixels.set(image.data.slice((row * image.width + x) * 4, (row * image.width + x + width) * 4), ((dy + row) * 11 + dx + x) * 4);
      }
    },
  };
  const sourceCanvas = { getContext: () => context };
  const viewCanvas = { width: 11, height: 11, getContext: () => ({ clearRect() {}, drawImage() {} }), hasPointerCapture: () => false };
  state.initializeStroke(viewCanvas, sourceCanvas, context.getImageData(0, 0, 11, 11), {left:0,top:0,right:11,bottom:11});
  state.drawPoint(context, {x:3.5,y:5.5}, 5);
  state.drawLine(context, {x:3.5,y:5.5}, {x:7.5,y:5.5}, 5);
  state.finishStroke({pointerId:1});
  const erased = new Uint8ClampedArray(pixels);
  assert.equal(pixels[(5 * 11 + 5) * 4 + 3], 0);
  assert.ok(pixels[(7 * 11 + 5) * 4 + 3] > 0 && pixels[(7 * 11 + 5) * 4 + 3] < 200);
  assert.equal(state.dirty.value, true);
  state.undo();
  assert.deepEqual(pixels, original);
  assert.equal(state.dirty.value, false);
  state.redo();
  assert.deepEqual(pixels, erased);
});

test('plus/minus changes only the active tool parameter, repeats, clamps and ignores text entry and modifiers', () => {
  const state = editor(null, 11, {magicWandEnabled:true});
  const previous = globalThis.Element;
  class Target { constructor(editable = false) { this.editable = editable; } closest() { return this.editable; } }
  globalThis.Element = Target;
  function press(key, options = {}) {
    const event = { key, target:new Target(), preventDefault() { this.defaultPrevented = true; }, ...options };
    state.onKeydown(event);
    return event;
  }
  try {
    assert.equal(state.wandTolerance.value, 20);
    assert.equal(press('+').defaultPrevented, true);
    press('=', {repeat:true}); press('-');
    assert.equal(state.wandTolerance.value, 21);
    assert.equal(state.brushSize.value, 5);
    for (const options of [{target:new Target(true)}, {ctrlKey:true}, {metaKey:true}, {altKey:true}, {isComposing:true}, {defaultPrevented:true}]) {
      press('+', options);
      assert.equal(state.wandTolerance.value, 21);
    }
    state.wandTolerance.value = 100; press('+'); assert.equal(state.wandTolerance.value, 100);
    state.wandTolerance.value = 0; press('_'); assert.equal(state.wandTolerance.value, 0);
    state.tool.value = 'brush';
    press('+'); assert.equal(state.brushSize.value, 6);
    press('-'); assert.equal(state.brushSize.value, 5);
    state.brushSize.value = 200; press('='); assert.equal(state.brushSize.value, 200);
    state.brushSize.value = 1; press('-'); assert.equal(state.brushSize.value, 1);
    assert.equal(state.brushFeather.value, 0, 'parameter keys never change feather');
    state.tool.value = 'browse';
    assert.equal(press('+').defaultPrevented, undefined);
    assert.equal(state.brushSize.value, 1);
    assert.equal(state.wandTolerance.value, 0);
    const legacy = editor();
    legacy.onKeydown({key:'+',target:new Target(),preventDefault(){ throw Error('legacy editor must ignore frame tool shortcuts'); }});
    assert.equal(legacy.brushSize.value, 5);
  } finally {
    if (previous === undefined) delete globalThis.Element;
    else globalThis.Element = previous;
  }
});
