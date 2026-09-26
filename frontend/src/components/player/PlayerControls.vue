<template>
  <div>
    <div class="flex items-center gap-4 px-4 py-3 bg-dark-surface border-t border-dark-border">
    <!-- Play/Pause button -->
    <button
      class="p-2 rounded-lg bg-primary hover:bg-primary-600 text-dark-bg transition-colors"
      @pointerdown="resumeAudioPlayback"
      @click="playerStore.togglePlay()"
    >
      <Play
        v-if="!isPlaying"
        class="w-5 h-5"
      />
      <Pause
        v-else
        class="w-5 h-5"
      />
    </button>

    <!-- Frame navigation -->
    <div class="flex items-center gap-2">
      <button
        class="p-1.5 rounded hover:bg-dark-border text-gray-400 hover:text-white transition-colors"
        :disabled="!canGoPrev"
        @click="playerStore.prevFrame()"
      >
        <SkipBack class="w-5 h-5" />
      </button>

      <span class="text-sm text-gray-400 min-w-[80px] text-center">
        {{ currentTimelineFrame }} / {{ timelineEndFrame }}
      </span>

      <button
        class="p-1.5 rounded hover:bg-dark-border text-gray-400 hover:text-white transition-colors"
        :disabled="!canGoNext"
        @click="playerStore.nextFrame()"
      >
        <SkipForward class="w-5 h-5" />
      </button>
    </div>

    <!-- Range slider (dual handle) — 音效轨展开时移入下方音效面板与波形对齐 -->
    <div class="flex-1 mx-4 flex items-center">
      <RangeSlider
        v-if="!(processStore.currentStep === 1 && showAudioTimeline)"
        :total-frames="timelineTotalFrames"
        :start-frame="timelineStartFrame"
        :end-frame="timelineEndFrame"
        :current-frame="currentTimelineFrame"
        :simple="processStore.currentStep > 1"
        @update:start-frame="onStartFrameChange"
        @update:end-frame="onEndFrameChange"
        @update:current-frame="onCurrentFrameChange"
      />
    </div>

    <!-- Playback settings -->
    <div class="flex items-center gap-2">
      <span class="text-xs text-gray-500">FPS</span>
      <div class="relative">
        <input
          ref="fpsInputRef"
          :value="playbackFps"
          type="number"
          min="1"
          max="120"
          class="w-20 bg-dark-surface border border-dark-border rounded px-2 py-1 pr-5 text-sm text-gray-300 text-center focus:outline-none focus:ring-1 focus:ring-primary"
          @input="onFpsInput"
          @blur="onFpsBlur"
          @keydown="onFpsKeydown"
        >
        <div class="absolute inset-y-1 right-1 w-4 flex flex-col border-l border-dark-border">
          <button
            type="button"
            class="flex-1 flex items-center justify-center hover:bg-dark-border rounded-tr text-gray-400 hover:text-white transition-colors"
            @mousedown.prevent="stepFps(1)"
          >
            <ChevronUp class="w-3 h-3" />
          </button>
          <button
            type="button"
            class="flex-1 flex items-center justify-center hover:bg-dark-border rounded-br text-gray-400 hover:text-white transition-colors"
            @mousedown.prevent="stepFps(-1)"
          >
            <ChevronDown class="w-3 h-3" />
          </button>
        </div>
      </div>
    </div>
    <div class="flex items-center gap-1.5">
      <button
        v-if="processStore.currentStep === 1"
        type="button"
        data-test="audio-track-toggle"
        :aria-expanded="showAudioTimeline"
        :class="[
          'flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors',
          showAudioTimeline
            ? 'border-primary bg-primary/15 text-primary'
            : 'border-dark-border text-gray-400 hover:border-gray-500 hover:text-white'
        ]"
        @click="showAudioTimeline = !showAudioTimeline"
      >
        <span
          class="audio-track-wave"
          :class="{ 'audio-track-wave--active': showAudioTimeline }"
          aria-hidden="true"
        >
          <span />
          <span />
          <span />
          <span />
        </span>
        <span>音效轨</span>
        <ChevronDown
          class="h-3.5 w-3.5 transition-transform duration-200"
          :class="showAudioTimeline ? 'rotate-180' : ''"
          aria-hidden="true"
        />
      </button>
      <button
        type="button"
        data-test="audio-mute-toggle"
        :aria-label="audioPlaybackEnabled ? '静音' : '取消静音'"
        :title="audioPlaybackEnabled ? '静音' : '取消静音'"
        :aria-pressed="!audioPlaybackEnabled"
        :class="[
          'grid h-9 w-9 place-items-center rounded-lg border transition-colors',
          audioPlaybackEnabled
            ? 'border-dark-border text-gray-400 hover:border-gray-500 hover:text-white'
            : 'border-primary bg-primary/15 text-primary'
        ]"
        @click="toggleAudioPlayback"
      >
        <Volume2 v-if="audioPlaybackEnabled" class="h-4 w-4" aria-hidden="true" />
        <VolumeX v-else class="h-4 w-4" aria-hidden="true" />
      </button>
    </div>
    </div>

    <AudioTimeline
      v-if="processStore.currentStep === 1 && showAudioTimeline"
      :total-frames="timelineTotalFrames"
      :current-frame="currentTimelineFrame"
      :audio-buffer="audioBuffer"
      :audio-loading="isAudioLoading"
      :audio-error="audioError"
      :audio-muted="!audioPlaybackEnabled"
      @reload-audio="loadAudioRuntime"
    >
      <template #track>
        <RangeSlider
          :total-frames="timelineTotalFrames"
          :start-frame="timelineStartFrame"
          :end-frame="timelineEndFrame"
          :current-frame="currentTimelineFrame"
          :simple="processStore.currentStep > 1"
          @update:start-frame="onStartFrameChange"
          @update:end-frame="onEndFrameChange"
          @update:current-frame="onCurrentFrameChange"
        />
      </template>
    </AudioTimeline>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { storeToRefs } from 'pinia';
