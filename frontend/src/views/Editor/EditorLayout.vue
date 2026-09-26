<template>
  <div class="h-screen flex flex-col bg-dark-bg">
    <Header full-width />

    <main class="flex-1 flex overflow-hidden">
      <!-- Left sidebar - Step configuration -->
      <aside class="w-80 border-r border-dark-border bg-dark-surface overflow-y-auto">
        <component
          :is="currentStepComponent"
          v-if="projectStore.currentProject && paramsLoaded"
        />
        <div
          v-else-if="!paramsLoaded"
          class="p-4 text-gray-500"
        >
          <p>{{ t('common.loading') }}</p>
        </div>
      </aside>

      <!-- Center - Player -->
      <div class="flex-1 flex flex-col p-4">
        <!-- Step navigator -->
        <StepNavigator class="mb-4" />

        <!-- Player container -->
        <div class="flex-1 min-h-0 bg-black rounded-xl overflow-hidden border border-dark-border">
          <FramePlayer v-if="playerStore.frames.length > 0" />
          <div
            v-else
            class="h-full flex items-center justify-center text-gray-500"
          >
            <div class="text-center">
              <Film class="w-16 h-16 mx-auto mb-4 opacity-30" />
              <p>{{ hiddenFrames.length > 0 ? t('frameVisibility.allHidden') : t('common.loading') }}</p>
            </div>
          </div>
        </div>

        <!-- Player controls -->
        <PlayerControls
          v-if="playerStore.frames.length > 0"
          :timeline-frame-count="timelineFrameCount"
          class="mt-4 rounded-xl"
        />

        <div
          v-if="frameVisibilityEnabled"
          class="mt-3 flex items-center justify-between gap-3 rounded-xl border border-dark-border bg-dark-surface px-4 py-3"
        >
          <div>
            <p class="text-sm text-gray-300">
              {{ t('frameVisibility.hiddenCount', { count: hiddenFrames.length }) }}
            </p>
            <p class="text-xs text-gray-500">
              {{ t('frameVisibility.hint') }}
            </p>
          </div>
          <div class="flex flex-wrap justify-end gap-2">
            <Button
              variant="danger"
              size="sm"
              :disabled="!playerStore.currentFrame || visibilityUpdating || processStore.isProcessing"
              @click="hideCurrentFrame"
            >
              <EyeOff class="mr-1.5 h-4 w-4" />
              {{ t('frameVisibility.hideCurrent') }}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              :disabled="hiddenFrames.length === 0 || visibilityUpdating || processStore.isProcessing"
              @click="restoreLastHiddenFrame"
            >
              <Undo2 class="mr-1.5 h-4 w-4" />
              {{ t('frameVisibility.restoreLast') }}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              :disabled="hiddenFrames.length === 0 || visibilityUpdating || processStore.isProcessing"
              @click="restoreAllHiddenFrames"
            >
              {{ t('frameVisibility.restoreAll') }}
            </Button>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { storeToRefs } from 'pinia';
import { useI18n } from 'vue-i18n';
import { EyeOff, Film, Undo2 } from 'lucide-vue-next';
import { useProjectStore } from '@/stores/project';
import { useProcessStore } from '@/stores/process';
import { usePlayerStore } from '@/stores/player';
import { api } from '@/api';
import Header from '@/components/layout/Header.vue';
import StepNavigator from '@/components/layout/StepNavigator.vue';
import FramePlayer from '@/components/player/FramePlayer.vue';
import PlayerControls from '@/components/player/PlayerControls.vue';
import Button from '@/components/common/Button.vue';
import Step1Extract from './Step1Extract.vue';
import Step2Background from './Step2Background.vue';
import Step3PostProcess from './Step3PostProcess.vue';

const router = useRouter();
const projectStore = useProjectStore();
const processStore = useProcessStore();
const playerStore = usePlayerStore();
const { t } = useI18n();

const { currentProject } = storeToRefs(projectStore);
const { currentStep, s1Params } = storeToRefs(processStore);

// Params loaded state
const paramsLoaded = ref(false);
const hiddenFrames = ref<string[]>([]);
const timelineFrameCount = ref(0);
const visibilityUpdating = ref(false);
let frameLoadRequestId = 0;

// Step components mapping
const stepComponents = {
  1: Step1Extract,
  2: Step2Background,
  3: Step3PostProcess
};

const currentStepComponent = computed(() => {
  return stepComponents[currentStep.value as keyof typeof stepComponents];
});

const frameVisibilityEnabled = computed(() => (
  (currentStep.value === 2 || currentStep.value === 3)
  && projectStore.isStepCompleted(currentStep.value)
));

// Load frames when step changes or project data changes
watch([currentStep, currentProject], async ([step]) => {
  if (!currentProject.value) return;
  await loadFramesForStep(step);
}, { immediate: true, deep: true });

