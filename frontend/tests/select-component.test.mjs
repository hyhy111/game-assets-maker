import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { after, test } from 'node:test';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';

after(closeSfcRenderer);

test('shared Select supports strings, numbers, placeholders, and accessible listbox keyboard controls', async () => {
  const selected = await renderSfc('components/common/Select.vue', {
    props: {
      modelValue: 5,
      options: [
        { value: 4, label: '4 秒' },
        { value: 5, label: '5 秒' },
      ],
      ariaLabel: '默认时长',
      dataTest: 'duration-select',
    },
  });
  const placeholder = await renderSfc('components/common/Select.vue', {
    props: {
      modelValue: '',
      options: [{ value: 'hero', label: '英雄' }],
      placeholder: '选择角色',
      ariaLabel: '目标角色',
    },
  });
  const source = await readFile(new URL('../src/components/common/Select.vue', import.meta.url), 'utf8');

  assert.match(selected, /<button[^>]*aria-label="默认时长"[^>]*data-test="duration-select"/);
  assert.match(selected, /aria-haspopup="listbox"/);
  assert.match(selected, /aria-expanded="false"/);
  assert.match(selected, />5 秒</);
  assert.match(placeholder, /aria-label="目标角色"/);
  assert.match(placeholder, />选择角色</);
  assert.match(source, /Listbox, ListboxButton, ListboxOptions, ListboxOption/);
  assert.match(source, /<ListboxOption[\s\S]*as="template"/);
  assert.match(source, /value: string \| number/);
  assert.match(source, /modelValue: string \| number/);
  assert.match(source, /emit\('update:modelValue', value\)/);
});
