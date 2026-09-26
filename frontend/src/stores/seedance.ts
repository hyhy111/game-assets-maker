import { defineStore } from 'pinia';
import { ref } from 'vue';
import { api } from '@/api';
import { SeedanceAsyncGuard, mergeTaskSnapshot, reconcileCurrentTask } from './seedance-async-state';
import type {
  SeedanceApiError,
  SeedanceCacheCleanResult,
  SeedanceCacheInfo,
  SeedanceCreateRequest,
  SeedanceDataResult,
  SeedanceHandoffResult,
  SeedanceRegenerationDraft,
  SeedanceSettings,
  SeedanceSettingsUpdate,
  SeedanceTask,
  SeedanceTaskLoadResult,
  SeedanceTaskResult,
} from '@/types';

let removeTaskUpdateListener: (() => void) | null = null;

function normalizeError(error: unknown): SeedanceApiError {
  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error) {
    const candidate = error as Partial<SeedanceApiError>;
    if (typeof candidate.code === 'string' && typeof candidate.message === 'string') {
      return {
        ...candidate,
        code: candidate.code,
        message: candidate.message,
        field: typeof candidate.field === 'string' ? candidate.field : null,
      };
    }
  }

  return {
    code: 'REQUEST_FAILED',
    message: error instanceof Error ? error.message : 'Unable to complete the Seedance request',
    field: null,
  };
}

