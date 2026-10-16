/**
 * API client for PyWebView backend
 * Provides typed access to Python backend functions
 */
import type { PyWebViewWindow } from '@/types/api';
import type {
  Project,
  CreateProjectData,
  RoleSummary,
  LegacyMigrationRequest,
  LegacyMigrationResult,
  LegacyProjectImportResult,
  FramesResponse,
  HiddenFramesResponse,
  VideoInfo,
  VideoValidation,
  TaskStatus,
  Step1Params,
  Step2Params,
  Step3Params,
  AppConfig,
  AppUpdateInfo,
  BackgroundColor,
  ModelStatus,
  ProjectTrimStatus,
  BatchTrimParams,
  BatchTrimResult,
  SeedanceCreateRequest,
  SeedanceRegenerationDraft,
  SeedanceTaskResult,
  SeedanceTaskListResult,
  SeedanceDeleteResult,
  SeedanceHandoffResult,
  SeedanceSettings,
  SeedanceSettingsUpdate,
  SeedanceSettingsResult,
  SeedanceDataResult,
  SeedanceCacheInfo,
  SeedanceCacheCleanResult,
  GenerationLayout,
  SeedreamCreateRequest,
  SeedreamBatchResult,
  SeedreamBatchListResult,
  SeedreamDeleteResult,
  SeedreamSettings,
  SeedreamSettingsResult,
  SeedreamDataResult,
  SeedreamHandoffImage,
  SeedreamCharacterResizeResult,
  SeedreamCharacterRestoreResult,
  SeedreamEraserResult,
  SeedreamRegenerationDraft,
  SeedreamActiveCountResult,
  SeedreamExitConfirmResult,
  AudioExtractionResult,
  AudioTimelineResult,
  AudioSaveResult,
  AudioClip,
  StorageSettingsDraft,
  StorageSettingsResult,
  StorageSaveResult,
  StorageMigrationResult,
  StorageMigrationStateResult,
  PlatformCapabilities,
  PlatformDataResult,
} from '@/types';

declare const window: PyWebViewWindow;

type PyWebViewApi = NonNullable<PyWebViewWindow['pywebview']>['api'];

/**
 * Wait for PyWebView API to be ready
 */
function waitForPyWebView(): Promise<PyWebViewApi> {
  return new Promise((resolve) => {
    // PyWebView injects an empty api object before registering its methods.
    if (typeof window.pywebview?.api.get_app_version === 'function') {
      resolve(window.pywebview.api);
    } else {
      window.addEventListener('pywebviewready', () => {
        if (window.pywebview?.api) {
          resolve(window.pywebview.api);
        }
      }, { once: true });
    }
  });
}

/**
 * Get PyWebView API instance (waits for ready)
 */
async function getApi() {
  const api = await waitForPyWebView();
  if (!api) {
    throw new Error('PyWebView API not available');
  }
  return api;
}

async function callApi<T>(
  snakeName: string,
  camelName: string,
  ...args: unknown[]
): Promise<T> {
  const api = await getApi();
  const apiObject = api as unknown as Record<string, (...args: unknown[]) => Promise<T>>;
  const method = apiObject[snakeName] ?? apiObject[camelName];

  if (!method) {
    throw new Error(`PyWebView API method not available: ${snakeName}/${camelName}`);
  }

  return method(...args);
}

/**
 * Check if PyWebView API is available (synchronous check)
 */
export function isApiAvailable(): boolean {
  return typeof window.pywebview?.api.get_app_version === 'function';
}

/**
 * Project API
 */
export const projectApi = {
  async getProjects(): Promise<Project[]> {
    return callApi<Project[]>('get_projects', 'getProjects');
  },

  async getRoles(): Promise<RoleSummary[]> {
    return callApi<RoleSummary[]>('get_roles', 'getRoles');
  },

  async getProject(projectId: string): Promise<Project | null> {
    return callApi<Project | null>('get_project', 'getProject', projectId);
  },

  async createProject(data: CreateProjectData): Promise<Project> {
    return callApi<Project>(
      'create_project',
      'createProject',
      data.role,
      data.action,
      data.video_path,
      data.frame_interval
    );
  },

  async deleteProject(projectId: string): Promise<boolean> {
    return callApi<boolean>('delete_project', 'deleteProject', projectId);
  },

  async deleteRole(role: string): Promise<boolean> {
    return callApi<boolean>('delete_role', 'deleteRole', role);
  },

  async updateProject(projectId: string, data: Partial<Project>): Promise<Project> {
    return callApi<Project>('update_project', 'updateProject', projectId, data);
  },

  async migrateLegacyProjects(migrations: LegacyMigrationRequest[] | string = 'Unknown'): Promise<LegacyMigrationResult> {
    return callApi<LegacyMigrationResult>('migrate_legacy_projects', 'migrateLegacyProjects', migrations);
  },

  async importLegacyProjectDirectory(sourceDirectory: string): Promise<LegacyProjectImportResult> {
    return callApi<LegacyProjectImportResult>(
      'import_legacy_project_directory',
      'importLegacyProjectDirectory',
      sourceDirectory
    );
  }
};

