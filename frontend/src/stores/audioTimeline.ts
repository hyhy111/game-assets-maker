/**
 * Audio Timeline Store - 管理音效时间线状态。
 *
 * 票 01：管理源 wav 引用、source_fps、total_frames、加载/错误状态。
 * 票 02：扩展 clips 数组 + load 时一并读 timeline + 建/改片段后持久化。
 * 票 03：选中活动片段、拖动改 placementFrame（live + 松手 save）、删除片段。
 */
import { defineStore } from 'pinia';
import { ref } from 'vue';
import { api } from '@/api';
import type { AudioClip } from '@/types';

/** 将 placementFrame clamp 到 [0, totalFrames - span]（无级，与 src 区间对齐）。 */
function clampPlacementFrame(clip: AudioClip, frame: number, total: number): number {
  const span = Math.max(0, clip.srcEndFrame - clip.srcStartFrame);
  const maxPlacement = Math.max(0, total - span);
  return Math.max(0, Math.min(maxPlacement, frame));
}

export const useAudioTimelineStore = defineStore('audioTimeline', () => {
  // 源音频元数据
  const sourceWav = ref('');
  const sourceFps = ref(0);
  const totalFrames = ref(0);

  // 片段数组（票 02）
  const clips = ref<AudioClip[]>([]);

  // 当前选中的片段索引集合（票 03 单选；框选扩展为多选；纯 UI 状态，不持久化）
  const selectedClipIndices = ref<number[]>([]);

  // 当前项目 id（save 时复用，createClip 内部持久化时使用）
  const currentProjectId = ref<string | null>(null);

  // 加载状态
  const loading = ref(false);
  const error = ref<string | null>(null);
  const loaded = ref(false);
  const playbackEnabled = ref(true);

  /**
   * 为项目抽取源音频并加载时间线（含已保存片段）。
   * 已缓存则复用；幂等--重复调用不会重复抽取。
   */
  async function load(projectId: string): Promise<void> {
    if (loading.value) return;
    loading.value = true;
    error.value = null;
    currentProjectId.value = projectId;
    try {
      const result = await api.audio.extractSourceAudio(projectId);
      if (result.success) {
        sourceWav.value = result.source_wav;
        sourceFps.value = result.source_fps;
        totalFrames.value = result.total_frames;
        loaded.value = true;
        // 读取已保存的时间线片段
        await loadTimeline(projectId);
      } else {
        sourceWav.value = '';
        sourceFps.value = 0;
        totalFrames.value = 0;
        clips.value = [];
        loaded.value = false;
        error.value = result.error || '音频抽取失败';
      }
    } catch (e) {
      sourceWav.value = '';
      sourceFps.value = 0;
      totalFrames.value = 0;
      clips.value = [];
      loaded.value = false;
      error.value = e instanceof Error ? e.message : '音频抽取失败';
    } finally {
      loading.value = false;
    }
  }

  /** 读取已保存的 audio_timeline.json，合并 clips 到 store。 */
  async function loadTimeline(projectId: string): Promise<void> {
    try {
      const timeline = await api.audio.loadTimeline(projectId);
      clips.value = Array.isArray(timeline.clips) ? [...timeline.clips] : [];
      // 以抽取结果为准，但时间线里的元数据可作为回退
      if (!sourceFps.value && timeline.source_fps) sourceFps.value = timeline.source_fps;
      if (!totalFrames.value && timeline.total_frames) totalFrames.value = timeline.total_frames;
      if (!sourceWav.value && timeline.source_wav) sourceWav.value = timeline.source_wav;
    } catch (e) {
      // 读取时间线失败不阻断加载（片段只是不可用，波形仍可显示）
      clips.value = [];
      console.warn('加载音效时间线失败:', e instanceof Error ? e.message : e);
    }
  }

  /** 持久化当前时间线到 audio_timeline.json。 */
  async function save(): Promise<void> {
    const projectId = currentProjectId.value;
    if (!projectId) return;
    try {
      await api.audio.saveTimeline(projectId, {
        source_fps: sourceFps.value,
        total_frames: totalFrames.value,
        source_wav: sourceWav.value,
        clips: clips.value,
      });
    } catch (e) {
      console.warn('保存音效时间线失败:', e instanceof Error ? e.message : e);
    }
  }

  /**
   * 从 Source Region 创建一个 Audio Clip，并入 store 并持久化。
   * 默认 placementFrame = 选区起始帧（初始置于选区位置）。
   */
  async function createClip(payload: {
    name: string;
    srcStartFrame: number;
    srcEndFrame: number;
    placementFrame?: number;
  }): Promise<void> {
    const placementFrame = payload.placementFrame ?? payload.srcStartFrame;
    const clip: AudioClip = {
      name: payload.name,
      srcStartFrame: payload.srcStartFrame,
      srcEndFrame: payload.srcEndFrame,
      placementFrame,
    };
    clips.value = [...clips.value, clip];
    await save();
  }

  /**
   * 选中片段。additive=true 时切换该索引的选中（shift 点击累加），否则单选该片段。
   * 纯 UI 状态，不持久化。
   */
  function selectClip(index: number, additive = false): void {
    if (index < 0 || index >= clips.value.length) return;
    if (additive) {
      const has = selectedClipIndices.value.includes(index);
      selectedClipIndices.value = has
        ? selectedClipIndices.value.filter((i) => i !== index)
        : [...selectedClipIndices.value, index];
    } else {
      selectedClipIndices.value = [index];
    }
  }

  /** 直接设置选中集合（框选用：传入与框相交的片段索引）。 */
  function selectClips(indices: number[]): void {
    selectedClipIndices.value = indices.slice().sort((a, b) => a - b);
  }

  /** 清空选中。 */
  function clearSelection(): void {
    selectedClipIndices.value = [];
  }

  /**
   * 拖动片段体时实时改 placementFrame（Frame-aligned + clamp）。
   * 仅更新状态、不持久化--持久化由松手后调用 save() 完成（避免拖动中频繁落盘）。
   */
  function moveClip(index: number, placementFrame: number): void {
    if (index < 0 || index >= clips.value.length) return;
    const clip = clips.value[index];
    const next = clampPlacementFrame(clip, placementFrame, totalFrames.value);
    clips.value = clips.value.map((c, i) => (i === index ? { ...c, placementFrame: next } : c));
  }

  /**
   * 删除所有选中片段并持久化（框选/多选批量删除）。
   * v1 重新裁剪 = 删除后重建，故删除即重裁路径（spec）。
   */
  async function deleteSelected(): Promise<void> {
    const toDelete = new Set(selectedClipIndices.value);
    if (toDelete.size === 0) return;
    clips.value = clips.value.filter((_, i) => !toDelete.has(i));
    selectedClipIndices.value = [];
    await save();
  }

  /** 删除单个指定片段（选中它再走 deleteSelected）。 */
  async function deleteClip(index: number): Promise<void> {
    if (index < 0 || index >= clips.value.length) return;
    selectedClipIndices.value = [index];
    await deleteSelected();
  }

  /** 重置状态（切换项目时调用） */
  function reset(): void {
    sourceWav.value = '';
    sourceFps.value = 0;
    totalFrames.value = 0;
    clips.value = [];
    selectedClipIndices.value = [];
    currentProjectId.value = null;
    loading.value = false;
    error.value = null;
    loaded.value = false;
    playbackEnabled.value = true;
  }

  return {
    sourceWav,
    sourceFps,
    totalFrames,
    clips,
    selectedClipIndices,
    loading,
    error,
    loaded,
    playbackEnabled,
    load,
    loadTimeline,
    save,
    createClip,
    selectClip,
    selectClips,
    clearSelection,
    moveClip,
    deleteClip,
    deleteSelected,
    reset,
  };
});
