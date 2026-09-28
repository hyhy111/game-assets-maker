/**
 * Project types
 */
export interface Project {
  id: string;
  role: string;
  action: string;
  legacy?: boolean;
  name: string;
  path: string;
  video_path: string;
  frame_interval: number;
  created_at: string;
  modified_at: string;
  output_path?: string;
  cache_path?: string;
  steps?: StepStatusMap;
}

export interface StepStatus {
  completed: boolean;
  data_ready: boolean;
  count: number;
}

export interface StepStatusMap {
  [key: string]: StepStatus;
}

export interface CreateProjectData {
  role: string;
  action: string;
  video_path: string;
  frame_interval: number;
}

export interface RoleSummary {
  name: string;
  projectCount: number;
}

export interface LegacyMigrationRequest {
  projectId: string;
  targetRole: string;
  targetAction: string;
}

export interface LegacyMigrationResult {
  success: boolean;
  migrated: Array<{
    from: string;
    to: string;
    path: string;
  }>;
  conflicts: Array<{
    projectId: string;
    targetPath: string;
    reason?: string;
  }>;
}

export interface LegacyProjectImportResult {
  success: boolean;
  source: string;
  imported: Array<{ projectId: string; path: string }>;
  skipped: Array<{ projectId: string; reason: string }>;
  failed: Array<{ projectId: string; reason: string }>;
}

/**
 * Frame types
 */
export interface Frame {
  index: number;
  /** 隐藏帧过滤前在步骤输出序列中的位置。 */
  timeline_index?: number;
  name: string;
  path: string;
  filename: string;
  url?: string;
}

export interface FramesResponse {
  success: boolean;
  frames: Frame[];
  total: number;
  /** 隐藏帧过滤前的完整时间轴长度。 */
  timeline_total?: number;
  page: number;
  page_size: number;
  total_pages: number;
  hidden_count?: number;
}

export interface HiddenFramesResponse {
  success: boolean;
  hidden_frames: string[];
}

/**
 * Video types
 */
export interface VideoInfo {
  success: boolean;
  fps?: number;
  frame_count?: number;
  width?: number;
  height?: number;
  duration?: number;
  duration_formatted?: string;
  error?: string;
}

export interface VideoValidation {
  success: boolean;
  valid?: boolean;
  errors?: string[];
  warnings?: string[];
  info?: VideoInfo;
}

/**
 * Audio Timeline types
 */
export interface AudioExtractionResult {
  success: boolean;
  source_wav: string;
  source_fps: number;
  total_frames: number;
  error?: string;
}

/**
 * 一个音效片段：从源音频的 Source Region 裁出，放到动画轴的 Placement Frame。
 * 所有坐标均为整数帧索引（Frame-aligned）。
 */
export interface AudioClip {
  name: string;
  srcStartFrame: number;
  srcEndFrame: number;
  placementFrame: number;
}

/**
 * 持久化的音效时间线对象（cache/audio_timeline.json）。
 */
export interface AudioTimeline {
  source_fps: number;
  total_frames: number;
  source_wav: string;
  clips: AudioClip[];
}

export interface AudioTimelineResult {
  source_fps: number;
  total_frames: number;
  source_wav: string;
  clips: AudioClip[];
}

export interface AudioSaveResult {
  success: boolean;
  error?: string;
}

export type ModelPhase = 'needs_download' | 'downloading' | 'initializing' | 'ready' | 'failed';

export interface ModelStatusError {
  code: 'MODEL_DOWNLOAD_FAILED' | 'MODEL_INITIALIZATION_FAILED';
  message: string;
}

export interface ModelStatus {
  model: string;
  phase: ModelPhase;
  downloaded_bytes: number | null;
  total_bytes: number | null;
  error: ModelStatusError | null;
}

/**
 * Process types
 */
export interface Step1Params {
  video_path?: string;
  frame_interval: number;
  start_frame: number;
  end_frame: number;
  fps: number;
  processed?: boolean;
  processing_time?: number;  // Processing time in seconds (not persisted)
}

// Step 2: Background removal only (rembg parameters)
export interface Step2Params {
  model?: 'u2net';  // Only supported rembg model
  alpha_matting: boolean;        // default true
  alpha_matting_erode_size: number;      // 0-20, default 5
  alpha_matting_background_threshold: number;  // 0-255, default 12
  alpha_matting_foreground_threshold: number;  // 100-250, default 240
  fps: number;                   // Playback fps for preview, default 30
  processed?: boolean;           // whether step 2 has been processed
  processing_time?: number;      // processing time in seconds
}

