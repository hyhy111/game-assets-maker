import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

test('project manager presents AI creation hero and lazily previews extracted animations', async () => {
  const [source, hero, zhLocale] = await Promise.all([
    readFile(new URL('../src/views/ProjectManager.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/project-manager/ProjectManagerHero.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/locales/zh-CN.ts', import.meta.url), 'utf8'),
  ]);

  assert.match(source, /<ProjectManagerHero @start-ai-creation="goToAICreation" \/>/);
  assert.match(hero, /Prompt →/);
  assert.match(hero, /Game Assets/);
  assert.match(hero, /v-for="capability in capabilities"/);
  assert.equal((hero.match(/v-else-if="activeStage === [123]"/g) ?? []).length, 3);
  assert.match(hero, /activeStage === 4/);
  assert.match(hero, /window\.setInterval\(advanceFlow, 2800\)/);
  assert.match(hero, /prefers-reduced-motion: reduce/);
  assert.doesNotMatch(hero, /hero-glow/);
  assert.match(hero, /background: linear-gradient\(145deg, rgb\(36 36 36 \/ 96%\), rgb\(24 24 24 \/ 98%\)\)/);
  assert.match(hero, /\.prompt-input\s*\{[^}]*box-shadow:\s*0 0 0 1px rgb\(255 189 92 \/ 8%\), 0 0 28px rgb\(255 189 92 \/ 22%\)/s);
  assert.match(zhLocale, /heroSubtitle: '一站式游戏资产工作台'/);
  assert.match(zhLocale, /heroStart: '开始 AI 创作'/);

  assert.match(source, /v-if="!loading && legacyProjects\.length > 0"/);
  assert.match(source, /font-mono text-\[10px\] tracking-\[0\.16em\] text-primary[^>]*>\s*Game Assets/);
  assert.doesNotMatch(source, /Animation Library/);
  assert.match(source, /@mouseenter="startProjectPreview\(project\)"/);
  assert.match(source, /step\.count > 0 && \(step\.data_ready \|\| step\.completed\)/);
  assert.match(source, /getFrames\(project\.id, previewSourceStep\(project\), 1, 12, true\)/);
  assert.match(source, /const cached = previewFrames\.value\[project\.id\]/);
  const previewStatusTag = source.match(/<span\s+v-if="canPreview\(project\)"[\s\S]*?>/)?.[0] ?? '';
  assert.match(previewStatusTag, /data-test="project-preview-status"/);
  assert.doesNotMatch(previewStatusTag, /opacity-0|group-hover:opacity-100|group-focus:opacity-100/);
  assert.match(zhLocale, /batchTrim: '统一裁剪并导出'/);
  assert.match(zhLocale, /animationLibrary: '游戏资产'/);
  assert.match(zhLocale, /deleteProject: '删除动画'/);
  assert.match(zhLocale, /deleteProjectConfirm: '确定要删除动画/);
  assert.doesNotMatch(zhLocale, /deleteProject: '删除项目'/);
});

test('project manager uses a role dock with one expanded role detail', async () => {
  const manager = await readFile(new URL('../src/views/ProjectManager.vue', import.meta.url), 'utf8');

  assert.match(manager, /data-test="project-manager-library-workbench"/);
  assert.match(manager, /data-test="project-manager-role-dock"/);
  assert.match(manager, /data-test="project-manager-role-detail"/);
  assert.match(manager, /const activeRole = ref\(''\)/);
  assert.match(manager, /const selectedGroup = computed/);
  assert.match(manager, /@click="selectRole\(group\.role\)"/);
  assert.match(manager, /v-for="project in paginatedProjects"/);
  assert.match(manager, /data-test="create-frame-animation"[\s\S]*type="search"[\s\S]*<nav/);
  assert.match(manager, /data-test="create-frame-animation"[\s\S]*@click="goToCreate\(\)"/);
  assert.match(manager, /t\('projectManager\.createNewRole'\)/);
  assert.match(manager, /\.library-workbench\s*\{[^}]*grid-template-columns:\s*minmax\(210px, 240px\) minmax\(0, 1fr\)/s);
  assert.doesNotMatch(manager, /\.role-dock\s*\{[^}]*border-right/s);
});

test('project manager uses a 24-hour clock in English', async () => {
  const manager = await readFile(new URL('../src/views/ProjectManager.vue', import.meta.url), 'utf8');

  assert.match(manager, /locale\.value\.startsWith\('en'\) \? \{ hourCycle: 'h23' as const \} : \{\}/);
});

test('project manager limits the role dock and paginates animation cards to four rows', async () => {
  const manager = await readFile(new URL('../src/views/ProjectManager.vue', import.meta.url), 'utf8');

  assert.match(manager, /\.role-nav\s*\{[^}]*max-height:\s*28\.95rem;[^}]*overflow-y:\s*auto;/s);
  assert.match(manager, /const cardsPerPage = ref\(16\)/);
  assert.match(manager, /const paginatedProjects = computed/);
  assert.match(manager, /v-for="project in paginatedProjects"/);
  assert.match(manager, /window\.addEventListener\('resize', updateCardsPerPage\)/);
  assert.match(manager, /if \(width >= 1280\) next = 16/);
  assert.match(manager, /else if \(width >= 1024\) next = 12/);
  assert.match(manager, /else if \(width >= 640\) next = 8/);
  assert.match(manager, /v-if="animationPageCount > 1"/);
});

