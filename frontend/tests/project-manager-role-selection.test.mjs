import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { renderSfc, closeSfcRenderer } from './vue-render-helper.mjs';
import { createScriptedPyWebViewBridge, closeFrontendHarness } from './scripted-pywebview-bridge.mjs';

after(async () => {
  await closeSfcRenderer();
  await closeFrontendHarness();
});

const projects = ['default-role', 'chosen-role'].map(role => ({
  id: `${role}/idle`, role, action: 'idle', name: 'idle',
  path: `/projects/${role}/idle`, video_path: '', frame_interval: 1,
  created_at: '2026-10-16T12:00:00', modified_at: '2026-10-16T12:00:00',
}));

async function mountLibrary(state, configure) {
  let bindings;
  const html = await renderSfc('views/ProjectManager.vue', {
    piniaState: state,
    configureSetup(value) {
      bindings = value;
      configure?.(value);
    },
  });
  return { bindings, html };
}

test('returning from the editor restores the selected library role after current project is cleared', async () => {
  createScriptedPyWebViewBridge({
    get_frames: [{ resolve: { success: true, frames: [] } }],
  });
  const { bindings } = await mountLibrary({ project: { projects, loading: false } });
  assert.equal(bindings.selectedGroup.value.role, 'default-role');
  bindings.selectRole('chosen-role');
  bindings.router.addRoute({ path: '/editor', component: { render: () => null } });
  await bindings.openProject(projects[1]);
  assert.equal(bindings.projectStore.currentProject.id, projects[1].id);
  await bindings.router.push('/');
  bindings.projectStore.setCurrentProject(null);

  const returned = await mountLibrary({ project: bindings.projectStore.$state });
  assert.equal(returned.bindings.selectedGroup.value.role, 'chosen-role');
  assert.match(returned.html, /aria-current="true"[^>]*>[\s\S]*?chosen-role/);
});

test('reloading projects keeps a valid role selection despite changed list order', async () => {
  createScriptedPyWebViewBridge({
    get_projects: [{ resolve: [{ ...projects[0], role: 'new-first-role', id: 'new-first-role/idle' }, ...projects] }],
    get_roles: [{ resolve: [] }],
  });
  const { bindings } = await mountLibrary({ project: { projects, loading: false } });
  bindings.selectRole('chosen-role');
  await bindings.projectStore.loadProjects();
  const returned = await mountLibrary({ project: bindings.projectStore.$state });
  assert.equal(returned.bindings.selectedGroup.value.role, 'chosen-role');
});

test('returning to a library whose selected role was removed falls back to an available role', async () => {
  const { bindings } = await mountLibrary({ project: { projects, loading: false } });
  bindings.selectRole('chosen-role');
  bindings.projectStore.projects = [projects[0]];
  const returned = await mountLibrary({ project: bindings.projectStore.$state });
  assert.equal(returned.bindings.selectedGroup.value.role, 'default-role');
});

const manyProjects = [
  ...projects,
  ...Array.from({ length: 18 }, (_, index) => ({
    ...projects[1],
    id: `chosen-role/test-${index}`,
    action: `test-${index}`,
    name: `test-${index}`,
  })),
];

test('returning restores search, page and both scroll positions after delayed loading and responsive sizing', async () => {
  let resolveProjects;
  const pendingProjects = new Promise(resolve => { resolveProjects = resolve; });
  const bridge = createScriptedPyWebViewBridge({
    get_projects: [{ resolve: () => pendingProjects }],
    get_roles: [{ resolve: [] }],
  });
  const scrolls = [];
  bridge.window.innerWidth = 900;
  bridge.window.scrollY = 730;
  bridge.window.scrollTo = options => scrolls.push(options);

  const { bindings } = await mountLibrary({ project: { projects: manyProjects, loading: false } });
  bindings.selectRole('chosen-role');
  bindings.searchQuery.value = 'chosen-role';
  bindings.animationPage.value = 2;
  bindings.roleNav.value = { scrollTop: 223 };
  bindings.rememberLibraryView();

  const returned = await mountLibrary({ project: bindings.projectStore.$state });
  returned.bindings.roleNav.value = { scrollTop: 0 };
  const initializing = returned.bindings.initializeLibrary();
  await new Promise(setImmediate);
  assert.equal(returned.bindings.projectStore.loading, true);
  assert.deepEqual(scrolls, []);

  resolveProjects(manyProjects);
  await initializing;
  assert.equal(returned.bindings.selectedGroup.value.role, 'chosen-role');
  assert.equal(returned.bindings.searchQuery.value, 'chosen-role');
  assert.equal(returned.bindings.cardsPerPage.value, 8);
  assert.equal(returned.bindings.animationPage.value, 2);
  assert.equal(returned.bindings.paginatedProjects.value[0].id, 'chosen-role/test-7');
  assert.equal(returned.bindings.roleNav.value.scrollTop, 223);
  assert.deepEqual(scrolls, [{ top: 730, behavior: 'auto' }]);
});

test('returning clamps a saved page when animations have been removed', async () => {
  const bridge = createScriptedPyWebViewBridge({
    get_projects: [{ resolve: projects }],
    get_roles: [{ resolve: [] }],
  });
  bridge.window.innerWidth = 1400;
  bridge.window.scrollTo = () => {};
  const { bindings } = await mountLibrary({
    project: {
      projects: manyProjects, loading: false, activeLibraryRole: 'chosen-role',
      libraryViewState: { searchQuery: '', animationPage: 2, scrollY: 730, roleScrollTop: 223 },
    },
  });
  await bindings.initializeLibrary();
  assert.equal(bindings.animationPage.value, 1);
  assert.equal(bindings.paginatedProjects.value[0].id, 'chosen-role/idle');
});

test('leaving during a slow reload prevents the old page from restoring scroll later', async () => {
  let resolveProjects;
  const pendingProjects = new Promise(resolve => { resolveProjects = resolve; });
  const bridge = createScriptedPyWebViewBridge({
    get_projects: [{ resolve: () => pendingProjects }],
    get_roles: [{ resolve: [] }],
  });
  const scrolls = [];
  bridge.window.innerWidth = 1400;
  bridge.window.scrollY = 42;
  bridge.window.scrollTo = options => scrolls.push(options);
  const { bindings } = await mountLibrary({ project: { projects, loading: false } });
  const initializing = bindings.initializeLibrary();
  bindings.roleNav.value = { scrollTop: 17 };
  bindings.rememberLibraryView();
  resolveProjects(projects);
  await initializing;
  assert.deepEqual(scrolls, []);
  assert.equal(bindings.projectStore.libraryViewState.scrollY, 42);
  assert.equal(bindings.projectStore.libraryViewState.roleScrollTop, 17);
});
