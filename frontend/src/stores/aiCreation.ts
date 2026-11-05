import { defineStore } from 'pinia';
import { nextTick, reactive, ref } from 'vue';
import { api } from '@/api';
import type { PyWebViewWindow } from '@/types/api';
import { readImageFile } from '@/seedream-image-drag';
import { correctPlatformImageParameters, defaultForm, type CreateForm as SeedreamCreateForm } from '@/seedream-ui';
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
    model: 'mini',
    resolution: '720p',
    ratio: '16:9',
    duration: 4,
    generate_audio: true,
    return_last_frame: true,
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
  const defaultModelIds = reactive({ image: '', video: '' });
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
    if (capabilitiesInFlight) return capabilitiesInFlight;
    if (!force && capabilities.value) return true;
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

  function initializeImageDraft(defaults: SeedreamCreateForm, defaultModelId = '') {
    Object.assign(imageDefaults, defaults);
    defaultModelIds.image = defaultModelId || defaults.model;
    if (!imageInitialized.value) {
      const factory = defaultForm();
      const pending = Object.fromEntries(Object.entries(imageDraft).filter(([key, value]) => value !== factory[key as keyof SeedreamCreateForm]));
      Object.assign(imageDraft, defaults, pending);
      if (generationSource.value === 'forfuner-ai' && !pending.model) imageDraft.model = defaultModelId || defaults.model;
      imageInitialized.value = true;
    }
  }

  function initializeVideoDraft(defaults: SeedanceCreateForm, defaultModelId = '') {
    Object.assign(videoDefaults, defaults);
    defaultModelIds.video = defaultModelId || defaults.model;
    if (!videoInitialized.value) {
      const factory = defaultVideoDraft();
      const pending = Object.fromEntries(Object.entries(videoDraft).filter(([key, value]) => value !== factory[key as keyof SeedanceCreateForm]));
      Object.assign(videoDraft, defaults, pending);
      if (generationSource.value === 'forfuner-ai' && !pending.model) videoDraft.model = defaultModelId || defaults.model;
      videoInitialized.value = true;
    }
  }

  async function patchAgentDraft(kind: CreationMode, patch: Record<string, unknown>) {
    const source = generationSource.value;
    if (kind === 'image' && source === 'forfuner-ai') {
      const usedCachedCapabilities = capabilities.value !== null && capabilitiesInFlight === null;
      if (!await ensureCapabilities()) throw new Error(capabilitiesError.value || 'CAPABILITIES_UNAVAILABLE');
      // Let the mounted form apply newly loaded options before reading its selection.
      await nextTick();
      const desired = { ...imageDraft, ...patch };
      const entry = capabilities.value?.image.models.find(model => model.model === desired.model);
      if (usedCachedCapabilities && (!entry || !entry.sizes?.includes(desired.resolution))) {
        if (!await ensureCapabilities(true)) throw new Error(capabilitiesError.value || 'CAPABILITIES_UNAVAILABLE');
        await nextTick();
      }
      if (generationSource.value !== source) throw new Error('DRAFT_CHANGED');
    }
    const draft = kind === 'image' ? imageDraft : videoDraft;
    const snapshot = JSON.stringify(draft);
    const capabilitySnapshot = capabilities.value;
    const normalized = { ...patch };
    if (kind === 'image' && normalized.reference_image === null) normalized.reference_image = '';
    if (kind === 'video' && normalized.last_frame === '') normalized.last_frame = null;
    const candidate = { ...draft, ...normalized };
    if (kind === 'image' && source === 'forfuner-ai') {
      const models = capabilities.value?.image.models ?? [];
      if (!models.length) throw new Error('NO_AVAILABLE_MODELS');
      const entry = models.find(model => model.model === candidate.model);
      if (!entry && Object.prototype.hasOwnProperty.call(patch, 'model')) throw new Error('UNSUPPORTED_MODEL');
      const selected = entry ?? models[0];
      if (!selected.sizes?.length) throw new Error('UNSUPPORTED_RESOLUTION');
      if (Object.prototype.hasOwnProperty.call(patch, 'resolution') && !selected.sizes.includes(candidate.resolution)) {
        throw new Error('UNSUPPORTED_RESOLUTION');
      }
      Object.assign(candidate, correctPlatformImageParameters(candidate.model, candidate.resolution as SeedreamCreateForm['resolution'], models));
    }
    const validationValues = kind === 'image' ? { ...candidate, source } : candidate;
    const validated = await (window as PyWebViewWindow).pywebview?.api.agent_validate_draft(kind, validationValues);
    if (!validated?.success) throw new Error(validated?.error || 'INPUT_INVALID');
    if (kind === 'image' && typeof validated.draft?.model === 'string') candidate.model = validated.draft.model;
    const previews: Record<string, string> = {};
    const imageFields = kind === 'image' ? ['reference_image'] : ['first_frame', 'last_frame'];
    for (const field of imageFields) {
      if (!Object.prototype.hasOwnProperty.call(patch, field)) continue;
      const path = patch[field];
      if (!path) previews[field] = '';
      else {
        const thumbnail = await api.frame.getFrameThumbnail(String(path), 320);
        if (!thumbnail) throw new Error('Image preview unavailable');
        previews[field] = `data:image/png;base64,${thumbnail}`;
      }
    }
    if (JSON.stringify(draft) !== snapshot || generationSource.value !== source
      || (kind === 'image' && source === 'forfuner-ai' && capabilities.value !== capabilitySnapshot)) {
      throw new Error('DRAFT_CHANGED');
    }
    Object.assign(draft, candidate);
    if (kind === 'image') {
      imageInitialized.value = true;
      if (Object.prototype.hasOwnProperty.call(previews, 'reference_image')) imagePreviewUrls.reference = previews.reference_image;
    } else {
      videoInitialized.value = true;
      if (Object.prototype.hasOwnProperty.call(previews, 'first_frame')) videoPreviewUrls.first_frame = previews.first_frame;
      if (Object.prototype.hasOwnProperty.call(previews, 'last_frame')) videoPreviewUrls.last_frame = previews.last_frame;
    }
    activeMode.value = kind;
    return { kind, draft: { ...draft } };
  }

  function resetImageDraft() {
    Object.assign(imageDraft, imageDefaults);
    if (generationSource.value === 'forfuner-ai') imageDraft.model = defaultModelIds.image;
    imagePreviewUrls.reference = '';
  }

  function resetVideoDraft() {
    Object.assign(videoDraft, videoDefaults);
    if (generationSource.value === 'forfuner-ai') videoDraft.model = defaultModelIds.video;
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
    setRecentFilter(generation.kind);
    candidateHandoffError.value = '';
  }

  function dismissCurrentGeneration() {
    currentGeneration.value = null;
    candidateHandoffError.value = '';
  }

  function setRecentFilter(filter: RecentGenerationFilter) {
    recentFilter.value = filter;
  }

  function setGenerationSource(source: GenerationSource) {
    if (generationSource.value === source) return;
    generationSource.value = source;
    imageDraft.model = source === 'forfuner-ai' ? defaultModelIds.image : imageDefaults.model;
    videoDraft.model = source === 'forfuner-ai' ? defaultModelIds.video : videoDefaults.model;
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
      if (!thumbnail) throw new Error('Image preview unavailable');
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

  async function setImageInput(path: string, field: 'reference' | VideoFrameField): Promise<void> {
    const thumbnail = await api.frame.getFrameThumbnail(path, 320);
    if (!thumbnail) throw new Error('Image preview unavailable');
    const previewUrl = `data:image/png;base64,${thumbnail}`;
    if (field === 'reference') {
      imageDraft.reference_image = path;
      imagePreviewUrls.reference = previewUrl;
    } else {
      videoDraft[field] = path;
      videoPreviewUrls[field] = previewUrl;
    }
  }

  async function handoffCandidateToImage(localId: string, attemptIndex: number): Promise<boolean> {
    if (candidateHandoffPending.value) return false;
    candidateHandoffPending.value = true;
    candidateHandoffError.value = '';
    try {
      const result = await api.seedream.getHandoffImage(localId, attemptIndex);
      if (!result.success) throw new Error(result.error.message);
      await setImageInput(result.data.local_path, 'reference');
      activeMode.value = 'image';
      return true;
    } catch (error) {
      candidateHandoffError.value = error instanceof Error ? error.message : 'Image unavailable';
      return false;
    } finally {
      candidateHandoffPending.value = false;
    }
  }

  async function importDroppedImage(file: File, field: 'reference' | VideoFrameField): Promise<boolean> {
    if (candidateHandoffPending.value) return false;
    candidateHandoffPending.value = true;
    candidateHandoffError.value = '';
    try {
      const result = await api.seedream.importReferenceImage(await readImageFile(file), file.name);
      if (!result.success) throw new Error(result.error.message);
      await setImageInput(result.path, field);
      return true;
    } catch (error) {
      candidateHandoffError.value = error instanceof Error ? error.message : 'Image unavailable';
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
    imageInitialized,
    videoInitialized,
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
    dismissCurrentGeneration,
    setRecentFilter,
    setGenerationSource,
    loadMoreRecent,
    resetRecentLoaded,
    rememberWorkspaceScroll,
    handoffCandidateToVideo,
    handoffCandidateToImage,
    importDroppedImage,
    setImageInput,
    patchAgentDraft,
  };
});
