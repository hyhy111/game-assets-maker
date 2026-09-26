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
  local_task_id: string;
};

export function useAgentControl() {
  const router = useRouter();
  const projectStore = useProjectStore();
  const processStore = useProcessStore();
  const seedanceStore = useSeedanceStore();
  let seedanceOpenGeneration = 0;

  const handleOpenStep = async (event: Event) => {
    const detail = (event as CustomEvent<AgentOpenStepDetail>).detail;
    if (!detail?.projectId) return;

    await projectStore.loadProject(detail.projectId);
    await router.push('/editor');
    processStore.setCurrentStep(detail.step);
  };

  const handleOpenSeedance = async (event: Event) => {
    const detail = (event as CustomEvent<AgentOpenSeedanceDetail>).detail;
    if (!detail?.local_task_id) return;

    const generation = ++seedanceOpenGeneration;
    const task = await seedanceStore.loadTask(detail.local_task_id);
    if (generation !== seedanceOpenGeneration || !task || 'stale' in task) return;
    await router.push(`/video-generation/tasks/${encodeURIComponent(detail.local_task_id)}`);
  };

  onMounted(() => {
    window.addEventListener('agent-open-step', handleOpenStep);
    window.addEventListener('agent-open-seedance', handleOpenSeedance);
  });

  onUnmounted(() => {
    window.removeEventListener('agent-open-step', handleOpenStep);
    window.removeEventListener('agent-open-seedance', handleOpenSeedance);
  });
}
