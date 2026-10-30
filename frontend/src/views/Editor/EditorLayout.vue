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
      <div class="min-w-0 flex-1 flex flex-col p-4">
        <!-- Step navigator -->
        <StepNavigator class="mb-4" />

        <!-- Player container -->
        <div class="flex flex-1 min-h-0 flex-col bg-black rounded-xl overflow-hidden border border-dark-border">
          <div v-if="frameRetouchEnabled" ref="frameToolbar" class="h-32 shrink-0 bg-dark-surface" data-test="frame-retouch-toolbar">
            <p v-if="!frameEditor" class="flex h-full items-center px-4 text-sm text-gray-400">{{ t('magicWand.idleHint') }}</p>
          </div>
          <div class="relative min-h-0 flex-1">
            <FramePlayer v-if="playerStore.frames.length > 0"
              :keyboard-disabled="frameEditorLoading || frameEditorSaving || navigationPending"
              :editing="!!frameEditor" :retouch-enabled="frameRetouchEnabled"
              :tools-disabled="frameEditorLoading || frameEditorSaving || navigationPending || processStore.isProcessing"
              :active-tool="frameEditor ? frameEditorTool : 'browse'" @tool="selectFrameTool">
              <SeedreamImageEraser v-if="frameEditor" ref="frameEditorRef"
                :image-url="frameEditor.imageUrl" :saving="frameEditorSaving" :magic-wand-enabled="true"
                :embedded="true" :toolbar-target="frameToolbar" :active-tool="frameEditorTool"
                :view-zoom="playerStore.zoom" :view-pan-x="playerStore.panX" :view-pan-y="playerStore.panY"
                :suspended="navigationPending || processStore.isProcessing" :error="frameEditorError"
                :title="t('magicWand.title', { filename: frameEditor.filename })"
                @cancel="closeFrameEditor" @apply="saveCurrentFrameEdit" />
            </FramePlayer>
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
        <p v-if="frameEditorError && !frameEditor" class="mt-2 text-sm text-danger" role="alert">{{ frameEditorError }}</p>
      </div>
    </main>
    <div v-if="navigationPending" class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      @keydown.esc.prevent="resolveFrameNavigation('stay')"
      @keydown="trapModalTab($event, $event.currentTarget as HTMLElement)">
      <section role="alertdialog" aria-modal="true" aria-labelledby="frame-unsaved-title" aria-describedby="frame-unsaved-hint"
        class="w-full max-w-lg rounded-xl border border-dark-border bg-dark-surface p-6 shadow-xl" data-test="frame-unsaved-dialog">
        <h2 id="frame-unsaved-title" class="text-lg font-semibold text-white">{{ t('magicWand.unsavedTitle') }}</h2>
        <p id="frame-unsaved-hint" class="mt-3 text-sm text-gray-400">{{ t('magicWand.unsavedHint') }}</p>
        <p v-if="frameEditorError" class="mt-3 text-sm text-danger" role="alert">{{ frameEditorError }}</p>
        <div class="mt-5 flex flex-wrap justify-end gap-2">
          <Button variant="primary" :loading="frameEditorSaving" @click="resolveFrameNavigation('save')">{{ t('magicWand.saveContinue') }}</Button>
          <Button ref="stayButton" variant="secondary" :disabled="frameEditorSaving" @click="resolveFrameNavigation('stay')">{{ t('magicWand.stay') }}</Button>
          <Button variant="danger" :disabled="frameEditorSaving" @click="resolveFrameNavigation('discard')">{{ t('magicWand.discard') }}</Button>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { onBeforeRouteLeave, useRouter, useRoute } from 'vue-router';
