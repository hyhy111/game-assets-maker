import { nextTick } from 'vue';
import { isNavigationFailure, NavigationFailureType, type Router } from 'vue-router';
import { api } from '@/api';
import { useProjectStore } from '@/stores/project';
import { useProcessStore } from '@/stores/process';
import { useSeedanceStore } from '@/stores/seedance';
import { useSeedreamStore } from '@/stores/seedream';

export type NavigationPayload = {
  target: string;
  project_id?: string;
  step?: number;
  local_id?: string;
};

function editorReceipt(projectId: string, step: number) {
  let done: (ready: boolean) => void;
  const promise = new Promise<boolean>(resolve => { done = resolve; });
  const listener = (event: Event) => {
    const detail = (event as CustomEvent<{ project_id: string; step: number }>).detail;
    if (detail.project_id === projectId && detail.step === step) done(true);
  };
  window.addEventListener('agent-editor-ready', listener);
  const timer = setTimeout(() => done(false), 8000);
  return { promise, dispose: () => {
    clearTimeout(timer);
    window.removeEventListener('agent-editor-ready', listener);
  } };
}

export function createAgentNavigator(router: Router) {
  const projectStore = useProjectStore();
  const processStore = useProcessStore();
  return async (payload: NavigationPayload) => {
    const routes: Record<string, string> = {
      projects: '/', 'project-create': '/create', editor: '/editor',
      'batch-trim': '/batch-trim', 'image-create': '/ai-creation?mode=image',
      'video-create': '/ai-creation?mode=video', settings: '/ai-creation/settings',
    };
    let route = routes[payload.target];
    let ready: ReturnType<typeof editorReceipt> | undefined;
    if (payload.target === 'editor') {
      if (!payload.project_id || ![1, 2, 3].includes(payload.step ?? 0)) throw new Error('INPUT_INVALID');
      const project = await api.project.getProject(payload.project_id);
      if (!project) throw new Error('PROJECT_NOT_FOUND');
      if (processStore.isProcessing) throw new Error('PROCESSING_ACTIVE');
      if ((payload.step! >= 2 && !project.steps?.['1']?.completed)
        || (payload.step === 3 && !project.steps?.['2']?.completed)) throw new Error('STEP_INPUT_MISSING');
      const params = await api.process.getStepParams(payload.project_id, payload.step!);
      ready = editorReceipt(project.id, payload.step!);
      projectStore.setCurrentProject(project);
      processStore.setCurrentStep(payload.step!);
      processStore.applyStepParams(payload.step!, params);
      route = `/editor?agent_step=${payload.step}`;
    } else if (payload.target === 'image-detail' || payload.target === 'video-detail') {
      if (!payload.local_id) throw new Error('INPUT_INVALID');
      if (payload.target === 'image-detail') {
        const result = await useSeedreamStore().loadBatch(payload.local_id);
        if (!result) throw new Error('GENERATION_NOT_FOUND');
        route = '/image-generation/batches/' + encodeURIComponent(payload.local_id);
      } else {
        const result = await useSeedanceStore().loadTask(payload.local_id);
        if (!result || 'stale' in result) throw new Error('GENERATION_NOT_FOUND');
        route = '/video-generation/tasks/' + encodeURIComponent(payload.local_id);
      }
    }
    if (!route) throw new Error('INPUT_INVALID');
    try {
      const failure = await router.push(route);
      if (failure && !isNavigationFailure(failure, NavigationFailureType.duplicated)) throw new Error('NAVIGATION_FAILED');
      await nextTick();
      if (ready && !await ready.promise) throw new Error('EDITOR_LOAD_TIMEOUT');
    } finally {
      ready?.dispose();
    }
    return { target: payload.target, path: router.currentRoute.value.fullPath,
      project_id: payload.target === 'editor' ? projectStore.currentProject?.id : undefined,
      step: payload.target === 'editor' ? processStore.currentStep : undefined, local_id: payload.local_id };
  };
}
