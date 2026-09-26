<template>
  <div class="p-4 space-y-6">
    <div>
      <h2 class="text-lg font-semibold text-white mb-1">
        {{ t('step1.title') }}
      </h2>
      <p class="text-sm text-gray-500">
        {{ t('step1.description') }}
      </p>
    </div>

    <ModelStatusCard
      :status="modelStatus"
      @retry="processStore.retryModel($event)"
    />

    <!-- Frame Interval setting -->
    <div class="space-y-2">
      <label class="block text-sm font-medium text-gray-300">{{ t('step1.frameInterval') }}</label>
      <div class="flex items-center gap-2 justify-between">
        <Input
          v-model.number="s1Params.frame_interval"
          type="number"
          min="1"
          :max="maxFrame"
          class="w-20"
          @blur="clampFrameInterval"
        />
        <Button
          variant="ghost"
          size="sm"
          @click="autoCalculateInterval"
        >
          <Calculator class="w-4 h-4 mr-1" />
          {{ t('step1.autoCalculate') }}
        </Button>
      </div>
      <p class="text-xs text-gray-500">
        {{ t('step1.intervalDesc', { interval: s1Params.frame_interval }) }}
      </p>
    </div>

    <!-- Frame range -->
    <div class="space-y-2">
      <div class="flex items-center gap-4">
        <!-- Start frame -->
        <div class="flex-1 space-y-1">
          <label class="block text-sm font-medium text-gray-300">{{ t('step1.startFrame') }}</label>
          <div class="flex items-center gap-2">
            <Input
              v-model.number="s1Params.start_frame"
              type="number"
              :min="0"
              :max="maxFrame"
              class="w-20"
              @blur="clampStartFrame"
            />
            <button
              class="p-2 rounded-lg bg-dark-surface border border-green-500/50 shadow-lg shadow-green-500/25 transition-all"
              :title="t('step1.useCurrentFrame')"
              @click="setStartToCurrent"
            >
              <Circle class="w-5 h-5 text-green-500 fill-green-500" />
            </button>
          </div>
        </div>

        <!-- End frame -->
        <div class="flex-1 space-y-1">
          <label class="block text-sm font-medium text-gray-300">{{ t('step1.endFrame') }}</label>
          <div class="flex items-center gap-2">
            <Input
              v-model.number="s1Params.end_frame"
              type="number"
              :min="0"
              :max="maxFrame"
              class="w-20"
              @blur="clampEndFrame"
            />
            <button
              class="p-2 rounded-lg bg-dark-surface border border-red-500/50 shadow-lg shadow-red-500/25 transition-all"
              :title="t('step1.useCurrentFrame')"
              @click="setEndToCurrent"
            >
              <Circle class="w-5 h-5 text-red-500 fill-red-500" />
            </button>
          </div>
        </div>
      </div>
      <p class="text-xs text-gray-500">
        {{ t('step1.selectedRange', { count: s1Params.end_frame - s1Params.start_frame + 1, start: s1Params.start_frame, end: s1Params.end_frame }) }}
      </p>
    </div>

    <!-- Estimated frames -->
    <div
      v-if="projectStore.currentProject"
      class="p-3 bg-primary/10 border border-primary/30 rounded-lg"
    >
      <p class="text-sm text-primary">
        {{ t('step1.estimatedFrames', { count: estimatedFrames }) }}
      </p>
    </div>

    <!-- Status -->
    <div
      v-if="isStepCompleted"
      class="p-3 bg-success-500/10 border border-success-500/30 rounded-lg"
    >
      <div class="flex items-center gap-2 text-success-500">
        <CheckCircle class="w-5 h-5" />
        <span class="text-sm">{{ t('step1.completed') }}</span>
      </div>
      <p class="text-xs text-gray-500 mt-1">
        {{ t('step1.extractedFrames', { count: stepStatus?.count ?? 0 }) }}
      </p>
    </div>

    <!-- Action buttons -->
    <div class="space-y-3 pt-4">
      <Button
        block
        :loading="isProcessing"
        @click="startProcessing"
      >
        <Play class="w-4 h-4 mr-2" />
        {{ isStepCompleted ? t('step1.reExtract') : t('step1.startExtraction') }}
      </Button>

      <Button
        v-if="isProcessing"
        variant="danger"
        block
        @click="cancelProcessing"
      >
        <X class="w-4 h-4 mr-2" />
        {{ t('common.cancel') }}
      </Button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { storeToRefs } from 'pinia';
import { useI18n } from 'vue-i18n';
import { Play, CheckCircle, X, Calculator, Circle } from 'lucide-vue-next';
import { useProjectStore } from '@/stores/project';
import { useProcessStore } from '@/stores/process';
import { usePlayerStore } from '@/stores/player';
import { api } from '@/api';
import type { VideoInfo } from '@/types';
import Button from '@/components/common/Button.vue';
import Input from '@/components/common/Input.vue';
import ModelStatusCard from '@/components/editor/ModelStatusCard.vue';

const projectStore = useProjectStore();
const processStore = useProcessStore();
const playerStore = usePlayerStore();
const { t } = useI18n();

const { s1Params, isProcessing, s2Params, modelStatus } = storeToRefs(processStore);
const { currentIndex } = storeToRefs(playerStore);

const isStepCompleted = computed(() => projectStore.isStepCompleted(1));
const stepStatus = computed(() => projectStore.currentProject?.steps?.['1']);

