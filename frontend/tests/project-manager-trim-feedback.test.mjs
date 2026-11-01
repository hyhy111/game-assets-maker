import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { renderSfc, closeSfcRenderer } from './vue-render-helper.mjs';
import { createScriptedPyWebViewBridge, closeFrontendHarness } from './scripted-pywebview-bridge.mjs';

after(async () => { await closeSfcRenderer(); await closeFrontendHarness(); });

const projects = ['idle', 'walk'].map(action => ({
  id: `hero/${action}`, role: 'hero', action, name: action,
  path: `/projects/hero/${action}`, video_path: '', frame_interval: 1,
  created_at: '', modified_at: '',
}));
const success = { projectId: 'hero/idle', projectName: 'idle', status: 'success', message: '已处理 5 帧', successCount: 5, failedCount: 0, outputPath: '/exports/batch-trim/idle', globalCropBox: [0, 0, 100, 100] };
const partial = { projectId: 'hero/walk', projectName: 'walk', status: 'partial', message: '1 帧失败', successCount: 4, failedCount: 1, outputPath: '/exports/batch-trim/walk', failedFrames: [{ filename: '2.png', reason: '无法读取图片' }], globalCropBox: [0, 0, 100, 100] };

async function library(responses) {
  const bridge = createScriptedPyWebViewBridge({ execute_batch_trim: responses });
  let bindings;
  await renderSfc('views/ProjectManager.vue', {
    piniaState: { project: { projects, loading: false } },
    configureSetup(value) { bindings = value; value.selectedProjectIds.value = new Set(projects.map(project => project.id)); },
  });
  return { bindings, bridge, group: { role: 'hero', projects } };
}

test('partial failures remain visible with both usable output and failed animation information', async () => {
  const { bindings, group } = await library([{ resolve: [success, partial] }]);
  await bindings.executeSelectedTrim(group);
  assert.equal(bindings.showTrimResultsModal.value, true);
  assert.deepEqual(bindings.trimResults.value.map(result => result.status), ['success', 'partial']);
  assert.deepEqual(bindings.failedTrimIds.value, ['hero/walk']);
  assert.deepEqual(bindings.trimOutputDirectories.value, ['/exports/batch-trim']);
  assert.deepEqual([...bindings.selectedProjectIds.value], projects.map(project => project.id));
});

test('exceptions become visible failed results and preserve selection and crop mode', async () => {
  const { bindings, group } = await library([{ reject: Error('Disk unavailable') }]);
  bindings.trimMode.value = 'individual';
  await bindings.executeSelectedTrim(group);
  assert.equal(bindings.showTrimResultsModal.value, true);
  assert.match(bindings.trimExecutionError.value, /Disk unavailable/);
  assert.equal(bindings.trimResults.value.length, 2);
  assert.ok(bindings.trimResults.value.every(result => result.status === 'error'));
  assert.equal(bindings.trimMode.value, 'individual');
  assert.equal(bindings.selectedProjectIds.value.size, 2);
  assert.equal(bindings.trimmingRole.value, null);
});

test('retry submits only failed animations with the original crop mode and shared bounds', async () => {
  const recovered = { ...partial, status: 'success', failedCount: 0, successCount: 5, outputPath: '/exports/batch-trim-2/walk' };
  const { bindings, bridge, group } = await library([{ resolve: [success, partial] }, { resolve: [recovered] }]);
  await bindings.executeSelectedTrim(group);
  bindings.trimMode.value = 'individual';
  bindings.selectedProjectIds.value.clear();
  await bindings.retryFailedTrim();
  const requests = bridge.calls.filter(call => call.method === 'execute_batch_trim').map(call => call.args[0]);
  assert.deepEqual(requests[1], { projectIds: ['hero/walk'], mode: 'global', outputDir: '', globalCropBox: [0, 0, 100, 100] });
  assert.deepEqual(bindings.failedTrimIds.value, []);
  assert.equal(bindings.trimResults.value[0].outputPath, success.outputPath);
  assert.deepEqual(bindings.trimOutputDirectories.value, ['/exports/batch-trim', '/exports/batch-trim-2']);
});

test('all-success and all-failed responses both display results with the right recovery options', async () => {
  for (const status of ['success', 'error']) {
    const results = projects.map(project => ({ ...success, projectId: project.id, projectName: project.action, status }));
    const { bindings, group } = await library([{ resolve: results }]);
    await bindings.executeSelectedTrim(group);
    assert.equal(bindings.showTrimResultsModal.value, true);
    assert.equal(bindings.failedTrimIds.value.length, status === 'error' ? 2 : 0);
    assert.equal(bindings.trimResultTitle.value, status === 'error' ? '裁剪导出失败' : '裁剪导出完成');
    assert.deepEqual(bindings.trimOutputDirectories.value, status === 'error' ? [] : ['/exports/batch-trim']);
  }
});

test('a missing result becomes a visible failure instead of silently disappearing', async () => {
  const { bindings, group } = await library([{ resolve: [success] }]);
  await bindings.executeSelectedTrim(group);
  assert.equal(bindings.trimResults.value.length, 2);
  assert.equal(bindings.trimResults.value[1].status, 'error');
  assert.match(bindings.trimResults.value[1].message, /未返回/);
  assert.deepEqual(bindings.failedTrimIds.value, ['hero/walk']);
});

test('a failed retry preserves already successful outputs and partial output directories', async () => {
  const { bindings, group } = await library([{ resolve: [success, partial] }, { reject: Error('Bridge disconnected') }]);
  await bindings.executeSelectedTrim(group);
  await bindings.retryFailedTrim();
  assert.equal(bindings.trimResults.value[0].status, 'success');
  assert.equal(bindings.trimResults.value[0].outputPath, success.outputPath);
  assert.equal(bindings.trimResults.value[1].status, 'error');
  assert.deepEqual(bindings.trimOutputDirectories.value, ['/exports/batch-trim']);
});

test('another export cannot start while a request is pending', async () => {
  let finish;
  const { bindings, bridge, group } = await library([{ resolve: () => new Promise(resolve => { finish = resolve; }) }]);
  const running = bindings.executeSelectedTrim(group);
  await new Promise(setImmediate);
  await bindings.executeSelectedTrim(group);
  await bindings.retryFailedTrim();
  assert.equal(bridge.calls.filter(call => call.method === 'execute_batch_trim').length, 1);
  finish([success, partial]);
  await running;
  assert.equal(bindings.trimmingRole.value, null);
});

test('failure to open output directories is visible and leaves their paths available to copy', async () => {
  const { bindings, group } = await library([{ resolve: [success, partial] }]);
  await bindings.executeSelectedTrim(group);
  createScriptedPyWebViewBridge({ open_project_folder: [{ resolve: false }] });
  await bindings.openTrimOutputDirectories();
  assert.match(bindings.trimDirectoryError.value, /无法打开/);
  assert.deepEqual(bindings.trimOutputDirectories.value, ['/exports/batch-trim']);
});

test('closing the results modal keeps a visible way back to the same results', async () => {
  const html = await renderSfc('views/ProjectManager.vue', {
    piniaState: { project: { projects, loading: false } },
    configureSetup(value) { value.trimResults.value = [success, partial]; value.showTrimResultsModal.value = false; },
  });
  assert.match(html, /data-test="trim-feedback-summary"/);
  assert.match(html, /查看裁剪结果/);
  assert.match(html, /成功 1 个 · 部分成功 1 个 · 失败 0 个动画/);
});
