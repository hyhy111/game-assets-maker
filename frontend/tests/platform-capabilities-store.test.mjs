import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { createPinia, setActivePinia } from 'pinia';
import {
  closeFrontendHarness,
  createScriptedPyWebViewBridge,
  loadFrontendModule,
} from './scripted-pywebview-bridge.mjs';

after(closeFrontendHarness);

const CAPABILITIES = {
  video: {
    models: [
      { model: 'doubao-seedance-2-0-260128', resolutions: ['480p', '720p', '1080p'], durations: [4, 5, 6] },
    ],
    ratios: ['adaptive', '16:9', '1:1', '4:3'],
  },
  image: { models: [{ model: 'doubao-seedream-5-0-pro-260628', sizes: ['1K', '1.5K', '2K'] }] },
};

/** 只装工作区 store（能力状态与拉取动作都在它这里，不牵涉 auth）。 */
async function setup(script = {}) {
  createScriptedPyWebViewBridge(script);
  setActivePinia(createPinia());
  const { useAICreationStore } = await loadFrontendModule('/src/stores/aiCreation.ts');
  return useAICreationStore();
}

const okScript = () => ({ get_platform_capabilities: [{ resolve: { success: true, data: CAPABILITIES } }] });

test('capabilities stay empty until explicitly loaded (no implicit bridge call)', async () => {
  const workspace = await setup(okScript());
  assert.equal(workspace.capabilities, null);
  assert.equal(await workspace.ensureCapabilities(), true);
  assert.deepEqual(workspace.capabilities, CAPABILITIES);
});

test('ensureCapabilities reuses the loaded list unless forced', async () => {
  // 脚本只给一份：若第二次未强制却仍发请求，会因脚本耗尽而失败
  const workspace = await setup(okScript());
  await workspace.ensureCapabilities();
  assert.equal(await workspace.ensureCapabilities(), true);
  assert.deepEqual(workspace.capabilities, CAPABILITIES);
});

test('forced reload fetches again', async () => {
  const workspace = await setup({
    get_platform_capabilities: [
      { resolve: { success: true, data: CAPABILITIES } },
      { resolve: { success: true, data: CAPABILITIES } },
    ],
  });
  await workspace.ensureCapabilities();
  assert.equal(await workspace.ensureCapabilities(true), true);
  assert.deepEqual(workspace.capabilities, CAPABILITIES);
});

test('a failed fetch yields no fallback list and records the backend message', async () => {
  const workspace = await setup({
    get_platform_capabilities: [{ resolve: { success: false, error: { code: 'X', message: '平台暂时不可用' } } }],
  });
  assert.equal(await workspace.ensureCapabilities(), false);
  assert.equal(workspace.capabilities, null, '拉取失败绝不能留下兜底清单（design D3）');
  assert.equal(workspace.capabilitiesError, '平台暂时不可用');
});

test('a failure can be retried and then succeeds', async () => {
  const workspace = await setup({
    get_platform_capabilities: [
      { resolve: { success: false, error: { code: 'X', message: 'boom' } } },
      { resolve: { success: true, data: CAPABILITIES } },
    ],
  });
  assert.equal(await workspace.ensureCapabilities(), false);
  assert.equal(await workspace.ensureCapabilities(true), true);
  assert.deepEqual(workspace.capabilities, CAPABILITIES);
  assert.equal(workspace.capabilitiesError, '');
});

test('concurrent ensureCapabilities share a single request', async () => {
  // 同样只给一份脚本：并发若各发一次，第二次会失败
  const workspace = await setup(okScript());
  const [a, b] = await Promise.all([workspace.ensureCapabilities(), workspace.ensureCapabilities()]);
  assert.equal(a, true);
  assert.equal(b, true);
  assert.deepEqual(workspace.capabilities, CAPABILITIES);
});

test('clearCapabilities drops the cached list and any error', async () => {
  const workspace = await setup(okScript());
  await workspace.ensureCapabilities();
  workspace.clearCapabilities();
  assert.equal(workspace.capabilities, null);
  assert.equal(workspace.capabilitiesError, '');
  assert.equal(workspace.capabilitiesLoading, false);
});

