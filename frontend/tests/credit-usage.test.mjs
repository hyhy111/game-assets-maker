import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import { createPinia, setActivePinia } from 'pinia';
import { reactive, nextTick } from 'vue';
import ts from 'typescript';

async function fixture() {
  const auth = reactive({ token: '', isLoggedIn: false });
  const billing = reactive({ account: null });
  const requests = [];
  const http = () => new Promise((resolve, reject) => requests.push({ resolve, reject }));
  globalThis.__creditUsageFixture = { auth, billing, http };
  let source = await readFile(new URL('../src/stores/creditUsage.ts', import.meta.url), 'utf8');
  source = source.replace(/from 'pinia'/, `from '${import.meta.resolve('pinia')}'`)
    .replace(/from 'vue'/, `from '${import.meta.resolve('vue')}'`)
    .replace(/import \{ httpGet, httpPost \} from[^;]+;/, 'const httpGet = globalThis.__creditUsageFixture.http; const httpPost = httpGet;')
    .replace(/import \{ useAuthStore \} from[^;]+;/, 'const useAuthStore = () => globalThis.__creditUsageFixture.auth;')
    .replace(/import \{ useBillingStore \} from[^;]+;/, 'const useBillingStore = () => globalThis.__creditUsageFixture.billing;');
  const code = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
  const module = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}#${Math.random()}`);
  setActivePinia(createPinia());
  const store = module.useCreditUsageStore();
  return { auth, billing, requests, store, dispose() { store.reset(); store.$dispose(); } };
}
const response = (general, bonus = 0) => ({ data: {
  asOf: '2026-10-29T00:00:00Z', refreshAt: '2026-10-29T00:01:00Z',
  account: { generalAvailable: general, bonusAvailable: bonus, buckets: [] },
  combinations: [{ context: { mediaType: 'image', model: 'a', sizeLabel: '2K', durationSec: null }, quote: 50, generalAvailable: general, bonusAvailable: bonus }],
} });
async function flush() { await nextTick(); await new Promise(resolve => setImmediate(resolve)); }

test('account switch discards the previous response even if it finishes last', async () => {
  const f = await fixture();
  try {
    f.auth.token = 'account-a'; f.auth.isLoggedIn = true; await flush();
    assert.equal(f.requests.length, 1);
    f.auth.token = 'account-b'; await flush();
    assert.equal(f.requests.length, 2);
    f.requests[1].resolve(response(20)); await flush();
    f.requests[0].resolve(response(900)); await flush();
    assert.equal(f.store.data.account.generalAvailable, 20);
    f.auth.isLoggedIn = false; await flush();
    assert.equal(f.store.data, null); assert.equal(f.store.ready, false);
  } finally { f.dispose(); }
});

test('refresh deduplicates, fails closed while pending and recovers after failure', async () => {
  const f = await fixture();
  try {
    f.auth.token = 'a'; f.auth.isLoggedIn = true; await flush();
    f.requests[0].resolve(response(100)); await flush(); assert.equal(f.store.ready, true);
    const first = f.store.refresh(), second = f.store.refresh();
    assert.equal(f.requests.length, 2); assert.equal(f.store.ready, false);
    f.requests[1].reject(new Error('offline')); await Promise.all([first, second]);
    assert.equal(f.store.ready, false); assert.equal(f.store.canPay('image', 'a', '2K'), false);
    const retry = f.store.refresh(); f.requests[2].resolve(response(100)); await retry;
    assert.equal(f.store.canPay('image', 'a', '2K'), true);
  } finally { f.dispose(); }
});

test('eligibility uses complete combinations and the whole image batch cost', async () => {
  const f = await fixture();
  try {
    f.auth.token = 'a'; f.auth.isLoggedIn = true; await flush();
    f.requests[0].resolve(response(10, 90)); await flush();
    assert.equal(f.store.canPay('image', 'a', '2K', undefined, 2), true);
    assert.equal(f.store.canPay('image', 'a', '2K', undefined, 3), false);
    assert.equal(f.store.canPay('image', 'a', '1K'), false);
    assert.equal(f.store.canPay('image', 'other'), false);
    assert.equal(f.store.canPay('video', 'a', '2K'), false);
  } finally { f.dispose(); }
});

test('a quote from the previous token cannot authorize the next account', async () => {
  const f = await fixture();
  try {
    f.auth.token = 'a'; f.auth.isLoggedIn = true; await flush();
    f.requests[0].resolve(response(100)); await flush();
    const quote = f.store.quote('image', { model: 'a', size: '2K' });
    const rejection = assert.rejects(quote, /登录状态已变化/);
    f.auth.token = 'b'; await flush();
    f.requests[1].resolve({ data: { canSubmit: true, quote: 50 } }); await rejection;
    f.requests[2].resolve(response(0)); await flush();
    assert.equal(f.store.canPay('image', 'a'), false);
  } finally { f.dispose(); }
});

