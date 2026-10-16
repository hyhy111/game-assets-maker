import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import ts from 'typescript';

const source = await readFile(new URL('../src/api/index.ts', import.meta.url), 'utf8');
const wait = source.match(/function waitForPyWebView\(\): Promise<PyWebViewApi> \{[\s\S]*?^\}/m)?.[0];
const available = source.match(/export function isApiAvailable\(\): boolean \{[\s\S]*?^\}/m)?.[0];
assert.ok(wait);
assert.ok(available);

function bridge(window) {
  const code = ts.transpileModule(`${wait}\n${available.replace('export ', '')}\n({ waitForPyWebView, isApiAvailable });`, {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  }).outputText;
  return vm.runInNewContext(code, { window });
}

test('an injected empty bridge waits for API registration before startup calls', async () => {
  let listener;
  const window = { pywebview: { api: {} }, addEventListener: (_name, callback) => { listener = callback; } };
  const api = bridge(window);
  let settled = false;
  const pending = api.waitForPyWebView().then(value => { settled = true; return value; });
  await Promise.resolve();
  assert.equal(settled, false);
  assert.equal(api.isApiAvailable(), false);
  window.pywebview.api.get_app_version = async () => '1.0.0';
  listener();
  assert.equal(await pending, window.pywebview.api);
  assert.equal(api.isApiAvailable(), true);
});

test('an already registered bridge resolves immediately', async () => {
  const window = { pywebview: { api: { get_app_version: async () => '1.0.0' } }, addEventListener: () => assert.fail('unexpected wait') };
  const api = bridge(window);
  assert.equal(await api.waitForPyWebView(), window.pywebview.api);
  assert.equal(api.isApiAvailable(), true);
});
