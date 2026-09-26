import type { SeedanceApiError, SeedanceCreateRequest, SeedanceDuration, SeedanceModel, SeedanceResolution, SeedanceTask, SeedanceTaskRequest } from '@/types';

export const MODEL_RESOLUTIONS: Record<SeedanceModel, SeedanceResolution[]> = {
  standard: ['480p', '720p', '1080p'],
  fast: ['480p', '720p'],
  mini: ['480p', '720p'],
};
export const DEFAULT_PRIORITY = 0;
export const DEFAULT_EXECUTION_EXPIRES_AFTER = 172800;
export const DOWNLOAD_URL_VALIDITY_MS = 24 * 60 * 60 * 1000;
export const DURATION_OPTIONS = [4, 5, 6] as const;
export const CREATE_REQUEST_KEYS = ['first_frame', 'last_frame', 'prompt', 'model', 'resolution', 'ratio', 'duration', 'generate_audio', 'return_last_frame', 'priority', 'execution_expires_after'] as const;

export type CreateForm = Required<Omit<SeedanceCreateRequest, 'last_frame' | 'priority' | 'execution_expires_after'>> & { last_frame: string | null };
export interface SeedanceValidationIssue {
  field: string;
  code: string;
  key: string;
}

export type CreateErrors = Partial<Record<'first_frame' | 'prompt' | 'duration' | 'body', SeedanceValidationIssue>>;

const VALIDATION_KEYS: Record<string, string> = {
  API_KEY_NOT_CONFIGURED: 'seedance.validation.apiKeyNotConfigured',
  FIRST_FRAME_REQUIRED: 'seedance.validation.firstFrameRequired',
  PROMPT_REQUIRED: 'seedance.validation.promptRequired',
  PROMPT_TOO_LONG: 'seedance.validation.promptTooLong',
  IMAGE_NOT_FOUND: 'seedance.validation.imageNotFound',
  IMAGE_TOO_LARGE: 'seedance.validation.imageTooLarge',
  INVALID_IMAGE: 'seedance.validation.invalidImage',
  UNSUPPORTED_IMAGE_FORMAT: 'seedance.validation.unsupportedImageFormat',
  INVALID_IMAGE_DIMENSIONS: 'seedance.validation.invalidImageDimensions',
  INVALID_IMAGE_ASPECT_RATIO: 'seedance.validation.invalidImageAspectRatio',
  UNSUPPORTED_MODEL: 'seedance.validation.unsupportedModel',
  UNSUPPORTED_RESOLUTION: 'seedance.validation.unsupportedResolution',
  UNSUPPORTED_RATIO: 'seedance.validation.unsupportedRatio',
  INVALID_DURATION: 'seedance.validation.invalidDuration',
  INVALID_PRIORITY: 'seedance.validation.invalidPriority',
  INVALID_EXPIRY: 'seedance.validation.invalidExpiry',
  PAYLOAD_TOO_LARGE: 'seedance.validation.payloadTooLarge',
};

const BODY_FIELDS = new Set(['payload', 'model', 'resolution', 'ratio']);

export function validationIssueForApiError(error: Pick<SeedanceApiError, 'code' | 'field'>): SeedanceValidationIssue {
  const code = typeof error.code === 'string' ? error.code : 'UNKNOWN';
  const field = error.field === 'payload' || BODY_FIELDS.has(error.field ?? '') ? 'body' : error.field || 'body';
  return { field, code, key: VALIDATION_KEYS[code] ?? 'seedance.validation.generic' };
}

export function correctResolution(model: SeedanceModel, resolution: SeedanceResolution): SeedanceResolution {
  return MODEL_RESOLUTIONS[model].includes(resolution) ? resolution : MODEL_RESOLUTIONS[model][0];
}

export function correctDuration(duration: SeedanceDuration): typeof DURATION_OPTIONS[number] {
  return DURATION_OPTIONS.includes(duration as typeof DURATION_OPTIONS[number])
    ? duration as typeof DURATION_OPTIONS[number]
    : DURATION_OPTIONS[0];
}

export function promptCount(prompt: string) {
  const trimmed = prompt.trim();
  const chinese = /[\u3400-\u9fff\u{20000}-\u{2ebef}]/u.test(trimmed);
  return { chinese, count: chinese ? [...trimmed].length : (trimmed.match(/\S+/g) ?? []).length, limit: chinese ? 500 : 1000 };
}

export function validateCreateForm(form: CreateForm): CreateErrors {
  const errors: CreateErrors = {};
  if (!form.first_frame) errors.first_frame = validationIssueForApiError({ field: 'first_frame', code: 'FIRST_FRAME_REQUIRED' });
  if (!form.prompt.trim()) errors.prompt = validationIssueForApiError({ field: 'prompt', code: 'PROMPT_REQUIRED' });
  if (form.duration !== -1 && (!Number.isInteger(form.duration) || form.duration < 4 || form.duration > 15)) errors.duration = validationIssueForApiError({ field: 'duration', code: 'INVALID_DURATION' });
  if (!MODEL_RESOLUTIONS[form.model].includes(form.resolution)) errors.body = validationIssueForApiError({ field: 'resolution', code: 'UNSUPPORTED_RESOLUTION' });
  return errors;
}

