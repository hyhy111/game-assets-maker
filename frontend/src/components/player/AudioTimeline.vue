<template>
  <section class="border-t border-dark-border bg-dark-surface px-4 py-3" @pointerdown="resumeSelectionPreview">
    <div class="mb-2 flex items-center justify-between gap-3 text-xs">
      <div class="flex items-center gap-2 text-gray-300">
        <Volume2 class="h-4 w-4 text-primary" />
        <span class="font-medium">音效轨</span>
      </div>
      <span v-if="audioStore.loaded" class="text-gray-500">
        {{ audioStore.totalFrames }} 帧 · {{ audioStore.sourceFps.toFixed(1) }} fps
      </span>
    </div>

    <!-- 帧轨道：由 PlayerControls 通过 #track 注入，与下方片段轨道共享当前步骤动画轴 -->
    <div class="mt-2 mb-1">
      <slot name="track" />
    </div>

    <div
      v-if="!clipOnly"
      ref="waveformRef"
      class="relative h-20 select-none overflow-hidden rounded-lg border border-dark-border bg-dark-bg"
      @mousedown="onSelectionStart"
    >
      <!-- 加载中 -->
      <div v-if="isLoading" class="absolute inset-0 flex items-center justify-center text-xs text-gray-500">
        正在抽取源音频…
      </div>

      <!-- 错误 / 无音轨 -->
      <div v-else-if="errorMessage" class="absolute inset-0 flex flex-col items-center justify-center gap-1 text-xs">
        <span class="text-red-400">{{ errorMessage }}</span>
        <button
          type="button"
          class="rounded border border-dark-border px-2 py-0.5 text-gray-400 hover:border-gray-500 hover:text-white"
          @click.stop="emit('reloadAudio')"
        >
          重试
        </button>
      </div>

      <!-- 空状态（已加载但无峰值数据） -->
      <div v-else-if="audioStore.loaded && timelinePeaks.length === 0" class="absolute inset-0 flex items-center justify-center text-xs text-gray-500">
        源音频为空
      </div>

      <!-- 真实波形 + 选区 + 播放头 -->
      <template v-else>
        <svg
          class="absolute inset-0 h-full w-full text-primary/60"
          viewBox="0 0 1000 80"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <path
            :d="wavePath"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          />
        </svg>

        <!-- Source Region 选区 -->
        <div
          v-if="hasValidSelection"
          class="absolute inset-y-0 z-10 bg-primary/25 ring-1 ring-inset ring-primary/60"
          :style="selectionStyle"
          data-test="audio-selection"
        />

        <!-- 播放头 -->
        <div
          class="absolute inset-y-0 z-20 w-px bg-white"
          :style="playheadStyle"
        />
      </template>
    </div>

    <!-- 片段轨道（与波形共享同一帧轴） -->
    <div
      v-if="audioStore.loaded"
      ref="clipTrackRef"
      class="relative mt-1 h-20 overflow-hidden rounded border border-dark-border/60 bg-dark-bg/50"
      data-test="audio-clip-track"
      @mousedown="onTrackBackgroundMouseDown"
    >
      <div
        v-for="(clip, idx) in audioStore.clips"
        :key="`${clip.name}-${idx}`"
        class="absolute top-0.5 bottom-0.5 flex cursor-grab items-center justify-center overflow-hidden rounded border px-1 text-[10px] text-white"
        :class="isClipSelected(idx) ? 'border-white bg-primary/40 ring-1 ring-white z-10' : 'border-primary/50 bg-primary/20'"
        :style="clipStyle(clip)"
        :title="`${clip.name}: 源 ${clip.srcStartFrame}-${clip.srcEndFrame} → 放置 ${clip.placementFrame}`"
        :data-selected="isClipSelected(idx) ? 'true' : null"
        data-test="audio-clip"
        @mousedown.stop="onClipMouseDown($event, idx)"
      >
        <svg
          v-if="clipPeaksList[idx]?.length"
          class="pointer-events-none absolute inset-0 h-full w-full text-white/70"
          viewBox="0 0 100 80"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <path :d="peaksToWavePath(clipPeaksList[idx], 100, 80)" fill="none" stroke="currentColor" stroke-width="2" />
        </svg>
      </div>
      <!-- 框选矩形 -->
      <div
        v-if="isBoxSelecting"
        class="pointer-events-none absolute inset-y-0 z-20 border border-dashed border-primary/70 bg-primary/20"
        :style="boxSelectStyle"
        data-test="audio-box-select"
      />
      <!-- playhead（clipOnly：片段轨道上的当前帧，当前步骤动画轴） -->
      <div
        v-if="clipOnly"
        class="pointer-events-none absolute inset-y-0 z-20 w-px bg-white"
        :style="{ left: `${timelineFramePercent(props.currentFrame, timelineFrames)}%` }"
      />
    </div>

    <!-- 工具栏：选区信息 + 创建片段 + 删除（仅 Step 1） -->
    <div v-if="!clipOnly && audioStore.loaded" class="mt-2 flex items-center gap-3 text-xs">
      <span v-if="hasValidSelection" class="text-gray-400">
        选区：帧 {{ normalizedSelection.start }} – {{ normalizedSelection.end }}
        （{{ normalizedSelection.end - normalizedSelection.start }} 帧）
      </span>
      <span v-else-if="hasSelectedClips" class="text-gray-400">
        已选中 {{ audioStore.selectedClipIndices.length }} 个片段（Delete 删除）
      </span>
      <span v-else class="text-gray-500">在波形上拖动以选择 Source Region</span>

      <div class="ml-auto flex items-center gap-2">
        <button
          type="button"
          class="rounded border border-dark-border px-2 py-1 text-gray-300 transition hover:border-gray-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="!hasValidSelection || !audioBuffer || audioMuted"
          :title="audioMuted ? '已静音' : ''"
          data-test="preview-audio-selection"
          @click="previewSelection"
        >
          试听选区
        </button>
        <button
          type="button"
          class="rounded bg-primary px-2 py-1 font-medium text-dark-bg transition disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="!hasValidSelection"
          data-test="create-audio-clip"
          @click="createClipFromSelection"
        >
          创建 Audio Clip
        </button>
        <button
          type="button"
          class="rounded border border-primary/60 px-2 py-1 text-primary transition hover:bg-primary/15 disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="!audioStore.loaded"
          data-test="auto-create-audio-clips"
          @click="autoCreateClips"
        >
          自动创建
        </button>
        <button
          v-if="hasSelectedClips"
          type="button"
          class="rounded border border-red-500/60 px-2 py-1 text-red-400 transition hover:bg-red-500/20 hover:text-red-300"
          data-test="delete-audio-clip"
          @click="onDeleteSelected"
        >
          删除片段{{ audioStore.selectedClipIndices.length > 1 ? `（${audioStore.selectedClipIndices.length}）` : '' }}
        </button>
      </div>
    </div>

    <p v-if="!clipOnly && audioStore.clips.length > 0" class="mt-2 text-xs text-gray-500">
      已保存 {{ audioStore.clips.length }} 个片段。拖动片段可改位，选中后可删除（或 Delete 键）。
    </p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { storeToRefs } from 'pinia';
