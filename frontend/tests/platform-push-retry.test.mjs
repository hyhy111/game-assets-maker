import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { createPinia, setActivePinia } from 'pinia';

import {
  closeFrontendHarness,
  createScriptedPyWebViewBridge,
  loadFrontendModule,
} from './scripted-pywebview-bridge.mjs';

after(async () => {
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

const neverSettles = () => new Promise(() => {});
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function freshAuthStore() {
  const { useAuthStore } = await loadFrontendModule('/src/stores/auth.ts');
  setActivePinia(createPinia());
  return useAuthStore();
}

/** 足够多份成功响应：一次失败重试之外，token 变化还会触发立即推送 */
function bridgeWithOneFailure() {
  return createScriptedPyWebViewBridge({
    set_platform_config: [
      { reject: new Error('bridge not ready') },
      ...Array.from({ length: 8 }, () => ({ resolve: { success: true } })),
    ],
  });
}

// ---------------------------------------------------------------------------
// 平台配置推送重试（auth.ts token watcher）
//
// 背景：平台 base URL + JWT 只存在 Python 进程内存，靠前端的 token watcher
// 推送。曾实现为"失败静默忽略，等下次 token 变化再推"——但 token 不变就永远
// 不再推，Python 侧整个会话拿不到 token，生成报
// "Platform generation is not configured; sign in first"（真实用户反馈）。
// ---------------------------------------------------------------------------

test('推送失败按退避重试，成功后不再重试', async () => {
  storage.clear();
  const { calls } = bridgeWithOneFailure();
  globalThis.fetch = neverSettles;

  await freshAuthStore(); // 启动 immediate 推送 → 第一次失败

  await sleep(1200); // 第一次重试（1s 退避）

  assert.equal(calls.length, 2, `应有一次重试，实际调用: ${JSON.stringify(calls)}`);
  assert.equal(calls[0].method, 'set_platform_config');
  assert.equal(calls[1].method, 'set_platform_config');

  await sleep(1200); // 越过了下一次退避点；成功之后不应再发起调用
  assert.equal(calls.length, 2, '成功后不应继续重试');
});

test('重试推送取当前最新 token，而非失败时的快照', async () => {
  storage.set('gam:auth:token', 'initial-token');
  const { calls } = bridgeWithOneFailure();
  globalThis.fetch = neverSettles;

  const store = await freshAuthStore(); // 推送 initial-token → 失败，1s 后重试
  store.token = 'fresh-token'; // 立即推送一次（消费成功响应），同时改变重试时应取的值

  await sleep(1200);

  const retried = calls[calls.length - 1];
  assert.equal(retried.args[1], 'fresh-token', `重试应携带最新 token，实际: ${JSON.stringify(calls)}`);
});

test('首次推送成功时一次调用即落定，无重试', async () => {
  storage.clear();
  const { calls } = createScriptedPyWebViewBridge({
    set_platform_config: [{ resolve: { success: true } }],
  });
  globalThis.fetch = neverSettles;

  await freshAuthStore();

  await sleep(1100);
  assert.equal(calls.length, 1, `成功后不应重试，实际调用: ${JSON.stringify(calls)}`);
});
