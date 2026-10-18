import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { renderSfc, closeSfcRenderer } from './vue-render-helper.mjs';

after(closeSfcRenderer);
const project = {
  id: 'knight/attack', role: 'knight', action: 'attack', name: 'attack',
  path: '/projects/knight/attack', video_path: '', frame_interval: 1,
  created_at: '2026-10-15T12:00:00', modified_at: '2026-10-15T12:00:00',
};

async function searchLibrary(query, clear = false, projects = [project]) {
  return renderSfc('views/ProjectManager.vue', {
    piniaState: { project: { projects, loading: false } },
    configureSetup(bindings) {
      bindings.searchQuery.value = query;
      if (clear) {
        assert.equal(bindings.selectedGroup.value, null);
        bindings.searchQuery.value = '';
        assert.equal(bindings.selectedGroup.value?.role, project.role);
      }
    },
  });
}

test('no search results keep the library and search field visible so the query can be cleared', async () => {
  const html = await searchLibrary('does-not-exist');
  assert.match(html, /没有找到匹配的角色或动画/);
  assert.match(html, /data-test="project-manager-role-dock"/);
  assert.match(html, /type="search"/);
  assert.match(html, /value="does-not-exist"/);
  assert.doesNotMatch(html, /data-test="project-manager-role-detail"/);
});

test('clearing an unmatched query restores the role and its animation', async () => {
  const html = await searchLibrary('does-not-exist', true);
  assert.match(html, /type="search"/);
  assert.match(html, /data-test="project-manager-role-detail"/);
  assert.match(html, /knight/);
  assert.match(html, /attack/);
  assert.doesNotMatch(html, /没有找到匹配的角色或动画/);
});

test('an empty library keeps its original create and import entrypoints', async () => {
  const html = await searchLibrary('', false, []);
  assert.match(html, /class="empty-library"/);
  assert.match(html, /data-test="import-legacy-projects-empty"/);
  assert.doesNotMatch(html, /没有找到匹配的角色或动画/);
});


test('a rename that no longer matches the search keeps the search recovery controls', async () => {
  const html = await renderSfc('views/ProjectManager.vue', {
    piniaState: { project: { projects: [project], roles: [], loading: false } },
    configureSetup(bindings) {
      bindings.searchQuery.value = 'knight';
      bindings.applyRenameResult({
        projects: [{ ...project, id: 'mage/attack', role: 'mage' }],
        roles: [{ name: 'mage', projectCount: 1 }],
        idMap: { 'knight/attack': 'mage/attack' },
      });
    },
  });
  assert.match(html, /没有找到匹配的角色或动画/);
  assert.match(html, /type="search"/);
  assert.match(html, /value="knight"/);
});
