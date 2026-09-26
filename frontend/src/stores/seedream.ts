import { defineStore } from 'pinia';
import { ref } from 'vue';
import { api } from '@/api';
import type {
  GenerationLayout,
  SeedreamApiError,
  SeedreamBatch,
  SeedreamCreateRequest,
  SeedreamEraserResult,
  SeedreamRegenerationDraft,
  SeedreamSettings,
} from '@/types';

let removeBatchUpdateListener: (() => void) | null = null;

function normalizeError(error: unknown): SeedreamApiError {
  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error) {
    const candidate = error as Partial<SeedreamApiError>;
    if (typeof candidate.code === 'string' && typeof candidate.message === 'string') {
      return {
        code: candidate.code,
        message: candidate.message,
        field: typeof candidate.field === 'string' ? candidate.field : null,
      };
    }
  }
  return {
    code: 'REQUEST_FAILED',
    message: error instanceof Error ? error.message : 'Unable to complete the Seedream request',
    field: null,
  };
}

/**
 * Merge per-attempt state so an older full-batch snapshot does not overwrite a
 * newer per-attempt update that arrived via a real-time event. Each attempt is
 * compared by its `updated_at` timestamp; the newer one wins.
 */
function mergeBatchAttempts(incoming: SeedreamBatch, current: SeedreamBatch | undefined): SeedreamBatch {
  if (!current || current.local_id !== incoming.local_id) return incoming;
  if (incoming.attempts.length !== current.attempts.length) return incoming;
  const mergedAttempts = incoming.attempts.map((incomingAttempt, index) => {
    const currentAttempt = current.attempts[index];
    if (!currentAttempt) return incomingAttempt;
    if (incomingAttempt.updated_at >= currentAttempt.updated_at) return incomingAttempt;
    return currentAttempt;
  });
  const newerBatch = incoming.updated_at >= current.updated_at ? incoming : current;
  // Preserve the sequence number: real-time events carry "" (the backend only
  // computes it in list_batches), so keep the non-empty value from either side.
  const sequence = incoming.sequence || current.sequence || '';
  return { ...newerBatch, attempts: mergedAttempts, sequence };
}