// Step 3: Post-processing (hole punching + alignment)
export interface Step3Params {
  enabled: boolean;              // whether hole punching is enabled, default true
  // Green intensity level (1-5): 1=bright green, 5=dark green
  green_intensity: number;       // 1-5, default 3
  feather_radius: number;        // Feather radius (0-10 pixels), default 3
  min_hole_size: number;         // Minimum hole area in pixels (0-500), default 5
  // Alignment parameters
  align_enabled: boolean;        // whether alignment is enabled, default false
  align_h: boolean;              // horizontal centering, default true
  align_v: boolean;              // vertical bottom alignment, default true
  use_padding: boolean;          // use bottom padding, default true
  padding_bottom: number;        // bottom padding pixels (0-50), default 10
  fps: number;                   // Playback fps for preview, default 30
  processed?: boolean;           // whether step 3 has been processed
  processing_time?: number;      // Processing time in seconds (not persisted)
}

// Background color from step 1
export interface BackgroundColor {
  hsv: [number, number, number];
  rgb: [number, number, number];
  sampled_from: string;
}

export type ProcessParams = Step1Params | Step2Params | Step3Params;

export interface TaskStatus {
  success: boolean;
  task_id?: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  current: number;
  total: number;
  step?: number;
  error?: string;
  processing_time?: number;  // Processing time in seconds
}

/**
 * Config types
 */
export interface AppConfig {
  language: string;
  theme: string;
  logger_enabled: boolean;
  paid_generation_confirmation_enabled: boolean;
  logger_config: LoggerConfig;
  seedance: SeedanceSettings;
}

export interface LoggerConfig {
  log_dir: string;
  max_log_size_mb: number;
  max_log_files: number;
  auto_cleanup_days: number;
  cleanup_interval_hours: number;
}

/**
 * Seedance public PyWebView contracts. These mirror the redacted dictionaries
 * emitted by backend.api.seedance_api, never the persisted API key.
 */
export type SeedanceModel = 'standard' | 'fast' | 'mini';
/**
 * 请求里携带的模型标识：直连模式是本地短键（SeedanceModel），
 * 平台源是能力清单下发的上游模型 ID。用 `(string & {})` 保留短键的字面量补全，
 * 同时允许任意上游 ID —— 后者必须能原样透传，否则运营上新模型时客户端会先失败。
 */
export type SeedanceModelRef = SeedanceModel | (string & {});
export type SeedanceResolution = '480p' | '720p' | '1080p';
export type SeedanceRatio = 'adaptive' | '16:9' | '1:1' | '4:3';
export type SeedanceDuration = -1 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15;
export type SeedanceRemoteStatus =
  | 'submitting'
  | 'submission_unknown'
  | 'queued'
  | 'running'
  | 'cancelling'
  | 'succeeded'
  | 'failed'
  | 'expired'
  | 'cancelled';
export type SeedanceDownloadStatus = 'pending' | 'downloading' | 'downloaded' | 'failed' | 'cleared';
export type SeedanceCacheStatus = 'complete' | 'cleared';

export interface SeedanceCreateRequest {
  first_frame: string;
  last_frame?: string | null;
  prompt?: string;
  model?: SeedanceModelRef;
  resolution?: SeedanceResolution;
  ratio?: SeedanceRatio;
  duration?: SeedanceDuration;
  generate_audio?: boolean;
  return_last_frame?: boolean;
  priority?: number;
  execution_expires_after?: number;
}

export interface SeedanceTaskRequest {
  prompt: string;
  model: SeedanceModel;
  resolution: SeedanceResolution;
  ratio: SeedanceRatio;
  duration: SeedanceDuration;
  generate_audio: boolean;
  return_last_frame: boolean;
  priority: number;
  execution_expires_after: number;
}

export interface SeedanceRegenerationDraft {
  request: SeedanceCreateRequest;
  preview_urls: Record<string, string>;
}

export interface SeedanceTaskError {
  code: string;
  message: string;
  status?: number;
  [key: string]: unknown;
}

export interface SeedanceApiError extends SeedanceTaskError {
  field: string | null;
}

export interface SeedanceSyncStatus {
  state?: 'ok' | 'error' | 'cancelling';
  last_synced_at?: string;
  error?: SeedanceTaskError;
  [key: string]: unknown;
}

export interface SeedanceRemote {
  created_at?: string;
  updated_at?: string;
  usage?: Record<string, unknown>;
  output?: Record<string, unknown>;
  error?: SeedanceTaskError;
  resolution?: string;
  ratio?: string;
  duration?: number;
  fps?: number;
  generate_audio?: boolean;
  return_last_frame?: boolean;
  [key: string]: unknown;
}

export interface SeedanceHandoff {
  project_id: string;
  role: string;
  action: string;
  created_at: string;
}