import { Volume2 } from 'lucide-vue-next';
import { useAudioTimelineStore } from '@/stores/audioTimeline';
import { usePlayerStore } from '@/stores/player';
import { useProcessStore } from '@/stores/process';
import {
  computeFrameAlignedPeaks,
  sliceFrameAlignedPeaks,
  peaksToWavePath,
  detectSoundSegments,
  createAudioPlaybackEngine,
} from '@/composables/audioPeaks';
import type { AudioClip } from '@/types';
import { frameFromTimelineRatio, timelineFramePercent } from './timelineMath';

const props = withDefaults(defineProps<{
  totalFrames: number;
  currentFrame: number;
  /** Step 2/3 只保留片段轨道（调位置），不显示原音轨波形/选区/创建工具 */
  clipOnly?: boolean;
  audioBuffer?: AudioBuffer | null;
  audioLoading?: boolean;
  audioError?: string | null;
  audioMuted?: boolean;
}>(), {
  clipOnly: false,
  audioBuffer: null,
  audioLoading: false,
  audioError: null,
  audioMuted: false,
});

const emit = defineEmits<{
  reloadAudio: [];
}>();

const audioStore = useAudioTimelineStore();
const playerStore = usePlayerStore();
const processStore = useProcessStore();
const { s1Params } = storeToRefs(processStore);
const audioBuffer = computed(() => props.audioBuffer);
const WAVEFORM_BUCKETS_PER_FRAME = 10;