const videoInfo = ref<VideoInfo>({ success: false });
const maxFrame = computed(() =>
  videoInfo.value.frame_count ? videoInfo.value.frame_count - 1 : 0
);

onMounted(async () => {
  if (!projectStore.currentProject) return;

  // Background preload model for Step 2
  processStore.preloadModel(s2Params.value.model);

  const path = projectStore.currentProject.video_path;
  if (!path) return;

  try {
    videoInfo.value = await api.video.getVideoInfo(path);
    const total = videoInfo.value.frame_count ?? 0;
    if (total > 0) {
      // Only set defaults if params haven't been loaded from saved config
      // Check if this looks like uninitialized params (end_frame is -1 or 0 with start_frame 0)
      const hasSavedParams = s1Params.value.end_frame > 0 || s1Params.value.start_frame > 0 || s1Params.value.frame_interval !== 1;

      if (!hasSavedParams) {
        // Replace legacy -1 default with actual last frame index
        if (s1Params.value.end_frame === -1 || s1Params.value.end_frame === 0) {
          s1Params.value.end_frame = total - 1;
        }
        // Initial clamp
        clampStartFrame();
        clampEndFrame();
      }

      // Sync range to player (whether loaded or default)
      playerStore.setPlaybackRange(
        s1Params.value.start_frame,
        s1Params.value.end_frame,
        s1Params.value.frame_interval
      );
    }
  } catch (e) {
    console.error('Failed to load video info:', e);
  }
});

function clampStartFrame() {
  const max = maxFrame.value;
  let val = Math.max(0, Math.min(s1Params.value.start_frame, max));
  if (val > s1Params.value.end_frame) {
    val = s1Params.value.end_frame;
  }
  s1Params.value.start_frame = val;
  // Sync to player
  playerStore.startFrame = val;
}

function clampEndFrame() {
  const max = maxFrame.value;
  let val = Math.max(0, Math.min(s1Params.value.end_frame, max));
  if (val < s1Params.value.start_frame) {
    val = s1Params.value.start_frame;
  }
  s1Params.value.end_frame = val;
  // Sync to player
  playerStore.endFrame = val;
}

function clampFrameInterval() {
  const max = maxFrame.value;
  const val = Math.max(1, Math.min(s1Params.value.frame_interval, max));
  s1Params.value.frame_interval = val;
  // Sync to player
  playerStore.frameInterval = val;
}

// Check if a number is prime
function isPrime(n: number): boolean {
  if (n < 2) return false;
  if (n === 2) return true;
  if (n % 2 === 0) return false;
  for (let i = 3; i <= Math.sqrt(n); i += 2) {
    if (n % i === 0) return false;
  }
  return true;
}

// Get the largest non-prime number less than n
function getPrevNonPrime(n: number): number {
  for (let i = n - 1; i >= 1; i--) {
    if (!isPrime(i)) return i;
  }
  return 1;
}

// Get all divisors of a number
function getDivisors(n: number): number[] {
  const divisors: number[] = [];
  for (let i = 1; i <= n; i++) {
    if (n % i === 0) divisors.push(i);
  }
  return divisors;
}

// Auto calculate frame interval
function autoCalculateInterval() {
  const start = s1Params.value.start_frame;
  const end = s1Params.value.end_frame;
  const length = end - start + 1;

  if (length <= 0) return;

  // If length is prime, find the largest non-prime less than it
  let n: number;
  if (isPrime(length)) {
    n = getPrevNonPrime(length);
  } else {
    n = length;
  }

  // Get all divisors of n
  const divisors = getDivisors(n);

  // Take the middle value
  const idx = Math.floor(divisors.length / 2);
  s1Params.value.frame_interval = divisors[idx];
  // Sync to player
  playerStore.frameInterval = divisors[idx];
}

const estimatedFrames = computed(() => {
  if (!videoInfo.value.frame_count) return 'Unknown';
  const range = s1Params.value.end_frame - s1Params.value.start_frame + 1;
  const interval = s1Params.value.frame_interval;
  return Math.max(0, Math.ceil(range / interval));
});

async function startProcessing() {
  if (!projectStore.currentProject) return;

  // Stop playback before processing
  playerStore.pause();

  // Mark as processed
  s1Params.value.processed = true;

  // First time processing: set fps to 10
  if (!isStepCompleted.value) {
    s1Params.value.fps = 10;
    playerStore.setPlaybackFps(10);
  }

  // Pass all step 1 parameters including video_path
  const params = {
    video_path: projectStore.currentProject.video_path,
    start_frame: s1Params.value.start_frame,
    end_frame: s1Params.value.end_frame,
    frame_interval: s1Params.value.frame_interval,
    fps: s1Params.value.fps,
    processed: true
  };

  await processStore.startProcessing(projectStore.currentProject.id, 1, params);
}

async function cancelProcessing() {
  await processStore.cancelProcessing();
}

function setStartToCurrent() {
  const frame = currentIndex.value;
  if (frame >= 0 && frame <= maxFrame.value) {
    s1Params.value.start_frame = frame;
    playerStore.startFrame = frame;
    clampStartFrame();
  }
}

function setEndToCurrent() {
  const frame = currentIndex.value;
  if (frame >= 0 && frame <= maxFrame.value) {
    s1Params.value.end_frame = frame;
    playerStore.endFrame = frame;
    clampEndFrame();
  }
}
</script>
