import assert from 'node:assert/strict';
import { test } from 'node:test';
import { selectionOutline } from '../src/utils/magic-wand.ts';

function outlineEdges(path) {
  const tokens = path.match(/[MHVZ]|\d+/g) ?? [];
  const edges = new Set();
  let x = 0, y = 0, startX = 0, startY = 0;
  function line(toX, toY) {
    assert.ok(toX === x || toY === y, 'contours never bridge pixels diagonally');
    while (x !== toX || y !== toY) {
      const nx = x + Math.sign(toX - x), ny = y + Math.sign(toY - y);
      const edge = [`${x},${y}`, `${nx},${ny}`].sort().join('/');
      assert.ok(!edges.has(edge), `duplicate edge ${edge}`);
      edges.add(edge);
      x = nx; y = ny;
    }
  }
  for (let i = 0; i < tokens.length;) {
    const command = tokens[i++];
    if (command === 'M') { x = startX = Number(tokens[i++]); y = startY = Number(tokens[i++]); }
    else if (command === 'H') line(Number(tokens[i++]), y);
    else if (command === 'V') line(x, Number(tokens[i++]));
    else { assert.equal(command, 'Z'); line(startX, startY); }
  }
  return edges;
}

test('selection outline follows image edges without outlining internal pixel seams', () => {
  const path = selectionOutline(new Uint8Array([1, 1, 1, 1]), 2, 2);
  const edges = outlineEdges(path);
  assert.equal(edges.size, 8);
  assert.ok(edges.has('0,0/1,0'));
  assert.ok(edges.has('2,1/2,2'));
  assert.ok(!edges.has('1,0/1,1'));
  assert.equal((path.match(/Z/g) ?? []).length, 1);
});

test('selection outline includes inner holes and preserves the selection mask', () => {
  const mask = new Uint8Array([1, 1, 1, 1, 0, 1, 1, 1, 1]);
  const before = new Uint8Array(mask);
  const path = selectionOutline(mask, 3, 3);
  const edges = outlineEdges(path);
  assert.equal(edges.size, 16);
  assert.ok(edges.has('1,1/2,1'));
  assert.ok(edges.has('1,2/2,2'));
  assert.equal((path.match(/Z/g) ?? []).length, 2);
  assert.deepEqual(mask, before);
});

test('disconnected and diagonally touching islands retain every boundary edge', () => {
  const disjoint = selectionOutline(new Uint8Array([1, 0, 1]), 3, 1);
  assert.equal(outlineEdges(disjoint).size, 8);
  assert.equal((disjoint.match(/Z/g) ?? []).length, 2);
  for (const mask of [new Uint8Array([1, 0, 0, 1]), new Uint8Array([0, 1, 1, 0])]) {
    assert.equal(outlineEdges(selectionOutline(mask, 2, 2)).size, 8);
  }
});

test('empty selections have no outline and one selected pixel has four edges', () => {
  assert.equal(selectionOutline(new Uint8Array(9), 3, 3), '');
  assert.equal(outlineEdges(selectionOutline(new Uint8Array([1]), 1, 1)).size, 4);
  assert.throws(() => selectionOutline(new Uint8Array(1), 2, 2), /dimensions/);
});