// toAxis/fromAxis：片段 placementFrame（源帧）与当前步骤动画轴位置互转（Step 2/3 轴 = output 帧）
function toAxis(placementFrame: number): number {
  if (!props.clipOnly) return placementFrame;
  const start = s1Params.value?.start_frame ?? 0;
  const interval = Math.max(1, s1Params.value?.frame_interval ?? 1);
  return (placementFrame - start) / interval;
}
function fromAxis(axisPos: number): number {
  if (!props.clipOnly) return axisPos;
  const start = s1Params.value?.start_frame ?? 0;
  const interval = Math.max(1, s1Params.value?.frame_interval ?? 1);
  return start + axisPos * interval;
}

// 选区试听使用独立播放源；动画同步播放由常驻的 PlayerControls 持有。
const selectionPreviewEngine = createAudioPlaybackEngine();
watch(audioBuffer, (buffer) => selectionPreviewEngine.setBuffer(buffer), { immediate: true });
watch(() => props.audioMuted, (muted) => {
  if (muted) selectionPreviewEngine.stopAll();
});

function resumeSelectionPreview() {
  if (!props.audioMuted) selectionPreviewEngine.resume();
}

// 合并抽取与解码的加载/错误状态
const isLoading = computed(() => audioStore.loading || props.audioLoading);
const errorMessage = computed(() => audioStore.error || props.audioError);

// 帧轴：音频已加载时用源视频帧数，否则回退到 props（动画轴；二者在音效激活时相等）
const timelineFrames = computed(() => props.clipOnly ? (props.totalFrames || 1) : (audioStore.totalFrames || props.totalFrames || 1));

// 波形与现有帧轴使用同一时间范围：N 个帧位置对应 N - 1 个音频帧间隔。
const timelinePeaks = computed(() => {
  const buf = audioBuffer.value;
  const fps = audioStore.sourceFps;
  const frameIntervals = Math.max((audioStore.totalFrames || timelineFrames.value) - 1, 0);
  if (!buf || fps <= 0 || frameIntervals <= 0) return [];
  return computeFrameAlignedPeaks(buf.getChannelData(0), {
    sampleRate: buf.sampleRate,
    sourceFps: fps,
    timelineFrames: frameIntervals,
    bucketsPerFrame: WAVEFORM_BUCKETS_PER_FRAME,
  });
});

const wavePath = computed(() => peaksToWavePath(timelinePeaks.value, 1000, 80));

const playheadStyle = computed(() => {
  return { left: `${timelineFramePercent(props.currentFrame, timelineFrames.value)}%` };
});

// ------------------------------------------------------------------
// Source Region 选区（波形上拖动，Frame-aligned 整数帧）
// ------------------------------------------------------------------
const waveformRef = ref<HTMLDivElement | null>(null);
const selectionStart = ref(0);
const selectionEnd = ref(0);
const isSelecting = ref(false);

const normalizedSelection = computed(() => ({
  start: Math.min(selectionStart.value, selectionEnd.value),
  end: Math.max(selectionStart.value, selectionEnd.value),
}));

