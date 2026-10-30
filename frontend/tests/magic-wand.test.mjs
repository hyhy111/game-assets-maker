import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { deleteSelection, eraseBrushSegment, selectColorRegion, selectionBounds } from '../src/utils/magic-wand.ts';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';

after(closeSfcRenderer);

function pixels(width, colors) {
  return { width, height: colors.length / width, data: new Uint8ClampedArray(colors.flat()) };
}
const green = [80, 170, 60, 255], gray = [120, 120, 130, 255], empty = [80, 170, 60, 0];

test('contiguous selection stays on the clicked color island and ignores transparency', () => {
  const image = pixels(5, [green, green, gray, green, empty]);
  assert.deepEqual([...selectColorRegion(image, 0, 0, 0)], [1, 1, 0, 0, 0]);
  assert.deepEqual([...selectColorRegion(image, 0, 0, 0, false)], [1, 1, 0, 1, 0]);
  assert.deepEqual([...selectColorRegion(image, 4, 0, 100)], [0, 0, 0, 0, 0]);
});

test('fixed seed tolerance cannot creep across a gradient into different colors', () => {
  const image = pixels(5, [0, 10, 20, 30, 40].map(v => [v, v, v, 255]));
  assert.deepEqual([...selectColorRegion(image, 0, 0, 8)], [1, 1, 1, 0, 0]);
});

test('four-connected islands do not leak through diagonal corners', () => {
  const image = pixels(2, [green, gray, gray, green]);
  assert.deepEqual([...selectColorRegion(image, 0, 0, 0)], [1, 0, 0, 0]);
  assert.equal(selectColorRegion(image, -1, 0, 0).reduce((a,b)=>a+b), 0);
});

test('zero-feather deletion only clears the selected pixels and leaves input unchanged', () => {
  const image = pixels(3, [gray, green, gray]);
  const before = new Uint8ClampedArray(image.data);
  const output = deleteSelection(image, new Uint8Array([0, 1, 0]), 0);
  assert.deepEqual([...output], [...gray, 0, 0, 0, 0, ...gray]);
  assert.deepEqual(image.data, before);
});

test('feathering starts inside the outermost selected pixel and never changes unselected pixels', () => {
  const image = pixels(7, Array.from({ length: 49 }, () => gray));
  const selected = new Uint8Array(49);
  for (let y = 1; y < 6; y++) for (let x = 1; x < 6; x++) selected[y * 7 + x] = 1;
  const output = deleteSelection(image, selected, 1);
  assert.equal(output[(1 * 7 + 3) * 4 + 3], 128, 'outer selected ring is partially retained');
  assert.equal(output[(2 * 7 + 3) * 4 + 3], 0, 'interior is erased');
  for (let index = 0; index < selected.length; index++) {
    if (!selected[index]) assert.deepEqual(output.slice(index * 4, index * 4 + 4), image.data.slice(index * 4, index * 4 + 4));
  }
  assert.deepEqual([...output.slice((1 * 7 + 3) * 4, (1 * 7 + 3) * 4 + 3)], gray.slice(0, 3));
  assert.equal(image.data[(2 * 7 + 3) * 4 + 3], 255, 'input is unchanged');
});

test('positive feather retains thin islands, respects existing alpha, and handles image borders and holes', () => {
  const image = pixels(3, Array.from({ length: 9 }, () => [120, 120, 130, 100]));
  const full = deleteSelection(image, new Uint8Array(9).fill(1), 1);
  assert.equal(full[3], 50, 'image edge is a boundary');
  assert.equal(full[4 * 4 + 3], 0, 'full-image selection has an erasable interior');
  const island = deleteSelection(image, new Uint8Array([0,0,0,0,1,0,0,0,0]), 12);
  assert.ok(island[4 * 4 + 3] > 0 && island[4 * 4 + 3] < 100);
  const ring = new Uint8Array(9).fill(1); ring[4] = 0;
  const hole = deleteSelection(image, ring, 1);
  assert.deepEqual(hole.slice(16, 20), image.data.slice(16, 20));
  assert.equal(hole[1 * 4 + 3], 50, 'selected ring around a hole is feathered');
});