export interface SeedanceTask {
  local_id: string;
  remote_id: string | null;
  remote_status: SeedanceRemoteStatus;
  sync_status: SeedanceSyncStatus;
  download_status: SeedanceDownloadStatus;
  cache_status: SeedanceCacheStatus;
  protected: boolean;
  request: SeedanceTaskRequest;
  input_urls: Record<string, string>;
  output_urls: Record<string, string>;
  file_size_bytes?: number | null;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
  download_url_received_at: string | null;
  elapsed_seconds: number;
  remote: SeedanceRemote;
  error: SeedanceTaskError | null;
  retry_of: string | null;
  handoffs: SeedanceHandoff[];
  /** 生成来源：api-key=直连 Ark；forfuner-ai=平台代生成 */
  source?: string;
}

export interface SeedanceStaleTaskResult {
  stale: true;
}

export type SeedanceTaskLoadResult = SeedanceTask | SeedanceStaleTaskResult | null;

export interface SeedanceSettings {
  api_key_configured: boolean;
  cache_dir: string;
  default_model: SeedanceModel;
  default_resolution: SeedanceResolution;
  default_ratio: SeedanceRatio;
  default_duration: SeedanceDuration;
  default_generate_audio: boolean;
  default_return_last_frame: boolean;
  default_priority: number;
  default_expires_after: number;
  retention_days: number;
  last_cleanup_at: string | null;
}

export type SeedanceSettingsUpdate = Partial<Omit<SeedanceSettings, 'api_key_configured'>> & {
  api_key?: string | null;
};

export interface SeedanceCacheInfo {
  total_bytes: number;
  task_count: number;
  protected_task_count: number;
  clearable_bytes: number;
}

export interface SeedanceCacheCleanResult {
  files_removed: number;
  bytes_released: number;
  tasks_cleared: number;
  protected_tasks_skipped: number;
}

export type SeedanceTaskResult =
  | { success: true; task: SeedanceTask }
  | { success: false; error: SeedanceApiError };
export type SeedanceTaskListResult =
  | { success: true; tasks: SeedanceTask[] }
  | { success: false; error: SeedanceApiError };
export type SeedanceDeleteResult =
  | { success: true }
  | { success: false; error: SeedanceApiError };
export type SeedanceSettingsResult =
  | { success: true; settings: SeedanceSettings }
  | { success: false; error: SeedanceApiError };
export type SeedanceDataResult<T> =
  | { success: true; data: T }
  | { success: false; error: SeedanceApiError };
export type SeedanceHandoffResult =
  | { success: true; project_id: string; task: SeedanceTask }
  | { success: false; error: SeedanceApiError };

/**
 * Player types
 */
export interface PlayerState {
  isPlaying: boolean;
  currentIndex: number;
  totalFrames: number;
  zoom: number;
  panX: number;
  panY: number;
  useNearest: boolean;
}

/**
 * Batch Trim types
 */
export interface ProjectTrimStatus {
  projectId: string;
  status: 'available' | 'fallback' | 'unavailable' | 'unchecked';
  hasHolePunched: boolean;
  hasNoBg: boolean;
  frameCount: number;
}

export interface FailedFrame {
  filename: string;
  reason: string;
}

export interface BatchTrimResult {
  projectId: string;
  projectName: string;
  status: 'success' | 'partial' | 'error';
  message: string;
  outputPath?: string;
  frameCount?: number;
  successCount?: number;
  failedCount?: number;
  failedFrames?: FailedFrame[];
  audioClipCount?: number;
  audioSkippedCount?: number;
  audioErrors?: string[];
}

export interface BatchTrimParams {
  projectIds: string[];
  mode: 'global' | 'individual';
  outputDir: string;
}

/**
 * Seedream image-generation public PyWebView contracts.
 */
export type SeedreamModel = 'pro' | 'flash' | 'lite';
/** 见 SeedanceModelRef：平台源的 model 是上游 ID。 */
export type SeedreamModelRef = SeedreamModel | (string & {});
export type SeedreamResolution = '1K' | '1.5K' | '2K';
export type SeedreamRatio = '1:1' | '16:9' | '9:16' | '4:3' | '3:4';
export type SeedreamAttemptStatus = 'queued' | 'generating' | 'downloading' | 'succeeded' | 'failed' | 'unknown' | 'download_failed';
export type SeedreamBatchStatus = 'generating' | 'completed' | 'partially_complete' | 'failed' | 'unknown';

export interface GenerationLayout {
  source_width: number;
  source_height: number;
  measured_top: number;
  measured_bottom: number;
  measured_height: number;
  target_height: number;
  character_height_ratio: number;
  bottom_distance: number;
  bottom_margin_ratio: number;
  scale: number;
}

export interface SeedreamCreateRequest {
  prompt: string;
  model?: SeedreamModelRef;
  resolution?: SeedreamResolution;
  ratio?: SeedreamRatio;
  count?: number;
  reference_image?: string | null;
}