/**
 * Video API
 */
export const videoApi = {
  async getVideoInfo(videoPath: string): Promise<VideoInfo> {
    return callApi<VideoInfo>('get_video_info', 'getVideoInfo', videoPath);
  },

  async validateVideo(videoPath: string): Promise<VideoValidation> {
    return callApi<VideoValidation>('validate_video', 'validateVideo', videoPath);
  }
};

/**
 * Frame API
 */
export const frameApi = {
  async getFrames(
    projectId: string,
    step: number,
    page: number = 1,
    pageSize: number = 50,
    useCache: boolean = true
  ): Promise<FramesResponse> {
    return callApi<FramesResponse>('get_frames', 'getFrames', projectId, step, page, pageSize, useCache);
  },

  async getFrameImage(framePath: string): Promise<string> {
    return callApi<string>('get_frame_image', 'getFrameImage', framePath);
  },

  async getFrameThumbnail(framePath: string, size: number = 128): Promise<string> {
    return callApi<string>('get_frame_thumbnail', 'getFrameThumbnail', framePath, size);
  },

  async getFrameUrl(framePath: string): Promise<string> {
    return callApi<string>('get_frame_url', 'getFrameUrl', framePath);
  },

  async getHiddenFrames(projectId: string): Promise<string[]> {
    return callApi<string[]>('get_hidden_frames', 'getHiddenFrames', projectId);
  },

  async setFrameHidden(projectId: string, filename: string, hidden: boolean): Promise<HiddenFramesResponse> {
    return callApi<HiddenFramesResponse>('set_frame_hidden', 'setFrameHidden', projectId, filename, hidden);
  },

  async restoreHiddenFrames(projectId: string): Promise<HiddenFramesResponse> {
    return callApi<HiddenFramesResponse>('restore_hidden_frames', 'restoreHiddenFrames', projectId);
  }
};

/**
 * Process API
 */
export const processApi = {
  async startProcessing(
    projectId: string,
    step: number,
    params: Step1Params | Step2Params | Step3Params
  ): Promise<string> {
    return callApi<string>(
      'start_processing',
      'startProcessing',
      projectId,
      step,
      params as unknown as Record<string, unknown>
    );
  },

  async getTaskStatus(taskId: string): Promise<TaskStatus> {
    return callApi<TaskStatus>('get_task_status', 'getTaskStatus', taskId);
  },

  async cancelTask(taskId: string): Promise<boolean> {
    return callApi<boolean>('cancel_task', 'cancelTask', taskId);
  },

  async getStepParams(
    projectId: string,
    step: number
  ): Promise<Step1Params | Step2Params | Step3Params> {
    return callApi<Step1Params | Step2Params | Step3Params>('get_step_params', 'getStepParams', projectId, step);
  },

  async saveStepParams(
    projectId: string,
    step: number,
    params: Step1Params | Step2Params | Step3Params
  ): Promise<boolean> {
    return callApi<boolean>(
      'save_step_params',
      'saveStepParams',
      projectId,
      step,
      params as unknown as Record<string, unknown>
    );
  },

  async getBackgroundColor(projectId: string): Promise<BackgroundColor | null> {
    return callApi<BackgroundColor | null>('get_background_color', 'getBackgroundColor', projectId);
  },

  async getModelStatus(model: string = 'u2net'): Promise<ModelStatus> {
    return callApi<ModelStatus>('get_model_status', 'getModelStatus', model);
  },

  async preloadModel(model: string = 'u2net', source?: 'modelscope' | 'github'): Promise<ModelStatus> {
    return callApi<ModelStatus>('preload_model', 'preloadModel', model, source ?? null);
  },

  async retryModel(model: string = 'u2net', source?: 'modelscope' | 'github'): Promise<ModelStatus> {
    return callApi<ModelStatus>('retry_model', 'retryModel', model, source ?? null);
  }

}

