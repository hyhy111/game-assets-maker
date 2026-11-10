import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { closeFrontendHarness, createScriptedPyWebViewBridge, loadFrontendModule } from './scripted-pywebview-bridge.mjs';

after(closeFrontendHarness);
const stored = new Map();
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: { getItem: key => stored.get(key) ?? null, setItem: (key, value) => stored.set(key, value), removeItem: key => stored.delete(key) },
});

for (const kind of ['connection', 'http', 'business', 'non-json']) {
  test(`frontend ${kind} failures reach the persistent log without credentials`, async t => {
    const bridge = createScriptedPyWebViewBridge({ report_network_error: [{ resolve: null }] });
    const { httpPost, setToken } = await loadFrontendModule('/src/api/http.ts');
    setToken('private-jwt-token');
    t.mock.method(globalThis, 'fetch', async () => {
      if (kind === 'connection') throw new TypeError('connection lost private-jwt-token');
      if (kind === 'non-json') return new Response('<html>bad gateway</html>', { status: 502 });
      return new Response(JSON.stringify({ code: kind === 'http' ? 200 : 500, msg: 'failed private-password private-jwt-token' }), { status: kind === 'http' ? 503 : 200 });
    });

    await assert.rejects(httpPost('/login?token=private-query', { password: 'private-password' }, { noRecovery: true }));
    await Promise.resolve();
    const calls = bridge.calls.filter(call => call.method === 'report_network_error');
    assert.equal(calls.length, 1);
    const report = calls[0].args[0];
    assert.equal(report.method, 'POST');
    assert.equal(report.error_type, { connection: 'NetworkError', http: 'HttpError', business: 'BusinessError', 'non-json': 'InvalidResponse' }[kind]);
    for (const secret of ['private-password', 'private-jwt-token', 'private-query']) assert.ok(!JSON.stringify(report).includes(secret));
    assert.ok(!('body' in report));
    assert.ok(!('headers' in report));
  });
}

test('a diagnostic bridge rejection cannot replace the original request error', async t => {
  createScriptedPyWebViewBridge({ report_network_error: [{ reject: new Error('logger unavailable') }] });
  const { httpGet, NETWORK_ERROR } = await loadFrontendModule('/src/api/http.ts');
  t.mock.method(globalThis, 'fetch', async () => { throw new TypeError('offline'); });
  await assert.rejects(httpGet('/test'), error => error.message === NETWORK_ERROR);
  await Promise.resolve();
});

test('a recoverable 401 is recorded even when the replay succeeds', async t => {
  const bridge = createScriptedPyWebViewBridge({ report_network_error: [{ resolve: null }] });
  const { httpGet, setToken, onUnauthorizedRecovery } = await loadFrontendModule('/src/api/http.ts');
  setToken('private-jwt-token');
  onUnauthorizedRecovery(async () => { setToken('fresh-token'); return true; });
  let count = 0;
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify(++count === 1 ? { code: 401, msg: 'expired' } : { code: 200, data: {} }), { status: 200 }));
  await httpGet('/profile');
  assert.equal(count, 2);
  assert.equal(bridge.calls.filter(call => call.method === 'report_network_error').length, 1);
  assert.equal(bridge.calls[0].args[0].code, 401);
});

test('errors before pywebviewready are flushed after the bridge becomes available', async t => {
  const bridge = createScriptedPyWebViewBridge({ report_network_error: [{ resolve: null }] });
  const original = bridge.window.pywebview;
  delete bridge.window.pywebview;
  const { httpGet } = await loadFrontendModule('/src/api/http.ts');
  t.mock.method(globalThis, 'fetch', async () => { throw new TypeError('offline at startup'); });
  await assert.rejects(httpGet('/profile'));
  assert.equal(bridge.calls.length, 0);
  bridge.window.pywebview = original;
  bridge.window.dispatchEvent(new Event('pywebviewready'));
  assert.equal(bridge.calls.length, 1);
  assert.match(bridge.calls[0].args[0].message, /offline at startup/);
});
