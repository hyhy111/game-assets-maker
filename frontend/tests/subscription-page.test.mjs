import assert from 'node:assert/strict';
import { after, test } from 'node:test';

import {
  closeFrontendHarness,
  createScriptedPyWebViewBridge,
  loadFrontendModule,
} from './scripted-pywebview-bridge.mjs';

after(closeFrontendHarness);

test('订阅窗口创建失败时向调用方报告错误', async () => {
  const storage = new Map([['gam:auth:token', 'test-token']]);
  globalThis.localStorage = {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: (key) => storage.delete(key),
  };
  globalThis.fetch = async () => ({
    status: 200,
    json: async () => ({ code: 200, url: 'https://example.com/subscription' }),
  });
  createScriptedPyWebViewBridge({
    open_subscription_window: [{ resolve: false }],
  });

  const { openSubscriptionPage } = await loadFrontendModule('/src/composables/useSubscriptionPage.ts');

  await assert.rejects(openSubscriptionPage(), /订阅窗口打开失败/);
});