import { storeToRefs } from 'pinia';
import { useI18n } from 'vue-i18n';
import { EyeOff, Film, Undo2 } from 'lucide-vue-next';
import { useProjectStore } from '@/stores/project';
import { useProcessStore } from '@/stores/process';
import { usePlayerStore } from '@/stores/player';
import { api } from '@/api';
import { trapModalTab } from '@/modal-focus';
import Header from '@/components/layout/Header.vue';
import StepNavigator from '@/components/layout/StepNavigator.vue';
import FramePlayer from '@/components/player/FramePlayer.vue';
import PlayerControls from '@/components/player/PlayerControls.vue';
import Button from '@/components/common/Button.vue';
import Step1Extract from './Step1Extract.vue';
import Step2Background from './Step2Background.vue';
import Step3PostProcess from './Step3PostProcess.vue';
import SeedreamImageEraser from '@/components/seedream/SeedreamImageEraser.vue';

const router = useRouter();
const route = useRoute();
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
const frameEditor = ref<{ projectId: string; filename: string; imageUrl: string; revision: string; step: number } | null>(null);
const frameEditorLoading = ref(false);
const frameEditorSaving = ref(false);
const frameEditorError = ref('');
const frameEditorTool = ref<'wand' | 'brush' | 'browse'>('browse');
const frameToolbar = ref<HTMLElement | null>(null);
const frameEditorRef = ref<InstanceType<typeof SeedreamImageEraser> | null>(null);
const stayButton = ref<InstanceType<typeof Button> | null>(null);
const navigationPending = ref(false);
let resolveNavigation: ((allowed: boolean) => void) | null = null;

function beforeFrameNavigation(): boolean | Promise<boolean> {
  if (frameEditorLoading.value || frameEditorSaving.value || navigationPending.value || frameEditorRef.value?.busy) return false;
  if (!frameEditor.value) return true;
  if (!frameEditorRef.value?.dirty) {
    closeFrameEditor();
    return true;
  }
  navigationPending.value = true;
  void nextTick(() => stayButton.value?.$el.focus());
  return new Promise(resolve => { resolveNavigation = resolve; });
}

async function resolveFrameNavigation(choice: 'save' | 'discard' | 'stay') {
  if (frameEditorSaving.value || !resolveNavigation) return;
  if (choice === 'save') {
    const imageData = frameEditorRef.value?.getImageData();
    if (!imageData || !await saveCurrentFrameEdit(imageData)) return;
  }
  const resolve = resolveNavigation;
  resolveNavigation = null;
  navigationPending.value = false;
  if (choice !== 'stay') closeFrameEditor();
  resolve(choice !== 'stay');
}

playerStore.setNavigationGuard(beforeFrameNavigation);
processStore.setNavigationGuard(beforeFrameNavigation);
onBeforeRouteLeave(beforeFrameNavigation);

function beforeUnload(event: BeforeUnloadEvent) {
  if (!frameEditorRef.value?.dirty) return;
  event.preventDefault();
  event.returnValue = '';
}

function onToolShortcut(event: KeyboardEvent) {
  if (event.defaultPrevented || event.repeat || event.ctrlKey || event.metaKey || event.altKey
    || !frameRetouchEnabled.value || processStore.isProcessing
    || frameEditorRef.value?.busy) return;
  if (event.target instanceof Element
    && event.target.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="textbox"]')) return;
  const key = event.key.toLowerCase();
  const tool = key === 'w' ? 'wand' : key === 'e' ? 'brush' : key === 'v' ? 'browse' : null;
  if (!tool) return;
  event.preventDefault();
  selectFrameTool(tool);
}

onMounted(() => {
  window.addEventListener('beforeunload', beforeUnload);
  window.addEventListener('keydown', onToolShortcut);
});
onBeforeUnmount(() => {
  playerStore.setNavigationGuard(null);
  processStore.setNavigationGuard(null);
  resolveNavigation?.(false);
  window.removeEventListener('beforeunload', beforeUnload);
  window.removeEventListener('keydown', onToolShortcut);
});

function selectFrameTool(tool: 'wand' | 'brush' | 'browse') {
  if (frameEditorSaving.value || frameEditorLoading.value || navigationPending.value) return;
  if (frameEditor.value) frameEditorTool.value = tool;
  else if (tool !== 'browse') void openFrameEditor(tool);
}