export interface SeedreamAttemptRequest {
  prompt: string;
  model: SeedreamModelRef;
  resolution: SeedreamResolution;
  ratio: SeedreamRatio;
  count: number;
  reference_image?: string | null;
  /** 生成来源：api-key=直连 Ark；forfuner-ai=平台代生成 */
  source?: string;
}

export interface SeedreamApiError {
  code: string;
  message: string;
  field: string | null;
}

export interface SeedreamAttemptError {
  code: string;
  message: string;
  status?: number;
  [key: string]: unknown;
}

export interface SeedreamAttempt {
  local_id: string;
  index: number;
  status: SeedreamAttemptStatus;
  request: SeedreamAttemptRequest;
  response: Record<string, unknown>;
  usage: Record<string, unknown>;
  total_tokens: number | null;
  image_url: string;
  image_width: number | null;
  image_height: number | null;
  local_path: string | null;
  generation_layout?: GenerationLayout | null;
  has_original_backup?: boolean;
  url_expired: boolean;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
  elapsed_seconds: number;
  error: SeedreamAttemptError | null;
}

export interface SeedreamBatch {
  local_id: string;
  request: SeedreamAttemptRequest;
  status: SeedreamBatchStatus;
  sequence: string;
  reference_image_url?: string | null;
  attempts: SeedreamAttempt[];
  created_at: string;
  updated_at: string;
}

export interface SeedreamSettings {
  default_count: number;
  default_model: SeedreamModel;
  default_resolution: SeedreamResolution;
  default_ratio: SeedreamRatio;
}

export interface SeedreamHandoffImage {
  local_path: string;
}

export interface SeedreamCharacterResizeResult {
  width: number;
  height: number;
  measured_height: number;
  target_height: number;
  bottom_distance: number;
  scale: number;
  background_color: [number, number, number];
  generation_layout: GenerationLayout;
}

export interface SeedreamCharacterRestoreResult {
  restored: true;
  width: number;
  height: number;
}

export interface SeedreamEraserResult {
  saved: true;
  width: number;
  height: number;
  generation_layout: GenerationLayout | null;
}

export interface SeedreamRegenerationDraft {
  request: SeedreamCreateRequest;
  reference_image_url?: string | null;
}

export type SeedreamBatchResult =
  | { success: true; batch: SeedreamBatch }
  | { success: false; error: SeedreamApiError };
export type SeedreamBatchListResult =
  | { success: true; batches: SeedreamBatch[] }
  | { success: false; error: SeedreamApiError };
export type SeedreamDeleteResult =
  | { success: true }
  | { success: false; error: SeedreamApiError };
export type SeedreamSettingsResult =
  | { success: true; settings: SeedreamSettings }
  | { success: false; error: SeedreamApiError };
export type SeedreamDataResult<T> =
  | { success: true; data: T }
  | { success: false; error: SeedreamApiError };

export type SeedreamActiveCountResult =
  | { success: true; data: { active_count: number } }
  | { success: false; error: SeedreamApiError };

export type SeedreamExitConfirmResult =
  | { success: true }
  | { success: false; error: SeedreamApiError };

/**
 * 平台可售能力清单（ForFuner AI 源）。
 *
 * 平台源下的模型与参数选项以此为唯一来源，取代客户端预设模型表——
 * 使"能选的"恒等于"平台能卖的"。见 openspec: gen-capabilities。
 */
export interface PlatformModelCapability {
  /** 上游模型标识（如 doubao-seedance-2-0-260128），可直接用于建单 */
  model: string;
  /** 用户在客户端看到的模型名（服务端下发）；为空时回退 model */
  displayName?: string;
  /** 视频：该模型有定价的分辨率档 */
  resolutions?: string[];
  /**
   * 视频：**每个分辨率各自**有定价的时长档。
   *
   * 刻意不是模型级的时长并集——可售单位是"分辨率 × 时长"的组合：
   * 480p 有 4s/5s、720p 只有 4s 时，并集会放出 720p+5s 这种没定价的搭配。
   */
  durationsByResolution?: Record<string, number[]>;
  /** 图片：该模型有定价的尺寸档（1K/1.5K/2K） */
  sizes?: string[];
}

export interface PlatformCapabilities {
  video: {
    models: PlatformModelCapability[];
    /** 平台固定接受的画面比例枚举（不影响定价） */
    ratios: string[];
  };
  image: {
    models: PlatformModelCapability[];
  };
}

/** 平台源级操作的统一返回信封（与 Seedance/Seedream 的 DataResult 同形）。 */
export type PlatformDataResult<T> =
  | { success: true; data: T }
  | { success: false; error: SeedanceApiError };
