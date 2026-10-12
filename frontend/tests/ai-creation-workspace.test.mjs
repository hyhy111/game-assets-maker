import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { after, test } from 'node:test';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';

after(closeSfcRenderer);

const source = (path) => readFile(new URL(`../src/${path}`, import.meta.url), 'utf8');

test('AI Creation Workspace starts in image mode with the shared header utilities', async () => {
  const html = await renderSfc('views/AICreationWorkspace.vue', {
    route: '/ai-creation',
  });

  assert.match(html, /Game Assets Maker/);
  assert.match(html, /class="h-5 w-5 object-contain"/);
  assert.doesNotMatch(html, /lucide-video-icon/);
  assert.match(html, /lucide-globe/);
  assert.match(html, /lucide-settings/);
  assert.match(html, /lucide-home-icon/);
  assert.match(html, /data-test="seedream-composer"/);
  assert.doesNotMatch(html, /data-test="seedance-composer"/);
});

test('shared AI Creation header uses the application logo', async () => {
  const nav = await source('components/layout/Header.vue');
  assert.match(nav, /new URL\('\.\.\/\.\.\/assets\/logo-2\.png', import\.meta\.url\)\.href/);
  assert.match(nav, /aria-label="Game Assets Maker"/);
  assert.doesNotMatch(nav, /brand-cloud/);
  assert.match(nav, /sticky\?: boolean/);
  assert.doesNotMatch(nav, /subtitle\?: string/);
  assert.match(nav, /Game Assets Maker/);
  assert.doesNotMatch(nav, /bg-primary\/15/);
  assert.doesNotMatch(nav, /<Video\b|\bVideo\s*[,}]/);
});

test('creation-mode controls live in each composer control row', async () => {
  const [imageHtml, videoHtml] = await Promise.all([
    renderSfc('views/SeedreamCreate.vue', { route: '/ai-creation' }),
    renderSfc('views/SeedanceCreate.vue', { route: '/ai-creation?mode=video' }),
  ]);

  for (const html of [imageHtml, videoHtml]) {
    assert.match(html, /data-test="creation-mode-image"/);
    assert.match(html, /data-test="creation-mode-video"/);
    assert.match(html, /生成图片/);
    assert.match(html, /生成视频/);
  }
});

test('workspace session state owns independent non-persisted drafts and mode-specific reset actions', async () => {
  const state = await source('stores/aiCreation.ts');

  assert.match(state, /activeMode = ref<CreationMode>\('image'\)/);
  assert.match(state, /const imageDraft = reactive<SeedreamCreateForm>/);
  assert.match(state, /const videoDraft = reactive<SeedanceCreateForm>/);
  assert.match(state, /function resetImageDraft/);
  assert.match(state, /function resetVideoDraft/);
  assert.match(state, /const currentGeneration = ref<CurrentGeneration \| null>\(null\)/);
  assert.match(state, /function setCurrentGeneration/);
  assert.doesNotMatch(state, /currentPanelCollapsed|collapseCurrentPanel|openCurrentPanel/);
  assert.doesNotMatch(state, /localStorage|sessionStorage|persist/);
});

