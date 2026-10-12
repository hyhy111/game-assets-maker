import type {
  SeedreamBatch,
  SeedreamBatchStatus,
  SeedreamCreateRequest,
  SeedreamModel,
  SeedreamModelRef,
  SeedreamRatio,
  SeedreamResolution,
} from '@/types';
export const MODEL_RESOLUTIONS: Record<SeedreamModel, SeedreamResolution[]> = {
  pro: ['1K', '1.5K', '2K'],
  flash: ['1K', '1.5K', '2K'],
};

export const ALLOWED_RATIOS: SeedreamRatio[] = ['1:1', '16:9', '9:16', '4:3', '3:4'];

// Retain retired model names for historical batches only.
export const MODEL_LABELS: Record<string, string> = {
  pro: 'Seedream 5.0 Pro',
  flash: 'Seedream 5.0 Flash',
  lite: 'Seedream 5.0 Lite',
};

export const ALLOWED_COUNTS = [1, 2, 3, 4] as const;
export const DEFAULT_COUNT = 2;

export interface CreateForm {
  prompt: string;
  /** 直连模式是本地短键；平台源是能力清单下发的上游 ID */
  model: SeedreamModelRef;
  resolution: SeedreamResolution;
  ratio: SeedreamRatio;
  count: number;
  reference_image: string;
}

export function defaultForm(defaultCount: number = DEFAULT_COUNT): CreateForm {
  return { prompt: '', model: 'pro', resolution: '1K', ratio: '16:9', count: defaultCount, reference_image: '' };
}

/** 本地预设表只覆盖直连短键；平台源下返回空数组表示"本地不管"。 */
export function localModelResolutions(model: string): SeedreamResolution[] {
  return MODEL_RESOLUTIONS[model as SeedreamModel] ?? [];
}

export function correctResolution(model: SeedreamModelRef, resolution: SeedreamResolution): SeedreamResolution {
  const allowed = localModelResolutions(model);
  if (!allowed.length) return resolution;
  return allowed.includes(resolution) ? resolution : allowed[0];
}

/** 模型展示名：认识的用本地文案，不认识的（运营新上的）直接显示上游 ID。 */
export function modelLabel(model: string): string {
  return MODEL_LABELS[model as SeedreamModel] ?? model;
}

export function createRequest(form: CreateForm): SeedreamCreateRequest {
  return {
    prompt: form.prompt.trim(),
    model: form.model,
    resolution: form.resolution,
    ratio: form.ratio,
    count: form.count,
    reference_image: form.reference_image || null,
  };
}

const CJK_REGEX = /[㐀-鿿\u{20000}-\u{2ebef}]/u;

export function promptCount(prompt: string) {
  const trimmed = prompt.trim();
  const chinese = CJK_REGEX.test(trimmed);
  return {
    chinese,
    count: chinese ? [...trimmed].length : (trimmed.match(/\S+/g) ?? []).length,
    limit: chinese ? 300 : 600,
  };
}

export function isPromptOverLimit(prompt: string): boolean {
  const info = promptCount(prompt);
  return info.count > info.limit;
}

const ACTIVE_ATTEMPT_STATUSES = new Set(['queued', 'generating', 'downloading']);

export function batchStatus(batch: SeedreamBatch): SeedreamBatchStatus {
  if (batch.status) return batch.status;
  // Fallback aggregation for backwards compatibility.
  const attempts = batch.attempts;
  if (!attempts.length) return 'generating';
  const statuses = attempts.map((a) => a.status);
  if (statuses.some((s) => ACTIVE_ATTEMPT_STATUSES.has(s))) return 'generating';
  if (statuses.every((s) => s === 'succeeded')) return 'completed';
  const hasSuccess = statuses.some((s) => s === 'succeeded');
  if (hasSuccess) return 'partially_complete';
  const hasUnknown = statuses.some((s) => s === 'unknown');
  return hasUnknown ? 'unknown' : 'failed';
}

export function isBatchActive(batch: SeedreamBatch): boolean {
  return batchStatus(batch) === 'generating';
}

export function isBatchDeletable(batch: SeedreamBatch): boolean {
  return !isBatchActive(batch);
}

export function formatElapsed(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds || 0));
  const minutes = Math.floor(total / 60);
  const secondsPart = total % 60;
  const part = (value: number) => String(value).padStart(2, '0');
  return minutes >= 60
    ? `${part(Math.floor(minutes / 60))}:${part(minutes % 60)}:${part(secondsPart)}`
    : `${part(minutes)}:${part(secondsPart)}`;
}

const CIRCLED_NUMBERS = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳';

/**
 * Compute a stable circle sequence number for batches with identical submit
 * parameters (prompt+model+resolution+ratio+count). Batches with different
 * parameters do not participate in the same sequence. The backend also
 * provides this in `list_batches`; this helper is a frontend fallback for
 * real-time event updates that don't carry the sequence field.
 */
export function batchSignature(batch: SeedreamBatch): string {
  const r = batch.request;
  return JSON.stringify([r.prompt, r.model, r.resolution, r.ratio, r.count]);
}

export function duplicateBatchSequence(batch: SeedreamBatch, batches: SeedreamBatch[]): string {
  // Prefer the backend-provided sequence when available.
  if (batch.sequence) return batch.sequence;
  const signature = batchSignature(batch);
  const duplicates = batches
    .filter((candidate) => batchSignature(candidate) === signature)
    .sort((left, right) => (
      left.created_at === right.created_at
        ? left.local_id.localeCompare(right.local_id)
        : left.created_at.localeCompare(right.created_at)
    ));
  if (duplicates.length < 2) return '';
  const sequence = duplicates.findIndex((candidate) => candidate.local_id === batch.local_id) + 1;
  return sequence >= 1 && sequence <= CIRCLED_NUMBERS.length
    ? CIRCLED_NUMBERS[sequence - 1]
    : `(${sequence})`;
}