const hasValidSelection = computed(
  () => normalizedSelection.value.end > normalizedSelection.value.start,
);

const selectionStyle = computed(() => {
  if (!hasValidSelection.value) return { display: 'none' };
  const total = timelineFrames.value;
  const start = normalizedSelection.value.start;
  const end = normalizedSelection.value.end;
  const leftPct = timelineFramePercent(start, total);
  const widthPct = timelineFramePercent(end, total) - leftPct;
  return { left: `${leftPct}%`, width: `${widthPct}%` };
});

function frameFromClientX(clientX: number): number {
  const el = waveformRef.value;
  if (!el) return 0;
  const rect = el.getBoundingClientRect();
  const ratio = rect.width > 0 ? (clientX - rect.left) / rect.width : 0;
  return frameFromTimelineRatio(ratio, timelineFrames.value);
}

function onSelectionStart(e: MouseEvent) {
  if (!audioStore.loaded || timelinePeaks.value.length === 0) return;
  e.preventDefault();
  selectionPreviewEngine.stopAll();
  const frame = frameFromClientX(e.clientX);
  selectionStart.value = frame;
  selectionEnd.value = frame;
  isSelecting.value = true;
  document.addEventListener('mousemove', onSelectionMove);
  document.addEventListener('mouseup', onSelectionEnd);
}

function onSelectionMove(e: MouseEvent) {
  if (!isSelecting.value) return;
  selectionEnd.value = frameFromClientX(e.clientX);
}

function onSelectionEnd() {
  if (!isSelecting.value) return;
  isSelecting.value = false;
  document.removeEventListener('mousemove', onSelectionMove);
  document.removeEventListener('mouseup', onSelectionEnd);
}

/** 从当前选区创建片段；默认 placementFrame = 选区起始帧。 */
async function createClipFromSelection() {
  if (!hasValidSelection.value) return;
  const start = normalizedSelection.value.start;
  const end = normalizedSelection.value.end;
  const name = `片段 ${audioStore.clips.length + 1}`;
  await audioStore.createClip({
    name,
    srcStartFrame: start,
    srcEndFrame: end,
    placementFrame: start,
  });
  // 清除选区
  selectionStart.value = 0;
  selectionEnd.value = 0;
}

function previewSelection() {
  if (props.audioMuted || !hasValidSelection.value || !audioBuffer.value || audioStore.sourceFps <= 0) return;
  playerStore.pause();
  selectionPreviewEngine.stopAll();
  selectionPreviewEngine.playClip({
    name: '选区试听',
    srcStartFrame: normalizedSelection.value.start,
    srcEndFrame: normalizedSelection.value.end,
    placementFrame: 0,
  }, audioStore.sourceFps);
}

/**
 * 自动创建：分析音频，在当前帧范围 [startFrame, endFrame] 内检测有声音的连续段，
 * 批量生成 Audio Clip（placementFrame = srcStartFrame，即声音在源里的位置），一次落盘。
 */
async function autoCreateClips() {
  const buf = audioBuffer.value;
  const fps = audioStore.sourceFps;
  if (!buf || fps <= 0) return;
  const sr = buf.sampleRate;
  const data = buf.getChannelData(0);
  const startF = playerStore.startFrame;
  const endF = playerStore.endFrame;
  const startSample = Math.max(0, Math.floor((startF / fps) * sr));
  const endSample = Math.min(data.length, Math.ceil(((endF + 1) / fps) * sr));
  if (endSample <= startSample) return;
  const segments = detectSoundSegments(data.subarray(startSample, endSample), { sampleRate: sr });
  if (segments.length === 0) return;
  const base = audioStore.clips.length;
  const newClips: AudioClip[] = segments.map((seg, i) => {
    const srcStartFrame = Math.round(((startSample + seg.startSample) / sr) * fps);
    const srcEndFrame = Math.max(srcStartFrame + 1, Math.round(((startSample + seg.endSample) / sr) * fps));
    return {
      name: `片段 ${base + i + 1}`,
      srcStartFrame,
      srcEndFrame,
      placementFrame: srcStartFrame,
    };
  });
  audioStore.clips = [...audioStore.clips, ...newClips];
  await audioStore.save();
}

