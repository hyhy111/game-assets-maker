import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

test('batch trim promotes the role board without losing the real workflow', async () => {
  const [source, zhLocale, enLocale] = await Promise.all([
    readFile(new URL('../src/views/BatchTrim.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/locales/zh-CN.ts', import.meta.url), 'utf8'),
    readFile(new URL('../src/locales/en.ts', import.meta.url), 'utf8'),
  ]);

  assert.match(source, /class="batch-trim-role-card"/);
  assert.match(source, /class="batch-trim-action-chip"/);
  assert.match(source, /class="batch-trim-toolbar"/);
  assert.match(source, /\.batch-trim-toolbar\s*\{[^}]*grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\);[^}]*gap:\s*1rem;/s);
  assert.doesNotMatch(source, /batch-trim-search-panel/);
  assert.match(source, /class="batch-trim-control-bar"/);
  assert.match(source, /\.batch-trim-control-bar\s*\{[^}]*grid-column:\s*span 2 \/ span 2;/s);
  assert.match(source, /class="batch-trim-output-path"/);
  assert.match(source, /\.batch-trim-search\s*\{[^}]*height:\s*2\.75rem;/s);
  assert.match(source, /\.batch-trim-control-bar\s*\{[^}]*height:\s*2\.75rem;/s);
  assert.match(source, /\.batch-trim-output-path\s*\{[^}]*display:\s*flex;/s);
  assert.match(source, /\.batch-trim-mode-toggle button\.active\s*\{[^}]*background:\s*rgb\(255 189 92 \/ 20%\);[^}]*color:\s*#ffda9a;/s);
  assert.doesNotMatch(source, /batch-trim-execution-dock/);
  assert.match(source, /\.batch-trim-page\s*\{\s*background: #1a1a1a;/);
  assert.doesNotMatch(source, /batchTrim\.boardEyebrow|batchTrim\.boardTitle|batchTrim\.boardSubtitle/);
  assert.doesNotMatch(source, /batch-trim-selection-count/);
  assert.match(source, /@click="toggleRole\(group\)"/);
  assert.match(source, /@click="toggleProject\(project\.id\)"/);
  assert.match(source, /@click="executeTrim"/);
  assert.match(source, /projectIds: selectedProjects\.value/);
  assert.match(source, /mode: trimMode\.value/);
  assert.match(source, /project\.steps\?\.\['3'\]\?\.count/);
  assert.match(source, /project\.steps\?\.\['2'\]\?\.count/);
  assert.doesNotMatch(source, /BatchTrimPrototype|route\.query\.variant|sampleProjects/);

  assert.doesNotMatch(zhLocale, /boardTitle: '从角色开始，整理动画'/);
  assert.doesNotMatch(enLocale, /boardTitle: 'Organize animations by role'/);
});
