import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { createServer } from 'vite';

const previousFetch = globalThis.fetch;
const previousStorage = globalThis.localStorage;
const storage = new Map();
globalThis.localStorage = {
  getItem: key => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, value),
  removeItem: key => storage.delete(key),
};
const servers = [];
after(async () => {
  globalThis.fetch = previousFetch;
  globalThis.localStorage = previousStorage;
  await Promise.all(servers.map(server => server.close()));
});

for (const code of ['', '渠道 A "quoted"']) {
  test(`startup and authentication carry exact package channel ${JSON.stringify(code)}`, async () => {
    const server = await createServer({
      appType: 'custom', logLevel: 'silent',
      define: { __GAM_CHANNEL_CODE__: JSON.stringify(code) },
      server: { middlewareMode: true },
    });
    servers.push(server);
    const auth = await server.ssrLoadModule('/src/api/auth.ts');
    const channel = await server.ssrLoadModule('/src/api/channel.ts');
    const http = await server.ssrLoadModule('/src/api/http.ts');
    const calls = [];
    globalThis.fetch = async (url, init) => {
      calls.push({ path: new URL(url).pathname, body: JSON.parse(init.body), auth: init.headers.get('Authorization') });
      return { status: 200, json: async () => ({ code: 200, token: 'test-token' }) };
    };
    http.setToken('existing-token');
    channel.reportStartup();
    channel.reportStartup();
    await auth.register({ email: 'tester@example.com', password: 'test', emailCode: 'test' });
    await auth.login({ username: 'tester@example.com', password: 'test' });
    assert.deepEqual(calls.map(c => c.path), ['/app/channel/startup', '/register', '/login']);
    assert.ok(calls.every(c => c.body.channelCode === code));
    assert.equal(calls[0].auth, null);
    let unauthorized = 0;
    http.onUnauthorized(() => unauthorized++);
    globalThis.fetch = async () => ({ status: 401, json: async () => ({ code: 401 }) });
    await assert.rejects(http.httpPost('/app/channel/startup', { channelCode: code }, { anonymous: true, noRecovery: true }));
    assert.equal(http.getToken(), 'existing-token');
    assert.equal(unauthorized, 0);
  });
}
