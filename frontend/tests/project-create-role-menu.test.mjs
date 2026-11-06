import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

test('project create role menu closes on Enter and outside pointer down', async () => {
  const source = await readFile(new URL('../src/views/ProjectCreate.vue', import.meta.url), 'utf8');

  assert.match(source, /<div ref="roleMenuContainer" class="relative">/);
  assert.match(source, /@keydown\.enter="roleMenuOpen = false"/);
  assert.match(source, /document\.addEventListener\('pointerdown', closeRoleMenuOnOutsidePointerDown\)/);
  assert.match(source, /document\.removeEventListener\('pointerdown', closeRoleMenuOnOutsidePointerDown\)/);
  assert.match(source, /if \(!roleMenuContainer\.value\?\.contains\(event\.target as Node\)\) \{\s*roleMenuOpen\.value = false;/);
  assert.match(source, /@mousedown\.prevent="selectRole\(role\.name\)"/);
});