test('draft clearing uses the shared in-app confirmation instead of a system dialog', async () => {
  const [dialog, imageCreate, videoCreate] = await Promise.all([
    renderSfc('components/ai-creation/DraftClearConfirmation.vue', { props: { open: true } }),
    source('views/SeedreamCreate.vue'),
    source('views/SeedanceCreate.vue'),
  ]);

  assert.match(dialog, /data-test="draft-clear-confirmation"/);
  assert.match(dialog, /class="[^"\n]*fixed inset-0[^"\n]*bg-black\/70/);
  assert.match(dialog, /max-w-md rounded-xl border border-dark-border bg-dark-surface p-6/);
  assert.match(dialog, /确认清空/);
  assert.match(dialog, /当前草稿尚未提交，确定清空吗？/);
  assert.match(dialog, /data-test="draft-clear-cancel"/);
  assert.match(dialog, /data-test="draft-clear-submit"/);
  for (const sourceText of [imageCreate, videoCreate]) {
    assert.match(sourceText, /<DraftClearConfirmation/);
    assert.doesNotMatch(sourceText, /window\.confirm\(t\('aiCreation\.clearConfirm'\)\)/);
  }
});

test('workspace remembers and restores scroll only for the current window session', async () => {
  const [state, workspace] = await Promise.all([
    source('stores/aiCreation.ts'),
    source('views/AICreationWorkspace.vue'),
  ]);

  assert.match(state, /const workspaceScrollY = ref\(0\)/);
  assert.match(state, /function rememberWorkspaceScroll\(scrollY: number\)/);
  assert.match(workspace, /onBeforeRouteLeave\(\(\) => \{[\s\S]*workspace\.rememberWorkspaceScroll\(window\.scrollY\)/);
  assert.match(workspace, /window\.scrollTo\(\{[\s\S]*top: workspace\.workspaceScrollY/);
  assert.doesNotMatch(state, /localStorage|sessionStorage|persist/);
});

test('creation workspace keeps a full-width composer and recent generations without a current-task sidebar', async () => {
  const workspace = await source('views/AICreationWorkspace.vue');

  assert.doesNotMatch(workspace, /ImageCurrentGenerationPanel|VideoCurrentGenerationPanel/);
  assert.doesNotMatch(workspace, /workAreaColumns|lg:grid-cols-/);
  assert.match(workspace, /<RecentGenerations/);
});

test('router exposes one workspace and safely redirects legacy create routes', async () => {
  const routes = await source('main.ts');

  assert.match(routes, /path: '\/ai-creation'/);
  assert.match(routes, /path: '\/image-generation\/create'[\s\S]*redirect:[\s\S]*\/ai-creation/);
  assert.match(routes, /path: '\/video-generation\/create'[\s\S]*redirect:[\s\S]*mode: 'video'/);
});

test('image and video details share AI Creation identity and return to the workspace without a mode override', async () => {
  const [imageHtml, videoHtml, imageSource, videoSource] = await Promise.all([
    renderSfc('views/SeedreamBatchDetail.vue', { route: '/image-generation/batches/missing' }),
    renderSfc('views/SeedancePreview.vue', { route: '/video-generation/tasks/missing' }),
    source('views/SeedreamBatchDetail.vue'),
    source('views/SeedancePreview.vue'),
  ]);

  assert.match(imageHtml, /Game Assets Maker/);
  assert.match(imageHtml, /AI 创作/);
  assert.match(imageHtml, /图片生成详情/);
  assert.match(imageHtml, /返回 AI 创作/);
  assert.doesNotMatch(imageHtml, /Seedream Studio/);
  assert.match(videoHtml, /Game Assets Maker/);
  assert.match(videoHtml, /AI 创作/);
  assert.match(videoHtml, /视频生成详情/);
  assert.match(videoHtml, /返回 AI 创作/);
  assert.doesNotMatch(videoHtml, /Seedance Studio/);
  assert.match(imageSource, /function backToTasks\(\) \{\s*router\.push\('\/ai-creation'\)/);
  assert.match(videoSource, /function backToTasks\(\) \{\s*void router\.push\('\/ai-creation'\)/);
  assert.match(imageSource, /await router\.push\('\/ai-creation'\)/);
  assert.match(videoSource, /await router\.push\('\/ai-creation'\)/);
});

test('AI Creation settings uses one canonical route and shared identity', async () => {
  const [routes, header, settings, html] = await Promise.all([
    source('main.ts'),
    source('components/layout/Header.vue'),
    source('views/SeedanceSettings.vue'),
    renderSfc('views/SeedanceSettings.vue', { route: '/ai-creation/settings' }),
  ]);

  assert.match(routes, /path: '\/ai-creation\/settings'[\s\S]*SeedanceSettings\.vue/);
  assert.match(routes, /path: '\/video-generation\/settings'[\s\S]*redirect: '\/ai-creation\/settings'/);
  assert.match(routes, /path: '\/image-generation\/settings'[\s\S]*redirect: '\/ai-creation\/settings'/);
  assert.match(header, /openSettings[\s\S]*router\.push\('\/video-generation\/settings'\)/);
  assert.match(settings, /<Header[\s\S]*sticky[\s\S]*page-aligned/);
  assert.doesNotMatch(settings, /<Header[^>]*:subtitle=/);
  assert.match(html, /Game Assets Maker/);
  assert.match(html, /<h1[^>]*>设置<\/h1>/);
  assert.doesNotMatch(html, /settings-back-to-workspace|返回 AI 创作/);
  assert.doesNotMatch(html, /Seedance Studio/);
});

test('unified settings cannot save placeholder defaults when any source failed to load', async () => {
  const [settings, config, seedream] = await Promise.all([
    source('views/SeedanceSettings.vue'),
    source('stores/config.ts'),
    source('stores/seedream.ts'),
  ]);

  assert.match(settings, /:disabled="!settingsReady"/);
  assert.match(settings, /if \(!settingsReady\.value\) return/);
  assert.match(settings, /seedanceSettingsLoaded\.value/);
  assert.match(settings, /const \[settingsLoaded, , , , storageResult\] = await Promise\.all/);
  assert.match(settings, /store\.settings[\s\S]*seedreamStore\.settings[\s\S]*configStore\.config/);
  assert.match(settings, /seedreamStore\.error[\s\S]*configStore\.error/);
  assert.match(config, /const error = ref<string \| null>\(null\)/);
  assert.match(seedream, /loadSettings[\s\S]*setError\(result\.error\)/);
  assert.match(await source('stores/seedance.ts'), /async function loadSettings\(\): Promise<boolean>[\s\S]*catch \(caught\)[\s\S]*return false/);
});

test('homepage presents one AI Creation pipeline entry', async () => {
  const manager = await source('views/ProjectManager.vue');

  assert.match(manager, /<ProjectManagerHero @start-ai-creation="goToAICreation" \/>/);
  assert.match(manager, /router\.push\('\/ai-creation'\)/);
  assert.doesNotMatch(manager, /projectManager\.aiImageGeneration/);
  assert.doesNotMatch(manager, /projectManager\.aiVideoGeneration/);
});
