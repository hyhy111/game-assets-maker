import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { createPinia, setActivePinia } from 'pinia';

import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';
import {
  closeFrontendHarness,
  createScriptedPyWebViewBridge,
  loadFrontendModule,
} from './scripted-pywebview-bridge.mjs';

after(async () => {
  await closeSfcRenderer();
  await closeFrontendHarness();
});

// ---------------------------------------------------------------------------
// 公共桩
// ---------------------------------------------------------------------------

const storage = new Map();
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: (key) => storage.delete(key),
  },
});

/** 永不落定的 fetch：渲染用例用，避免真打网络、也避免异步回填覆盖预置状态 */
const neverSettles = () => new Promise(() => {});

const CREDENTIALS_CIPHERTEXT = 'stub-cipher';

/** 桩住 pywebview 桥（凭证加解密走它），并预置本地凭证 */
function stubBridgeWithCredentials() {
  return createScriptedPyWebViewBridge({
    encrypt_credential: [{ resolve: CREDENTIALS_CIPHERTEXT }],
    // 队列会被消费，多备几份以支持同一用例内的多次读取
    decrypt_credential: Array.from({ length: 8 }, () => ({
      resolve: JSON.stringify({ email: 'tester@example.com', password: 'pw' }),
    })),
  });
}

/**
 * 脚本化 fetch：记录每次调用（路径/方法/携带的 token），由 handler 决定响应。
 * handler 返回 { status?, body? }。use() 可在用例中途换挡（模拟"会话在后台过期"）。
 */
function scriptFetch(handler) {
  const calls = [];
  let current = handler;
  globalThis.fetch = async (url, init = {}) => {
    const record = {
      path: String(url).replace(/^https?:\/\/[^/]+/, ''),
      method: (init.method ?? 'GET').toUpperCase(),
      auth: new Headers(init.headers).get('Authorization'),
      body: init.body,
    };
    calls.push(record);
    const res = current(record, calls.length - 1) ?? {};
    if (res.networkError) throw new TypeError('fetch failed');
    return {
      status: res.status ?? 200,
      json: async () => res.body ?? { code: 200 },
    };
  };
  return { calls, use: (next) => { current = next; } };
}

async function freshAuthStore() {
  const { useAuthStore } = await loadFrontendModule('/src/stores/auth.ts');
  setActivePinia(createPinia());
  return useAuthStore();
}

async function http() {
  return loadFrontendModule('/src/api/http.ts');
}

const loginCalls = (calls) => calls.filter((c) => c.path === '/login').length;

// ---------------------------------------------------------------------------
// 到期时间格式
// ---------------------------------------------------------------------------

const SUBSCRIBED_AUTH = {
  token: 'test-token',
  userInfo: { email: 'tester@example.com' },
  status: 'authenticated',
  loading: false,
  error: null,
  sessionExpired: false,
};

async function renderHeaderWithExpiry(expiry) {
  globalThis.fetch = neverSettles;
  return renderSfc('components/layout/Header.vue', {
    piniaState: {
      auth: { ...SUBSCRIBED_AUTH },
      billing: {
        account: null,
        subscriptionStatus: {
          hasSubscription: true,
          levelRank: 1,
          concurrency: 1,
          currentPeriodEnd: expiry,
          queueEnd: expiry,
          activePeriods: 1,
          queuedPeriods: 0,
        },
      },
    },
  });
}

// 到期日相对当前年份推算，否则"同年"这个前提会随时间失效、用例静默失去意义
const YEAR = new Date().getFullYear();

test('同年到期：展示完整年月日，不省略年份', async () => {
  const html = await renderHeaderWithExpiry(`${YEAR}-11-17 13:18:38`);

  assert.match(html, new RegExp(`到期 ${YEAR}-11-17`));
  assert.doesNotMatch(html, /到期 11-17/);
});

test('跨年到期：同样展示完整年月日', async () => {
  const html = await renderHeaderWithExpiry(`${YEAR + 1}-01-05 13:18:38`);

  assert.match(html, new RegExp(`到期 ${YEAR + 1}-01-05`));
  assert.doesNotMatch(html, /到期 01-05/);
});