function frameEditError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error);
  if (message.includes('FRAME_EDIT_STALE')) return t('magicWand.stale');
  if (message.includes('PROCESSING_ACTIVE')) return t('magicWand.processing');
  return t('magicWand.failed');
}

async function openFrameEditor(tool: 'wand' | 'brush') {
  const project = currentProject.value;
  const frame = playerStore.currentFrame;
  const step = currentStep.value;
  if (!project || !frame || !frameRetouchEnabled.value || processStore.isProcessing || frameEditorLoading.value) return;
  playerStore.pause();
  frameEditorLoading.value = true;
  frameEditorError.value = '';
  try {
    const editable = await api.frame.getEditableFrame(project.id, frame.filename, step);
    if (currentProject.value?.id !== project.id || currentStep.value !== step || playerStore.currentFrame?.filename !== frame.filename) return;
    frameEditorTool.value = tool;
    frameEditor.value = { projectId: project.id, filename: frame.filename, imageUrl: editable.image_data_url, revision: editable.revision, step };
  } catch (error) {
    frameEditorError.value = frameEditError(error);
  } finally {
    frameEditorLoading.value = false;
  }
}

function closeFrameEditor() {
  if (frameEditorSaving.value) return;
  frameEditor.value = null;
  frameEditorTool.value = 'browse';
  frameEditorError.value = '';
}

async function saveCurrentFrameEdit(imageDataUrl: string) {
  const editing = frameEditor.value;
  if (!editing || frameEditorSaving.value) return false;
  if (processStore.isProcessing) { frameEditorError.value = t('magicWand.processing'); return false; }
  frameEditorSaving.value = true;
  frameEditorError.value = '';
  try {
    const saved = await api.frame.saveFrameEdit(editing.projectId, editing.filename, imageDataUrl, editing.revision, editing.step);
    editing.revision = saved.revision;
    editing.imageUrl = imageDataUrl;
    frameEditorRef.value?.markSaved();
    playerStore.replaceFrameImage(editing.filename, imageDataUrl);
    return true;
  } catch (error) {
    frameEditorError.value = frameEditError(error);
    return false;
  } finally {
    frameEditorSaving.value = false;
  }
}

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

const frameRetouchEnabled = computed(() => currentStep.value === 3 && frameVisibilityEnabled.value);

// Load frames when step changes or project data changes
watch([currentStep, currentProject], async ([step]) => {
  if (!currentProject.value) return;
  if (frameEditor.value?.projectId === currentProject.value.id && frameEditor.value.step === step) return;
  const projectId = currentProject.value.id;
  const loaded = await loadFramesForStep(step);
  if (loaded && paramsLoaded.value && currentProject.value?.id === projectId && currentStep.value === step) signalEditorReady();
}, { immediate: true, deep: true });

function signalEditorReady() {
  window.dispatchEvent(new CustomEvent('agent-editor-ready', { detail: {
    project_id: currentProject.value?.id, step: currentStep.value,
  } }));
}

async function loadFramesForStep(step: number) {
  const project = currentProject.value;
  if (!project) return false;

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
  if (!isCurrentRequest()) return false;
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

    if (!isCurrentRequest()) return false;
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
      return isCurrentRequest();
    }
  } catch (e) {
    if (!isCurrentRequest()) return false;
    console.error('Failed to load frames:', e);
    playerStore.loadFrames([]);
    timelineFrameCount.value = 0;
  }
  return false;
}

async function hideCurrentFrame() {
  if (!await beforeFrameNavigation()) return;
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
  if (!await beforeFrameNavigation()) return;
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
  if (!await beforeFrameNavigation()) return;
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

  // Normal project navigation starts at Step 1; agent navigation keeps its validated target.
  const requestedStep = Number(route.query.agent_step);
  if ([1, 2, 3].includes(requestedStep)) processStore.goToStep(requestedStep);
  else processStore.goToStep(1);

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
  const loaded = await loadFramesForStep(currentStep.value);
  if (loaded) signalEditorReady();
});
</script>
