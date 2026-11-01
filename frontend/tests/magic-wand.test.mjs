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

test('feathering clears the whole selected core and softens only its outside neighborhood', () => {
  const image = pixels(7, Array.from({ length: 49 }, () => gray));
  const selected = new Uint8Array(49);
  for (let y = 2; y < 5; y++) for (let x = 2; x < 5; x++) selected[y * 7 + x] = 1;
  const before = new Uint8ClampedArray(image.data);
  const output = deleteSelection(image, selected, 1);
  for (let index = 0; index < selected.length; index++) {
    if (selected[index]) assert.deepEqual([...output.slice(index * 4, index * 4 + 4)], [0,0,0,0]);
  }
  assert.equal(output[(1 * 7 + 3) * 4 + 3], 128, 'the adjacent unselected pixel is feathered');
  assert.deepEqual(output.slice(3 * 4, 3 * 4 + 4), image.data.slice(3 * 4, 3 * 4 + 4), 'pixels beyond the radius stay unchanged');
  assert.deepEqual([...output.slice((1 * 7 + 3) * 4, (1 * 7 + 3) * 4 + 3)], gray.slice(0,3));
  assert.deepEqual(image.data,before);
});

test('outward feather handles thin islands, existing alpha, borders and holes without double fading', () => {
  const image = pixels(3, Array.from({ length: 9 }, () => [120,120,130,100]));
  const full = deleteSelection(image, new Uint8Array(9).fill(1), 1);
  assert.ok(full.every(value=>value===0), 'a fully selected image is completely removed');
  const island = deleteSelection(image, new Uint8Array([0,0,0,0,1,0,0,0,0]), 12);
  assert.equal(island[4 * 4 + 3],0, 'even a single selected pixel is fully removed');
  assert.ok(island[1 * 4 + 3]>0 && island[1 * 4 + 3]<100);
  const ring = new Uint8Array(9).fill(1); ring[4]=0;
  assert.equal(deleteSelection(image,ring,1)[4 * 4 + 3],50, 'inner holes also receive outward feathering');
  const border = deleteSelection(image,new Uint8Array([1,0,0,0,0,0,0,0,0]),1);
  assert.equal(border[3],0);
  assert.equal(border[1 * 4 + 3],50);
  assert.equal(border[8 * 4 + 3],100);
  const line = pixels(5,Array.from({length:5},()=>[120,120,130,100]));
  assert.equal(deleteSelection(line,new Uint8Array([0,1,0,1,0]),1)[2 * 4 + 3],50);
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

test('frame editor exposes initial-version restore and disables it when no verified baseline exists', async () => {
  for (const initial of ['', 'data:image/png;base64,fixture']) {
    const html = await renderSfc('components/seedream/SeedreamImageEraser.vue', {
      props:{imageUrl:'',saving:false,magicWandEnabled:true,originalImageUrl:initial},
      configureSetup(bindings){bindings.loading.value=false;},
    });
    const button=html.match(/<button([^>]*data-test="image-editor-restore-original"[^>]*)>/);
    assert.ok(button);
    assert.match(html,/恢复初始版本/);
    assert.equal(/\sdisabled(?:\s|=|$)/.test(button[1]),!initial);
  }
});


test('an older running backend shows a restart hint rather than suggesting unsupported reprocessing', async () => {
  const html = await renderSfc('components/seedream/SeedreamImageEraser.vue', {
    props:{imageUrl:'',saving:false,magicWandEnabled:true,initialRestoreUnsupported:true},
    configureSetup(bindings){bindings.loading.value=false;},
  });
  assert.match(html,/请保存当前修改并重启应用/);
});
