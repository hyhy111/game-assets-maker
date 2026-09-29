/**
 * PyWebView API types
 */
import type {
  Project,
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
  ModelStatus,
  ProjectTrimStatus,
  BatchTrimResult,
  BatchTrimParams,
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
  StorageSettingsDraft,
  StorageSettingsResult,
  StorageSaveResult,
  StorageMigrationResult,
  StorageMigrationStateResult,
} from './index';

/**
 * Extended Window interface for PyWebView
 */
export interface PyWebViewWindow extends Window {
  pywebview?: {
    api: {
      // Project API
      get_projects: () => Promise<Project[]>;
      get_roles: () => Promise<RoleSummary[]>;
      get_project: (project_id: string) => Promise<Project | null>;
      create_project: (role: string, action: string, video_path: string, fps: number) => Promise<Project>;
      delete_project: (project_id: string) => Promise<boolean>;
      delete_role: (role: string) => Promise<boolean>;
      update_project: (project_id: string, data: Partial<Project>) => Promise<Project>;
      migrate_legacy_projects: (migrations: LegacyMigrationRequest[] | string) => Promise<LegacyMigrationResult>;
      import_legacy_project_directory: (source_directory: string) => Promise<LegacyProjectImportResult>;

      // Video API
      get_video_info: (video_path: string) => Promise<VideoInfo>;
      validate_video: (video_path: string) => Promise<VideoValidation>;

      // Frame API
      get_frames: (project_id: string, step: number, page?: number, page_size?: number) => Promise<FramesResponse>;
      get_frame_image: (frame_path: string) => Promise<string>;
      get_frame_thumbnail: (frame_path: string, size?: number) => Promise<string>;
      get_frame_url: (frame_path: string) => Promise<string>;
      get_hidden_frames: (project_id: string) => Promise<string[]>;
      set_frame_hidden: (project_id: string, filename: string, hidden: boolean) => Promise<HiddenFramesResponse>;
      restore_hidden_frames: (project_id: string) => Promise<HiddenFramesResponse>;

      // Process API
      start_processing: (project_id: string, step: number, params: Record<string, unknown>) => Promise<string>;
      get_task_status: (task_id: string) => Promise<TaskStatus>;
      cancel_task: (task_id: string) => Promise<boolean>;
      get_step_params: (project_id: string, step: number) => Promise<Step1Params | Step2Params | Step3Params>;
      save_step_params: (project_id: string, step: number, params: Record<string, unknown>) => Promise<boolean>;
      get_background_color: (project_id: string) => Promise<{ hsv: [number, number, number]; rgb: [number, number, number]; sampled_from: string } | null>;
      get_model_status: (model: string) => Promise<ModelStatus>;
      preload_model: (model: string) => Promise<ModelStatus>;
      retry_model: (model: string) => Promise<ModelStatus>;

      // Config API
      get_config: () => Promise<AppConfig>;
      save_config: (config: AppConfig) => Promise<boolean>;

      // Storage settings & migration API
      storage_get_settings: () => Promise<StorageSettingsResult>;
      storage_save_settings: (draft: StorageSettingsDraft) => Promise<StorageSaveResult>;
      storage_execute_migration: (token: string) => Promise<StorageMigrationResult>;
      storage_migration_state: () => Promise<StorageMigrationStateResult>;

      // App lifecycle API
      request_app_restart: () => Promise<{ success: boolean; restart_requested?: boolean; error?: string }>;
      close_app: () => Promise<{ success: boolean; close_requested?: boolean; error?: string }>;
      get_available_sizes: () => Promise<number[]>;

      // System API
      select_video_file: () => Promise<string | null>;
      select_directory: () => Promise<string | null>;
      open_project_folder: (project_path: string) => Promise<boolean>;
      get_app_version: () => Promise<string>;
      /** 打开订阅落地页隔离窗（js_api=None，token 走 postMessage） */
      open_subscription_window: (url: string) => Promise<boolean>;

      // Batch Trim API
      check_projects_for_trim: (project_ids: string[]) => Promise<ProjectTrimStatus[]>;
      execute_batch_trim: (params: BatchTrimParams) => Promise<BatchTrimResult[]>;

      // Seedance API
      seedance_select_image_file: () => Promise<string | null>;
      seedance_get_editable_image: (source_path: string) => Promise<SeedanceDataResult<{
        image_data_url: string;
        edit_source_data_url: string;
        width: number;
        height: number;
        generation_layout: GenerationLayout | null;
      }>>;
      seedance_save_edited_image: (
        source_path: string,
        image_data_url: string,
        edit_source_data_url: string,
        generation_layout: GenerationLayout | null
      ) => Promise<SeedanceDataResult<{
        path: string;
        width: number;
        height: number;
        generation_layout: GenerationLayout | null;
      }>>;
      seedance_save_video: (local_id: string) => Promise<SeedanceDataResult<{ saved: boolean; path?: string }>>;
      seedance_create_task: (request: SeedanceCreateRequest) => Promise<SeedanceTaskResult>;
      seedance_validate_request: (request: SeedanceCreateRequest) => Promise<SeedanceDataResult<{ valid: true }>>;
      seedance_list_tasks: () => Promise<SeedanceTaskListResult>;
      seedance_get_task: (local_id: string) => Promise<SeedanceTaskResult>;
      seedance_get_regeneration_draft: (local_id: string) => Promise<SeedanceDataResult<SeedanceRegenerationDraft>>;
      seedance_cancel_task: (local_id: string) => Promise<SeedanceTaskResult>;
      seedance_retry_task: (local_id: string) => Promise<SeedanceTaskResult>;
      seedance_retry_download: (local_id: string) => Promise<SeedanceTaskResult>;
      seedance_continue_task: (local_id: string) => Promise<SeedanceTaskResult>;
      seedance_delete_task: (local_id: string, allow_protected?: boolean) => Promise<SeedanceDeleteResult>;
      seedance_handoff: (local_id: string, role: string, action: string) => Promise<SeedanceHandoffResult>;
      seedance_get_settings: () => Promise<SeedanceSettings>;
      seedance_save_settings: (settings: SeedanceSettingsUpdate) => Promise<SeedanceSettingsResult>;
      seedance_test_connection: (api_key?: string) => Promise<SeedanceDataResult<{ configured: true }>>;
      seedance_cache_status: () => Promise<SeedanceDataResult<SeedanceCacheInfo>>;
      seedance_clean_cache: (older_than_days?: number) => Promise<SeedanceDataResult<SeedanceCacheCleanResult>>;

      // Credential Crypto (记住账号密码, DPAPI 加密)
      encrypt_credential: (plaintext: string) => Promise<string>;
      decrypt_credential: (ciphertext: string) => Promise<string>;
    };
  };
}
