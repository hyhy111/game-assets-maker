import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { createPinia, setActivePinia } from 'pinia';
import { createMemoryHistory, createRouter } from 'vue-router';
import { closeFrontendHarness, createScriptedPyWebViewBridge, loadFrontendModule } from './scripted-pywebview-bridge.mjs';

after(closeFrontendHarness);

async function navigation() {
  setActivePinia(createPinia());
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/', component: {} }, { path: '/editor', component: {} },
    { path: '/ai-creation/settings', component: {} },
  ] });
  await router.push('/');
  const { createAgentNavigator } = await loadFrontendModule('/src/agent-navigation.ts');
  return { router, navigate: createAgentNavigator(router) };
}

test('settings navigation confirms the actual route without resetting drafts', async () => {
  createScriptedPyWebViewBridge();
  const { router, navigate } = await navigation();
  const { useAICreationStore } = await loadFrontendModule('/src/stores/aiCreation.ts');
  useAICreationStore().videoDraft.prompt = 'keep';
  const result = await navigate({ target: 'settings' });
  assert.equal(result.path, '/ai-creation/settings');
  assert.equal(router.currentRoute.value.path, '/ai-creation/settings');
  assert.equal(useAICreationStore().videoDraft.prompt, 'keep');
});


test('missing project preserves route and existing project', async () => {
  createScriptedPyWebViewBridge({ get_project: [{ resolve: null }] });
  const { router, navigate } = await navigation();
  const { useProjectStore } = await loadFrontendModule('/src/stores/project.ts');
  useProjectStore().setCurrentProject({ id: 'existing' });
  await assert.rejects(navigate({ target: 'editor', project_id: 'missing', step: 2 }), /PROJECT_NOT_FOUND/);
  assert.equal(router.currentRoute.value.path, '/');
  assert.equal(useProjectStore().currentProject.id, 'existing');
});

test('target step opens with saved parameters and same-page requests succeed', async () => {
  createScriptedPyWebViewBridge({ get_project: [{ resolve: { id: 'hero/idle', steps: { '1': { completed: true } } } }],
    get_step_params: [{ resolve: { alpha_matting: false, alpha_matting_erode_size: 7 } }] });
  const { router, navigate } = await navigation();
  const { useProcessStore } = await loadFrontendModule('/src/stores/process.ts');
  const operation = navigate({ target: 'editor', project_id: 'hero/idle', step: 2 });
  await new Promise(resolve => setTimeout(resolve, 10));
  window.dispatchEvent(new CustomEvent('agent-editor-ready', { detail: { project_id: 'hero/idle', step: 2 } }));
  await operation;
  assert.equal(router.currentRoute.value.path, '/editor');
  assert.equal(useProcessStore().currentStep, 2);
  assert.equal(useProcessStore().s2Params.alpha_matting_erode_size, 7);
  await navigate({ target: 'settings' });
  await navigate({ target: 'settings' });
});


test('loading extraction parameters does not overwrite active step preview fps', async () => {
  createScriptedPyWebViewBridge();
  setActivePinia(createPinia());
  const { useProcessStore } = await loadFrontendModule('/src/stores/process.ts');
  const { usePlayerStore } = await loadFrontendModule('/src/stores/player.ts');
  const process = useProcessStore();
  process.currentStep = 2;
  process.applyStepParams(2, { fps: 24 });
  process.applyStepParams(1, { fps: 30 });
  assert.equal(usePlayerStore().playbackFps, 24);
});