/**
 * Config API
 */
export const configApi = {
  async getConfig(): Promise<AppConfig> {
    return callApi<AppConfig>('get_config', 'getConfig');
  },

  async saveConfig(config: Partial<AppConfig>): Promise<boolean> {
    return callApi<boolean>('save_config', 'saveConfig', config);
  },

  async setCliGenerationEnabled(enabled: boolean, confirmed: boolean = false): Promise<boolean> {
    const result = await callApi<{ success: boolean }>('save_cli_generation_enabled', 'saveCliGenerationEnabled', enabled, confirmed);
    return result.success;
  },

  async setArkAuditEnabled(enabled: boolean): Promise<boolean> {
    const result = await callApi<{ success: boolean }>('save_ark_audit_enabled', 'saveArkAuditEnabled', enabled);
    return result.success;
  },

  async getAvailableSizes(): Promise<number[]> {
    return callApi<number[]>('get_available_sizes', 'getAvailableSizes');
  }
};

/**
 * System API
 */
export const systemApi = {
  async selectVideoFile(): Promise<string | null> {
    return callApi<string | null>('select_video_file', 'selectVideoFile');
  },

  async selectDirectory(): Promise<string | null> {
    return callApi<string | null>('select_directory', 'selectDirectory');
  },

  async openProjectFolder(projectPath: string): Promise<boolean> {
    return callApi<boolean>('open_project_folder', 'openProjectFolder', projectPath);
  },

  async checkAppUpdate(): Promise<AppUpdateInfo> {
    return callApi<AppUpdateInfo>('check_app_update', 'checkAppUpdate');
  },

  async ignoreAppUpdate(version: string): Promise<boolean> {
    return callApi<boolean>('ignore_app_update', 'ignoreAppUpdate', version);
  },

  async openAppUpdate(): Promise<boolean> {
    return callApi<boolean>('open_app_update', 'openAppUpdate');
  },

  async getAppVersion(): Promise<string> {
    return callApi<string>('get_app_version', 'getAppVersion');
  }
};

/**
 * Batch Trim API
 */
export const batchTrimApi = {
  async checkProjects(projectIds: string[]): Promise<ProjectTrimStatus[]> {
    return callApi<ProjectTrimStatus[]>('check_projects_for_trim', 'checkProjectsForTrim', projectIds);
  },

  async executeTrim(params: BatchTrimParams): Promise<BatchTrimResult[]> {
    return callApi<BatchTrimResult[]>('execute_batch_trim', 'executeBatchTrim', params);
  }
};

/**
 * Audio API
 */
export const audioApi = {
  async extractSourceAudio(projectId: string): Promise<AudioExtractionResult> {
    return callApi<AudioExtractionResult>('extract_source_audio', 'extractSourceAudio', projectId);
  },

  async loadTimeline(projectId: string): Promise<AudioTimelineResult> {
    return callApi<AudioTimelineResult>('load_timeline', 'loadTimeline', projectId);
  },

  async saveTimeline(projectId: string, timeline: {
    source_fps: number;
    total_frames: number;
    source_wav: string;
    clips: AudioClip[];
  }): Promise<AudioSaveResult> {
    return callApi<AudioSaveResult>('save_timeline', 'saveTimeline', projectId, timeline);
  }
};

/**
 * Seedance video-generation API. The backend returns structured success/error
 * envelopes for every task operation; settings reads are already redacted.
 */
