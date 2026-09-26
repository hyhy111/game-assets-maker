import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';

after(closeSfcRenderer);

const renderWarning = (props = {}) =>
  renderSfc('components/seedream/SeedreamCloseWarning.vue', {
    props: { open: true, count: 2, ...props },
  });

test('Seedream close warning renders nothing when closed', async () => {
  const html = await renderWarning({ open: false });
  assert.equal(html, '<!---->');
});

test('Seedream close warning renders the title text', async () => {
  const html = await renderWarning();
  assert.match(html, /图片生成仍在进行/);
});

test('Seedream close warning interpolates the active count into the body', async () => {
  const html = await renderWarning({ count: 3 });
  assert.match(html, /当前有 3 张图片正在生成。现在退出后将无法恢复生成结果，并且请求可能已经产生费用。/);
});

test('Seedream close warning renders both action buttons', async () => {
  const html = await renderWarning();
  assert.match(html, /继续等待/);
  assert.match(html, /仍然退出/);
});

test('Seedream close warning marks the dialog as modal with title and body ids', async () => {
  const html = await renderWarning();
  assert.match(html, /role="dialog"/);
  assert.match(html, /aria-modal="true"/);
  assert.match(html, /id="seedream-close-warning-title"/);
  assert.match(html, /id="seedream-close-warning-body"/);
});

test('Seedream close warning exposes continue and exit data-test hooks', async () => {
  const html = await renderWarning();
  assert.match(html, /data-test="seedream-close-continue"/);
  assert.match(html, /data-test="seedream-close-exit"/);
});

test('Seedream close warning count updates per render', async () => {
  const htmlOne = await renderWarning({ count: 1 });
  assert.match(htmlOne, /当前有 1 张图片正在生成/);
  const htmlFour = await renderWarning({ count: 4 });
  assert.match(htmlFour, /当前有 4 张图片正在生成/);
});