test('model selection uses applicable credits rather than the price of a generation', async () => {
  const f = await fixture();
  try {
    f.auth.token = 'a'; f.auth.isLoggedIn = true; await flush();
    const snapshot = response(0, 20);
    snapshot.data.combinations.push({ ...snapshot.data.combinations[0], context: { mediaType: 'image', model: 'other', sizeLabel: '2K' }, bonusAvailable: 0 });
    f.requests[0].resolve(snapshot); await flush();
    assert.equal(f.store.canSelectModel('image', 'a'), true);
    assert.equal(f.store.canPay('image', 'a', '2K'), false);
    assert.equal(f.store.canSelectModel('image', 'other'), false);
    assert.equal(f.store.canSelectModel('video', 'a'), false);
    assert.equal(f.store.canSelectModel('image', 'missing'), false);
    const refresh = f.store.refresh();
    assert.equal(f.store.canSelectModel('image', 'a'), false);
    f.requests[1].reject(new Error('offline')); await refresh;
    assert.equal(f.store.canSelectModel('image', 'a'), false);
  } finally { f.dispose(); }
});

test('exhausted credits preserve only their declared model scope and exclude future buckets', async () => {
  const f = await fixture();
  try {
    f.auth.token = 'a'; f.auth.isLoggedIn = true; await flush();
    const snapshot = response(0);
    snapshot.data.combinations.push({ ...snapshot.data.combinations[0], context: { mediaType: 'image', model: 'other', sizeLabel: '2K' } });
    snapshot.data.account.buckets = [
      { bucket: { bucketId: 'bonus', remainAmount: 0, usageMode: 'RESTRICTED' }, rules: [snapshot.data.combinations[0].context] },
      { bucket: { bucketId: 'future', remainAmount: 100, usageMode: 'UNRESTRICTED', effectiveFrom: '2099-01-01T00:00:00Z' } },
    ];
    f.requests[0].resolve(snapshot); await flush();
    assert.equal(f.store.canSelectModel('image', 'a'), true);
    assert.equal(f.store.canSelectModel('image', 'other'), false);
    assert.equal(f.store.canPay('image', 'a', '2K'), false);
    f.auth.isLoggedIn = false; await flush();
    assert.equal(f.store.canSelectModel('image', 'a'), false);
  } finally { f.dispose(); }
});

for (const staleFails of [false, true]) {
  test(`balance changes queue a fresh snapshot after an in-flight ${staleFails ? 'failure' : 'success'}`, async () => {
    const f = await fixture();
    try {
      f.auth.token = 'a'; f.auth.isLoggedIn = true; await flush();
      f.billing.account = { totalAvailable: 50 }; await flush();
      f.billing.account = { totalAvailable: 100 }; await flush();
      assert.equal(f.requests.length, 1, 'coalesce balance changes while a request is pending');
      if (staleFails) f.requests[0].reject(new Error('obsolete failure'));
      else f.requests[0].resolve(response(0));
      await flush();
      assert.equal(f.store.ready, false, 'the obsolete snapshot must not authorize or block a selection');
      assert.equal(f.requests.length, 2, 'refresh immediately instead of waiting for the expiry timer');
      f.requests[1].resolve(response(100)); await flush();
      assert.equal(f.store.ready, true);
      assert.equal(f.store.canPay('image', 'a', '2K', undefined, 2), true);
    } finally { f.dispose(); }
  });
}

test('logout cancels a queued balance refresh', async () => {
  const f = await fixture();
  try {
    f.auth.token = 'a'; f.auth.isLoggedIn = true; await flush();
    f.billing.account = { totalAvailable: 100 }; await flush();
    f.auth.isLoggedIn = false; await flush();
    f.requests[0].resolve(response(100)); await flush();
    assert.equal(f.requests.length, 1);
    assert.equal(f.store.data, null);
    assert.equal(f.store.ready, false);
  } finally { f.dispose(); }
});

test('unchanged account refreshes do not keep invalidating an in-flight snapshot', async () => {
  const f = await fixture();
  try {
    f.billing.account = { totalAvailable: 100 }; await flush();
    f.auth.token = 'a'; f.auth.isLoggedIn = true; await flush();
    f.requests[0].resolve(response(100)); await flush();
    const pending = f.store.refresh();
    f.billing.account = { totalAvailable: 100 }; await flush();
    f.requests[1].resolve(response(100)); await pending; await flush();
    assert.equal(f.requests.length, 2);
    assert.equal(f.store.ready, true);
  } finally { f.dispose(); }
});