import { Play, Pause, SkipBack, SkipForward, ChevronUp, ChevronDown, Volume2, VolumeX } from 'lucide-vue-next';
import { usePlayerStore } from '@/stores/player';
import { useProcessStore } from '@/stores/process';
import { useAudioTimelineStore } from '@/stores/audioTimeline';
import { useProjectStore } from '@/stores/project';
import {
  createAudioPlaybackEngine,
  createAudioSyncController,
  useAudioWaveform,
} from '@/composables/audioPeaks';
import RangeSlider from './RangeSlider.vue';
import AudioTimeline from './AudioTimeline.vue';
import {
  nearestVisibleFrameIndex,
  sourceFrameFromTimelineFrame,
  timelineFrameForVisibleIndex,
} from './timelineMath';

const props = withDefaults(defineProps<{
  timelineFrameCount?: number;
}>(), {
  timelineFrameCount: 0,
});

const playerStore = usePlayerStore();
const processStore = useProcessStore();
const audioStore = useAudioTimelineStore();
const projectStore = useProjectStore();

const { isPlaying, currentIndex, totalFrames, playbackFps, canGoNext, canGoPrev, startFrame, endFrame } = storeToRefs(playerStore);
const { s1Params } = storeToRefs(processStore);
const { playbackEnabled: audioPlaybackEnabled } = storeToRefs(audioStore);

const fpsInputRef = ref<HTMLInputElement | null>(null);
const showAudioTimeline = ref(false);

// 音频运行时常驻在播放器控制层；折叠 AudioTimeline 只影响编辑 UI。
const { peaks, audioBuffer, loading: wavLoading, error: wavError, load: loadWaveform } = useAudioWaveform();
const audioEngine = createAudioPlaybackEngine();
const syncController = createAudioSyncController({ audioStore, engine: audioEngine });
const isAudioLoading = computed(() => audioStore.loading || wavLoading.value);
const audioError = computed(() => audioStore.error || wavError.value);
const audioPlaybackActive = computed(() => audioPlaybackEnabled.value);
const timelineTotalFrames = computed(() => (
  processStore.currentStep === 1
    ? totalFrames.value
    : Math.max(props.timelineFrameCount, totalFrames.value)
));
const currentTimelineFrame = computed(() => (
  processStore.currentStep === 1
    ? currentIndex.value
    : timelineFrameForVisibleIndex(playerStore.frames, currentIndex.value)
));
const timelineStartFrame = computed(() => processStore.currentStep === 1 ? startFrame.value : 0);
const timelineEndFrame = computed(() => (
  processStore.currentStep === 1
    ? endFrame.value
    : Math.max(0, timelineTotalFrames.value - 1)
));

function mapToSource(frame: number): number {
  if (processStore.currentStep === 1) return frame;
  const start = s1Params.value?.start_frame ?? 0;
  const interval = Math.max(1, s1Params.value?.frame_interval ?? 1);
  const timelineFrame = timelineFrameForVisibleIndex(playerStore.frames, frame);
  return sourceFrameFromTimelineFrame(timelineFrame, start, interval);
}

watch(audioBuffer, (buffer) => audioEngine.setBuffer(buffer));
playerStore.setFrameAdvanceHook((prev, next) => {
  if (!audioPlaybackActive.value) return;
  syncController.onFrameAdvance(mapToSource(prev), mapToSource(next));
});

const stopWatchPlaying = watch(
  () => playerStore.isPlaying,
  (playing) => {
    if (playing && audioPlaybackActive.value) audioEngine.resume();
    else audioEngine.stopAll();
  },
);
const stopWatchAudioPlayback = watch(audioPlaybackActive, (active) => {
  if (!active) audioEngine.stopAll();
});
const stopWatchFrame = watch(
  () => playerStore.currentIndex,
  (frame) => syncController.onFrameChanged(mapToSource(frame)),
);