// --------------------------------------------------------------------------
// 加载时机（composables/usePlatformCapabilities）：登录后 / 切平台源 / 登出
// --------------------------------------------------------------------------

// auth store 在 setup 期读 localStorage 取 token（http.ts:getToken），Node 里没这个全局
const storage = new Map();
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: (key) => storage.delete(key),
  },
});

const settle = () => new Promise((resolve) => setImmediate(resolve));

async function setupTiming(script = okScript()) {
  createScriptedPyWebViewBridge(script);
  setActivePinia(createPinia());
  const { useAICreationStore } = await loadFrontendModule('/src/stores/aiCreation.ts');
  const { useAuthStore } = await loadFrontendModule('/src/stores/auth.ts');
  const { usePlatformCapabilities } = await loadFrontendModule('/src/composables/usePlatformCapabilities.ts');
  const workspace = useAICreationStore();
  const auth = useAuthStore();
  usePlatformCapabilities();
  return { workspace, auth };
}

test('timing: nothing is fetched while logged out, even on the platform source', async () => {
  const { workspace } = await setupTiming();
  workspace.setGenerationSource('forfuner-ai');
  await settle();
  assert.equal(workspace.capabilities, null);
});

test('timing: logging in while already on the platform source triggers the fetch', async () => {
  const { workspace, auth } = await setupTiming();
  workspace.setGenerationSource('forfuner-ai');
  await settle();
  assert.equal(workspace.capabilities, null);

  auth.status = 'authenticated';
  await settle();
  assert.deepEqual(workspace.capabilities, CAPABILITIES);
});

test('timing: switching to the platform source while logged in triggers the fetch', async () => {
  const { workspace, auth } = await setupTiming();
  auth.status = 'authenticated';
  await settle();
  assert.equal(workspace.capabilities, null, '自定义 Key 源下不该拉取');

  workspace.setGenerationSource('forfuner-ai');
  await settle();
  assert.deepEqual(workspace.capabilities, CAPABILITIES);
});

test('timing: logging out clears the cached capabilities', async () => {
  const { workspace, auth } = await setupTiming();
  auth.status = 'authenticated';
  workspace.setGenerationSource('forfuner-ai');
  await settle();
  assert.deepEqual(workspace.capabilities, CAPABILITIES);

  auth.status = 'guest';
  await settle();
  assert.equal(workspace.capabilities, null);
  assert.equal(workspace.capabilitiesError, '');
});

test('timing: switching back to the platform source refetches instead of using the cache', async () => {
  // 运营随时可能上下架模型/改展示名；读缓存会让用户看到已经下架的模型。
  // 脚本准备两份：若切回来不发请求，第二次断言会因脚本耗尽而失败。
  const { workspace, auth } = await setupTiming({
    get_platform_capabilities: [
      { resolve: { success: true, data: CAPABILITIES } },
      { resolve: { success: true, data: { ...CAPABILITIES, video: { ...CAPABILITIES.video, models: [] } } } },
    ],
  });
  auth.status = 'authenticated';
  workspace.setGenerationSource('forfuner-ai');
  await settle();
  assert.equal(workspace.capabilities.video.models.length, 1, '首次拉取拿到模型');

  workspace.setGenerationSource('api-key');
  await settle();
  workspace.setGenerationSource('forfuner-ai');
  await settle();
  assert.deepEqual(workspace.capabilities.video.models, [], '切回来必须重新拉取，取到服务端最新状态');
});

test('timing: logging in again while on the platform source refetches', async () => {
  const { workspace, auth } = await setupTiming({
    get_platform_capabilities: [
      { resolve: { success: true, data: CAPABILITIES } },
      { resolve: { success: true, data: CAPABILITIES } },
    ],
  });
  auth.status = 'authenticated';
  workspace.setGenerationSource('forfuner-ai');
  await settle();
  assert.deepEqual(workspace.capabilities, CAPABILITIES);

  // 换账号：登出 → 清空 → 登录 → 重新拉取
  auth.status = 'guest';
  await settle();
  assert.equal(workspace.capabilities, null);
  auth.status = 'authenticated';
  await settle();
  assert.deepEqual(workspace.capabilities, CAPABILITIES);
});
