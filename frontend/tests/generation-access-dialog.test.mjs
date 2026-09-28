import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { after, test } from 'node:test';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';

after(closeSfcRenderer);

test('guest access dialog offers login and API key configuration', async () => {
  const html = await renderSfc('components/ai-creation/GenerationAccessDialog.vue', {
    props: { open: true, loggedIn: false },
  });
  assert.match(html, /选择生成方式/);
  assert.match(html, /登录账户/);
  assert.match(html, /配置 API Key/);
  assert.match(html, /data-test="generation-access-dialog"/);
});

test('logged-in access dialog points at the platform source or an API key', async () => {
  const html = await renderSfc('components/ai-creation/GenerationAccessDialog.vue', {
    props: { open: true, loggedIn: true },
  });
  assert.match(html, /切换到 ForFuner AI/);
  assert.match(html, /配置 API Key/);
  assert.doesNotMatch(html, /登录账户/);
});

test('both composers guard creation before calling the backend preflight or task API', async () => {
  const [image, video] = await Promise.all([
    readFile(new URL('../src/views/SeedreamCreate.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/views/SeedanceCreate.vue', import.meta.url), 'utf8'),
  ]);
  assert.match(image, /if \(!ensureGenerationAccess\(\)\) return;/);
  // 平台源请求覆盖 return_last_frame；其余与 ensureGenerationAccess 之后立即构造。
  assert.match(video, /if \(!ensureGenerationAccess\(\)\) return;[\s\S]{0,200}createRequest\(form\)/);
  assert.match(image, /keySettingsStore\.settings\?\.api_key_configured/);
  assert.match(video, /store\.settings\?\.api_key_configured/);
});

test('both composers show the source selector next to send whenever the account is logged in', async () => {
  const [image, video, loggedInWithoutKey, keyWithoutLogin] = await Promise.all([
    renderSfc('views/SeedreamCreate.vue', {
      route: '/image-generation/create',
      piniaState: {
        auth: { status: 'authenticated' },
        seedance: { settings: { api_key_configured: true } },
      },
    }),
    renderSfc('views/SeedanceCreate.vue', {
      route: '/video-generation/create',
      props: { showTaskList: false },
      piniaState: {
        auth: { status: 'authenticated' },
        seedance: { settings: { api_key_configured: true } },
      },
    }),
    renderSfc('views/SeedreamCreate.vue', {
      route: '/image-generation/create',
      piniaState: { auth: { status: 'authenticated' } },
    }),
    renderSfc('views/SeedanceCreate.vue', {
      route: '/video-generation/create',
      props: { showTaskList: false },
      piniaState: { seedance: { settings: { api_key_configured: true } } },
    }),
  ]);

  for (const html of [image, video, loggedInWithoutKey]) {
    assert.match(html, /data-test="(?:seedream|seedance)-generation-source"/);
    assert.match(html, /自定义 Key/);
  }
  // 未登录：即使配置了 Key 也不显示生成方式选择器（平台源需登录）。
  assert.doesNotMatch(keyWithoutLogin, /data-test="seedance-generation-source"/);
});

test('ForFuner AI is shared by both composers and submits through the platform source', async () => {
  const [image, video, workspaceStore] = await Promise.all([
    readFile(new URL('../src/views/SeedreamCreate.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/views/SeedanceCreate.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/stores/aiCreation.ts', import.meta.url), 'utf8'),
  ]);

  for (const source of [image, video]) {
    assert.match(source, /\{ value: 'forfuner-ai', label: t\('aiCreation\.forfunerAI'\) \}/);
    assert.match(source, /workspace\.generationSource === 'forfuner-ai'/);
    assert.match(source, /workspace\.setGenerationSource\((?:source as GenerationSource|next)\)/);
  }
  assert.match(workspaceStore, /const generationSource = ref<GenerationSource>\('api-key'\)/);
  assert.match(workspaceStore, /function setGenerationSource\(source: GenerationSource\)/);
  // 平台源不再硬拦截提交：视频走 return_last_frame 覆盖 + 来源透传，图片按来源建批。
  assert.match(video, /platformGenerationSelected\.value\s*\? \{ \.\.\.createRequest\(form\), return_last_frame: false \}/);
  assert.match(video, /store\.validateRequest\(request, workspace\.generationSource\)/);
  assert.match(video, /store\.createTask\(request, source\)/);
  assert.doesNotMatch(image, /if \(platformGenerationSelected\.value\) return;/);
  assert.match(image, /store\.createBatch\(request, source\)/);
  // 平台源报价走 quote-preview，且报价未就绪时禁止确认。
  assert.match(video, /store\.quoteVideo\(createRequest\(form\)\)/);
  assert.match(video, /platformConfirmBlocked/);
  // 图片源单价走图片报价端点，总数 = 单价 × 数量（N 张 = N 个平台任务）。
  assert.match(image, /store\.quoteImage\(createRequest\(form\)\)/);
  assert.match(image, /quoteUnit\.value \* form\.count/);
});
