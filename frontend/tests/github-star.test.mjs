import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import { ref } from 'vue';

const source = await readFile(new URL('../src/components/layout/AppUpdateSettings.vue', import.meta.url), 'utf8');
const script = source.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1].replace(/^import .*;$/gm, '');

function createAction(openGithubRepository) {
  return vm.runInNewContext(`${script}\n({ openingRepository, repositoryError, openRepository });`, {
    ref, useI18n: () => ({ t: value => value }), useUpdateStore: () => ({}),
    api: { system: { openGithubRepository } },
  });
}

for (const fail of [async () => false, async () => { throw new Error('bridge unavailable'); }]) {
  test('browser failure is shown and a successful retry clears it without update state', async () => {
    let attempts = 0;
    const action = createAction(() => ++attempts === 1 ? fail() : Promise.resolve(true));
    await action.openRepository();
    assert.equal(action.repositoryError.value, true);
    assert.equal(action.openingRepository.value, false);
    await action.openRepository();
    assert.equal(action.repositoryError.value, false);
    assert.equal(action.openingRepository.value, false);
    assert.equal(attempts, 2);
  });
}

test('repeated clicks while the browser is opening trigger only one request', async () => {
  let finish;
  let attempts = 0;
  const action = createAction(() => { attempts++; return new Promise(resolve => { finish = resolve; }); });
  const pending = action.openRepository();
  assert.equal(action.openingRepository.value, true);
  await action.openRepository();
  assert.equal(attempts, 1);
  finish(true);
  await pending;
  assert.equal(action.openingRepository.value, false);
  assert.equal(action.repositoryError.value, false);
});
