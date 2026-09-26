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

test('logged-in access dialog clearly requires an API key until platform generation exists', async () => {
  const html = await renderSfc('components/ai-creation/GenerationAccessDialog.vue', {
    props: { open: true, loggedIn: true },
  });
  assert.match(html, /平台生成服务仍在开发中/);
  assert.match(html, /配置 API Key/);
  assert.doesNotMatch(html, /登录账户/);
});

test('both composers guard creation before calling the backend preflight or task API', async () => {
  const [image, video] = await Promise.all([
    readFile(new URL('../src/views/SeedreamCreate.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/views/SeedanceCreate.vue', import.meta.url), 'utf8'),
  ]);
  assert.match(image, /if \(!ensureGenerationAccess\(\)\) return;/);
  assert.match(video, /if \(!ensureGenerationAccess\(\)\) return;\n  const request = createRequest\(form\);/);
  assert.match(image, /keySettingsStore\.settings\?\.api_key_configured/);
  assert.match(video, /store\.settings\?\.api_key_configured/);
});

test('both composers show the source selector next to send only when login and a custom key are both available', async () => {
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

  for (const html of [image, video]) {
    assert.match(html, /data-test="(?:seedream|seedance)-generation-source"/);
    assert.match(html, /自定义 Key/);
  }
  assert.doesNotMatch(loggedInWithoutKey, /data-test="seedream-generation-source"/);
  assert.doesNotMatch(keyWithoutLogin, /data-test="seedance-generation-source"/);
});

test('ForFuner AI is shared by both composers, shows an estimate, and cannot submit a provider request', async () => {
  const [image, video, workspaceStore] = await Promise.all([
    readFile(new URL('../src/views/SeedreamCreate.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/views/SeedanceCreate.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/stores/aiCreation.ts', import.meta.url), 'utf8'),
  ]);

  for (const source of [image, video]) {
    assert.match(source, /\{ value: 'forfuner-ai', label: t\('aiCreation\.forfunerAI'\) \}/);
    assert.match(source, /workspace\.generationSource === 'forfuner-ai'/);
    assert.match(source, /platformGenerationSelected \|\|/);
    assert.match(source, /workspace\.setGenerationSource\(source as GenerationSource\)/);
  }
  assert.match(workspaceStore, /const generationSource = ref<GenerationSource>\('api-key'\)/);
  assert.match(workspaceStore, /function setGenerationSource\(source: GenerationSource\)/);
  assert.match(image, /if \(platformGenerationSelected\.value\) return;\n  if \(!ensureGenerationAccess\(\)\) return;/);
  assert.match(video, /if \(platformGenerationSelected\.value\) return;\n  submitting\.value = true;/);
});