export const seedanceApi = {
  async openVideoDirectory(localId: string): Promise<SeedanceDeleteResult> {
    return callApi('seedance_open_video_directory', 'seedanceOpenVideoDirectory', localId);
  },
  async selectImageFile(): Promise<string | null> {
    return callApi<string | null>('seedance_select_image_file', 'seedanceSelectImageFile');
  },

  async getEditableImage(sourcePath: string): Promise<SeedanceDataResult<{
    image_data_url: string;
    edit_source_data_url: string;
    width: number;
    height: number;
    generation_layout: GenerationLayout | null;
  }>> {
    return callApi('seedance_get_editable_image', 'seedanceGetEditableImage', sourcePath);
  },

  async saveEditedImage(
    sourcePath: string,
    imageDataUrl: string,
    editSourceDataUrl: string,
    generationLayout: GenerationLayout | null
  ): Promise<SeedanceDataResult<{
    path: string;
    width: number;
    height: number;
    generation_layout: GenerationLayout | null;
  }>> {
    return callApi(
      'seedance_save_edited_image',
      'seedanceSaveEditedImage',
      sourcePath,
      imageDataUrl,
      editSourceDataUrl,
      generationLayout
    );
  },

  async saveVideo(localId: string): Promise<SeedanceDataResult<{ saved: boolean; path?: string }>> {
    return callApi<SeedanceDataResult<{ saved: boolean; path?: string }>>(
      'seedance_save_video',
      'seedanceSaveVideo',
      localId
    );
  },

  async createTask(request: SeedanceCreateRequest, source: string = 'api-key'): Promise<SeedanceTaskResult> {
    return callApi<SeedanceTaskResult>('seedance_create_task', 'seedanceCreateTask', request, source);
  },

  async validateRequest(request: SeedanceCreateRequest, source: string = 'api-key'): Promise<SeedanceDataResult<{ valid: true }>> {
    return callApi<SeedanceDataResult<{ valid: true }>>('seedance_validate_request', 'seedanceValidateRequest', request, source);
  },

  async quoteVideo(request: SeedanceCreateRequest): Promise<SeedanceDataResult<{ quote: number }>> {
    return callApi<SeedanceDataResult<{ quote: number }>>('seedance_quote_video', 'seedanceQuoteVideo', request);
  },

  async listTasks(): Promise<SeedanceTaskListResult> {
    return callApi<SeedanceTaskListResult>('seedance_list_tasks', 'seedanceListTasks');
  },

  async getTask(localId: string): Promise<SeedanceTaskResult> {
    return callApi<SeedanceTaskResult>('seedance_get_task', 'seedanceGetTask', localId);
  },

  async getRegenerationDraft(localId: string): Promise<SeedanceDataResult<SeedanceRegenerationDraft>> {
    return callApi<SeedanceDataResult<SeedanceRegenerationDraft>>(
      'seedance_get_regeneration_draft',
      'seedanceGetRegenerationDraft',
      localId
    );
  },

  async getContinuationDraft(localId: string): Promise<SeedanceDataResult<SeedanceRegenerationDraft>> {
    return callApi<SeedanceDataResult<SeedanceRegenerationDraft>>(
      'seedance_get_continuation_draft',
      'seedanceGetContinuationDraft',
      localId
    );
  },

  async cancelTask(localId: string): Promise<SeedanceTaskResult> {
    return callApi<SeedanceTaskResult>('seedance_cancel_task', 'seedanceCancelTask', localId);
  },

  async retryTask(localId: string): Promise<SeedanceTaskResult> {
    return callApi<SeedanceTaskResult>('seedance_retry_task', 'seedanceRetryTask', localId);
  },

  async retryDownload(localId: string): Promise<SeedanceTaskResult> {
    return callApi<SeedanceTaskResult>('seedance_retry_download', 'seedanceRetryDownload', localId);
  },

  async continueTask(localId: string): Promise<SeedanceTaskResult> {
    return callApi<SeedanceTaskResult>('seedance_continue_task', 'seedanceContinueTask', localId);
  },

  async deleteTask(localId: string, allowProtected: boolean = false): Promise<SeedanceDeleteResult> {
    return callApi<SeedanceDeleteResult>('seedance_delete_task', 'seedanceDeleteTask', localId, allowProtected);
  },

  async handoff(localId: string, role: string, action: string): Promise<SeedanceHandoffResult> {
    return callApi<SeedanceHandoffResult>('seedance_handoff', 'seedanceHandoff', localId, role, action);
  },

  async getSettings(): Promise<SeedanceSettings> {
    return callApi<SeedanceSettings>('seedance_get_settings', 'seedanceGetSettings');
  },

  async saveSettings(settings: SeedanceSettingsUpdate): Promise<SeedanceSettingsResult> {
    return callApi<SeedanceSettingsResult>('seedance_save_settings', 'seedanceSaveSettings', settings);
  },

  async testConnection(apiKey?: string): Promise<SeedanceDataResult<{ configured: true }>> {
    return callApi<SeedanceDataResult<{ configured: true }>>('seedance_test_connection', 'seedanceTestConnection', apiKey);
  },

  async getCacheStatus(): Promise<SeedanceDataResult<SeedanceCacheInfo>> {
    return callApi<SeedanceDataResult<SeedanceCacheInfo>>('seedance_cache_status', 'seedanceCacheStatus');
  },

  async cleanCache(olderThanDays?: number): Promise<SeedanceDataResult<SeedanceCacheCleanResult>> {
    return callApi<SeedanceDataResult<SeedanceCacheCleanResult>>(
      'seedance_clean_cache',
      'seedanceCleanCache',
      olderThanDays
    );
  }
};