function clipStyle(clip: AudioClip) {
  const total = timelineFrames.value;
  const left = toAxis(clip.placementFrame);
  const span = Math.max(0, toAxis(clip.srcEndFrame) - toAxis(clip.srcStartFrame));
  const leftPct = timelineFramePercent(left, total);
  const widthPct = Math.max(0, Math.min(100 - leftPct, timelineFramePercent(left + span, total) - leftPct));
  return { left: `${leftPct}%`, width: `${widthPct}%` };
}

// 片段直接截取原始音轨的共享峰值，确保同一 Source Region 的波形形状完全一致。
const clipPeaksList = computed(() => audioStore.clips.map((clip) => (
  sliceFrameAlignedPeaks(
    timelinePeaks.value,
    clip.srcStartFrame,
    clip.srcEndFrame,
    WAVEFORM_BUCKETS_PER_FRAME,
  )
)));

// ------------------------------------------------------------------
// 片段交互（票 03）：选中、拖动改 placementFrame、删除
// ------------------------------------------------------------------
const clipTrackRef = ref<HTMLDivElement | null>(null);
const dragState = ref<{
  index: number;
  startClientX: number;
  startAxisPos: number;
  startPlacement: number;
} | null>(null);

// 选中状态（多选：selectedClipIndices）
const hasSelectedClips = computed(() => audioStore.selectedClipIndices.length > 0);
const isClipSelected = (idx: number) => audioStore.selectedClipIndices.includes(idx);

/** 片段轨道上的 clientX -> 整数帧（与波形共享同一帧轴）。 */
function frameFromClientXOnTrack(clientX: number): number {
  const el = clipTrackRef.value;
  if (!el) return 0;
  const rect = el.getBoundingClientRect();
  const ratio = rect.width > 0 ? (clientX - rect.left) / rect.width : 0;
  return frameFromTimelineRatio(ratio, timelineFrames.value);
}

/** 点片段：shift 累加选中，否则单选 + 进入拖动。实时改 placementFrame，松手后 save。 */
function onClipMouseDown(e: MouseEvent, idx: number) {
  if (!audioStore.loaded) return;
  e.preventDefault();
  if (e.shiftKey) {
    audioStore.selectClip(idx, true);
    return;
  }
  audioStore.selectClip(idx, false);
  const clip = audioStore.clips[idx];
  if (!clip) return;
  dragState.value = {
    index: idx,
    startClientX: e.clientX,
    startAxisPos: toAxis(clip.placementFrame),
    startPlacement: clip.placementFrame,
  };
  document.addEventListener('mousemove', onDragMove);
  document.addEventListener('mouseup', onDragEnd);
}

function onDragMove(e: MouseEvent) {
  const ds = dragState.value;
  if (!ds) return;
  const clip = audioStore.clips[ds.index];
  if (!clip) return;
  const total = timelineFrames.value;
  const spanAxis = Math.max(0, toAxis(clip.srcEndFrame) - toAxis(clip.srcStartFrame));
  const delta = frameFromClientXOnTrack(e.clientX) - frameFromClientXOnTrack(ds.startClientX);
  const nextAxis = Math.max(0, Math.min(total - spanAxis, ds.startAxisPos + delta));
  audioStore.moveClip(ds.index, fromAxis(nextAxis));
}

function onDragEnd() {
  const ds = dragState.value;
  dragState.value = null;
  document.removeEventListener('mousemove', onDragMove);
  document.removeEventListener('mouseup', onDragEnd);
  // 仅当 placementFrame 真正变化时落盘（纯点击不触发 save）
  if (ds) {
    const current = audioStore.clips[ds.index]?.placementFrame;
    if (current !== undefined && current !== ds.startPlacement) {
      audioStore.save();
    }
  }
}

