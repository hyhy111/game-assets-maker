import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { createPinia, setActivePinia } from 'pinia';
import { closeFrontendHarness, createScriptedPyWebViewBridge, loadFrontendModule } from './scripted-pywebview-bridge.mjs';

after(closeFrontendHarness);

test('frame reload ignores late image loads from before a manual edit', async () => {
  createScriptedPyWebViewBridge({});
  const { usePlayerStore } = await loadFrontendModule('/src/stores/player.ts');
  setActivePinia(createPinia());
  const store = usePlayerStore();
  const previous = globalThis.Image;
  const pending = [];
  globalThis.Image = class {
    set src(value) { this.url = value; pending.push(this); }
  };
  try {
    store.loadFrames(['frame.png', 'next.png', 'third.png', 'last.png'].map(path => ({path, url: `before-${path}`})));
    store.loadFrames([{ path: 'frame.png', url: 'edited' }]);
    assert.equal(pending.length, 4);
    pending[3].onload();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(store.imageElementCache.get('frame.png').url, 'edited');
    pending.slice(0, 3).forEach(image => image.onload());
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(store.imageElementCache.get('frame.png').url, 'edited');
    assert.equal(store.loadingPaths.size, 0);
    assert.equal(pending.length, 4, 'the old preload queue must not start more frames');
    assert.deepEqual([...store.imageElementCache.keys()], ['frame.png']);
  } finally {
    globalThis.Image = previous;
  }
});
