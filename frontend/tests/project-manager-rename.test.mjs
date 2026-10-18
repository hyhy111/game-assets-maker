import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { renderSfc, closeSfcRenderer } from './vue-render-helper.mjs';
import { createScriptedPyWebViewBridge, closeFrontendHarness } from './scripted-pywebview-bridge.mjs';

after(async () => {
  await closeSfcRenderer();
  await closeFrontendHarness();
});
const idle = {
  id: 'hero/idle', role: 'hero', action: 'idle', name: 'idle',
  path: '/projects/hero/idle', video_path: '', frame_interval: 1,
  created_at: '2026-10-16T12:00:00', modified_at: '2026-10-16T12:00:00',
  steps: { '1': { count: 2, completed: true, data_ready: true } },
};
const other = { ...idle, id: 'enemy/idle', role: 'enemy' };
const renamed = { ...idle, role: 'knight', id: 'knight/idle', path: '/projects/knight/idle' };
const result = {
  projects: [renamed], roles: [{ name: 'knight', projectCount: 1 }, { name: 'enemy', projectCount: 1 }],
  idMap: { 'hero/idle': 'knight/idle' },
};
async function mount(state = {}) {
  let b;
  const html = await renderSfc('views/ProjectManager.vue', {
    piniaState: { project: { projects: [idle, other], roles: [], loading: false, ...state } },
    configureSetup(value) { b = value; },
  });
  return { b, html };
}

test('role menus follow the name and card menus precede the always visible delete button', async () => {
  const { html } = await mount();
  assert.match(html, /data-item-menu="role:hero"/);
  assert.match(html, /data-item-menu="project:hero\/idle"/);
  assert.doesNotMatch(html, /opacity-0/);
  assert.match(html, /hover:bg-danger\/15 hover:text-danger/);
  assert.match(html, /<button[^>]*aria-current="true"[\s\S]*?<\/button>\s*<div[^>]*data-item-menu="role:hero"/);
  const card = html.slice(html.indexOf('data-item-menu="project:hero/idle"'));
  assert.ok(card.indexOf('动画「idle」的更多操作') < card.indexOf('删除动画'));
  const source = await readFile(new URL('../src/components/project-manager/LibraryItemMenu.vue', import.meta.url), 'utf8');
  assert.equal((source.match(/<MenuItem\s/g) ?? []).length, 1);
  assert.match(source, /Teleport to="body"/);
  assert.match(source, /@click\.stop/);
  assert.match(source, /@keydown\.stop/);
});

test('role rename updates selection, current project and selected IDs together', async () => {
  const bridge = createScriptedPyWebViewBridge({ rename_role: [{ resolve: result }] });
  const { b } = await mount({ currentProject: idle, activeLibraryRole: 'hero' });
  b.toggleProjectSelection(idle.id);
  b.beginRoleRename('hero');
  assert.equal(b.renameName.value, 'hero');
  b.renameName.value = 'knight';
  await b.submitRename();
  assert.deepEqual(bridge.calls.filter(call => call.method === 'rename_role'), [{ method: 'rename_role', args: ['hero', 'knight'] }]);
  assert.equal(b.activeRole.value, 'knight');
  assert.equal(b.selectedGroup.value.role, 'knight');
  assert.equal(b.projectStore.currentProject.id, 'knight/idle');
  assert.deepEqual([...b.selectedProjectIds.value], ['knight/idle']);
  assert.equal(b.projectStore.projects[1].id, 'enemy/idle');
  assert.equal(b.renameTarget.value, null);
});

test('renaming another role preserves the selected role', async () => {
  const { b } = await mount({ activeLibraryRole: 'enemy' });
  b.applyRenameResult(result);
  await new Promise(setImmediate);
  assert.equal(b.activeRole.value, 'enemy');
});

test('animation rename calls its bridge and preserves a valid page', async () => {
  const attack = { ...idle, action: 'attack', name: 'attack', id: 'hero/attack' };
  const bridge = createScriptedPyWebViewBridge({ rename_project: [{ resolve: {
    projects: [attack], roles: [{ name: 'hero', projectCount: 20 }], idMap: { 'hero/idle': 'hero/attack' },
  } }] });
  const projects = [idle, ...Array.from({ length: 19 }, (_, i) => ({ ...idle, id: `hero/test-${i}`, action: `test-${i}` }))];
  const { b } = await mount({ projects, activeLibraryRole: 'hero' });
  b.animationPage.value = 2;
  b.beginProjectRename(idle);
  b.renameName.value = 'attack';
  await b.submitRename();
  assert.equal(b.animationPage.value, 2);
  assert.equal(b.activeRole.value, 'hero');
  assert.equal(b.projectStore.projects[0].name, 'attack');
  assert.deepEqual(bridge.calls.find(call => call.method === 'rename_project'), { method: 'rename_project', args: ['hero/idle', 'attack'] });
});

