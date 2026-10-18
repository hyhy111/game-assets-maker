import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import ts from 'typescript';
import { SEEDREAM_IMAGE_DRAG_TYPE, hasImageDrop, readImageDrop, writeSeedreamImageDrag } from '../src/seedream-image-drag.ts';

function fixture() {
  const listeners = new Map();
  const elements = [];
  const document = {
    createElement: tag => {
      assert.equal(tag, 'span');
      const element = { style: {}, setAttribute: () => {}, remove: () => { element.removed = true; } };
      elements.push(element);
      return element;
    },
    body: { appendChild: element => { element.connected = true; } },
    addEventListener: (name, callback) => listeners.set(name, callback),
    removeEventListener: (name, callback) => {
      if (listeners.get(name) === callback) listeners.delete(name);
    },
  };
  const transfers = [];
  const transfer = {
    setData: (...args) => transfers.push(args),
    setDragImage: () => assert.fail('Do not override the native WebView drag bitmap'),
  };
  return { document, source: { ownerDocument: document }, transfer, transfers, elements, listeners };
}

const payload = { localId: 'batch-1', attemptIndex: 2 };

test('main-image and small-image drags use the same corresponding thumbnail preview', async () => {
  const source = await readFile(new URL('../src/components/ai-creation/RecentImageGenerationCard.vue', import.meta.url), 'utf8');
  const handler = source.match(/function startImageDrag\([\s\S]*?\n\}/)[0];
  const compiled = ts.transpileModule(handler, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;
  const thumbnail = { name: 'thumbnail-2' };
  const card = { querySelector(selector) { assert.equal(selector, '[data-test="recent-image-thumbnail-2"]'); return thumbnail; } };
  const previews = [];
  const startDrag = vm.runInNewContext(`${compiled}\nstartImageDrag;`, {
    props: { batch: { local_id: 'batch-1' } },
    writeSeedreamImageDrag: (...args) => previews.push(args[4]),
  });
  for (const name of ['main-preview', 'small-preview']) {
    startDrag({ currentTarget: { name, closest: () => card } }, { index: 2, absolute_path: '/cache/2.png' });
  }
  assert.deepEqual(previews, [thumbnail, thumbnail]);
});

for (const absolutePath of ['/Users/example/GAM cache/角色.png', 'C:\\Users\\example\\GAM cache\\角色.png']) {
  test(`external inputs receive the literal absolute path: ${absolutePath}`, () => {
    const values = new Map();
    writeSeedreamImageDrag({ setData: (type, value) => values.set(type, value) }, payload, null, absolutePath);
    assert.equal(values.get('text/plain'), absolutePath);
    assert.equal(values.get(SEEDREAM_IMAGE_DRAG_TYPE), JSON.stringify(payload));
    const transfer = { types: ['text/plain'], files: [], getData: type => type === 'text/plain' ? values.get(type) : '' };
    assert.deepEqual(readImageDrop(transfer), { kind: 'candidate', candidate: payload });
    assert.equal(readImageDrop({ ...transfer, getData: () => '/unrelated/image.png' }).kind, 'error');
  });
}

test('native transport retaining only standard text still delivers the image candidate', () => {
  const values = new Map();
  writeSeedreamImageDrag({ setData: (type, value) => values.set(type, value) }, payload);
  assert.ok(values.get('text/plain'));
  const received = {
    types: ['text/plain'], files: [],
    getData: type => type === 'text/plain' ? values.get(type) || '' : '',
  };
  assert.equal(hasImageDrop(received), true);
  assert.deepEqual(readImageDrop(received), { kind: 'candidate', candidate: payload });
});

test('large previews reuse the rendered thumbnail as the only drag bitmap', () => {
  const f = fixture();
  const thumbnail = { clientWidth: 56, clientHeight: 56 };
  const previews = [];
  f.transfer.setDragImage = (...args) => previews.push(args);
  writeSeedreamImageDrag(f.transfer, payload, f.source, '/cache/image.png', thumbnail);
  assert.deepEqual(previews, [[thumbnail, 28, 28]]);
  assert.deepEqual(f.transfers, [
    [SEEDREAM_IMAGE_DRAG_TYPE, JSON.stringify(payload)],
    ['text/plain', '/cache/image.png'],
  ]);
  f.listeners.get('dragend')();
});

test('an unavailable thumbnail preview does not prevent transferring the image path', () => {
  const f = fixture();
  f.transfer.setDragImage = () => { throw new Error('Native preview unavailable'); };
  assert.doesNotThrow(() => writeSeedreamImageDrag(
    f.transfer, payload, f.source, '/cache/image.png', { clientWidth: 56, clientHeight: 56 },
  ));
  assert.ok(f.transfers.some(([type, value]) => type === 'text/plain' && value === '/cache/image.png'));
  f.listeners.get('dragend')();
});

test('plain text, URLs and unmarked JSON never become internal image candidates', () => {
  for (const value of ['hello', 'https://example.com/image.png', JSON.stringify(payload)]) {
    assert.deepEqual(readImageDrop({ files: [], getData: type => type === 'text/plain' ? value : '' }),
      { kind: 'error', key: 'aiCreation.dropInvalidImage' });
  }
});

test('pointer decoration never replaces the native drag bitmap or intercepts drop events', () => {
  const f = fixture();
  writeSeedreamImageDrag(f.transfer, payload, f.source);
  assert.equal(f.transfer.effectAllowed, 'copy');
  assert.deepEqual(f.transfers, [
    [SEEDREAM_IMAGE_DRAG_TYPE, JSON.stringify(payload)],
    ['text/plain', 'gam-seedream-image:' + JSON.stringify(payload)],
  ]);
  const effect = f.elements[0];
  assert.ok(effect.connected);
  assert.match(effect.style.cssText, /pointer-events:\s*none/);
  f.listeners.get('dragover')({ clientX: 100, clientY: 200 });
  assert.equal(effect.style.transform, 'translate(112px, 212px)');
  assert.equal(effect.style.visibility, 'visible');
  f.listeners.get('dragend')();
});

test('drop and cancelled drag clear the effect and every listener', () => {
  for (const event of ['drop', 'dragend']) {
    const f = fixture();
    writeSeedreamImageDrag(f.transfer, payload, f.source);
    f.listeners.get('dragleave')({ relatedTarget: null });
    assert.equal(f.elements[0].style.visibility, 'hidden');
    f.listeners.get(event)();
    assert.ok(f.elements[0].removed);
    assert.equal(f.listeners.size, 0);
  }
});

test('starting another drag removes the previous decoration', () => {
  const first = fixture();
  const second = fixture();
  writeSeedreamImageDrag(first.transfer, payload, first.source);
  writeSeedreamImageDrag(second.transfer, payload, second.source);
  assert.ok(first.elements[0].removed);
  assert.equal(first.listeners.size, 0);
  second.listeners.get('dragend')();
});

test('decoration failure cannot cancel a valid native drag payload', () => {
  const f = fixture();
  f.document.createElement = () => { throw new Error('decoration unavailable'); };
  assert.doesNotThrow(() => writeSeedreamImageDrag(f.transfer, payload, f.source));
  assert.equal(f.transfers.length, 2);
  assert.equal(f.listeners.size, 0);
});

test('drag payloads do not require a source element and null transfers do nothing', () => {
  const f = fixture();
  writeSeedreamImageDrag(f.transfer, payload);
  assert.equal(f.transfers.length, 2);
  writeSeedreamImageDrag(null, payload, f.source);
  assert.equal(f.elements.length, 0);
});