export const useSeedanceStore = defineStore('seedance', () => {
  const tasks = ref<SeedanceTask[]>([]);
  const currentTask = ref<SeedanceTask | null>(null);
  const settings = ref<SeedanceSettings | null>(null);
  const creatingTask = ref(false);
  const cacheStatus = ref<SeedanceCacheInfo | null>(null);
  const loading = ref(false);
  const error = ref<SeedanceApiError | null>(null);

  let pendingRequests = 0;
  const asyncGuard = new SeedanceAsyncGuard();
  const taskRevisions = new Map<string, number>();

  function beginLoading() {
    pendingRequests += 1;
    loading.value = true;
  }

  function endLoading() {
    pendingRequests = Math.max(0, pendingRequests - 1);
    loading.value = pendingRequests > 0;
  }

  function beginOperation(resource: Parameters<SeedanceAsyncGuard['begin']>[0]) {
    const ticket = asyncGuard.begin(resource);
    error.value = null;
    beginLoading();
    return ticket;
  }

  function setOperationError(ticket: ReturnType<SeedanceAsyncGuard['begin']>, value: unknown) {
    if (asyncGuard.isLatestOperation(ticket)) error.value = normalizeError(value);
  }

  function incrementTaskRevision(localId: string) {
    taskRevisions.set(localId, (taskRevisions.get(localId) ?? 0) + 1);
  }

  function upsertTask(task: SeedanceTask) {
    incrementTaskRevision(task.local_id);
    const index = tasks.value.findIndex((item) => item.local_id === task.local_id);
    if (index === -1) {
      tasks.value.push(task);
    } else {
      tasks.value[index] = task;
    }
    tasks.value.sort((left, right) => {
      if (left.created_at !== right.created_at) return right.created_at.localeCompare(left.created_at);
      return right.local_id.localeCompare(left.local_id);
    });

    if (currentTask.value?.local_id === task.local_id) {
      currentTask.value = task;
    }
  }

  function useTaskResult(ticket: ReturnType<SeedanceAsyncGuard['begin']>, result: SeedanceTaskResult): SeedanceTask | null {
    if (!result.success) {
      setOperationError(ticket, result.error);
      return null;
    }
    upsertTask(result.task);
    return result.task;
  }

  function useDataResult<T>(ticket: ReturnType<SeedanceAsyncGuard['begin']>, result: SeedanceDataResult<T>): T | null {
    if (!result.success) {
      setOperationError(ticket, result.error);
      return null;
    }
    return result.data;
  }

  async function selectImageFile(): Promise<{ path: string; previewUrl: string } | null> {
    const ticket = beginOperation('image-selection');
    try {
      const path = await api.seedance.selectImageFile();
      if (!path) return null;
      const thumbnail = await api.frame.getFrameThumbnail(path, 320);
      return { path, previewUrl: `data:image/png;base64,${thumbnail}` };
    } catch (caught) {
      setOperationError(ticket, caught);
      return null;
    } finally {
      endLoading();
    }
  }

  async function createTask(request: SeedanceCreateRequest): Promise<SeedanceTask | null> {
    if (creatingTask.value) return null;
    creatingTask.value = true;
    const ticket = beginOperation('task-action');
    try {
      const result = await api.seedance.createTask(request);
      if (!asyncGuard.isResourceCurrent(ticket)) return null;
      const task = useTaskResult(ticket, result);
      if (task) currentTask.value = task;
      return task;
    } catch (caught) {
      setOperationError(ticket, caught);
      return null;
    } finally {
      endLoading();
      creatingTask.value = false;
    }
  }

  async function saveVideo(localId: string): Promise<boolean> {
    const ticket = beginOperation('task-action');
    try {
      const result = await api.seedance.saveVideo(localId);
      if (!asyncGuard.isResourceCurrent(ticket)) return false;
      return useDataResult(ticket, result)?.saved === true;
    } catch (caught) {
      setOperationError(ticket, caught);
      return false;
    } finally {
      endLoading();
    }
  }

  async function validateRequest(request: SeedanceCreateRequest): Promise<boolean> {
    const ticket = beginOperation('task-action');
    try {
      const result = await api.seedance.validateRequest(request);
      if (!asyncGuard.isResourceCurrent(ticket)) return false;
      return useDataResult(ticket, result)?.valid === true;
    } catch (caught) {
      setOperationError(ticket, caught);
      return false;
    } finally {
      endLoading();
    }
  }

  async function loadTasks(): Promise<SeedanceTask[]> {
    const ticket = beginOperation('tasks');
    const snapshotRevisions = new Map(taskRevisions);
    try {
      const result = await api.seedance.listTasks();
      if (!result.success) {
        setOperationError(ticket, result.error);
        return tasks.value;
      }
      if (asyncGuard.isResourceCurrent(ticket)) {
        const mergedTasks = mergeTaskSnapshot(result.tasks, tasks.value, snapshotRevisions, taskRevisions);
        tasks.value = mergedTasks;
        currentTask.value = reconcileCurrentTask(currentTask.value, mergedTasks, snapshotRevisions, taskRevisions);
      }
      return tasks.value;
    } catch (caught) {
      setOperationError(ticket, caught);
      return tasks.value;
    } finally {
      endLoading();
    }
  }

  async function loadTask(localId: string): Promise<SeedanceTaskLoadResult> {
    const ticket = beginOperation('task-detail');
    try {
      const result = await api.seedance.getTask(localId);
      if (!asyncGuard.isResourceCurrent(ticket)) return { stale: true };
      const task = useTaskResult(ticket, result);
      if (task) currentTask.value = task;
      return task;
    } catch (caught) {
      if (!asyncGuard.isResourceCurrent(ticket)) return { stale: true };
      setOperationError(ticket, caught);
      return null;
    } finally {
      endLoading();
    }
  }

  async function loadRegenerationDraft(localId: string): Promise<SeedanceRegenerationDraft | null> {
    const ticket = beginOperation('task-detail');
    try {
      const result = await api.seedance.getRegenerationDraft(localId);
      if (!asyncGuard.isResourceCurrent(ticket)) return null;
      return useDataResult(ticket, result);
    } catch (caught) {
      setOperationError(ticket, caught);
      return null;
    } finally {
      endLoading();
    }
  }

  async function loadContinuationDraft(localId: string): Promise<SeedanceRegenerationDraft | null> {
    const ticket = beginOperation('task-detail');
    try {
      const result = await api.seedance.getContinuationDraft(localId);
      if (!asyncGuard.isResourceCurrent(ticket)) return null;
      return useDataResult(ticket, result);
    } catch (caught) {
      setOperationError(ticket, caught);
      return null;
    } finally {
      endLoading();
    }
  }

  async function cancelTask(localId: string): Promise<SeedanceTask | null> {
    return runTaskAction(() => api.seedance.cancelTask(localId));
  }

  async function retryTask(localId: string): Promise<SeedanceTask | null> {
    return runTaskAction(() => api.seedance.retryTask(localId));
  }

  async function retryDownload(localId: string): Promise<SeedanceTask | null> {
    return runTaskAction(() => api.seedance.retryDownload(localId));
  }

  async function continueTask(localId: string): Promise<SeedanceTask | null> {
    return runTaskAction(() => api.seedance.continueTask(localId));
  }

  async function runTaskAction(action: () => Promise<SeedanceTaskResult>): Promise<SeedanceTask | null> {
    const ticket = beginOperation('task-action');
    try {
      const result = await action();
      if (!asyncGuard.isResourceCurrent(ticket)) return null;
      return useTaskResult(ticket, result);
    } catch (caught) {
      setOperationError(ticket, caught);
      return null;
    } finally {
      endLoading();
    }
  }

  async function deleteTask(localId: string, allowProtected: boolean = false): Promise<boolean> {
    const ticket = beginOperation('task-action');
    try {
      const result = await api.seedance.deleteTask(localId, allowProtected);
      if (!asyncGuard.isResourceCurrent(ticket)) return false;
      if (!result.success) {
        setOperationError(ticket, result.error);
        return false;
      }
      incrementTaskRevision(localId);
      tasks.value = tasks.value.filter((task) => task.local_id !== localId);
      if (currentTask.value?.local_id === localId) currentTask.value = null;
      return true;
    } catch (caught) {
      setOperationError(ticket, caught);
      return false;
    } finally {
      endLoading();
    }
  }

  async function handoff(localId: string, role: string, action: string): Promise<SeedanceHandoffResult | null> {
    const ticket = beginOperation('task-action');
    try {
      const result = await api.seedance.handoff(localId, role, action);
      if (!asyncGuard.isResourceCurrent(ticket)) return null;
      if (!result.success) {
        setOperationError(ticket, result.error);
        return null;
      }
      upsertTask(result.task);
      currentTask.value = result.task;
      return result;
    } catch (caught) {
      setOperationError(ticket, caught);
      return null;
    } finally {
      endLoading();
    }
  }

  async function loadSettings(): Promise<boolean> {
    const ticket = beginOperation('settings');
    try {
      const result = await api.seedance.getSettings();
      if (!asyncGuard.isResourceCurrent(ticket)) return false;
      settings.value = result;
      return true;
    } catch (caught) {
      setOperationError(ticket, caught);
      return false;
    } finally {
      endLoading();
    }
  }

  async function saveSettings(update: SeedanceSettingsUpdate): Promise<SeedanceSettings | null> {
    const ticket = beginOperation('settings');
    try {
      const result = await api.seedance.saveSettings(update);
      if (!asyncGuard.isResourceCurrent(ticket)) return null;
      if (!result.success) {
        setOperationError(ticket, result.error);
        return null;
      }
      settings.value = result.settings;
      return result.settings;
    } catch (caught) {
      setOperationError(ticket, caught);
      return null;
    } finally {
      endLoading();
    }
  }

  async function testConnection(apiKey?: string): Promise<boolean> {
    const ticket = beginOperation('connection');
    try {
      const result = await api.seedance.testConnection(apiKey);
      if (!asyncGuard.isResourceCurrent(ticket)) return false;
      return result.success && result.data.configured === true;
    } catch {
      return false;
    } finally {
      endLoading();
    }
  }

  async function loadCacheStatus(): Promise<SeedanceCacheInfo | null> {
    const ticket = beginOperation('cache');
    try {
      const result = await api.seedance.getCacheStatus();
      if (!asyncGuard.isResourceCurrent(ticket)) return null;
      const status = useDataResult(ticket, result);
      if (status) cacheStatus.value = status;
      return status;
    } catch (caught) {
      setOperationError(ticket, caught);
      return null;
    } finally {
      endLoading();
    }
  }

  async function cleanCache(olderThanDays?: number): Promise<SeedanceCacheCleanResult | null> {
    const ticket = beginOperation('cache');
    try {
      const response = await api.seedance.cleanCache(olderThanDays);
      if (!asyncGuard.isResourceCurrent(ticket)) return null;
      const result = useDataResult(ticket, response);
      if (result && asyncGuard.isResourceCurrent(ticket)) await loadCacheStatus();
      return result;
    } catch (caught) {
      setOperationError(ticket, caught);
      return null;
    } finally {
      endLoading();
    }
  }

  function initEventListeners(): () => void {
    if (removeTaskUpdateListener) return removeTaskUpdateListener;

    const handleTaskUpdate = (event: Event) => {
      const task = (event as CustomEvent<unknown>).detail;
      if (typeof task === 'object' && task !== null && typeof (task as SeedanceTask).local_id === 'string') {
        upsertTask(task as SeedanceTask);
      }
    };

    window.addEventListener('seedance-task-updated', handleTaskUpdate);
    removeTaskUpdateListener = () => {
      window.removeEventListener('seedance-task-updated', handleTaskUpdate);
      removeTaskUpdateListener = null;
    };
    return removeTaskUpdateListener;
  }

  return {
    tasks,
    currentTask,
    settings,
    creatingTask,
    cacheStatus,
    loading,
    error,
    upsertTask,
    selectImageFile,
    saveVideo,
    createTask,
    validateRequest,
    loadTasks,
    loadTask,
    loadRegenerationDraft,
    loadContinuationDraft,
    cancelTask,
    retryTask,
    retryDownload,
    continueTask,
    deleteTask,
    handoff,
    loadSettings,
    saveSettings,
    testConnection,
    loadCacheStatus,
    cleanCache,
    initEventListeners,
  };
});

const hot = (import.meta as ImportMeta & {
  hot?: { dispose(callback: () => void): void };
}).hot;

if (hot) {
  hot.dispose(() => removeTaskUpdateListener?.());
}