test('cancel and empty input never call the bridge', async () => {
  const bridge = createScriptedPyWebViewBridge({});
  const { b } = await mount();
  b.beginProjectRename(idle);
  b.renameName.value = ' ';
  await b.submitRename();
  b.closeRename();
  await b.submitRename();
  assert.equal(b.renameTarget.value, null);
  assert.equal(b.projectStore.projects[0].id, idle.id);
  assert.equal(bridge.calls.filter(call => call.method.startsWith('rename_')).length, 0);
});

test('failed save preserves input and supports retry', async () => {
  const bridge = createScriptedPyWebViewBridge({ rename_role: [
    { reject: { message: 'RENAME_CONFLICT: duplicate' } }, { resolve: result },
  ] });
  const { b } = await mount();
  b.beginRoleRename('hero');
  b.renameName.value = 'knight';
  await b.submitRename();
  assert.equal(b.renameName.value, 'knight');
  assert.equal(b.renameTarget.value.id, 'hero');
  assert.match(b.renameError.value, /名称已存在/);
  assert.equal(b.projectStore.projects[0].id, idle.id);
  await b.submitRename();
  assert.equal(b.renameTarget.value, null);
  assert.equal(bridge.calls.filter(call => call.method.startsWith('rename_')).length, 2);
});

test('pending save blocks duplicate submits and cancellation', async () => {
  let finish;
  const pending = new Promise(resolve => { finish = resolve; });
  const bridge = createScriptedPyWebViewBridge({ rename_role: [{ resolve: () => pending }] });
  const { b } = await mount();
  b.beginRoleRename('hero');
  b.renameName.value = 'knight';
  const saving = b.submitRename();
  await new Promise(setImmediate);
  await b.submitRename();
  b.closeRename();
  assert.equal(b.renaming.value, true);
  assert.equal(b.renameTarget.value.id, 'hero');
  assert.equal(bridge.calls.filter(call => call.method.startsWith('rename_')).length, 1);
  finish(result);
  await saving;
  assert.equal(b.renaming.value, false);
});

test('old preview responses cannot restore old URLs after rename', async () => {
  let finish;
  const pending = new Promise(resolve => { finish = resolve; });
  createScriptedPyWebViewBridge({ get_frames: [{ resolve: () => pending }] });
  const { b } = await mount();
  const loading = b.loadPreviewFrames(idle);
  await new Promise(setImmediate);
  b.applyRenameResult(result);
  finish({ success: true, frames: [{ url: '/old/hero/idle.png' }] });
  assert.deepEqual(await loading, []);
  assert.equal(b.previewFrames.value[idle.id], undefined);
  assert.equal(b.previewLoading.value.size, 0);
});

test('legacy rename maps migration drafts without losing user input', async () => {
  const old = { ...idle, id: 'old', role: '未迁移', action: 'old', legacy: true };
  const { b, html } = await mount({ projects: [old] });
  assert.doesNotMatch(html, /data-item-menu="role:未迁移"/);
  b.beginRoleRename('未迁移');
  assert.equal(b.renameTarget.value, null);
  b.migrationDrafts.value.old = { targetRole: 'chosen', targetAction: 'custom' };
  b.applyRenameResult({ projects: [{ ...old, id: 'new', action: 'new', name: 'new' }], roles: [], idMap: { old: 'new' } });
  await new Promise(setImmediate);
  assert.deepEqual(b.migrationDrafts.value.new, { targetRole: 'chosen', targetAction: 'custom' });
  assert.equal(b.migrationDrafts.value.old, undefined);
});

test('search survives rename and clearing it recovers the renamed project', async () => {
  const { b } = await mount({ activeLibraryRole: 'hero' });
  b.searchQuery.value = 'hero';
  await new Promise(setImmediate);
  b.applyRenameResult(result);
  await new Promise(setImmediate);
  assert.equal(b.searchQuery.value, 'hero');
  assert.equal(b.selectedGroup.value, null);
  b.searchQuery.value = '';
  assert.equal(b.selectedGroup.value.role, 'knight');
});


test('an unknown bridge failure does not claim a successful rollback', async () => {
  createScriptedPyWebViewBridge({ rename_role: [{ reject: new Error('bridge disconnected') }] });
  const { b } = await mount();
  b.beginRoleRename('hero');
  b.renameName.value = 'knight';
  await b.submitRename();
  assert.match(b.renameError.value, /未能确认重命名结果/);
  assert.doesNotMatch(b.renameError.value, /已保留/);
  assert.equal(b.renameTarget.value.id, 'hero');
});
