import assert from 'node:assert/strict';
import { after, beforeEach, test } from 'node:test';
import { createPinia, setActivePinia } from 'pinia';

import {
  closeFrontendHarness,
  createScriptedPyWebViewBridge,
  loadFrontendModule,
} from './scripted-pywebview-bridge.mjs';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';

after(async () => {
  await closeSfcRenderer();
  await closeFrontendHarness();
});

const storage = new Map();
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: (key) => storage.delete(key),
  },
});

const CREDENTIALS = { email: 'saved@example.com', password: 'saved-pw' };
const CIPHERTEXT = 'stub-cipher';

// localStorage 是模块级共享的：不清干净的话，"已登出"标记会从一个用例泄漏到下一个
beforeEach(() => storage.clear());

/**
 * 桩住 pywebview 桥（凭证加解密走它）。
 * decrypt 返回同一份凭证；队列多备几份以支持同一用例内多次读取。
 */
function stubBridge(creds = CREDENTIALS) {
  return createScriptedPyWebViewBridge({
    encrypt_credential: Array.from({ length: 6 }, () => ({ resolve: CIPHERTEXT })),
    decrypt_credential: Array.from({ length: 12 }, () => ({
      resolve: JSON.stringify(creds),
    })),
  });
}

function scriptFetch(handler) {
  const calls = [];
  globalThis.fetch = async (url, init = {}) => {
    const record = {
      path: String(url).replace(/^https?:\/\/[^/]+/, ''),
      method: (init.method ?? 'GET').toUpperCase(),
    };
    calls.push(record);
    const res = handler(record) ?? {};
    return { status: res.status ?? 200, json: async () => res.body ?? { code: 200 } };
  };
  return calls;
}

async function freshAuthStore() {
  const { useAuthStore } = await loadFrontendModule('/src/stores/auth.ts');
  setActivePinia(createPinia());
  return useAuthStore();
}

const vault = () => loadFrontendModule('/src/api/credentialVault.ts');
const loginCalls = (calls) => calls.filter((c) => c.path === '/login').length;

// ---------------------------------------------------------------------------
// 1. 凭证保管层：已登出标记
// ---------------------------------------------------------------------------

test('已登出标记：默认未置位，置位与清除可往返', async () => {
  const { markLoggedOut, clearLoggedOutMark, isLoggedOut } = await vault();

  assert.equal(isLoggedOut(), false, '默认不应处于已登出状态');

  markLoggedOut();
  assert.equal(isLoggedOut(), true);

  clearLoggedOutMark();
  assert.equal(isLoggedOut(), false);
});

test('标记与凭证相互独立：置位标记不影响凭证存在性', async () => {
  stubBridge();
  const { markLoggedOut, hasStoredCredentials } = await vault();

  storage.set('gam:auth:credentials', CIPHERTEXT);
  markLoggedOut();

  assert.equal(hasStoredCredentials(), true, '标记不应影响凭证');
});

// ---------------------------------------------------------------------------
// 2. 回填决策（纯函数）
// ---------------------------------------------------------------------------

test('回填：空字段被填充', async () => {
  const { applyPrefill } = await loadFrontendModule('/src/login-prefill.ts');

  assert.deepEqual(applyPrefill({ email: '', password: '' }, CREDENTIALS), CREDENTIALS);
});

test('回填：用户已输入的内容不被覆盖', async () => {
  const { applyPrefill, hasPrefillableFields } = await loadFrontendModule('/src/login-prefill.ts');
  const typed = { email: 'typed@x.com', password: 'typed-pw' };

  assert.deepEqual(applyPrefill(typed, CREDENTIALS), typed);
  assert.equal(hasPrefillableFields(typed, CREDENTIALS), false);
});

test('回填：只填空的那一半（路由带入账号、密码为空）', async () => {
  const { applyPrefill } = await loadFrontendModule('/src/login-prefill.ts');

  assert.deepEqual(
    applyPrefill({ email: 'from-query@x.com', password: '' }, CREDENTIALS),
    { email: 'from-query@x.com', password: CREDENTIALS.password },
  );
});

test('本地无密文时 loadCredentials 返回 null', async () => {
  stubBridge();
  const { loadCredentials } = await vault();

  assert.equal(storage.get('gam:auth:credentials'), undefined, '前置：本地不应有密文');
  assert.equal(await loadCredentials(), null);
});

