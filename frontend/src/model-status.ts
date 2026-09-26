import type { ModelStatus } from './types';

export interface ModelStatusPresentation {
  messageKey: string;
  busy: boolean;
  retryable: boolean;
  tone: 'info' | 'success' | 'danger';
}

const PRESENTATION: Record<ModelStatus['phase'], ModelStatusPresentation> = {
  needs_download: {
    messageKey: 'modelStatus.needsDownload',
    busy: false,
    retryable: false,
    tone: 'info',
  },
  downloading: {
    messageKey: 'modelStatus.downloading',
    busy: true,
    retryable: false,
    tone: 'info',
  },
  initializing: {
    messageKey: 'modelStatus.initializing',
    busy: true,
    retryable: false,
    tone: 'info',
  },
  ready: {
    messageKey: 'modelStatus.ready',
    busy: false,
    retryable: false,
    tone: 'success',
  },
  failed: {
    messageKey: 'modelStatus.failed',
    busy: false,
    retryable: true,
    tone: 'danger',
  },
};

const APPROXIMATE_MODEL_SIZE_MB: Record<string, number> = {
  u2net: 176,
};

export function modelStatusPresentation(status: ModelStatus): ModelStatusPresentation {
  return PRESENTATION[status.phase];
}

export function modelProgressPercent(status: ModelStatus): number | null {
  if (
    status.phase !== 'downloading'
    || status.downloaded_bytes === null
    || status.total_bytes === null
    || status.total_bytes <= 0
  ) {
    return null;
  }
  return Math.max(0, Math.min(100, Math.round((status.downloaded_bytes / status.total_bytes) * 100)));
}

export function modelApproximateSizeMb(model: string): number | null {
  return APPROXIMATE_MODEL_SIZE_MB[model] ?? null;
}

export function canStartStep2(step1Completed: boolean, status: ModelStatus, selectedModel: string): boolean {
  return step1Completed && status.model === selectedModel && status.phase === 'ready';
}
