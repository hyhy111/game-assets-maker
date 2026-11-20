import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import ts from 'typescript';
import { ref, shallowRef } from 'vue';

const source = await readFile(new URL('../src/components/common/ControlTooltip.vue', import.meta.url), 'utf8');
const script = source.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1].replace(/^import .*;$/gm, '');
const javascript = ts.transpileModule(script, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;

function harness() {
  const timers = new Map();
  let nextId = 0;
  class Element {
    constructor(attributes = {}, dataset = {}) {
      this.attributes = new Map(Object.entries(attributes));
      this.dataset = dataset;
      this.isConnected = true;
      this.hovered = true;
    }
    closest() { return this; }
    getAttribute(name) { return this.attributes.get(name) ?? null; }
    hasAttribute(name) { return this.attributes.has(name); }
    setAttribute(name, value) { this.attributes.set(name, value); }
    removeAttribute(name) { this.attributes.delete(name); }
    matches() { return this.hovered; }
    contains(node) { return node === this; }
  }
  const window = {
    setTimeout(callback, delay) { const id = ++nextId; timers.set(id, { callback, delay }); return id; },
    clearTimeout(id) { timers.delete(id); },
  };
  const setup = new Function('ref', 'shallowRef', 'nextTick', 'onMounted', 'onBeforeUnmount', 'window', 'Element', 'Node',
    `${javascript}\nreturn { show, hide, leave, trigger, text };`);
  const bindings = setup(ref, shallowRef, () => Promise.resolve(), () => {}, () => {}, window, Element, Element);
  return {
    ...bindings, Element, timers,
    hover(target) { bindings.show({ type: 'pointerover', target }); },
    runTimer() {
      const [id, timer] = timers.entries().next().value;
      timers.delete(id);
      timer.callback();
    },
  };
}

test('hover waits 500ms and suppresses the native title throughout the wait', () => {
  const h = harness();
  const button = new h.Element({ title: 'Download', 'aria-describedby': 'existing' });
  h.hover(button);
  assert.equal(h.trigger.value, null);
  assert.equal([...h.timers.values()][0].delay, 500);
  assert.equal(button.getAttribute('title'), null);
  assert.equal(button.getAttribute('aria-label'), 'Download');
  h.runTimer();
  assert.equal(h.trigger.value, button);
  assert.equal(h.text.value, 'Download');
  h.hide();
  assert.equal(button.getAttribute('title'), 'Download');
  assert.equal(button.getAttribute('aria-label'), null);
  assert.equal(button.getAttribute('aria-describedby'), 'existing');
});

test('leaving or clicking before the delay cancels the tooltip and restores the title', () => {
  for (const action of ['leave', 'hide']) {
    const h = harness();
    const button = new h.Element({ title: 'Download', 'aria-label': 'Save video' });
    h.hover(button);
    if (action === 'leave') h.leave({ relatedTarget: null });
    else h.hide();
    assert.equal(h.timers.size, 0);
    assert.equal(h.trigger.value, null);
    assert.equal(button.getAttribute('title'), 'Download');
    assert.equal(button.getAttribute('aria-label'), 'Save video');
  }
});

test('existing explicit delays are preserved, including an explicit zero', () => {
  for (const delay of [0, 500, 900]) {
    const h = harness();
    const button = new h.Element({ 'data-tooltip': 'Hint' }, { tooltipDelay: String(delay) });
    h.hover(button);
    if (delay === 0) assert.equal(h.trigger.value, button);
    else {
      assert.equal(h.trigger.value, null);
      assert.equal([...h.timers.values()][0].delay, delay);
      h.runTimer();
      assert.equal(h.trigger.value, button);
    }
  }
});

test('keyboard focus remains immediate and interrupted hover never reveals a stale tooltip', () => {
  const h = harness();
  const first = new h.Element({ title: 'First' });
  const second = new h.Element({ title: 'Second' });
  h.hover(first);
  h.hover(second);
  assert.equal(first.getAttribute('title'), 'First');
  assert.equal(h.timers.size, 1);
  second.hovered = false;
  h.runTimer();
  assert.equal(h.trigger.value, null);
  assert.equal(second.getAttribute('title'), 'Second');
  h.show({ type: 'focusin', target: first });
  assert.equal(h.trigger.value, first);
  assert.equal(h.timers.size, 0);
});