test('解密失败时 loadCredentials 返回 null、不抛错，并清除残留密文', async () => {
  // 注意：这里必须用桥的脚本队列来制造失败。bridge.api 是 Proxy，只有 get 陷阱，
  // 直接给 api.decrypt_credential 赋值不会生效（会被 get 覆盖回队列里的函数）。
  createScriptedPyWebViewBridge({
    decrypt_credential: [{ reject: new Error('decrypt failed') }],
  });
  storage.set('gam:auth:credentials', CIPHERTEXT);
  const { loadCredentials } = await vault();

  assert.equal(await loadCredentials(), null, '解密失败应安静返回 null，不向上抛');
  assert.equal(storage.get('gam:auth:credentials'), undefined, '残留密文应被清除');
});

// ---------------------------------------------------------------------------
// 3. 登出语义
// ---------------------------------------------------------------------------

test('登出：凭证保留、标记置位、状态回游客态', async () => {
  stubBridge();
  storage.set('gam:auth:token', 'tok');
  storage.set('gam:auth:credentials', CIPHERTEXT);
  scriptFetch(() => ({ body: { code: 200 } }));

  const store = await freshAuthStore();
  await store.logout();

  assert.equal(storage.get('gam:auth:credentials'), CIPHERTEXT, '登出 MUST NOT 删除凭证');
  assert.equal(storage.get('gam:auth:token'), undefined, '登出应清除 token');
  assert.equal(store.status, 'guest');
  assert.equal((await vault()).isLoggedOut(), true, '登出应置位已登出标记');
});

test('登录成功：清除已登出标记，恢复自动登录资格', async () => {
  stubBridge();
  scriptFetch((req) =>
    req.path === '/login'
      ? { body: { code: 200, token: 'new-token' } }
      : { body: { code: 200, user: { email: CREDENTIALS.email } } },
  );

  const v = await vault();
  v.markLoggedOut();
  assert.equal(v.isLoggedOut(), true);

  const store = await freshAuthStore();
  await store.login(CREDENTIALS.email, CREDENTIALS.password, true);

  assert.equal(v.isLoggedOut(), false, '重新登录后应恢复自动登录资格');
  assert.equal(store.status, 'authenticated');
});

// ---------------------------------------------------------------------------
// 4. 启动流程
// ---------------------------------------------------------------------------

test('已登出后重启：即使存在凭证也不自动登录', async () => {
  stubBridge();
  storage.set('gam:auth:credentials', CIPHERTEXT);
  (await vault()).markLoggedOut();

  const calls = scriptFetch(() => ({ body: { code: 200 } }));

  const store = await freshAuthStore();
  await store.init();

  assert.equal(store.status, 'guest', '已登出状态重启应停在游客态');
  assert.equal(loginCalls(calls), 0, '不得自动登录');
});

test('未登出时：按既有流程用凭证自动登录', async () => {
  stubBridge();
  storage.set('gam:auth:credentials', CIPHERTEXT);

  const calls = scriptFetch((req) =>
    req.path === '/login'
      ? { body: { code: 200, token: 'tok' } }
      : { body: { code: 200, user: { email: CREDENTIALS.email } } },
  );

  const store = await freshAuthStore();
  await store.init();

  assert.equal(store.status, 'authenticated', '未登出时仍应自动登录');
  assert.equal(loginCalls(calls), 1);
});

// ---------------------------------------------------------------------------
// 5. 记住账号密码默认勾选
// ---------------------------------------------------------------------------

test('登录页「记住账号密码」默认勾选', async () => {
  globalThis.fetch = () => new Promise(() => {});
  const html = await renderSfc('views/Login.vue', { route: '/login' });

  const checkbox = html.match(/<input[^>]*data-test="remember-checkbox"[^>]*>/);
  assert.ok(checkbox, '登录页应存在记住账号密码勾选框');
  assert.match(checkbox[0], /\schecked/, '勾选框应默认为勾选态');
});

test('组合：有标记无凭证 -> 游客态且不报错', async () => {
  stubBridge();
  (await vault()).markLoggedOut();
  const calls = scriptFetch(() => ({ body: { code: 200 } }));

  const store = await freshAuthStore();
  await store.init();

  assert.equal(store.status, 'guest');
  assert.equal(loginCalls(calls), 0);
});