async function loadFramesForStep(step: number) {
  const project = currentProject.value;
  if (!project) return;

  const requestId = ++frameLoadRequestId;
  const isCurrentRequest = () => (
    requestId === frameLoadRequestId
    && currentProject.value?.id === project.id
    && currentStep.value === step
  );

  // Clear current frames to show loading state
  playerStore.loadFrames([]);
  timelineFrameCount.value = 0;
  const nextHiddenFrames = step > 1
    ? await api.frame.getHiddenFrames(project.id)
    : [];
  if (!isCurrentRequest()) return;
  hiddenFrames.value = nextHiddenFrames;

  // Determine which step's frames to show
  // Show the output of the current step if completed, otherwise show the previous step's output
  let sourceStep = step;
  if (step === 2 && !projectStore.isStepCompleted(2)) {
    sourceStep = 1; // Show input frames (step 1 output) if step 2 results not ready
  } else if (step === 3 && !projectStore.isStepCompleted(3)) {
    sourceStep = 2; // Show step 2 results if step 3 not ready
  }

  // Ensure sourceStep 1 shows output/01_frames (not cache) if we are in Step 2 preview
  // The backend already prefers cache for step 1, but for Step 2 preview we want the filtered frames
  
  try {
    const response = await api.frame.getFrames(
      project.id,
      sourceStep,
      1,
      500, // Increase page size to see more frames in sequence
      !(step === 2 && sourceStep === 1) // Disable cache only if previewing Step 1 results in Step 2
    );

    if (!isCurrentRequest()) return;
    if (response.success) {
      playerStore.loadFrames(response.frames);
      timelineFrameCount.value = response.timeline_total ?? response.total;
      
      if (step === 1 && s1Params.value) {
        // Sync playback range from Step1 params ONLY for Step 1.
        // s1Params.start_frame/end_frame 是源帧空间（cache 索引）。
        const total = response.frames.length;
        const startSrc = Math.max(0, s1Params.value.start_frame);
        if (total > startSrc) {
          // cache 已加载（帧数覆盖 start），按 s1Params 范围设置
          const end = s1Params.value.end_frame > 0 ? Math.min(s1Params.value.end_frame, total - 1) : total - 1;
          playerStore.setPlaybackRange(startSrc, end, Math.max(1, s1Params.value.frame_interval));
        } else {
          // 加载到 output（帧数少于 start_frame，如 Step2 后切换回来），源帧范围不适用，播放全部已加载帧
          playerStore.setPlaybackRange(0, Math.max(0, total - 1), Math.max(1, s1Params.value.frame_interval));
        }
      } else {
        // For Step 2 and 3, play the entire sequence loop correctly
        // Response frames are already sequential from output dir
        playerStore.setPlaybackRange(0, response.frames.length - 1, 1);
      }
    }
  } catch (e) {
    if (!isCurrentRequest()) return;
    console.error('Failed to load frames:', e);
    playerStore.loadFrames([]);
    timelineFrameCount.value = 0;
  }
}

async function hideCurrentFrame() {
  const project = currentProject.value;
  const frame = playerStore.currentFrame;
  if (!project || !frame) return;

  const nextIndex = playerStore.currentIndex;
  visibilityUpdating.value = true;
  playerStore.pause();
  try {
    const result = await api.frame.setFrameHidden(project.id, frame.filename, true);
    hiddenFrames.value = result.hidden_frames;
    await loadFramesForStep(currentStep.value);
    playerStore.goToFrame(Math.min(nextIndex, playerStore.frames.length - 1));
  } finally {
    visibilityUpdating.value = false;
  }
}

async function restoreLastHiddenFrame() {
  const project = currentProject.value;
  const filename = hiddenFrames.value[hiddenFrames.value.length - 1];
  if (!project || !filename) return;

  visibilityUpdating.value = true;
  try {
    const result = await api.frame.setFrameHidden(project.id, filename, false);
    hiddenFrames.value = result.hidden_frames;
    await loadFramesForStep(currentStep.value);
  } finally {
    visibilityUpdating.value = false;
  }
}

async function restoreAllHiddenFrames() {
  const project = currentProject.value;
  if (!project || hiddenFrames.value.length === 0) return;

  visibilityUpdating.value = true;
  try {
    const result = await api.frame.restoreHiddenFrames(project.id);
    hiddenFrames.value = result.hidden_frames;
    await loadFramesForStep(currentStep.value);
  } finally {
    visibilityUpdating.value = false;
  }
}

onMounted(async () => {
  // Redirect if no project selected
  if (!currentProject.value) {
    router.push('/');
    return;
  }

  // A Pinia store survives project navigation, but each newly opened action starts at Step 1.
  processStore.goToStep(1);

  // Refresh project status from backend (important for steps state)
  await projectStore.loadProject(currentProject.value.id);

  // Load saved step parameters for all steps
  // Only load params if the step has been processed, otherwise use frontend defaults
  await processStore.loadStepParams(currentProject.value.id, 1);
  if (projectStore.isStepCompleted(2)) {
    await processStore.loadStepParams(currentProject.value.id, 2);
  }
  if (projectStore.isStepCompleted(3)) {
    await processStore.loadStepParams(currentProject.value.id, 3);
  }

  // Mark params as loaded so child components can render
  paramsLoaded.value = true;

  // The initial watcher can run before Step 1 parameters arrive.
  await loadFramesForStep(currentStep.value);
});
</script>
