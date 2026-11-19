import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { closeSfcRenderer, renderSfc } from './vue-render-helper.mjs';

after(closeSfcRenderer);

const project = {
  id: '骑士/待机',
  role: '骑士',
  action: '待机',
  path: 'C:\\GAM Assets\\角色\\骑士\\待机',
  steps: { 1: { completed: true }, 2: { completed: true }, 3: { completed: true } },
};

test('both batch trim modes expose the shared delayed tooltip on the homepage and batch trim page', async () => {
  for (const view of ['views/ProjectManager.vue', 'views/BatchTrim.vue']) {
    const html = await renderSfc(view, {
      piniaState: { project: { projects: [project] } },
    });
    for (const hint of ['所有帧裁剪到相同尺寸', '每帧极致裁剪并生成 offset 数据']) {
      const button = [...html.matchAll(/<button\b[^>]*>/g)]
        .map(match => match[0]).find(tag => tag.includes(`data-tooltip="${hint}"`));
      assert.ok(button, `${view} missing tooltip: ${hint}`);
      assert.match(button, /class="[^"]*\bcontrol-tooltip\b/);
      assert.doesNotMatch(button, /\stitle=/);
    }
  }
});

test('start and end frame controls use solid green and red circles', async () => {
  const html = await renderSfc('views/Editor/Step1Extract.vue');
  const start = html.match(/<button[^>]*data-test="set-start-frame"[^>]*>([\s\S]*?)<\/button>/)?.[1];
  const end = html.match(/<button[^>]*data-test="set-end-frame"[^>]*>([\s\S]*?)<\/button>/)?.[1];
  assert.match(start, /lucide-circle/);
  assert.match(start, /text-green-500 fill-green-500/);
  assert.match(end, /lucide-circle/);
  assert.match(end, /text-red-500 fill-red-500/);
  assert.match(html, /aria-label="将当前帧设为起始帧"/);
  assert.match(html, /aria-label="将当前帧设为结束帧"/);
});

test('every processing step places the project directory before the navigation actions', async () => {
  for (const step of [1, 2, 3]) {
    const piniaState = { project: { currentProject: project }, process: { currentStep: step } };
    const html = await renderSfc('components/layout/StepNavigator.vue', { piniaState });
    const folderIndex = html.indexOf('data-test="step-open-project-folder"');
    assert.ok(folderIndex >= 0);
    assert.match(html, /aria-label="打开项目文件夹"/);
    const nextAction = step === 1 ? 'aria-label="下一步"' : 'aria-label="上一步"';
    assert.ok(folderIndex < html.indexOf(nextAction));
    const header = await renderSfc('components/layout/Header.vue', { route: '/editor', piniaState });
    assert.doesNotMatch(header, /aria-label="打开项目文件夹"/);
  }
});

test('project directory access remains disabled while processing', async () => {
  const html = await renderSfc('components/layout/StepNavigator.vue', {
    piniaState: { project: { currentProject: project }, process: { currentStep: 2, taskStatus: { status: 'running' } } },
  });
  const folder = html.match(/<button[^>]*data-test="step-open-project-folder"[^>]*>/)?.[0];
  assert.match(folder, /\sdisabled(?:\s|>|=)/);
  assert.match(folder, /处理中/);
});

test('icon buttons keep their accessible label and square size while showing loading state', async () => {
  const html = await renderSfc('components/common/Button.vue', {
    props: { iconOnly: true, tooltip: '保存设置', loading: true },
    slots: { default: () => 'Original icon' },
  });
  assert.match(html, /aria-label="保存设置"/);
  assert.match(html, /aria-busy="true"/);
  assert.match(html, /icon-button/);
  assert.match(html, /disabled/);
  assert.doesNotMatch(html, /Original icon/);
});