// 框选多片段状态
const boxStart = ref<number | null>(null);
const boxEnd = ref<number | null>(null);
const isBoxSelecting = ref(false);

const boxSelectStyle = computed(() => {
  if (!isBoxSelecting.value || boxStart.value === null || boxEnd.value === null) return { display: 'none' };
  const total = timelineFrames.value;
  const lo = Math.min(boxStart.value, boxEnd.value);
  const hi = Math.max(boxStart.value, boxEnd.value);
  const leftPct = timelineFramePercent(lo, total);
  return { left: `${leftPct}%`, width: `${timelineFramePercent(hi, total) - leftPct}%` };
});

/** 在轨道空白处拖动：框选与之相交的片段。 */
function onTrackBackgroundMouseDown(e: MouseEvent) {
  if (!audioStore.loaded) return;
  e.preventDefault();
  if (props.clipOnly) {
    audioStore.clearSelection();
    return;
  }
  const frame = frameFromClientXOnTrack(e.clientX);
  boxStart.value = frame;
  boxEnd.value = frame;
  isBoxSelecting.value = true;
  audioStore.clearSelection();
  document.addEventListener('mousemove', onBoxSelectMove);
  document.addEventListener('mouseup', onBoxSelectEnd);
}

function onBoxSelectMove(e: MouseEvent) {
  if (!isBoxSelecting.value) return;
  boxEnd.value = frameFromClientXOnTrack(e.clientX);
  const lo = Math.min(boxStart.value!, boxEnd.value!);
  const hi = Math.max(boxStart.value!, boxEnd.value!);
  const indices: number[] = [];
  audioStore.clips.forEach((clip, idx) => {
    const left = toAxis(clip.placementFrame);
    const span = Math.max(0, toAxis(clip.srcEndFrame) - toAxis(clip.srcStartFrame));
    if (left <= hi && left + span >= lo) indices.push(idx);
  });
  audioStore.selectClips(indices);
}

function onBoxSelectEnd() {
  if (!isBoxSelecting.value) return;
  isBoxSelecting.value = false;
  boxStart.value = null;
  boxEnd.value = null;
  document.removeEventListener('mousemove', onBoxSelectMove);
  document.removeEventListener('mouseup', onBoxSelectEnd);
}

/** 删除所有选中片段（按钮入口；Delete/Backspace 键另有处理）。 */
async function onDeleteSelected() {
  await audioStore.deleteSelected();
}

function onKeyDown(e: KeyboardEvent) {
  if (e.defaultPrevented || document.querySelector('[role="dialog"][aria-modal="true"]')) return;
  const target = e.target as HTMLElement | null;
  const isEditing =
    target?.tagName === 'INPUT' ||
    target?.tagName === 'TEXTAREA' ||
    target?.isContentEditable === true;
  if (e.key === 'Escape') {
    audioStore.clearSelection();
  } else if (
    !props.clipOnly &&
    hasSelectedClips.value &&
    !isEditing &&
    (e.key === 'Delete' || e.key === 'Backspace')
  ) {
    e.preventDefault();
    void audioStore.deleteSelected();
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKeyDown);
});

onUnmounted(() => {
  selectionPreviewEngine.dispose();
  // 防止拖动/键盘监听器泄漏
  document.removeEventListener('mousemove', onSelectionMove);
  document.removeEventListener('mouseup', onSelectionEnd);
  document.removeEventListener('mousemove', onDragMove);
  document.removeEventListener('mouseup', onDragEnd);
  document.removeEventListener('mousemove', onBoxSelectMove);
  document.removeEventListener('mouseup', onBoxSelectEnd);
  window.removeEventListener('keydown', onKeyDown);
});
</script>
