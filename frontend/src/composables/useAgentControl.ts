import { nextTick } from 'vue';
import { useAgentBatchTrimStore, type AgentTrimResult } from '@/stores/agentBatchTrim';
import { useSeedreamStore } from '@/stores/seedream';
import { useAICreationStore, type CreationMode } from '@/stores/aiCreation';
import { createAgentNavigator, type NavigationPayload } from '@/agent-navigation';
import type { PyWebViewWindow } from '@/types/api';
import { onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import { useProjectStore } from '@/stores/project';
import { useProcessStore } from '@/stores/process';
import { useSeedanceStore } from '@/stores/seedance';

type AgentOpenStepDetail = {
  projectId: string;
  step: number;
};

type AgentOpenSeedanceDetail = {
  local_task_id?: string;
  localTaskId?: string;
};

export function useAgentControl() {
  const router = useRouter();
  const projectStore = useProjectStore();
  const processStore = useProcessStore();
  const seedanceStore = useSeedanceStore();
  let seedanceOpenGeneration = 0;
  const navigate = createAgentNavigator(router);
  let pending = Promise.resolve();
  const handleOperation = (event: Event) => {
    const request = (event as CustomEvent<{ request_id: string; operation: string; payload: NavigationPayload & { kind: CreationMode; patch: Record<string, unknown> }; applied?: { task_id?: string } & Partial<AgentTrimResult> }>).detail;
    if (!request?.request_id) return;
    // Serialize state changes so an older load cannot overwrite a newer target.
    pending = pending.then(async () => {
      let result: { ok: boolean; data?: unknown; error?: string };
      try {
        if (request.operation === 'generation.submit') {
          const submitted = await (window as PyWebViewWindow).pywebview?.api.agent_submit_generation(
            request.request_id, useAICreationStore().generationSource,
          );
          if (submitted?.success && submitted.task) {
            seedanceStore.currentTask = submitted.task;
            useAICreationStore().setCurrentGeneration({ kind: 'video', localId: submitted.task.local_id });
          } else if (submitted?.success && submitted.batch) {
            useSeedreamStore().currentBatch = submitted.batch;
            useAICreationStore().setCurrentGeneration({ kind: 'image', localId: submitted.batch.local_id });
          }
          result = { ok: submitted?.success === true, data: submitted };
        } else if (request.operation === 'batch.trim') {
          if (!request.applied?.raw_results || !request.applied.project_ids || !request.applied.mode) throw new Error('INPUT_INVALID');
          useAgentBatchTrimStore().result = { raw_results: request.applied.raw_results,
            project_ids: request.applied.project_ids, mode: request.applied.mode };
          await navigate({ target: 'batch-trim' });
          await nextTick();
          result = { ok: true, data: request.applied };
        } else if (request.operation === 'step.set' || request.operation === 'step.run') {
          await navigate({ target: 'editor', project_id: request.payload.project_id, step: request.payload.step });
          if (request.applied?.task_id) processStore.observeAgentTask(request.applied.task_id);
          result = { ok: true, data: request.applied };
        } else if (['draft.get', 'draft.patch', 'draft.restore', 'draft.reuse'].includes(request.operation)) {
          const workspace = useAICreationStore();
          const kind = request.payload.kind;
          if (request.operation !== 'draft.get') {
            // Mount the existing form first so its configured defaults are initialized.
            await navigate({ target: kind === 'image' ? 'image-create' : 'video-create' });
            result = { ok: true, data: await workspace.patchAgentDraft(kind, request.payload.patch) };
          } else {
            result = { ok: true, data: { kind, draft: { ...(kind === 'image' ? workspace.imageDraft : workspace.videoDraft) } } };
          }
        } else {
          if (request.operation !== 'ui.navigate') throw new Error('INPUT_INVALID');
          result = { ok: true, data: await navigate(request.payload) };
        }
      } catch (error) {
        result = { ok: false, error: error instanceof Error ? error.message : 'UI_APPLY_FAILED' };
      }
      await (window as PyWebViewWindow).pywebview?.api.agent_acknowledge(request.request_id, result);
    }).catch(error => console.error('Agent receipt failed', error));
  };

  const handleOpenStep = async (event: Event) => {
    const detail = (event as CustomEvent<AgentOpenStepDetail>).detail;
    if (!detail?.projectId) return;

    await projectStore.loadProject(detail.projectId);
    await router.push('/editor');
    processStore.setCurrentStep(detail.step);
  };

  const handleOpenSeedance = async (event: Event) => {
    const detail = (event as CustomEvent<AgentOpenSeedanceDetail>).detail;
    const localId = detail?.local_task_id ?? detail?.localTaskId;
    if (!localId) return;

    const generation = ++seedanceOpenGeneration;
    const task = await seedanceStore.loadTask(localId);
    if (generation !== seedanceOpenGeneration || !task || 'stale' in task) return;
    await router.push(`/video-generation/tasks/${encodeURIComponent(localId)}`);
  };

  onMounted(() => {
    window.addEventListener('agent-operation', handleOperation);
    window.addEventListener('agent-open-step', handleOpenStep);
    window.addEventListener('agent-open-seedance', handleOpenSeedance);
  });

  onUnmounted(() => {
    window.removeEventListener('agent-operation', handleOperation);
    window.removeEventListener('agent-open-step', handleOpenStep);
    window.removeEventListener('agent-open-seedance', handleOpenSeedance);
  });
}