/**
 * Seedream image-generation API. Reuses the same Ark API key as Seedance.
 */
export const seedreamApi = {
  async openImageDirectory(localId: string, attemptIndex: number): Promise<SeedreamDeleteResult> {
    return callApi('seedream_open_image_directory', 'seedreamOpenImageDirectory', localId, attemptIndex);
  },

  async importReferenceImage(imageDataUrl: string, filename: string): Promise<
    { success: true; path: string } | { success: false; error: { code: string; message: string } }
  > {
    return callApi('seedream_import_reference_image', 'seedreamImportReferenceImage', imageDataUrl, filename);
  },
  async selectImageFile(): Promise<string | null> {
    return callApi<string | null>('seedream_select_image_file', 'seedreamSelectImageFile');
  },

  async createBatch(request: SeedreamCreateRequest, source: string = 'api-key'): Promise<SeedreamBatchResult> {
    return callApi<SeedreamBatchResult>('seedream_create_batch', 'seedreamCreateBatch', request, source);
  },

  /** 平台源单价报价（只依赖 model + resolution）；总数 = 单价 × count。 */
  async quoteImage(request: SeedreamCreateRequest): Promise<SeedreamDataResult<{ quote: number }>> {
    return callApi<SeedreamDataResult<{ quote: number }>>('seedream_quote_image', 'seedreamQuoteImage', request);
  },

  async getBatch(localId: string): Promise<SeedreamBatchResult> {
    return callApi<SeedreamBatchResult>('seedream_get_batch', 'seedreamGetBatch', localId);
  },

  async listBatches(): Promise<SeedreamBatchListResult> {
    return callApi<SeedreamBatchListResult>('seedream_list_batches', 'seedreamListBatches');
  },

  async saveImage(localId: string, attemptIndex: number): Promise<SeedreamDataResult<{ saved: boolean; path?: string }>> {
    return callApi<SeedreamDataResult<{ saved: boolean; path?: string }>>(
      'seedream_save_image',
      'seedreamSaveImage',
      localId,
      attemptIndex
    );
  },

  async resizeCharacter(
    localId: string,
    attemptIndex: number,
    top: number,
    bottom: number,
    targetHeight: number,
    bottomDistance: number
  ): Promise<SeedreamDataResult<SeedreamCharacterResizeResult>> {
    return callApi<SeedreamDataResult<SeedreamCharacterResizeResult>>(
      'seedream_resize_character',
      'seedreamResizeCharacter',
      localId,
      attemptIndex,
      top,
      bottom,
      targetHeight,
      bottomDistance
    );
  },

  async restoreCharacter(
    localId: string,
    attemptIndex: number
  ): Promise<SeedreamDataResult<SeedreamCharacterRestoreResult>> {
    return callApi<SeedreamDataResult<SeedreamCharacterRestoreResult>>(
      'seedream_restore_character',
      'seedreamRestoreCharacter',
      localId,
      attemptIndex
    );
  },

  async applyEraser(
    localId: string,
    attemptIndex: number,
    imageDataUrl: string,
    editSourceDataUrl: string,
    generationLayout: GenerationLayout | null
  ): Promise<SeedreamDataResult<SeedreamEraserResult>> {
    return callApi<SeedreamDataResult<SeedreamEraserResult>>(
      'seedream_apply_eraser',
      'seedreamApplyEraser',
      localId,
      attemptIndex,
      imageDataUrl,
      editSourceDataUrl,
      generationLayout
    );
  },

  async getHandoffImage(localId: string, attemptIndex: number): Promise<SeedreamDataResult<SeedreamHandoffImage>> {
    return callApi<SeedreamDataResult<SeedreamHandoffImage>>(
      'seedream_get_handoff_image',
      'seedreamGetHandoffImage',
      localId,
      attemptIndex
    );
  },

  async deleteBatch(localId: string): Promise<SeedreamDeleteResult> {
    return callApi<SeedreamDeleteResult>('seedream_delete_batch', 'seedreamDeleteBatch', localId);
  },

  async getRegenerationDraft(localId: string): Promise<SeedreamDataResult<SeedreamRegenerationDraft>> {
    return callApi<SeedreamDataResult<SeedreamRegenerationDraft>>(
      'seedream_get_regeneration_draft',
      'seedreamGetRegenerationDraft',
      localId
    );
  },

  async retryDownload(localId: string, attemptIndex: number): Promise<SeedreamBatchResult> {
    return callApi<SeedreamBatchResult>('seedream_retry_download', 'seedreamRetryDownload', localId, attemptIndex);
  },

  async getSettings(): Promise<SeedreamSettingsResult> {
    return callApi<SeedreamSettingsResult>('seedream_get_settings', 'seedreamGetSettings');
  },

  async saveSettings(settings: SeedreamSettings): Promise<SeedreamSettingsResult> {
    return callApi<SeedreamSettingsResult>('seedream_save_settings', 'seedreamSaveSettings', settings);
  },

  async getActiveAttemptCount(): Promise<SeedreamActiveCountResult> {
    return callApi<SeedreamActiveCountResult>(
      'seedream_get_active_attempt_count',
      'seedreamGetActiveAttemptCount'
    );
  },

  async confirmExit(): Promise<SeedreamExitConfirmResult> {
    return callApi<SeedreamExitConfirmResult>('seedream_confirm_exit', 'seedreamConfirmExit');
  }
};