test('订阅入口在有未结束期段时文案为"续费"', async () => {
  const html = await renderHeaderWithExpiry(`${YEAR}-11-17 13:18:38`);

  assert.match(html, /data-test="subscribe-button"/);
  assert.match(html, /续费/);
});

test('会话失效落到游客态时顶栏给出"登录已过期"提示', async () => {
  globalThis.fetch = neverSettles;
  const html = await renderSfc('components/layout/Header.vue', {
    piniaState: {
      auth: { ...SUBSCRIBED_AUTH, token: null, userInfo: null, status: 'guest', sessionExpired: true },
      billing: { account: null, subscriptionStatus: null },
    },
  });

  assert.match(html, /data-test="session-expired"/);
  assert.match(html, /登录已过期/);
});

test('主动登出（非失效）不显示过期提示', async () => {
  globalThis.fetch = neverSettles;
  const html = await renderSfc('components/layout/Header.vue', {
    piniaState: {
      auth: { ...SUBSCRIBED_AUTH, token: null, userInfo: null, status: 'guest', sessionExpired: false },
      billing: { account: null, subscriptionStatus: null },
    },
  });

  assert.doesNotMatch(html, /data-test="session-expired"/);
});

// ---------------------------------------------------------------------------
// 运行中 token 失效的静默恢复
// ---------------------------------------------------------------------------

/**
 * 把 store 带到"已登录且正在运行"的状态（token 有效、getInfo 可取），
 * 这是挂机场景的真正起点 —— 不是刚启动时的 unknown。
 * 返回 { store, net }，net.use() 用于随后切到"会话已过期"。
 */
async function startedAndAuthenticated() {
  stubBridgeWithCredentials();
  storage.set('gam:auth:token', 'good-token');
  storage.set('gam:auth:credentials', CREDENTIALS_CIPHERTEXT);

  const net = scriptFetch((req) =>
    req.path === '/getInfo'
      ? { body: { code: 200, user: { email: 'tester@example.com' } } }
      : { body: { code: 200 } },
  );

  const store = await freshAuthStore();
  await store.init();
  assert.equal(store.status, 'authenticated', '前置条件：已处于登录态');

  // 切挡：此后除登录接口外一律 401，模拟 token 在后台自然过期
  net.use((req) => {
    if (req.path === '/login') return { body: { code: 200, token: 'fresh-token' } };
    if (req.auth === 'Bearer fresh-token') return { body: { code: 200, ok: req.path } };
    return { status: 401, body: { code: 401, msg: '登录状态已过期' } };
  });

  return { store, net };
}

test('401 后静默重登并重放原请求，全程不落游客态', async () => {
  const { store, net } = await startedAndAuthenticated();

  const transitions = [];
  store.$subscribe((_m, state) => transitions.push(state.status), { flush: 'sync' });

  const { httpGet } = await http();
  const result = await httpGet('/app/credit/account');

  assert.equal(result.ok, '/app/credit/account', '原请求被重放并返回真实结果');
  assert.equal(loginCalls(net.calls), 1, '只重登一次');
  assert.equal(store.status, 'authenticated');
  assert.equal(store.sessionExpired, false);
  assert.ok(
    !transitions.includes('guest'),
    `恢复期间不应出现游客态过渡，实际: ${JSON.stringify(transitions)}`,
  );
});

test('并发 401 只触发一次重登，各自重放', async () => {
  const { store, net } = await startedAndAuthenticated();

  const { httpGet } = await http();
  const results = await Promise.all([
    httpGet('/app/credit/account'),
    httpGet('/app/credit/subscription-status'),
    httpGet('/app/order/FFN1'),
  ]);

  assert.equal(loginCalls(net.calls), 1, '三个并发 401 只应重登一次');
  assert.deepEqual(
    results.map((r) => r.ok),
    ['/app/credit/account', '/app/credit/subscription-status', '/app/order/FFN1'],
  );
  assert.equal(store.status, 'authenticated');
});