test('project manager imports a user-selected legacy project directory', async () => {
  const [manager, store, zhLocale] = await Promise.all([
    readFile(new URL('../src/views/ProjectManager.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/stores/project.ts', import.meta.url), 'utf8'),
    readFile(new URL('../src/locales/zh-CN.ts', import.meta.url), 'utf8'),
  ]);

  assert.match(manager, /data-test="import-legacy-projects"/);
  assert.match(manager, /api\.system\.selectDirectory\(\)/);
  assert.match(manager, /projectStore\.importLegacyProjectDirectory\(directory\)/);
  assert.match(store, /api\.project\.importLegacyProjectDirectory\(sourceDirectory\)/);
  assert.match(store, /await loadProjects\(\)/);
  assert.match(zhLocale, /importLegacyProjects: '导入旧版项目'/);
  assert.match(zhLocale, /importLegacyProjectsHint: '选择旧版 Video to Sheet 的 project 目录/);
});

test('project manager selects and directly trims animation cards', async () => {
  const [manager, zhLocale] = await Promise.all([
    readFile(new URL('../src/views/ProjectManager.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/locales/zh-CN.ts', import.meta.url), 'utf8'),
  ]);

  assert.match(manager, /type="checkbox"/);
  assert.match(manager, /@change="toggleProjectSelection\(project\.id\)"/);
  assert.match(manager, /role="radiogroup"/);
  assert.match(manager, /inline-flex h-\[34px\] items-center/);
  assert.match(manager, /@click="trimMode = 'global'"/);
  assert.match(manager, /@click="trimMode = 'individual'"/);
  assert.match(manager, /:aria-checked="trimMode === 'global'"/);
  assert.match(manager, /:aria-checked="trimMode === 'individual'"/);
  assert.equal((manager.match(/bg-primary\/20 text-primary-200/g) ?? []).length, 2);
  assert.match(manager, /const trimMode = ref<'global' \| 'individual'>\('global'\)/);
  assert.match(manager, /@click="executeSelectedTrim\(selectedGroup\)"/);
  assert.match(manager, /:variant="selectedInRole\(selectedGroup\) > 0 \? 'primary' : 'ghost'"/);
  assert.match(manager, /api\.batchTrim\.executeTrim\(\{/);
  assert.match(manager, /mode: trimMode\.value/);
  assert.match(manager, /:show="showTrimSuccessModal"/);
  assert.match(manager, /v-for="path in trimOutputDirectories"/);
  assert.match(manager, /api\.system\.openProjectFolder\(path\)/);
  assert.match(manager, /@click="toggleRoleSelection\(selectedGroup\)"/);
  assert.match(manager, /isRoleFullySelected\(selectedGroup\)/);
  assert.match(manager, /@click="copyOutputPath\(path\)"/);
  assert.match(manager, /navigator\.clipboard\?\.writeText/);
  assert.match(manager, /document\.execCommand\('copy'\)/);
  assert.match(zhLocale, /trimExport: '裁剪导出'/);
  assert.match(zhLocale, /trimSuccessTitle: '裁剪导出完成'/);
});