export function createRequest(form: CreateForm): SeedanceCreateRequest {
  return {
    first_frame: form.first_frame,
    last_frame: form.last_frame || null,
    prompt: form.prompt.trim(),
    model: form.model,
    resolution: form.resolution,
    ratio: form.ratio,
    duration: form.duration,
    generate_audio: form.generate_audio,
    return_last_frame: form.return_last_frame,
    priority: DEFAULT_PRIORITY,
    execution_expires_after: DEFAULT_EXECUTION_EXPIRES_AFTER,
  };
}

export function formatElapsed(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds || 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secondsPart = total % 60;
  const part = (value: number) => String(value).padStart(2, '0');
  return hours ? `${part(hours)}:${part(minutes)}:${part(secondsPart)}` : `${part(minutes)}:${part(secondsPart)}`;
}

export function hasMedia(task: SeedanceTask): boolean {
  return task.cache_status === 'complete' && task.download_status === 'downloaded';
}

export type SeedanceTaskPhase =
  | 'submitting'
  | 'queued'
  | 'running'
  | 'cancelling'
  | 'downloading'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'expired'
  | 'cleared';

export type SeedanceTaskAction =
  | 'cancel'
  | 'view'
  | 'continue'
  | 'regenerate'
  | 'retry-generation'
  | 'retry-download'
  | 'delete';

export function seedanceTaskPhase(task: SeedanceTask): SeedanceTaskPhase {
  if (task.cache_status === 'cleared') return 'cleared';
  if (task.download_status === 'downloading') return 'downloading';
  if (task.remote_status === 'succeeded' && task.download_status === 'downloaded') return 'succeeded';
  if (
    task.remote_status === 'submission_unknown'
    || task.remote_status === 'failed'
    || task.download_status === 'failed'
  ) {
    return 'failed';
  }
  if (task.remote_status === 'succeeded') return 'downloading';
  return task.remote_status;
}

export function downloadUrlMayBeExpired(task: SeedanceTask, now: number = Date.now()): boolean {
  if (!task.download_url_received_at) return false;
  const receivedAt = Date.parse(task.download_url_received_at);
  return Number.isFinite(receivedAt) && now - receivedAt >= DOWNLOAD_URL_VALIDITY_MS;
}

export function seedanceTaskActions(task: SeedanceTask): SeedanceTaskAction[] {
  const actions: SeedanceTaskAction[] = [];
  if (task.remote_status === 'queued') actions.push('cancel');
  if (task.remote_status === 'succeeded' && hasMedia(task)) actions.push('view');
  if (
    task.remote_status === 'succeeded'
    && hasMedia(task)
    && task.output_urls.returned_last_frame
  ) {
    actions.push('continue');
  }
  if (task.remote_status === 'failed') actions.push('retry-generation');
  if (task.download_status === 'failed') actions.push('retry-download');
  if (task.cache_status === 'complete') actions.push('regenerate');
  if (task.remote_status !== 'queued') actions.push('delete');
  return actions;
}

const TASK_REQUEST_KEYS: (keyof SeedanceTaskRequest)[] = [
  'prompt',
  'model',
  'resolution',
  'ratio',
  'duration',
  'generate_audio',
  'return_last_frame',
  'priority',
  'execution_expires_after',
];

export function taskRequestSignature(task: SeedanceTask): string {
  return JSON.stringify(TASK_REQUEST_KEYS.map((key) => task.request[key]));
}

export function duplicateTaskSequence(task: SeedanceTask, tasks: SeedanceTask[]): string {
  const signature = taskRequestSignature(task);
  const duplicates = tasks
    .filter((candidate) => taskRequestSignature(candidate) === signature)
    .sort((left, right) => (
      left.created_at === right.created_at
        ? left.local_id.localeCompare(right.local_id)
        : left.created_at.localeCompare(right.created_at)
    ));
  if (duplicates.length < 2) return '';
  const sequence = duplicates.findIndex((candidate) => candidate.local_id === task.local_id) + 1;
  const circled = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳';
  return sequence >= 1 && sequence <= circled.length ? circled[sequence - 1] : `(${sequence})`;
}

export function taskTitle(task: SeedanceTask, fallback: string, maxLength = 56): string {
  const value = task.request.prompt.trim() || fallback;
  return value.length > maxLength
    ? `${value.slice(0, maxLength - 1).trimEnd()}…`
    : value;
}

export function actualOutputParameters(task: SeedanceTask): Record<'resolution' | 'ratio' | 'duration' | 'fps', string> {
  const output = task.remote.output ?? {};
  const value = (key: string) => output[key] ?? task.remote[key];
  const text = (key: string) => typeof value(key) === 'string' || typeof value(key) === 'number' ? String(value(key)) : '—';
  return { resolution: text('resolution'), ratio: text('ratio'), duration: text('duration'), fps: text('fps') };
}

export function formatBytes(bytes: number | null | undefined): string {
  return typeof bytes === 'number' && bytes >= 0 ? `${(bytes / 1024 / 1024).toFixed(2)} MB` : '—';
}