test('eraser hard and soft strokes stay within the brush and soften inward', () => {
  const before = pixels(11, Array.from({ length: 121 }, () => gray));
  const hard = { ...before, data: new Uint8ClampedArray(before.data) };
  eraseBrushSegment(hard, before, {x:5.5,y:5.5}, {x:5.5,y:5.5}, 5, 0);
  assert.equal(hard.data[(5 * 11 + 5) * 4 + 3], 0);
  assert.equal(hard.data[(5 * 11 + 7) * 4 + 3], 0);
  const soft = { ...before, data: new Uint8ClampedArray(before.data) };
  eraseBrushSegment(soft, before, {x:5.5,y:5.5}, {x:5.5,y:5.5}, 5, 2);
  assert.equal(soft.data[(5 * 11 + 5) * 4 + 3], 0);
  assert.ok(soft.data[(5 * 11 + 7) * 4 + 3] > 0 && soft.data[(5 * 11 + 7) * 4 + 3] < 255);
  assert.deepEqual([...soft.data.slice((5 * 11 + 8) * 4, (5 * 11 + 8) * 4 + 4)], gray);
  const single = { ...before, data: new Uint8ClampedArray(before.data) };
  eraseBrushSegment(single, before, {x:5.5,y:5.5}, {x:5.5,y:5.5}, 1, 0);
  assert.equal(single.data[(5 * 11 + 5) * 4 + 3], 0);
  assert.equal(single.data[(5 * 11 + 6) * 4 + 3], 255);
});

test('soft stroke overlap is independent of pointer sampling and preserves source pixels', () => {
  const before = pixels(11, Array.from({ length: 121 }, () => [120, 120, 130, 140]));
  const whole = { ...before, data: new Uint8ClampedArray(before.data) };
  const split = { ...before, data: new Uint8ClampedArray(before.data) };
  eraseBrushSegment(whole, before, {x:2.5,y:5.5}, {x:8.5,y:5.5}, 5, 2);
  for (let x = 2.5; x < 8.5; x++) {
    eraseBrushSegment(split, before, {x,y:5.5}, {x:x+1,y:5.5}, 5, 2);
    eraseBrushSegment(split, before, {x,y:5.5}, {x:x+1,y:5.5}, 5, 2);
  }
  assert.deepEqual(split.data, whole.data);
  assert.equal(before.data[(5 * 11 + 5) * 4 + 3], 140);
  const offset = (7 * 11 + 5) * 4;
  assert.ok(split.data[offset + 3] > 0 && split.data[offset + 3] < 140);
  assert.deepEqual(split.data.slice(offset, offset + 3), before.data.slice(offset, offset + 3));
});

test('no selection is a no-op and padded selection bounds are clamped to the image', () => {
  const image = pixels(3, [gray, green, gray]);
  assert.deepEqual(deleteSelection(image, new Uint8Array(3), 4), image.data);
  assert.equal(selectionBounds(new Uint8Array(3), 3, 1), null);
  assert.deepEqual(selectionBounds(new Uint8Array([0, 1, 0]), 3, 1, 1), { x: 0, y: 0, width: 3, height: 1 });
});

test('magic wand UI is opt-in and includes selection preview, tolerance and delete controls', async () => {
  const html = await renderSfc('components/seedream/SeedreamImageEraser.vue', {
    props: { imageUrl: '', saving: false, magicWandEnabled: true },
  });
  assert.match(html, /magic-wand-tool/);
  assert.match(html, /magic-wand-tolerance/);
  assert.match(html, /magic-wand-feather/);
  assert.match(html, /magic-wand-delete/);
  assert.match(html, /magic-wand-selection/);
  const existing = await renderSfc('components/seedream/SeedreamImageEraser.vue', { props: { imageUrl: '', saving: false } });
  assert.doesNotMatch(existing, /data-test="magic-wand-tool"/);
});

test('frame eraser exposes a 5px brush and a separate zero-default feather slider', async () => {
  const html = await renderSfc('components/seedream/SeedreamImageEraser.vue', {
    props: { imageUrl: '', saving: false, magicWandEnabled: true, activeTool: 'brush' },
  });
  assert.match(html, /data-test="seedream-eraser-size"[\s\S]*?value="5"/);
  assert.match(html, /data-test="seedream-eraser-feather"[\s\S]*?value="0"/);
});
