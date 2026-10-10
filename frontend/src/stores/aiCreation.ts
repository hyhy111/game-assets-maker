import { defineStore } from 'pinia';
import { reactive, ref } from 'vue';
import { api } from '@/api';
import type { PyWebViewWindow } from '@/types/api';
import { readImageFile } from '@/seedream-image-drag';
import { defaultForm, type CreateForm as SeedreamCreateForm } from '@/seedream-ui';
import type { CreateForm as SeedanceCreateForm } from '@/seedance-ui';

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

  function initializeImageDraft(defaults: SeedreamCreateForm) {
    Object.assign(imageDefaults, defaults);
    if (!imageInitialized.value) {
      const factory = defaultForm();
      const pending = Object.fromEntries(Object.entries(imageDraft).filter(([key, value]) => value !== factory[key as keyof SeedreamCreateForm]));
      Object.assign(imageDraft, defaults, pending);
      imageInitialized.value = true;
    }
  }

  function initializeVideoDraft(defaults: SeedanceCreateForm) {
    Object.assign(videoDefaults, defaults);
    if (!videoInitialized.value) {
      const factory = defaultVideoDraft();
      const pending = Object.fromEntries(Object.entries(videoDraft).filter(([key, value]) => value !== factory[key as keyof SeedanceCreateForm]));
      Object.assign(videoDraft, defaults, pending);
      videoInitialized.value = true;
    }
  }

  async function patchAgentDraft(kind: CreationMode, patch: Record<string, unknown>) {
    const draft = kind === 'image' ? imageDraft : videoDraft;
    const snapshot = JSON.stringify(draft);
    const normalized = { ...patch };
    if (kind === 'image' && normalized.reference_image === null) normalized.reference_image = '';
    if (kind === 'video' && normalized.last_frame === '') normalized.last_frame = null;
    const candidate = { ...draft, ...normalized };
    const validated = await (window as PyWebViewWindow).pywebview?.api.agent_validate_draft(kind, candidate);
    if (!validated?.success) throw new Error(validated?.error || 'INPUT_INVALID');
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
    if (JSON.stringify(draft) !== snapshot) throw new Error('DRAFT_CHANGED');
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

  function dismissCurrentGeneration() {
    currentGeneration.value = null;
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
    videoPreviewUrls,
    imagePreviewUrls,
    currentGeneration,
    recentFilter,
    recentLoaded,
    workspaceScrollY,
    candidateHandoffPending,
    candidateHandoffError,
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
