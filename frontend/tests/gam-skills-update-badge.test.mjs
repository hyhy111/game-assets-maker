import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { createPinia, setActivePinia } from 'pinia';
import { closeFrontendHarness, createScriptedPyWebViewBridge, loadFrontendModule } from './scripted-pywebview-bridge.mjs';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';

after(closeFrontendHarness);
after(closeSfcRenderer);

const available = {
  status: 'update_available', source: 'npx', installed_count: 6, total_count: 6, outdated: ['gam-cli'],
  error: '', can_check: true, can_install: true, node_available: true,
};
const current = { ...available, status: 'up_to_date', outdated: [] };

async function fixture(entries) {
  const bridge = createScriptedPyWebViewBridge({ get_gam_skills_updates: entries });
  setActivePinia(createPinia());
  const { useGamSkillsUpdatesStore } = await loadFrontendModule('/src/stores/gamSkillsUpdates.ts');
  return { bridge, store: useGamSkillsUpdatesStore() };
}

test('startup checks once and waits for a confirmed npx update before showing a badge', async () => {
  let resolve;
  const pending = new Promise(done => { resolve = done; });
  const { bridge, store } = await fixture([{ resolve: () => pending }]);
  assert.equal(store.hasUpdate, false);
  const check = store.initialize();
  await store.initialize();
  assert.equal(store.checking, true);
  assert.equal(store.hasUpdate, false);
  resolve({ 'claude-code': available });
  await check;
  assert.equal(bridge.calls.length, 1);
  assert.equal(bridge.calls[0].method, 'get_gam_skills_updates');
  assert.deepEqual(bridge.calls[0].args, []);
  assert.equal(store.hasUpdate, true);
  assert.equal(store.updateAgent, 'claude-code');
});

for (const state of [
  { ...available, source: 'other' },
  { ...available, source: 'none' },
  { ...available, status: 'error', error: 'CHECK_FAILED' },
  { ...available, can_check: false },
  current,
]) {
  test(`${state.source}/${state.status}/${state.can_check}: no badge without a verified tracked update`, async () => {
    const { store } = await fixture([{ resolve: { codex: state } }]);
    await store.initialize();
    assert.equal(store.hasUpdate, false);
  });
}

test('refresh after installation clears all updated agent notifications', async () => {
  const { store } = await fixture([
    { resolve: { codex: available, 'claude-code': available } },
    { resolve: { codex: current, 'claude-code': current } },
  ]);
  await store.initialize();
  assert.equal(store.hasUpdate, true);
  await store.refresh();
  assert.equal(store.hasUpdate, false);
});

test('a failed refresh does not retain an unconfirmed update badge', async () => {
  const { store } = await fixture([{ reject: new Error('offline') }]);
  store.record('codex', available);
  await store.refresh();
  assert.equal(store.hasUpdate, false);
  assert.equal(store.checking, false);
});

test('an older startup response cannot restore the badge cleared by settings', async () => {
  let resolve;
  const pending = new Promise(done => { resolve = done; });
  const { store } = await fixture([{ resolve: () => pending }]);
  const checking = store.initialize();
  store.record('claude-code', current);
  resolve({ 'claude-code': available, codex: current });
  await checking;
  assert.equal(store.states['claude-code'].status, 'up_to_date');
  assert.equal(store.hasUpdate, false);
});

test('home badge links to the matching agent and disappears for other installations', async () => {
  const render = state => renderSfc('components/project-manager/ProjectManagerHero.vue', {
    piniaState: { 'gam-skills-updates': { states: { 'claude-code': state } } },
  });
  const html = await render(available);
  assert.match(html, /data-test="gam-skills-update-badge"/);
  assert.match(html, /href="\/ai-creation\/settings\?skillsAgent=claude-code#gam-skills"/);
  assert.match(html, /title="GAM Skills 有更新"/);
  assert.match(html, /h-2 w-2 rounded-full bg-primary/);
  const unmanaged = await render({ ...available, source: 'other' });
  assert.doesNotMatch(unmanaged, /data-test="gam-skills-update-badge"/);
  assert.match(unmanaged, /href="\/ai-creation\/settings#gam-skills"/);
});
