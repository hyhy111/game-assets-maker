import { defineStore } from 'pinia';
import { reactive, ref } from 'vue';
import { api } from '@/api';
import { defaultForm, type CreateForm as SeedreamCreateForm } from '@/seedream-ui';
import type { CreateForm as SeedanceCreateForm } from '@/seedance-ui';
import type { PlatformCapabilities } from '@/types';

export type CreationMode = 'image' | 'video';
export type GenerationSource = 'api-key' | 'forfuner-ai';
export type RecentGenerationFilter = CreationMode;
export type VideoFrameField = 'first_frame' | 'last_frame';
export interface CurrentGeneration {
  kind: CreationMode;
  localId: string;
}

export const RECENT_GENERATION_PAGE_SIZE = 12;

export function defaultVideoDraft(): SeedanceCreateForm {
  return {
    first_frame: '',
    last_frame: null,
    prompt: '',
    model: 'standard',
    resolution: '720p',
    ratio: 'adaptive',
    duration: 4,
    generate_audio: false,
    return_last_frame: false,
  };
}

export const useAICreationStore = defineStore('ai-creation', () => {
  const activeMode = ref<CreationMode>('image');
  const generationSource = ref<GenerationSource>('api-key');
  const imageDraft = reactive<SeedreamCreateForm>(defaultForm());
  const videoDraft = reactive<SeedanceCreateForm>(defaultVideoDraft());
  const videoPreviewUrls = reactive<Record<'first_frame' | 'last_frame', string>>({
    first_frame: '',
    last_frame: '',
  });
  const imagePreviewUrls = reactive<Record<'reference', string>>({ reference: '' });
  const imageDefaults = reactive<SeedreamCreateForm>(defaultForm());
  const videoDefaults = reactive<SeedanceCreateForm>(defaultVideoDraft());
  const imageInitialized = ref(false);
  const videoInitialized = ref(false);
  const currentGeneration = ref<CurrentGeneration | null>(null);
  const recentFilter = ref<RecentGenerationFilter>('image');
  const recentLoaded = reactive<Record<RecentGenerationFilter, number>>({
    image: RECENT_GENERATION_PAGE_SIZE,
    video: RECENT_GENERATION_PAGE_SIZE,
  });
  const workspaceScrollY = ref(0);
  const candidateHandoffPending = ref(false);
  const candidateHandoffError = ref('');

  // 平台可售能力清单：视频页与图片页共享同一份（拉取与缓存收敛在此处，避免两页各自漂移）。
  const capabilities = ref<PlatformCapabilities | null>(null);
  const capabilitiesLoading = ref(false);
  const capabilitiesError = ref('');
  let capabilitiesInFlight: Promise<boolean> | null = null;

  /**
   * 拉取能力清单。已在手且非强制时直接复用。
   *
   * 失败**不设兜底清单**（design D3）：回退到客户端预设模型表会把"选中后必然失败"
   * 的组合重新放出来；调用方据此阻断平台源提交。
   */
  async function ensureCapabilities(force = false): Promise<boolean> {
    if (!force && capabilities.value) return true;
    if (capabilitiesInFlight) return capabilitiesInFlight;
    capabilitiesLoading.value = true;
    capabilitiesError.value = '';
    capabilitiesInFlight = (async () => {
      try {
        const result = await api.platform.getCapabilities();
        if (!result.success) {
          capabilities.value = null;
          capabilitiesError.value = result.error?.message || 'CAPABILITIES_UNAVAILABLE';
          return false;
        }
        capabilities.value = result.data;
        return true;
      } catch (error) {
        capabilities.value = null;
        capabilitiesError.value = error instanceof Error ? error.message : 'CAPABILITIES_UNAVAILABLE';
        return false;
      } finally {
        capabilitiesLoading.value = false;
        capabilitiesInFlight = null;
      }
    })();
    return capabilitiesInFlight;
  }

  function clearCapabilities() {
    capabilities.value = null;
    capabilitiesError.value = '';
    capabilitiesLoading.value = false;
  }

  function initializeImageDraft(defaults: SeedreamCreateForm) {
    Object.assign(imageDefaults, defaults);
    if (!imageInitialized.value) {
      Object.assign(imageDraft, defaults);
      imageInitialized.value = true;
    }
  }

  function initializeVideoDraft(defaults: SeedanceCreateForm) {
    Object.assign(videoDefaults, defaults);
    if (!videoInitialized.value) {
      const pendingFirstFrame = videoDraft.first_frame;
      Object.assign(videoDraft, defaults);
      if (pendingFirstFrame) videoDraft.first_frame = pendingFirstFrame;
      videoInitialized.value = true;
    }
  }

  function resetImageDraft() {
    Object.assign(imageDraft, imageDefaults);
    imagePreviewUrls.reference = '';
  }

  function resetVideoDraft() {
    Object.assign(videoDraft, videoDefaults);
    videoPreviewUrls.first_frame = '';
    videoPreviewUrls.last_frame = '';
  }

  function imageDraftChanged() {
    return JSON.stringify(imageDraft) !== JSON.stringify(imageDefaults);
  }

  function videoDraftChanged() {
    return JSON.stringify(videoDraft) !== JSON.stringify(videoDefaults);
  }

  function setCurrentGeneration(generation: CurrentGeneration) {
    currentGeneration.value = generation;
    candidateHandoffError.value = '';
  }

  function setRecentFilter(filter: RecentGenerationFilter) {
    recentFilter.value = filter;
  }

  function setGenerationSource(source: GenerationSource) {
    generationSource.value = source;
  }

  function loadMoreRecent(filter: RecentGenerationFilter) {
    recentLoaded[filter] += RECENT_GENERATION_PAGE_SIZE;
  }

  function resetRecentLoaded(filter: RecentGenerationFilter) {
    recentLoaded[filter] = RECENT_GENERATION_PAGE_SIZE;
  }

  function rememberWorkspaceScroll(scrollY: number) {
    workspaceScrollY.value = Math.max(0, scrollY);
  }

  async function handoffCandidateToVideo(
    localId: string,
    attemptIndex: number,
    field: VideoFrameField = 'first_frame',
  ): Promise<boolean> {
    if (candidateHandoffPending.value) return false;
    candidateHandoffPending.value = true;
    candidateHandoffError.value = '';
    try {
      const result = await api.seedream.getHandoffImage(localId, attemptIndex);
      if (!result.success) {
        candidateHandoffError.value = result.error.message;
        return false;
      }
      const localPath = result.data.local_path;
      const thumbnail = await api.frame.getFrameThumbnail(localPath, 320);
      videoDraft[field] = localPath;
      videoPreviewUrls[field] = `data:image/png;base64,${thumbnail}`;
      activeMode.value = 'video';
      return true;
    } catch (error) {
      candidateHandoffError.value = error instanceof Error ? error.message : 'Unable to load candidate image';
      return false;
    } finally {
      candidateHandoffPending.value = false;
    }
  }

  return {
    activeMode,
    generationSource,
    imageDraft,
    videoDraft,
    videoPreviewUrls,
    imagePreviewUrls,
    currentGeneration,
    recentFilter,
    recentLoaded,
    workspaceScrollY,
    candidateHandoffPending,
    candidateHandoffError,
    capabilities,
    capabilitiesLoading,
    capabilitiesError,
    ensureCapabilities,
    clearCapabilities,
    initializeImageDraft,
    initializeVideoDraft,
    resetImageDraft,
    resetVideoDraft,
    imageDraftChanged,
    videoDraftChanged,
    setCurrentGeneration,
    setRecentFilter,
    setGenerationSource,
    loadMoreRecent,
    resetRecentLoaded,
    rememberWorkspaceScroll,
    handoffCandidateToVideo,
  };
});