test('重放后仍 401：不再重试，落游客态', async () => {
  stubBridgeWithCredentials();
  storage.set('gam:auth:token', 'stale-token');
  storage.set('gam:auth:credentials', CREDENTIALS_CIPHERTEXT);

  const { store, net } = await startedAndAuthenticated();

  // 登录成功，但新 token 对业务接口同样无效
  net.use((req) =>
    req.path === '/login'
      ? { body: { code: 200, token: 'fresh-token' } }
      : { status: 401, body: { code: 401, msg: '过期' } },
  );

  const { httpGet } = await http();

  await assert.rejects(() => httpGet('/app/credit/account'), /过期/);

  assert.equal(loginCalls(net.calls), 1, '不应进入重登-401-重登的循环');
  assert.equal(store.status, 'guest');
  assert.equal(store.sessionExpired, true);
});

test('未保存凭证：不尝试重登，直接回游客态并标记过期', async () => {
  stubBridgeWithCredentials();
  storage.set('gam:auth:token', 'stale-token');
  storage.delete('gam:auth:credentials');

  const net = scriptFetch(() => ({ status: 401, body: { code: 401, msg: '过期' } }));

  const store = await freshAuthStore();
  const { httpGet } = await http();

  await assert.rejects(() => httpGet('/app/credit/account'));

  assert.equal(loginCalls(net.calls), 0, '无凭证不应发起登录');
  assert.equal(store.status, 'guest');
  assert.equal(store.sessionExpired, true);
});

test('重登失败：清凭证、进游客态，冷却期内不再尝试', async () => {
  stubBridgeWithCredentials();
  storage.set('gam:auth:token', 'stale-token');
  storage.set('gam:auth:credentials', CREDENTIALS_CIPHERTEXT);

  // 登录接口同样返回 401（密码已改）
  const net = scriptFetch(() => ({ status: 401, body: { code: 401, msg: '密码错误' } }));

  const store = await freshAuthStore();
  const { httpGet } = await http();

  await assert.rejects(() => httpGet('/app/credit/account'));
  assert.equal(loginCalls(net.calls), 1, '登录接口自身返回 401 不应触发递归重登');
  assert.equal(store.status, 'guest');
  assert.equal(storage.get('gam:auth:credentials'), undefined, '失败后应清除保存的凭证');

  // 冷却期内再来一个 401
  await assert.rejects(() => httpGet('/app/credit/account'));
  assert.equal(loginCalls(net.calls), 1, '冷却期内不应再次尝试登录');
});

test('半登录态：网络恢复后任意已认证请求成功即补拉用户信息', async () => {
  stubBridgeWithCredentials();
  storage.set('gam:auth:token', 'good-token');
  storage.delete('gam:auth:credentials');

  // 启动时后端不可达：应保留 token 进半登录态，不得据此判定失效
  const net = scriptFetch(() => ({ networkError: true }));

  const store = await freshAuthStore();
  await store.init();

  assert.equal(store.status, 'unknown', '网络错误应保持半登录态');
  assert.equal(storage.get('gam:auth:token'), 'good-token', '网络错误不得清除 token');

  net.use((req) =>
    req.path === '/getInfo'
      ? { body: { code: 200, user: { email: 'tester@example.com' } } }
      : { body: { code: 200 } },
  );

  const { httpGet } = await http();
  await httpGet('/app/credit/account');

  // 补拉由 onAuthedSuccess 异步触发，等它落定
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(store.status, 'authenticated', '任意已认证请求成功后应补拉并进入登录态');
  assert.equal(store.userInfo?.email, 'tester@example.com');
});

// ---------------------------------------------------------------------------
// 窗口激活刷新
// ---------------------------------------------------------------------------

async function freshBillingStore() {
  const { useBillingStore } = await loadFrontendModule('/src/stores/billing.ts');
  setActivePinia(createPinia());
  return useBillingStore();
}

const activationCtx = (overrides = {}) => ({
  isLoggedIn: true,
  visibilityState: 'visible',
  subOpenedAt: 0,
  now: 1_000_000,
  ...overrides,
});

