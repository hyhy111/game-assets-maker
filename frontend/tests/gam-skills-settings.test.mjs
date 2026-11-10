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

const absent = { status: 'not_installed', source: 'none', installed_count: 0, total_count: 6, outdated: [], error: '', can_check: false, can_install: true, node_available: true };
function setup(clipboard, fallback = true, system = {}, query = {}) {
  const calls = { copied: [], removed: 0, focused: 0 };
  const textarea = { style: {}, select() {}, remove() { calls.removed++; } };
  const document = {
    activeElement: { focus() { calls.focused++; } },
    createElement: () => textarea,
    body: { append() {} },
    execCommand(action) { assert.equal(action, 'copy'); calls.copied.push(textarea.value); return fallback; },
  };
  const compiled = ts.transpileModule(`${script}\n({ agent, agentOptions, command, copied, copyFailed, copyCommand, status, checking, installing, installed, operationError, refreshStatus, installSkills });`, {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const state = vm.runInNewContext(compiled, {
    computed, ref, watch, onMounted() {}, onBeforeUnmount() {},
    useRoute: () => ({ query }),
    useGamSkillsUpdatesStore: () => ({ record() {}, refresh: async () => {} }),
    api: { system: { getGamSkillsStatus: async () => ({ ...absent }), ...system } },
    useI18n: () => ({ t: key => key }), navigator: { clipboard }, document,
  });
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
  assert.match(html, /id="gam-skills"/);
  assert.match(html, /npx skills add hyhy111\/gam-skills -g -a codex --skill &quot;\*&quot;/);
  assert.match(html, /一键安装/);
});

test('home hero links below AI creation directly to the GAM Skills installation section', async () => {
  const html = await renderSfc('components/project-manager/ProjectManagerHero.vue');
  assert.match(html, /<a[^>]*href="\/ai-creation\/settings#gam-skills"[^>]*data-test="project-manager-install-skills"/);
  assert.match(html, /安装 GAM Skills/);
  assert.ok(html.indexOf('data-test="project-manager-hero-start"') < html.indexOf('data-test="project-manager-install-skills"'));
  assert.ok(html.indexOf('data-test="project-manager-install-skills"') < html.indexOf('文生图'));
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

test('only an npx installation exposes update checking while other installations stay untouched', async () => {
  for (const source of ['npx', 'other', 'none']) {
    const state = { ...absent, source, status: source === 'other' ? 'unmanaged' : source === 'npx' ? 'update_available' : 'not_installed',
      can_install: source !== 'other', can_check: source === 'npx', installed_count: source === 'npx' ? 6 : 0,
      outdated: source === 'npx' ? ['gam-cli'] : [] };
    const html = await renderSfc('components/settings/GamSkillsSettings.vue', {
      configureSetup(bindings) { bindings.status.value = state; },
    });
    assert.match(html, /data-test="gam-skills-install"/);
    if (source === 'npx') {
      assert.match(html, /data-test="gam-skills-check"/);
      assert.match(html, /其中 1 个有更新/);
      assert.match(html.replace(/<!--[\s\S]*?-->/g, ''), /data-test="gam-skills-install"[^>]*>\s*更新\s*<\/button>/);
      assert.doesNotMatch(html, /安装 \/ 更新/);
    } else assert.doesNotMatch(html, /data-test="gam-skills-check"/);
    if (source === 'other') {
      assert.match(html, /请通过原安装方式维护/);
      assert.match(html, /<button[^>]*disabled[^>]*data-test="gam-skills-install"/);
    }
  }
});

test('up-to-date skills hide the install action unless some skills are missing', async () => {
  for (const count of [6, 4]) {
    const html = await renderSfc('components/settings/GamSkillsSettings.vue', {
      configureSetup(bindings) {
        bindings.status.value = { ...absent, status: 'up_to_date', source: 'npx', installed_count: count, can_check: true };
      },
    });
    assert.match(html, /data-test="gam-skills-check"/);
    if (count === 6) assert.doesNotMatch(html, /data-test="gam-skills-install"/);
    else assert.match(html.replace(/<!--[\s\S]*?-->/g, ''), /data-test="gam-skills-install"[^>]*>\s*一键安装\s*<\/button>/);
  }
});

test('missing Node.js disables one-click install but keeps the copyable command', async () => {
  const html = await renderSfc('components/settings/GamSkillsSettings.vue', {
    configureSetup(bindings) { bindings.status.value = { ...absent, node_available: false }; },
  });
  assert.match(html, /<button[^>]*disabled[^>]*data-test="gam-skills-install"/);
  assert.match(html, /Node\.js 22\.20/);
  assert.match(html, /data-test="gam-skills-copy"/);
});

test('different independent copies explain the version conflict and cannot be overwritten', async () => {
  const html = await renderSfc('components/settings/GamSkillsSettings.vue', {
    configureSetup(bindings) {
      bindings.status.value = { ...absent, status: 'unmanaged', source: 'other', can_install: false, error: 'COPY_VERSION_MISMATCH' };
    },
  });
  assert.match(html, /无法确认所选工具的版本/);
  assert.match(html, /请通过原安装方式更新/);
  assert.doesNotMatch(html, /检测到其他方式安装/);
  assert.match(html, /<button[^>]*disabled[^>]*data-test="gam-skills-install"/);
});

test('switching agents discards the previous check response', async () => {
  let resolveOld;
  const old = new Promise(resolve => { resolveOld = resolve; });
  const { state } = setup(undefined, true, {
    getGamSkillsStatus: async agent => agent === 'codex' ? old : { ...absent, status: 'unmanaged', source: 'other' },
  });
  const checking = state.refreshStatus();
  state.agent.value = 'cursor';
  await nextTick();
  await nextTick();
  resolveOld({ ...absent, source: 'npx', status: 'update_available', outdated: ['gam-cli'] });
  await checking;
  assert.equal(state.status.value.source, 'other');
  assert.equal(state.checking.value, false);
});

test('install is explicit, prevents duplicates and reports failed verification', async () => {
  let finish;
  let calls = 0;
  const pending = new Promise(resolve => { finish = resolve; });
  const { state } = setup(undefined, true, { installGamSkills: async agent => {
    assert.equal(agent, 'codex'); calls++; return pending;
  } });
  state.status.value = { ...absent };
  assert.equal(calls, 0);
  const installing = state.installSkills();
  await state.installSkills();
  assert.equal(calls, 1);
  assert.equal(state.installing.value, true);
  finish({ success: false, state: { ...absent, error: 'INSTALL_FAILED' } });
  await installing;
  assert.equal(state.installed.value, false);
  assert.equal(state.operationError.value, 'INSTALL_FAILED');
  assert.equal(state.installing.value, false);
});

test('a verified install refreshes the version status and reports completion', async () => {
  const managed = { ...absent, source: 'npx', status: 'installed', installed_count: 6, can_check: true };
  const { state } = setup(undefined, true, {
    installGamSkills: async () => ({ success: true, state: managed }),
    getGamSkillsStatus: async () => ({ ...managed, status: 'up_to_date' }),
  });
  state.status.value = { ...absent };
  await state.installSkills();
  assert.equal(state.installed.value, true);
  assert.equal(state.status.value.status, 'up_to_date');
  assert.equal(state.installing.value, false);
});

test('a home badge link selects its agent while unrecognized query values use the default', () => {
  assert.equal(setup(undefined, true, {}, { skillsAgent: 'claude-code' }).state.agent.value, 'claude-code');
  assert.equal(setup(undefined, true, {}, { skillsAgent: 'unknown' }).state.agent.value, 'codex');
});
