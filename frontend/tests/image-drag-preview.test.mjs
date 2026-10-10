import assert from 'node:assert/strict';
import { test } from 'node:test';
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