test('激活决策：游客态不刷新', async () => {
  const { decideActivationRefresh } = await loadFrontendModule('/src/window-activation.ts');

  assert.deepEqual(decideActivationRefresh(activationCtx({ isLoggedIn: false })), { refresh: false });
});

test('激活决策：visibilitychange 转为隐藏时不刷新', async () => {
  const { decideActivationRefresh } = await loadFrontendModule('/src/window-activation.ts');

  assert.deepEqual(decideActivationRefresh(activationCtx({ visibilityState: 'hidden' })), { refresh: false });
});

test('激活决策：普通激活走节流', async () => {
  const { decideActivationRefresh } = await loadFrontendModule('/src/window-activation.ts');

  assert.deepEqual(decideActivationRefresh(activationCtx()), { refresh: true, force: false });
});

test('激活决策：从订阅窗回来绕过节流', async () => {
  const { decideActivationRefresh, SUBSCRIPTION_RETURN_MS } = await loadFrontendModule('/src/window-activation.ts');
  const now = 1_000_000;

  assert.deepEqual(
    decideActivationRefresh(activationCtx({ subOpenedAt: now - SUBSCRIPTION_RETURN_MS - 1, now })),
    { refresh: true, force: true },
  );
});

test('激活决策：订阅窗刚打开（未满阈值）不算付完款回来', async () => {
  const { decideActivationRefresh, SUBSCRIPTION_RETURN_MS } = await loadFrontendModule('/src/window-activation.ts');
  const now = 1_000_000;

  assert.deepEqual(
    decideActivationRefresh(activationCtx({ subOpenedAt: now - SUBSCRIPTION_RETURN_MS + 1, now })),
    { refresh: true, force: false },
  );
});

test('窗口激活刷新：节流窗口内重复激活不产生请求', async () => {
  const net = scriptFetch(() => ({ body: { code: 200 } }));
  const store = await freshBillingStore();

  await store.refreshOnActivation();
  const afterFirst = net.calls.length;
  assert.ok(afterFirst > 0, '首次激活应发起请求');

  await store.refreshOnActivation();
  await store.refreshOnActivation();

  assert.equal(net.calls.length, afterFirst, '节流窗口内的重复激活不应产生新请求');
});

test('窗口激活刷新：超过最小间隔后再次拉取', async () => {
  const { ACTIVATION_REFRESH_INTERVAL_MS } = await loadFrontendModule('/src/stores/billing.ts');
  const net = scriptFetch(() => ({ body: { code: 200 } }));
  const store = await freshBillingStore();

  const realNow = Date.now;
  let fake = realNow.call(Date);
  Date.now = () => fake;
  try {
    await store.refreshOnActivation();
    const afterFirst = net.calls.length;

    fake += ACTIVATION_REFRESH_INTERVAL_MS + 1;
    await store.refreshOnActivation();
    assert.ok(net.calls.length > afterFirst, '超过最小间隔后应再次请求');
  } finally {
    Date.now = realNow;
  }
});

test('窗口激活刷新：force 绕过节流（付完款回到主窗）', async () => {
  const net = scriptFetch(() => ({ body: { code: 200 } }));
  const store = await freshBillingStore();

  await store.refreshOnActivation();
  const afterFirst = net.calls.length;

  await store.refreshOnActivation({ force: true });

  assert.ok(net.calls.length > afterFirst, 'force 应立即刷新，不受节流限制');
});

test('登录接口的 401 不触发静默重登', async () => {
  stubBridgeWithCredentials();
  storage.set('gam:auth:token', 'stale-token');
  storage.set('gam:auth:credentials', CREDENTIALS_CIPHERTEXT);

  const net = scriptFetch(() => ({ status: 401, body: { code: 401, msg: '密码错误' } }));

  await freshAuthStore();
  const { login } = await loadFrontendModule('/src/api/auth.ts');

  await assert.rejects(() => login({ username: 'a', password: 'b' }));

  assert.equal(loginCalls(net.calls), 1, '认证接口豁免恢复，不会自我递归');
});