export const useSeedreamStore = defineStore('seedream', () => {
  const batches = ref<SeedreamBatch[]>([]);
  const currentBatch = ref<SeedreamBatch | null>(null);
  const settings = ref<SeedreamSettings | null>(null);
  const creatingBatch = ref(false);
  const loading = ref(false);
  const error = ref<SeedreamApiError | null>(null);

  let pendingRequests = 0;

  function beginLoading() {
    pendingRequests += 1;
    loading.value = true;
  }

  function endLoading() {
    pendingRequests = Math.max(0, pendingRequests - 1);
    loading.value = pendingRequests > 0;
  }

  function setError(value: unknown) {
    error.value = value ? normalizeError(value) : null;
  }

  function upsertBatch(batch: SeedreamBatch) {
    const index = batches.value.findIndex((item) => item.local_id === batch.local_id);
    if (index === -1) {
      batches.value.unshift(batch);
    } else {
      const existing = batches.value[index];
      const merged = mergeBatchAttempts(batch, existing);
      batches.value[index] = merged;
    }
    batches.value.sort((left, right) => right.created_at.localeCompare(left.created_at));
    if (currentBatch.value?.local_id === batch.local_id) {
      const existing = currentBatch.value;
      currentBatch.value = mergeBatchAttempts(batch, existing);
    }
  }

  async function createBatch(request: SeedreamCreateRequest): Promise<SeedreamBatch | null> {
    if (creatingBatch.value) return null;
    creatingBatch.value = true;
    beginLoading();
    try {
      const result = await api.seedream.createBatch(request);
      if (!result.success) {
        setError(result.error);
        return null;
      }
      upsertBatch(result.batch);
      currentBatch.value = result.batch;
      return result.batch;
    } catch (caught) {
      setError(caught);
      return null;
    } finally {
      endLoading();
      creatingBatch.value = false;
    }
  }

  async function selectReferenceImage(): Promise<{ path: string; previewUrl: string } | null> {
    beginLoading();
    try {
      const path = await api.seedream.selectImageFile();
      if (!path) return null;
      const thumbnail = await api.frame.getFrameThumbnail(path, 320);
      return { path, previewUrl: `data:image/png;base64,${thumbnail}` };
    } catch (caught) {
      setError(caught);
      return null;
    } finally {
      endLoading();
    }
  }

  async function loadBatch(localId: string): Promise<SeedreamBatch | null> {
    beginLoading();
    try {
      const result = await api.seedream.getBatch(localId);
      if (!result.success) {
        setError(result.error);
        return null;
      }
      upsertBatch(result.batch);
      if (currentBatch.value?.local_id === localId) {
        currentBatch.value = mergeBatchAttempts(result.batch, currentBatch.value);
      }
      return result.batch;
    } catch (caught) {
      setError(caught);
      return null;
    } finally {
      endLoading();
    }
  }

  async function loadBatches(): Promise<SeedreamBatch[]> {
    beginLoading();
    try {
      const result = await api.seedream.listBatches();
      if (!result.success) {
        setError(result.error);
        return batches.value;
      }
      batches.value = result.batches.sort((left, right) => right.created_at.localeCompare(left.created_at));
      return batches.value;
    } catch (caught) {
      setError(caught);
      return batches.value;
    } finally {
      endLoading();
    }
  }

  async function saveImage(localId: string, attemptIndex: number): Promise<boolean> {
    beginLoading();
    try {
      const result = await api.seedream.saveImage(localId, attemptIndex);
      if (!result.success) {
        setError(result.error);
        return false;
      }
      return result.data.saved === true;
    } catch (caught) {
      setError(caught);
      return false;
    } finally {
      endLoading();
    }
  }

  async function resizeCharacter(
    localId: string,
    attemptIndex: number,
    top: number,
    bottom: number,
    targetHeight: number,
    bottomDistance: number
  ): Promise<boolean> {
    beginLoading();
    try {
      const result = await api.seedream.resizeCharacter(
        localId, attemptIndex, top, bottom, targetHeight, bottomDistance
      );
      if (!result.success) {
        setError(result.error);
        return false;
      }
      setError(null);
      return true;
    } catch (caught) {
      setError(caught);
      return false;
    } finally {
      endLoading();
    }
  }

  async function restoreCharacter(localId: string, attemptIndex: number): Promise<boolean> {
    beginLoading();
    try {
      const result = await api.seedream.restoreCharacter(localId, attemptIndex);
      if (!result.success) {
        setError(result.error);
        return false;
      }
      setError(null);
      return result.data.restored;
    } catch (caught) {
      setError(caught);
      return false;
    } finally {
      endLoading();
    }
  }

  async function applyEraser(
    localId: string,
    attemptIndex: number,
    imageDataUrl: string,
    editSourceDataUrl: string,
    generationLayout: GenerationLayout | null
  ): Promise<SeedreamEraserResult | null> {
    beginLoading();
    try {
      const result = await api.seedream.applyEraser(
        localId, attemptIndex, imageDataUrl, editSourceDataUrl, generationLayout
      );
      if (!result.success) {
        setError(result.error);
        return null;
      }
      setError(null);
      return result.data;
    } catch (caught) {
      setError(caught);
      return null;
    } finally {
      endLoading();
    }
  }

  async function deleteBatch(localId: string): Promise<boolean> {
    beginLoading();
    try {
      const result = await api.seedream.deleteBatch(localId);
      if (!result.success) {
        setError(result.error);
        return false;
      }
      batches.value = batches.value.filter((batch) => batch.local_id !== localId);
      if (currentBatch.value?.local_id === localId) currentBatch.value = null;
      return true;
    } catch (caught) {
      setError(caught);
      return false;
    } finally {
      endLoading();
    }
  }

  async function retryDownload(localId: string, attemptIndex: number): Promise<boolean> {
    beginLoading();
    try {
      const result = await api.seedream.retryDownload(localId, attemptIndex);
      if (!result.success) {
        setError(result.error);
        return false;
      }
      upsertBatch(result.batch);
      if (currentBatch.value?.local_id === localId) {
        currentBatch.value = mergeBatchAttempts(result.batch, currentBatch.value);
      }
      return true;
    } catch (caught) {
      setError(caught);
      return false;
    } finally {
      endLoading();
    }
  }

  async function loadSettings(): Promise<void> {
    beginLoading();
    try {
      const result = await api.seedream.getSettings();
      if (result.success) {
        settings.value = result.settings;
        setError(null);
      } else {
        setError(result.error);
      }
    } catch (caught) {
      setError(caught);
    } finally {
      endLoading();
    }
  }

  async function loadRegenerationDraft(localId: string): Promise<SeedreamRegenerationDraft | null> {
    beginLoading();
    try {
      const result = await api.seedream.getRegenerationDraft(localId);
      if (!result.success) {
        setError(result.error);
        return null;
      }
      return result.data;
    } catch (caught) {
      setError(caught);
      return null;
    } finally {
      endLoading();
    }
  }

  async function saveSettings(update: SeedreamSettings): Promise<boolean> {
    beginLoading();
    try {
      const result = await api.seedream.saveSettings(update);
      if (!result.success) {
        setError(result.error);
        return false;
      }
      settings.value = result.settings;
      return true;
    } catch (caught) {
      setError(caught);
      return false;
    } finally {
      endLoading();
    }
  }

  function initEventListeners(): () => void {
    if (removeBatchUpdateListener) return removeBatchUpdateListener;

    const handleBatchUpdate = (event: Event) => {
      const batch = (event as CustomEvent<unknown>).detail;
      if (typeof batch === 'object' && batch !== null && typeof (batch as SeedreamBatch).local_id === 'string') {
        upsertBatch(batch as SeedreamBatch);
      }
    };

    window.addEventListener('seedream-batch-updated', handleBatchUpdate);
    removeBatchUpdateListener = () => {
      window.removeEventListener('seedream-batch-updated', handleBatchUpdate);
      removeBatchUpdateListener = null;
    };
    return removeBatchUpdateListener;
  }

  return {
    batches,
    currentBatch,
    settings,
    creatingBatch,
    loading,
    error,
    upsertBatch,
    createBatch,
    selectReferenceImage,
    loadBatch,
    loadBatches,
    saveImage,
    resizeCharacter,
    restoreCharacter,
    applyEraser,
    deleteBatch,
    retryDownload,
    loadSettings,
    saveSettings,
    loadRegenerationDraft,
    initEventListeners,
  };
});

const hot = (import.meta as ImportMeta & {
  hot?: { dispose(callback: () => void): void };
}).hot;

if (hot) {
  hot.dispose(() => removeBatchUpdateListener?.());
}
