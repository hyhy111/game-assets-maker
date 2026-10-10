/**
 * Process Store - Manages processing workflow state
 */
import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { api } from '@/api';
import { useProjectStore } from './project';
import { usePlayerStore } from './player';
import type { ModelStatus, Step1Params, Step2Params, Step3Params, TaskStatus } from '@/types';

export const useProcessStore = defineStore('process', () => {
  // State
  const currentStep = ref(1);
  const maxStep = ref(3);

  // Step parameters
  const s1Params = ref<Step1Params>({
    frame_interval: 1,
    start_frame: 0,
    end_frame: -1,
    fps: 30,
    processed: false
  });

  // Step 2: Background removal only (rembg parameters)
  const s2Params = ref<Step2Params>({
    model: 'u2net',
    alpha_matting: true,
    alpha_matting_erode_size: 5,
    alpha_matting_background_threshold: 120,
    alpha_matting_foreground_threshold: 240,
    fps: 10,
    processed: false,
    processing_time: 0
  });

  // Step 3: Post-processing (hole punching + alignment)
  const s3Params = ref<Step3Params>({
    enabled: true,  // Hole punching enabled
    green_intensity: 3,  // 1=bright green, 5=dark green
    feather_radius: 3,
    min_hole_size: 5,
    align_enabled: false,  // Alignment disabled by default
    align_h: false,        // Horizontal centering (default off)
    align_v: false,        // Vertical bottom alignment (default off)
    use_padding: true,     // Use bottom padding
    padding_bottom: 10,    // Bottom padding pixels
    fps: 10,
    processed: false,
    processing_time: 0
  });

  // Task tracking
  const currentTask = ref<string | null>(null);
  const taskStatus = ref<TaskStatus | null>(null);
  const isPolling = ref(false);

  // Shared Step 1/Step 2 model state
  const modelStatus = ref<ModelStatus>({
    model: 'u2net',
    phase: 'needs_download',
    downloaded_bytes: null,
    total_bytes: null,
    error: null,
  });

  // Getters
  const canGoNext = computed(() => {
    const projectStore = useProjectStore();
    // Step 1 must be processed before going to step 2
    if (currentStep.value === 1 && !projectStore.isStepCompleted(1)) {
      return false;
    }
    // Step 2 must be processed before going to step 3
    if (currentStep.value === 2 && !projectStore.isStepCompleted(2)) {
      return false;
    }
    return currentStep.value < maxStep.value;
  });
  const canGoPrev = computed(() => currentStep.value > 1);
  const isProcessing = computed(() => taskStatus.value?.status === 'running');
  const progress = computed(() => taskStatus.value?.progress ?? 0);
  const stepStatus = computed(() => {
    const projectStore = useProjectStore();
    return {
      1: {
        completed: projectStore.isStepCompleted(1),
        processing: currentStep.value === 1 && isProcessing.value
      },
      2: {
        completed: projectStore.isStepCompleted(2),
        processing: currentStep.value === 2 && isProcessing.value
      },
      3: {
        completed: projectStore.isStepCompleted(3),
        processing: currentStep.value === 3 && isProcessing.value
      }
    };
  });

  // Actions
  function goToStep(step: number) {
    if (step >= 1 && step <= maxStep.value) {
      currentStep.value = step;
    }
  }

  function setCurrentStep(step: number) {
    goToStep(step);
  }

  function nextStep() {
    if (canGoNext.value) {
      currentStep.value++;
    }
  }

  function prevStep() {
    if (canGoPrev.value) {
      currentStep.value--;
    }
  }

  function applyStepParams(step: number, params: Partial<Step1Params | Step2Params | Step3Params>) {
    if (step === 1) s1Params.value = { ...s1Params.value, ...params } as Step1Params;
    else if (step === 2) s2Params.value = { ...s2Params.value, ...params, model: 'u2net' } as Step2Params;
    else if (step === 3) s3Params.value = { ...s3Params.value, ...params } as Step3Params;
    else throw new Error('INVALID_STEP');
    const saved = step === 1 ? s1Params.value : step === 2 ? s2Params.value : s3Params.value;
    if (step === currentStep.value && saved.fps) usePlayerStore().setPlaybackFps(saved.fps);
  }

  async function loadStepParams(projectId: string, step: number) {
    try {
      applyStepParams(step, await api.process.getStepParams(projectId, step));
      return true;
    } catch (e) {
      console.error(`Failed to load step ${step} params:`, e);
      return false;
    }
  }

  async function startProcessing(projectId: string, step: number, customParams?: Partial<Step1Params | Step2Params | Step3Params>) {
    const playerStore = usePlayerStore();

    let params: Step1Params | Step2Params | Step3Params;
    if (step === 1) {
      params = { ...s1Params.value, ...customParams } as Step1Params;
    } else if (step === 2) {
      params = { ...s2Params.value, ...customParams } as Step2Params;
    } else {
      params = { ...s3Params.value, ...customParams } as Step3Params;
    }

    if (
      step === 2
      && (
        modelStatus.value.phase !== 'ready'
        || modelStatus.value.model !== ((params as Step2Params).model ?? 'u2net')
      )
    ) {
      throw new Error('Background-removal model is not ready');
    }

    // Stop playback before processing
    playerStore.pause();

    // Reset previous task status before starting new one
    currentTask.value = null;
    taskStatus.value = {
      success: true,
      task_id: '',
      status: 'pending',
      progress: 0,
      current: 0,
      total: 0
    };

    try {
      const taskId = await api.process.startProcessing(projectId, step, params);
      currentTask.value = taskId;

      // Start polling
      startPolling(taskId);

      return taskId;
    } catch (e) {
      console.error('Failed to start processing:', e);
      throw e;
    }
  }

  function observeAgentTask(taskId: string) {
    usePlayerStore().pause();
    currentTask.value = taskId;
    startPolling(taskId);
  }

  function startPolling(taskId: string) {
    isPolling.value = true;

    const poll = async () => {
      if (!isPolling.value) return;

      try {
        const status = await api.process.getTaskStatus(taskId);
        taskStatus.value = status;

        if (['pending', 'running'].includes(status.status) && isPolling.value) {
          setTimeout(poll, 500);
        } else {
          // Task finished (completed, failed, or cancelled)
          // Refresh project to get updated step status
          const projectStore = useProjectStore();
          if (projectStore.currentProject) {
            await projectStore.loadProject(projectStore.currentProject.id);
          }
          stopPolling();
        }
      } catch (e) {
        console.error('Polling error:', e);
        stopPolling();
      }
    };

    poll();
  }

  function stopPolling() {
    isPolling.value = false;
  }

  /**
   * Initialize global progress listeners for push updates from backend
   */
  function initProgressListeners() {
    // Listen for progress events from backend via evaluate_js
    window.addEventListener('task-progress', ((event: CustomEvent) => {
      const detail = event.detail;
      if (currentTask.value && detail.taskId === currentTask.value) {
        taskStatus.value = {
          ...taskStatus.value,
          taskId: detail.taskId,
          status: detail.status,
          progress: detail.progress,
          current: detail.current,
          total: detail.total,
          error: undefined
        } as TaskStatus;
      }
    }) as EventListener);

    window.addEventListener('task-complete', ((event: CustomEvent) => {
      const detail = event.detail;
      if (currentTask.value && detail.taskId === currentTask.value) {
        taskStatus.value = {
          ...taskStatus.value,
          taskId: detail.taskId,
          status: detail.success ? 'completed' : 'failed',
          progress: detail.success ? 100 : (taskStatus.value?.progress ?? 0),
          error: detail.error,
          processing_time: detail.processing_time
        } as TaskStatus;

        // Store processing time in step params (in memory only, not saved to config)
        if (detail.success && detail.processing_time) {
          const step = taskStatus.value?.step;
          if (step === 1) {
            s1Params.value.processing_time = detail.processing_time;
          } else if (step === 2) {
            s2Params.value.processing_time = detail.processing_time;
          } else if (step === 3) {
            s3Params.value.processing_time = detail.processing_time;
          }
        }

        // Refresh project to get updated step status
        const projectStore = useProjectStore();
        if (projectStore.currentProject) {
          projectStore.loadProject(projectStore.currentProject.id);
        }

        stopPolling();
      }
    }) as EventListener);

    window.addEventListener('model-status', ((event: CustomEvent<ModelStatus>) => {
      const detail = event.detail;
      if (detail.model === s2Params.value.model) {
        modelStatus.value = detail;
      }
    }) as EventListener);
  }

  async function cancelProcessing() {
    if (currentTask.value) {
      try {
        await api.process.cancelTask(currentTask.value);
        stopPolling();
        currentTask.value = null;
        taskStatus.value = null;
      } catch (e) {
        console.error('Failed to cancel task:', e);
      }
    }
  }

  async function preloadModel(model: string = 'u2net') {
    try {
      modelStatus.value = await api.process.getModelStatus(model);
      if (modelStatus.value.phase === 'ready' || modelStatus.value.phase === 'failed') return;
      modelStatus.value = await api.process.preloadModel(model);
    } catch (e) {
      console.error('Failed to trigger preload:', e);
      modelStatus.value = {
        model,
        phase: 'failed',
        downloaded_bytes: null,
        total_bytes: null,
        error: { code: 'MODEL_INITIALIZATION_FAILED', message: 'Model initialization failed' },
      };
    }
  }

  async function retryModel(source?: 'modelscope' | 'github') {
    try {
      modelStatus.value = await api.process.retryModel('u2net', source);
    } catch (e) {
      console.error('Failed to prepare model:', e);
      modelStatus.value = { ...modelStatus.value, phase: 'failed', error: { code: 'MODEL_DOWNLOAD_FAILED', message: 'Model preparation failed' } };
    }
  }

  return {
    // State
    currentStep,
    maxStep,
    s1Params,
    s2Params,
    s3Params,
    currentTask,
    taskStatus,
    isPolling,
    modelStatus,
    // Getters
    canGoNext,
    canGoPrev,
    isProcessing,
    progress,
    stepStatus,
    // Actions
    setCurrentStep,
    goToStep,
    nextStep,
    prevStep,
    loadStepParams,
    applyStepParams,
    startProcessing,
    observeAgentTask,
    startPolling,
    stopPolling,
    cancelProcessing,
    initProgressListeners,
    preloadModel,
    retryModel,
  };
});
