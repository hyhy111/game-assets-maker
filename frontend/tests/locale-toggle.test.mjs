import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { createServer } from 'vite';

const storage = new Map();
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, String(value)),
  },
});

const vite = await createServer({
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
});

after(() => vite.close());

test('locale toggle switches in both directions on consecutive clicks', async () => {
  const { getLocale, setLocale, toggleLocale } = await vite.ssrLoadModule('/src/locales/index.ts');
  setLocale('zh-CN');

  toggleLocale();
  assert.equal(getLocale(), 'en');

  toggleLocale();
  assert.equal(getLocale(), 'zh-CN');
});
