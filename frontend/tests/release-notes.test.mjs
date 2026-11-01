import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { renderReleaseNotes } from '../src/release-notes.ts';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';

after(closeSfcRenderer);

const notes = '## Improvements\n\n- **Wand** feathering\n- Keep `config.json`\n\n1. Download\n2. Install\n\n```sh\nnpm run build\n```';
const release = {current_version:'1.0.2',latest_version:'1.0.3',status:'available',release_notes:notes,
  release_url:'https://github.com/hyhy111/game-assets-maker/releases/tag/v1.0.3',error:''};

test('release Markdown renders headings, emphasis, lists, inline code, fenced code and tables', () => {
  const html = renderReleaseNotes(notes + '\n\n| Change | State |\n| --- | --- |\n| Preview | Ready |');
  assert.match(html, /<h2>Improvements<\/h2>/);
  assert.match(html, /<ul>[\s\S]*<strong>Wand<\/strong>/);
  assert.match(html, /<ol>/);
  assert.match(html, /<code>config.json<\/code>/);
  assert.match(html, /<pre><code class="language-sh">npm run build/);
  assert.match(html, /<table>[\s\S]*<td>Ready<\/td>/);
});

test('raw HTML stays inert and script/data/file links are rejected', () => {
  const html = renderReleaseNotes('<script>alert(1)</script>\n\n<img src=x onerror=alert(1)>\n\n[bad](javascript:alert(1))\n\n[encoded](java&#x73;cript:alert(1))\n\n[data](data:text/html,test)\n\n[file](file:///etc/passwd)');
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<(script|img|iframe)\b/i);
  assert.doesNotMatch(html, /href=["'](?:javascript|data|file|vbscript):/i);
});

test('release links open separately with safe target attributes', () => {
  const html = renderReleaseNotes('[Download](https://github.com/hyhy111/game-assets-maker/releases)');
  assert.match(html, /href="https:\/\/github.com\/hyhy111\/game-assets-maker\/releases"/);
  assert.match(html, /target="_blank"/);
  assert.match(html, /rel="noopener noreferrer"/);
});

async function settings(state = release) {
  return renderSfc('components/layout/AppUpdateSettings.vue', {
    configureSetup(bindings) {
      bindings.updates.currentVersion = '1.0.2';
      bindings.updates.state = {...state};
    },
  });
}

for (const status of ['available','ignored']) {
  test(`${status} release details default to collapsed while the update action stays visible`, async () => {
    const html = await settings({...release,status});
    const details = html.match(/<details\b([^>]*)>/);
    assert.ok(details);
    assert.doesNotMatch(details[1], /\sopen(?:\s|=|$)/);
    assert.match(html, /查看更新详情/);
    assert.match(html, /收起更新详情/);
    assert.match(html, /<h2>Improvements<\/h2>/);
    assert.ok(html.indexOf('data-test="app-update-open"') < html.indexOf('<details'));
    assert.doesNotMatch(html, /## Improvements/);
  });
}

test('empty notes and versions without an update do not expose an empty details control', async () => {
  for (const state of [{...release,release_notes:''}, {...release,status:'up_to_date'}]) {
    assert.doesNotMatch(await settings(state), /data-test="app-update-details"/);
  }
});
