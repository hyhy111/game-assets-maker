import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import ts from 'typescript';
import { computed, nextTick, ref, watch } from 'vue';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';

after(closeSfcRenderer);
const source = await readFile(new URL('../src/components/settings/GamSkillsSettings.vue', import.meta.url), 'utf8');
const script = source.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1].replace(/^import .*;$/gm, '');

function setup(clipboard, fallback = true) {
  const calls = { copied: [], removed: 0, focused: 0 };
  const textarea = { style: {}, select() {}, remove() { calls.removed++; } };
  const document = {
    activeElement: { focus() { calls.focused++; } },
    createElement: () => textarea,
    body: { append() {} },
    execCommand(action) { assert.equal(action, 'copy'); calls.copied.push(textarea.value); return fallback; },
  };
  const compiled = ts.transpileModule(`${script}\n({ agent, agentOptions, command, copied, copyFailed, copyCommand });`, {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const state = vm.runInNewContext(compiled, { computed, ref, watch, useI18n: () => ({ t: key => key }), navigator: { clipboard }, document });
  return { state, calls };
}

test('each agent selection produces its own global all-skills command and clears copy feedback', async () => {
  const copied = [];
  const { state } = setup({ writeText: async text => copied.push(text) });
  assert.equal(state.agent.value, 'codex');
  for (const agent of state.agentOptions) {
    state.agent.value = agent.value;
    await nextTick();
    assert.equal(state.copied.value, false);
    const command = `npx skills add hyhy111/gam-skills -g -a ${agent.value} --skill "*"`;
    assert.equal(state.command.value, command);
    await state.copyCommand();
    assert.equal(copied.at(-1), command);
    assert.equal(state.copied.value, true);
  }
});

test('clipboard rejection falls back to selectable text and restores focus', async () => {
  const { state, calls } = setup({ writeText: async () => { throw new Error('denied'); } });
  await state.copyCommand();
  assert.deepEqual(calls.copied, [state.command.value]);
  assert.equal(calls.removed, 1);
  assert.equal(calls.focused, 1);
  assert.equal(state.copied.value, true);
});

test('failed clipboard copy reports a failure without claiming success', async () => {
  const { state, calls } = setup(undefined, false);
  await state.copyCommand();
  assert.equal(state.copied.value, false);
  assert.equal(state.copyFailed.value, true);
  assert.equal(calls.removed, 1);
  state.agent.value = 'cursor';
  await nextTick();
  assert.equal(state.copyFailed.value, false);
});

test('settings show the installer immediately below the update card', async () => {
  const html = await renderSfc('views/SeedanceSettings.vue', { route: '/ai-creation/settings' });
  assert.ok(html.indexOf('data-test="app-update-settings"') < html.indexOf('data-test="gam-skills-settings"'));
  assert.match(html, /data-test="gam-skills-agent"/);
  assert.match(html, /npx skills add hyhy111\/gam-skills -g -a codex --skill &quot;\*&quot;/);
  assert.match(html, /Node\.js/);
});

test('settings offer common model defaults without separate ForFuner AI controls', async () => {
  const html = await renderSfc('views/SeedanceSettings.vue', {
    route: '/ai-creation/settings',
    piniaState: {
      seedance: { settings: { default_model: 'mini', default_resolution: '720p', default_duration: 4, cache_dir: '', default_ratio: '16:9' } },
      seedream: { settings: { default_model: 'pro', default_resolution: '2K', default_count: 1 } },
      config: { config: { logger_enabled: false, project_dir: 'project', seedance: {} } },
    },
  });
  assert.match(html, /aria-label="默认模型"/);
  assert.doesNotMatch(html, /ForFuner AI.*默认模型|platform-default-|自定义 API Key 默认模型/);
});
