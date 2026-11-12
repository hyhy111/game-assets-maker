/**
 * Process Store - Manages processing workflow state
 */
import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { api } from '@/api';
import { useProjectStore } from './project';
import { usePlayerStore } from './player';
import { createNavigationGuard } from '@/utils/navigation-guard';
import type { BackgroundRemovalModel, ModelStatus, Step1Params, Step2Params, Step3Params, TaskStatus } from '@/types';
import { logEvent } from '@/debug/request-log';

export const useProcessStore = defineStore('process', () => {
  const navigation = createNavigationGuard();

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

  const step2Defaults: Step2Params = {
    model: 'u2net',
    alpha_matting: true,
    alpha_matting_erode_size: 5,
    alpha_matting_background_threshold: 120,
    alpha_matting_foreground_threshold: 240,
    fps: 10,
    processed: false,
    processing_time: 0
  };
  const s2Params = ref({ ...step2Defaults });

  const step3Defaults: Step3Params = {
    enabled: true,  // Hole punching enabled
    green_intensity: 3,  // 1=bright green, 5=dark green
    feather_radius: 3,
    min_hole_size: 5,
    edge_shrink_enabled: false,
    edge_shrink_px: 0,
    edge_feather_px: 0,
    align_enabled: false,  // Alignment disabled by default
    align_h: false,        // Horizontal centering (default off)
    align_v: false,        // Vertical bottom alignment (default off)
    use_padding: true,     // Use bottom padding
    padding_bottom: 10,    // Bottom padding pixels
    fps: 10,
    processed: false,
    processing_time: 0
  };
  const s3Params = ref({ ...step3Defaults });

  // Task tracking
  const currentTask = ref<string | null>(null);
  const taskStatus = ref<TaskStatus | null>(null);
  const isPolling = ref(false);

  const selectedModel = computed(() => s2Params.value.model ?? 'u2net');
  const modelStatuses = ref<Record<string, ModelStatus>>({});
  const modelStatus = computed<ModelStatus>(() => modelStatuses.value[selectedModel.value] ?? {
    model: selectedModel.value,
    phase: 'initializing',
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
  const isProcessing = computed(() => taskStatus.value?.status === 'running' || taskStatus.value?.status === 'pending');
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
      if (step === currentStep.value) return;
      return navigation.run(() => { currentStep.value = step; });
    }
  }

  function setCurrentStep(step: number) {
    goToStep(step);
  }

  function nextStep() {
    if (canGoNext.value) {
      return goToStep(currentStep.value + 1);
    }
  }

  function prevStep() {
    if (canGoPrev.value) {
      return goToStep(currentStep.value - 1);
    }
  }

  function applyStepParams(step: number, params: Partial<Step1Params | Step2Params | Step3Params>) {
    if (step === 1) s1Params.value = { ...s1Params.value, ...params } as Step1Params;
    else if (step === 2) s2Params.value = { ...s2Params.value, ...params } as Step2Params;
    else if (step === 3) s3Params.value = { ...s3Params.value, ...params } as Step3Params;
    else throw new Error('INVALID_STEP');
    const saved = step === 1 ? s1Params.value : step === 2 ? s2Params.value : s3Params.value;
    if (step === currentStep.value && saved.fps) usePlayerStore().setPlaybackFps(saved.fps);
  }

  async function loadStepParams(projectId: string, step: number) {
    try {
      const defaults = step === 2 ? step2Defaults : step === 3 ? step3Defaults : {};
      applyStepParams(step, { ...defaults, ...await api.process.getStepParams(projectId, step) });
      return true;
    } catch (e) {
      logEvent([`Failed to load step ${step} params:`, e].join(' '), 'error');
      return false;
    }
  }

  async function startProcessing(projectId: string, step: number, customParams?: Partial<Step1Params | Step2Params | Step3Params>) {
    if (!await navigation.check()) return;
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
      step,
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
      logEvent(['Failed to start processing:', e].join(' '), 'error');
      taskStatus.value = { success: false, task_id: '', status: 'failed', step, progress: 0, current: 0, total: 0, error: String(e) };
      return;

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
        logEvent(['Polling error:', e].join(' '), 'error');
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
          status: detail.success ? 'completed' : detail.error === 'Task cancelled' ? 'cancelled' : 'failed',
          progress: detail.success ? 100 : (taskStatus.value?.progress ?? 0),
          error: detail.error === 'Task cancelled' ? undefined : detail.error,
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
      modelStatuses.value[detail.model] = detail;
    }) as EventListener);
  }

  async function cancelProcessing() {
    if (currentTask.value) {
      try {
        await api.process.cancelTask(currentTask.value);
      } catch (e) {
        logEvent(['Failed to cancel task:', e].join(' '), 'error');
      }
    }
  }

  async function prepareModel(
    model: BackgroundRemovalModel,
    retry: boolean,
    source?: 'modelscope' | 'github',
  ) {
    const previous = modelStatuses.value[model];
    try {
      const status = retry ? await api.process.retryModel(model, source) : await api.process.preloadModel(model);
      if (modelStatuses.value[model] === previous) modelStatuses.value[model] = status;
    } catch (e) {
      logEvent(['Failed to prepare model:', e].join(' '), 'error');
      if (modelStatuses.value[model] === previous) {
        modelStatuses.value[model] = {
          model,
          phase: 'failed',
          downloaded_bytes: null,
          total_bytes: null,
          error: { code: 'MODEL_INITIALIZATION_FAILED', message: 'Model preparation failed' },
        };
      }
    }
  }

  function preloadModel(model: BackgroundRemovalModel = 'u2net') {
    return prepareModel(model, false);
  }

  function retryModel(source?: 'modelscope' | 'github') {
    return prepareModel(selectedModel.value, true, source);
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
    selectedModel,
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
    setNavigationGuard: navigation.set,
  };
});
