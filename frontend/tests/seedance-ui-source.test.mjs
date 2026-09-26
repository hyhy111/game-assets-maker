import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

const source = async (name) => readFile(new URL(`../src/${name}`, import.meta.url), 'utf8');

test('Seedance UI defines the fixed capability and request guards', async () => {
  const ui = await source('seedance-ui.ts');
  assert.match(ui, /standard:\s*\['480p', '720p', '1080p'\]/);
  assert.doesNotMatch(ui, /4k/);
  assert.match(ui, /fast:\s*\['480p', '720p'\]/);
  assert.match(ui, /mini:\s*\['480p', '720p'\]/);
  assert.match(ui, /export function correctResolution/);
  assert.match(ui, /export function validateCreateForm/);
  assert.match(ui, /export function createRequest/);
  assert.match(ui, /CREATE_REQUEST_KEYS/);
  assert.match(ui, /return hours \?/);
});

test('Seedance option controls share the compact input height', async () => {
  const styles = await source('styles/main.css');
  assert.match(styles, /\.seedance-control:not\(textarea\)\s*\{\s*height:\s*42px;/);
});

test('Seedance detailed settings use a compact ratio selector and custom duration dropdown', async () => {
  const [create, ratioPicker] = await Promise.all([
    source('views/SeedanceCreate.vue'),
    source('components/seedance/SeedanceRatioPicker.vue'),
  ]);
  assert.match(create, /data-test="seedance-duration"/);
  assert.doesNotMatch(create, /<select[^>]*data-test="seedance-duration"/);
  assert.match(ratioPicker, /grid-cols-4 gap-1 rounded-xl bg-black\/15 p-1/);
  assert.doesNotMatch(ratioPicker, /shapeClass|border-primary/);
});

test('Seedance header delegates to the unified AI Creation navigation', async () => {
  const navigation = await source('components/seedance/SeedanceTopNav.vue');
  assert.match(navigation, /<Header[\s\S]*sticky[\s\S]*page-aligned/);
  assert.doesNotMatch(navigation, /subtitle/);
  assert.doesNotMatch(navigation, /<nav/);
  assert.doesNotMatch(navigation, /seedanceResultRoute|seedance\.nav\.(?:create|tasks|preview)/);
});

test('role-animation entry points use role language without technical source details', async () => {
  const [zh, handoff] = await Promise.all([
    source('locales/zh-CN.ts'),
    source('components/seedance/SeedanceHandoffPanel.vue'),
  ]);
  assert.match(zh, /createNew: '创建新动画'/);
  assert.match(zh, /title: '创建角色动画'/);
  assert.match(zh, /createProject: '创建动画'/);
  assert.match(zh, /createVideo: '创建视频'/);
  assert.match(zh, /submit: '创建逐帧动画'/);
  assert.match(zh, /creatingProject: '角色动画正在创建中'/);
  assert.match(zh, /success: '角色动画已创建：\{id\}'/);
  assert.doesNotMatch(handoff, /projectPath|sourceHint|task\.local_id|handoff\.description/);
});

test('project creation aligns its back action to the right edge', async () => {
  const projectCreate = await source('views/ProjectCreate.vue');
  assert.match(projectCreate, /<Header page-aligned \/>/);
  assert.match(projectCreate, /class="mb-4 ml-auto flex w-fit items-center gap-1/);
});

test('homepage header aligns with the 1320px page content while other header modes stay available', async () => {
  const [header, pageBar, manager] = await Promise.all([
    source('components/layout/Header.vue'),
    source('components/seedance/SeedancePageBar.vue'),
    source('views/ProjectManager.vue'),
  ]);
  assert.match(header, /pageAligned \? 'mx-auto w-full max-w-\[1320px\] sm:px-6'/);
  assert.match(header, /pageAligned\?: boolean/);
  assert.match(header, /'flex items-center justify-between px-4'/);
  assert.match(header, /sticky \? 'h-16 gap-6' : 'h-14'/);
  assert.match(manager, /<Header\s+page-aligned/);
  assert.match(manager, /<section class="mx-auto w-full max-w-\[1320px\]/);
  assert.match(pageBar, /<div class="seedance-container py-4">/);
  assert.match(pageBar, /rounded-\[14px\][^\"]*border[^\"]*bg-\[#1d1e1d\]/);
});

test('shared header uses the supplied application logo', async () => {
  const header = await source('components/layout/Header.vue');
  assert.match(header, /new URL\('\.\.\/\.\.\/assets\/logo-2\.png', import\.meta\.url\)\.href/);
  assert.match(header, /:src="logoUrl"/);
  assert.match(header, /flex items-end gap-2 text-lg font-semibold leading-none text-white/);
  assert.doesNotMatch(header, /<Film\b|\bFilm,/);
});

test('logged-out header uses the amber round account login icon', async () => {
  const header = await source('components/layout/Header.vue');
  assert.match(header, /CircleUserRound/);
  assert.match(header, /<CircleUserRound class="h-5 w-5"/);
  assert.match(header, /text-\[#ffbd5c\]/);
  assert.doesNotMatch(header, /<LogIn\b/);
});

test('project processing restores the edge-aligned full-width header', async () => {
  const [header, editor] = await Promise.all([
    source('components/layout/Header.vue'),
    source('views/Editor/EditorLayout.vue'),
  ]);
  assert.match(header, /fullWidth\?: boolean/);
  assert.match(editor, /<Header full-width \/>/);
});

test('Seedance preview and create retain protected actions and preflight guards', async () => {
  const [preview, create] = await Promise.all([
    source('views/SeedancePreview.vue'),
    source('views/SeedanceCreate.vue'),
  ]);
  assert.match(preview, /function requestDelete\(\) \{\s*if \(task\.value\) void openConfirmation\('delete'\)/);
  assert.match(preview, /deleteTask\(!!task\?\.protected\)/);
  assert.match(preview, /protectedDeleteWarning/);
  assert.match(preview, /pendingPaidAction/);
  assert.match(preview, /retryBillingWarning/);
  assert.match(preview, /function continueFromReturnedFrame/);
  assert.match(preview, /query: \{ continue: task\.value\.local_id \}/);
  assert.doesNotMatch(preview, /store\.continueTask/);
  assert.match(preview, /query: \{ regenerate: task\.value\.local_id \}/);
  assert.match(preview, /store\.retryTask/);
  assert.match(preview, /if \(!task\.value \|\| confirmingPaidAction\.value\) return/);
  assert.match(preview, /:disabled="confirmingPaidAction"/);
  assert.match(preview, /trapModalTab/);
  assert.match(preview, /@click="downloadVideo"/);
  assert.match(preview, /variant="primary"\s+@click="regenerate"/);
  assert.match(preview, /@click="regenerate"[\s\S]*@click="continueFromReturnedFrame"[\s\S]*@click="downloadVideo"/);
  assert.doesNotMatch(preview, /seedance\.preview\.nextSteps/);
  assert.match(preview, /variant="primary"\s+:loading="savingVideo"\s+@click="downloadVideo"/);
  assert.match(preview, /store\.saveVideo/);
  assert.match(preview, /seedance\.preview\.saveVideo/);
  assert.match(preview, /:creating="handoffCreating"/);
  assert.match(preview, /await router\.push\('\/editor'\)/);
  assert.doesNotMatch(preview, /<a(?:\s|>)[\s\S]*?download[\s\S]*?downloadVideo/);
  assert.match(create, /validationModal/);
  assert.match(create, /createRequest\(form\)/);
  assert.match(create, /await store\.validateRequest/);
  assert.match(create, /store\.loadRegenerationDraft\(regenerateId\)/);
  assert.match(create, /store\.loadContinuationDraft\(continuationId\)/);
  assert.match(create, /const draftLoadFailed = ref\(false\)/);
  assert.match(create, /if \(!source\) \{\s*draftLoadFailed\.value = true/);
  assert.match(create, /:disabled="submitting \|\| platformGenerationSelected \|\| draftLoadFailed \|\| !form\.first_frame \|\| !form\.prompt\.trim\(\)"/);
  assert.match(create, /const submitting = ref\(false\)/);
  assert.match(create, /if \(submitting\.value\) return/);
  assert.match(create, /form\.first_frame = request\.first_frame/);
  assert.match(create, /if \(!preflight\) \{/);
  assert.doesNotMatch(create, /form\.priority|form\.execution_expires_after|seedance-priority-error|seedance-expiry-error/);
});

test('generation information copies the complete prompt with a WebView fallback', async () => {
  const info = await source('components/seedance/SeedanceGenerationInfo.vue');
  assert.match(info, /@click="copyPrompt"/);
  assert.match(info, /navigator\.clipboard\?\.writeText/);
  assert.match(info, /document\.execCommand\('copy'\)/);
  assert.match(info, /promptCopied/);
});

test('Seedance handoff disables repeat submission while creating the project', async () => {
  const panel = await source('components/seedance/SeedanceHandoffPanel.vue');
  assert.match(panel, /creating\?: boolean/);
  assert.match(panel, /creating: false/);
  assert.match(panel, /:disabled="disabled \|\| creating \|\| !canSubmit"/);
  assert.match(panel, /creating \? t\('seedance\.handoff\.creatingProject'\) : t\('seedance\.handoff\.submit'\)/);
});

test('task-list continuation opens the create screen directly', async () => {
  const [card, tasks] = await Promise.all([
    source('components/seedance/SeedanceTaskCard.vue'),
    source('components/seedance/SeedanceTaskList.vue'),
  ]);
  assert.match(card, /continue: \[id: string\]/);
  assert.match(card, /if \(action === 'continue'\) \{\s*emit\('continue', props\.task\.local_id\);/);
  assert.match(tasks, /@continue="continueFromReturnedFrame"/);
  assert.match(tasks, /query: \{ continue: id \}/);
});

test('Seedance create page embeds a prompt-free double-column task list', async () => {
  const [create, list, card] = await Promise.all([
    source('views/SeedanceCreate.vue'),
    source('components/seedance/SeedanceTaskList.vue'),
    source('components/seedance/SeedanceTaskCard.vue'),
  ]);
  assert.match(create, /class="w-full"/);
  assert.match(create, /data-test="seedance-create-task-list"/);
  assert.match(create, /<SeedanceTaskList \/>/);
  assert.match(list, /grid gap-4 md:grid-cols-2/);
  assert.doesNotMatch(card, /taskTitle|task\.request\.prompt/);
});

test('Seedance list routes collapse into the create page while task detail remains available', async () => {
  const routes = await source('main.ts');
  assert.match(routes, /path: '\/video-generation\/tasks', redirect: \{ path: '\/ai-creation', query: \{ mode: 'video' \} \}/);
  assert.match(routes, /path: '\/video-generation\/preview', redirect: \{ path: '\/ai-creation', query: \{ mode: 'video' \} \}/);
  assert.match(routes, /path: '\/video-generation\/tasks\/:localTaskId'/);
});

test('Seedance result video hides controls while playing and restores them when requested', async () => {
  const stage = await source('components/seedance/SeedanceVideoStage.vue');
  assert.match(stage, /:controls="showControls"/);
  assert.match(stage, /@play="hideControls"/);
  assert.match(stage, /@pause="showControls = true"/);
  assert.match(stage, /@ended="showControls = true"/);
  assert.match(stage, /@click="showControls = true"/);
});

test('Seedance detail preview omits the provider-specific video caption', async () => {
  const preview = await source('views/SeedancePreview.vue');
  assert.doesNotMatch(preview, /:summary="t\('seedance\.preview\.videoSummary'\)"/);
});

test('Seedance create screen does not expose task scheduling controls', async () => {
  const [create, en, zh] = await Promise.all([
    source('views/SeedanceCreate.vue'),
    source('locales/en.ts'),
    source('locales/zh-CN.ts'),
  ]);

  assert.doesNotMatch(create, /seedance\.ui\.noExtraOptions|seedance\.create\.priority|seedance\.create\.expiresAfter/);
  assert.doesNotMatch(en, /web search/i);
  assert.doesNotMatch(zh, /联网搜索/);
});

test('Never retention disables manual cache cleanup', async () => {
  const settings = await source('views/SeedanceSettings.vue');
  assert.match(settings, /<option :value="0">/);
  assert.match(settings, /:disabled="retentionDisabled"/);
  assert.match(settings, /retentionDisabled/);
  assert.match(settings, /draft\.retention_days === 0/);
});

test('image and video creation share the settings-only paid confirmation preference', async () => {
  const [videoCreate, imageCreate, settings, zh] = await Promise.all([
    source('views/SeedanceCreate.vue'),
    source('views/SeedreamCreate.vue'),
    source('views/SeedanceSettings.vue'),
    source('locales/zh-CN.ts'),
  ]);

  for (const create of [videoCreate, imageCreate]) {
    assert.match(create, /paid_generation_confirmation_enabled/);
    assert.doesNotMatch(create, /skipPaidConfirmation|dontShowAgain/);
    assert.doesNotMatch(create, /saveConfig\(\{ paid_generation_confirmation_enabled: false \}\)/);
  }
  assert.match(settings, /v-model="appDraft\.paid_generation_confirmation_enabled"/);
  assert.match(settings, /class="\[&_span\]:!text-danger"/);
  assert.match(zh, /paidGenerationConfirmation: '生成请求前确认弹窗'/);
  assert.doesNotMatch(zh, /不再提示/);
  assert.match(zh, /paidConfirmCost: '确认后将产生费用，'/);
  assert.match(zh, /paidConfirmIrrevocable: '任务不支持撤回。'/);
  assert.match(zh, /irrevocable: '任务不支持撤回。'/);
  assert.match(videoCreate, /data-test="seedance-paid-confirm-irrevocable"[^>]*class="text-warning"|class="text-warning"[^>]*data-test="seedance-paid-confirm-irrevocable"/);
  assert.match(imageCreate, /data-test="seedream-paid-confirm-irrevocable"[^>]*class="text-warning"|class="text-warning"[^>]*data-test="seedream-paid-confirm-irrevocable"/);
  assert.match(zh, /生成完成后系统会自动下载并保存到本地；/);
  assert.match(zh, /云端结果链接仅保留 24 小时，如发生意外报错，可在有效期内重新下载。/);
});

test('Seedance task deletion and cache cleanup use accessible confirmation modals', async () => {
  const [tasks, settings] = await Promise.all([
    source('components/seedance/SeedanceTaskList.vue'),
    source('views/SeedanceSettings.vue'),
  ]);
  assert.match(tasks, /v-if="taskToDelete"/);
  assert.match(tasks, /ref="deleteModalRoot"/);
  assert.match(tasks, /@click\.self="closeDeleteConfirmation"/);
  assert.match(tasks, /trapModalTab\(event, deleteModalRoot\.value\)/);
  assert.doesNotMatch(tasks, /window\.confirm\(message\)/);
  assert.match(settings, /@click="openCacheCleanConfirmation"/);
  assert.match(settings, /v-if="confirmCacheClean"/);
  assert.match(settings, /ref="cacheCleanModalRoot"/);
  assert.match(settings, /clearCacheConfirmation/);
  assert.match(settings, /trapModalTab\(event, cacheCleanModalRoot\.value\)/);
});

test('task-list deletion uses the same global Seedance dialog style as the preview', async () => {
  const [preview, tasks, styles] = await Promise.all([
    source('views/SeedancePreview.vue'),
    source('components/seedance/SeedanceTaskList.vue'),
    source('styles/main.css'),
  ]);
  assert.match(preview, /class="seedance-modal"/);
  assert.match(tasks, /class="seedance-modal"/);
  assert.match(styles, /\.seedance-modal\s*\{[\s\S]*fixed inset-0 z-50/);
  assert.match(styles, /\.seedance-modal > div\s*\{/);
});

test('Seedance detail puts a right-aligned back action above the framed video stage', async () => {
  const preview = await source('views/SeedancePreview.vue');
  assert.match(preview, /class="ml-auto flex w-fit/);
  assert.match(preview, /data-test="seedance-preview-back"/);
  assert.match(preview, /data-test="seedance-preview-stage-frame"/);
  assert.match(preview, /data-test="`seedance-detail-favorite-\$\{task\.local_id\}`"/);
  assert.match(preview, /useRecentMediaFavorites\(\)/);
  assert.match(preview, /bg-\[#252525\]/);
  assert.match(preview, /router\.push\('\/ai-creation'\)/);
});

test('Seedance settings retains the safe full configuration workflow', async () => {
  const settings = await source('views/SeedanceSettings.vue');
  assert.match(settings, /api_key_configured/);
  assert.match(settings, /autocomplete="new-password"/);
  assert.match(settings, /api_key:\s*null/);
  assert.match(settings, /confirmClear/);
  assert.match(settings, /store\.testConnection/);
  assert.match(settings, /default_generate_audio/);
  assert.match(settings, /default_return_last_frame/);
  assert.match(settings, /class="h-\[42px\] shrink-0"/);
  assert.match(settings, /variant="danger"/);
  assert.doesNotMatch(settings, /v-model\.number="draft\.default_priority"|v-model\.number="draft\.default_expires_after"/);
  assert.match(settings, /store\.loadCacheStatus/);
  assert.match(settings, /total_bytes/);
  assert.match(settings, /clearable_bytes/);
  assert.match(settings, /protected_task_count/);
  assert.match(settings, /\[7, 30, 90, 180\]/);
  assert.match(settings, /saveFeedback/);
});

test('settings save action stays in the page bar and logging uses its own row', async () => {
  const settings = await source('views/SeedanceSettings.vue');
  assert.match(settings, /form="seedance-settings-form"/);
  assert.match(settings, /id="seedance-settings-form"/);
  assert.match(settings, /Switch v-model="appDraft\.logger_enabled"/);
  assert.doesNotMatch(settings, /default_fps|settings\.defaultFps/);
});

test('animation cards use a responsive minimum width grid', async () => {
  const manager = await source('views/ProjectManager.vue');
  assert.match(manager, /grid-cols-1 gap-3\.5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4/);
});

test('Seedance clear-key confirmation has the shared accessible modal lifecycle', async () => {
  const settings = await source('views/SeedanceSettings.vue');
  assert.match(settings, /ref="clearModalRoot"/);
  assert.match(settings, /role="dialog"/);
  assert.match(settings, /aria-modal="true"/);
  assert.match(settings, /aria-labelledby="clear-key-title"/);
  assert.match(settings, /aria-describedby="clear-key-description"/);
  assert.match(settings, /@click\.self="closeClearConfirmation"/);
  assert.match(settings, /@keydown="onClearKeydown"/);
  assert.match(settings, /await nextTick\(\)/);
  assert.match(settings, /trapModalTab\(event, clearModalRoot\.value\)/);
  assert.match(settings, /onBeforeUnmount\(\(\) =>/);
});

test('settings blocks navigation when configuration changes are unsaved', async () => {
  const settings = await source('views/SeedanceSettings.vue');
  assert.match(settings, /onBeforeRouteLeave/);
  assert.match(settings, /hasUnsavedChanges/);
  assert.match(settings, /markSettingsSaved\(\)/);
  assert.match(settings, /unsaved-settings-title/);
  assert.match(settings, /continueEditing/);
  assert.match(settings, /discardAndLeave/);
});

test('modal focus helper cycles tab focus deterministically', async () => {
  const focus = await source('modal-focus.ts');
  assert.match(focus, /export function nextFocusIndex/);
  assert.match(focus, /return \(currentIndex/);
  assert.match(focus, /export function trapModalTab/);
});