/**
 * Storage settings & migration API
 */
export const storageApi = {
  async getSettings(): Promise<StorageSettingsResult> {
    return callApi<StorageSettingsResult>('storage_get_settings', 'storageGetSettings');
  },

  async saveSettings(draft: StorageSettingsDraft): Promise<StorageSaveResult> {
    return callApi<StorageSaveResult>('storage_save_settings', 'storageSaveSettings', draft);
  },

  async executeMigration(token: string): Promise<StorageMigrationResult> {
    return callApi<StorageMigrationResult>('storage_execute_migration', 'storageExecuteMigration', token);
  },

  async getMigrationState(): Promise<StorageMigrationStateResult> {
    return callApi<StorageMigrationStateResult>('storage_migration_state', 'storageMigrationState');
  }
};

/**
 * App lifecycle API
 */
export const lifecycleApi = {
  async requestAppRestart(): Promise<{ success: boolean; restart_requested?: boolean; error?: string }> {
    return callApi<{ success: boolean; restart_requested?: boolean; error?: string }>(
      'request_app_restart',
      'requestAppRestart'
    );
  },
  async closeApp(): Promise<{ success: boolean; close_requested?: boolean; error?: string }> {
    return callApi<{ success: boolean; close_requested?: boolean; error?: string }>(
      'close_app',
      'closeApp'
    );
  }
};

/**
 * Platform (ForFuner AI) bridge config. The platform base URL + JWT live in
 * Python process memory only; the frontend re-pushes them whenever auth state
 * changes (see stores/auth.ts token watcher).
 */
export const platformApi = {
  async setConfig(baseUrl: string, token: string | null): Promise<{ success: boolean; error?: string }> {
    return callApi<{ success: boolean; error?: string }>('set_platform_config', 'setPlatformConfig', baseUrl, token);
  },

  /** 平台可售能力清单；平台源下渲染模型/参数选项的唯一来源。 */
  async getCapabilities(): Promise<PlatformDataResult<PlatformCapabilities>> {
    return callApi<PlatformDataResult<PlatformCapabilities>>(
      'get_platform_capabilities',
      'getPlatformCapabilities',
    );
  }
};

/**
 * Combined API export
 */
export const api = {
  project: projectApi,
  video: videoApi,
  frame: frameApi,
  process: processApi,
  config: configApi,
  system: systemApi,
  batchTrim: batchTrimApi,
  audio: audioApi,
  seedance: seedanceApi,
  seedream: seedreamApi,
  storage: storageApi,
  lifecycle: lifecycleApi,
  platform: platformApi,
  isAvailable: isApiAvailable
};