async function loadAudioRuntime() {
  const projectId = projectStore.projectId;
  if (!projectId) return;
  await audioStore.load(projectId);
  if (audioStore.sourceWav) {
    await loadWaveform(audioStore.sourceWav, 1000);
  }
}

onMounted(loadAudioRuntime);

watch(() => projectStore.projectId, (newId, oldId) => {
  if (newId === oldId) return;
  audioStore.reset();
  peaks.value = [];
  audioBuffer.value = null;
  audioEngine.setBuffer(null);
  if (newId) void loadAudioRuntime();
});

onUnmounted(() => {
  playerStore.setFrameAdvanceHook(null);
  stopWatchPlaying();
  stopWatchFrame();
  stopWatchAudioPlayback();
  audioEngine.dispose();
});

function resumeAudioPlayback() {
  if (audioPlaybackActive.value) audioEngine.resume();
}

function toggleAudioPlayback() {
  audioPlaybackEnabled.value = !audioPlaybackEnabled.value;
  if (!audioPlaybackEnabled.value) audioEngine.stopAll();
}

function stepFps(delta: number) {
  if (!fpsInputRef.value) return;
  fpsInputRef.value.stepUp(delta);
  onFpsInput({ target: fpsInputRef.value } as unknown as Event);
  onFpsBlur({ target: fpsInputRef.value } as unknown as Event);
}

function onStartFrameChange(value: number) {
  playerStore.startFrame = value;
  // 仅 Step 1 同步到抽取参数；Step 2/3 的播放范围不是源帧抽取范围，写回会污染 s1Params
  if (processStore.currentStep === 1) s1Params.value.start_frame = value;
}

function onEndFrameChange(value: number) {
  playerStore.endFrame = value;
  if (processStore.currentStep === 1) s1Params.value.end_frame = value;
}

function onCurrentFrameChange(value: number) {
  const visibleIndex = processStore.currentStep === 1
    ? value
    : nearestVisibleFrameIndex(playerStore.frames, value);
  playerStore.goToFrame(visibleIndex);
}

function onFpsInput(event: Event) {
  const target = event.target as HTMLInputElement;
  let value = Number(target.value);
  // Allow empty input while typing
  if (target.value === '' || isNaN(value)) return;
  // Clamp value between 1 and 120
  value = Math.max(1, Math.min(120, value));
  playerStore.setPlaybackFps(value);
  // Sync to step1 params
  s1Params.value.fps = value;
}

function onFpsBlur(event: Event) {
  const target = event.target as HTMLInputElement;
  let value = Number(target.value);
  // Default to 30 if empty or invalid
  if (target.value === '' || isNaN(value)) {
    value = 30;
  }
  // Clamp value between 1 and 120
  value = Math.max(1, Math.min(120, value));
  // Update input display and store
  target.value = String(value);
  playerStore.setPlaybackFps(value);
  // Sync to step1 params
  s1Params.value.fps = value;
}

function onFpsKeydown(event: KeyboardEvent) {
  // Blur input on Enter key to confirm input
  if (event.key === 'Enter') {
    const target = event.target as HTMLInputElement;
    target.blur();
  }
}
</script>

<style scoped>
/* Hide default number spinner arrows */
input[type="number"]::-webkit-inner-spin-button,
input[type="number"]::-webkit-outer-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

/* Firefox */
input[type="number"] {
  -moz-appearance: textfield;
}

.audio-track-wave {
  display: inline-flex;
  width: 1rem;
  height: 1rem;
  align-items: center;
  justify-content: center;
  gap: 2px;
}

.audio-track-wave span {
  width: 2px;
  border-radius: 9999px;
  background: currentColor;
  transform-origin: center;
}

.audio-track-wave span:nth-child(1) { height: 0.375rem; }
.audio-track-wave span:nth-child(2) { height: 0.75rem; }
.audio-track-wave span:nth-child(3) { height: 1rem; }
.audio-track-wave span:nth-child(4) { height: 0.625rem; }

.audio-track-wave--active span {
  animation: audio-track-wave 650ms ease-in-out infinite alternate;
}

.audio-track-wave--active span:nth-child(2) { animation-delay: -180ms; }
.audio-track-wave--active span:nth-child(3) { animation-delay: -360ms; }
.audio-track-wave--active span:nth-child(4) { animation-delay: -90ms; }

@keyframes audio-track-wave {
  from { transform: scaleY(0.5); }
  to { transform: scaleY(1); }
}

@media (prefers-reduced-motion: reduce) {
  .audio-track-wave--active span {
    animation: none;
  }
}
</style>
