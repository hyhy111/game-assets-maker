<template>
  <div class="h-screen flex flex-col bg-dark-bg">
    <Header full-width />

    <main class="flex-1 flex overflow-hidden">
      <!-- Left sidebar - Step configuration -->
      <aside class="w-80 border-r border-dark-border bg-dark-surface overflow-y-auto">
        <component
          :is="currentStepComponent"
          v-if="projectStore.currentProject && paramsLoaded"
          @reset-post-processing="openPostProcessingReset()"
          @undo-post-processing="openPostProcessingReset('last')"
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
          <div
            v-if="frameRetouchEnabled"
            ref="frameToolbar"
            class="h-32 shrink-0 bg-dark-surface"
            data-test="frame-retouch-toolbar"
          >
            <p
              v-if="!frameEditor"
              class="flex h-full items-center px-4 text-sm text-gray-400"
            >
              {{ t('magicWand.idleHint') }}
            </p>
          </div>
          <div
            ref="frameViewport"
            class="relative min-h-0 flex-1 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary"
            role="region"
            :aria-label="t('player.framePreview')"
            tabindex="-1"
          >
            <FramePlayer
              v-if="playerStore.frames.length > 0"
              :keyboard-disabled="frameEditorLoading || frameEditorSaving || navigationPending || postProcessingResetOpen"
              :editing="!!frameEditor"
              :retouch-enabled="frameRetouchEnabled"
              :tools-disabled="visibilityUpdating || frameEditorLoading || frameEditorSaving || navigationPending || processStore.isProcessing"
              :active-tool="frameEditor ? frameEditorTool : 'browse'"
              :preview-frame-index="previewFrameIndex"
              @preview-step="stepCandidateFrame"
              @preview-cancel="closeFramePicker(true)"
              @preview-ready="readyPreviewFrame = $event"
              @tool="selectFrameTool"
            >
              <SeedreamImageEraser
                v-if="frameEditor"
                ref="frameEditorRef"
                :image-url="frameEditor.imageUrl"
                :original-image-url="frameEditor.originalImageUrl"
                :initial-restore-unsupported="frameEditor.initialRestoreUnsupported"
                :saving="frameEditorSaving"
                :magic-wand-enabled="true"
                :embedded="true"
                :toolbar-target="frameToolbar"
                :active-tool="frameEditorTool"
                :view-zoom="playerStore.zoom"
                :view-pan-x="playerStore.panX"
                :view-pan-y="playerStore.panY"
                :suspended="navigationPending || processStore.isProcessing || postProcessingResetOpen"
                :error="frameEditorError"
                :title="t('magicWand.title', { filename: frameEditor.filename })"
                @cancel="closeFrameEditor"
                @apply="saveCurrentFrameEdit"
              />
            </FramePlayer>
            <div
              v-else
              class="h-full flex items-center justify-center text-gray-500"
            >
              <div class="text-center">
                <Film class="w-16 h-16 mx-auto mb-4 opacity-30" />
                <p
                  v-if="previewLoadFailed"
                  role="alert"
                >
                  {{ t('previewCleanup.loadFailed') }}
                </p>
                <p v-else>
                  {{ hiddenFrames.length > 0 ? t('frameVisibility.allHidden') : t('common.loading') }}
                </p>
              </div>
            </div>
          </div>
          <FramePicker
            v-if="framePicker"
            :key="framePicker.baseFrame"
            v-bind="framePicker"
            :can-replace="canReplaceFrame"
            @step="stepCandidateFrame"
            @compare="framePicker.showCurrent = !framePicker.showCurrent"
            @restore="setCandidateFrame(framePicker.baseFrame)"
            @close="closeFramePicker(true)"
            @replace="selectReplacementFrame"
          />
        </div>

        <!-- Player controls -->
        <PlayerControls
          v-if="playerStore.frames.length > 0"
          :timeline-frame-count="timelineFrameCount"
          :active-base-frame="framePicker?.baseFrame"
          :preview-frame-index="previewFrameIndex"
          class="mt-4 rounded-xl"
          @edit-frame="openFramePicker"
        />

        <HiddenFramesPanel
          v-if="frameVisibilityEnabled"
          :key="currentProject?.id"
          :filenames="hiddenFrames"
          :previews="hiddenFramePreviews"
          :can-hide="!!playerStore.currentFrame"
          :busy="visibilityUpdating || navigationPending || processStore.isProcessing"
          :error="frameVisibilityError"
          @hide="hideCurrentFrame"
          @restore="restoreHiddenFrame"
          @restore-all="restoreAllHiddenFrames"
        />
        <p
          v-if="frameEditorError && !frameEditor"
          class="mt-2 text-sm text-danger"
          role="alert"
        >
          {{ frameEditorError }}
        </p>
      </div>
    </main>
    <div
      v-if="navigationPending"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      @keydown.esc.prevent="resolveFrameNavigation('stay')"
      @keydown="trapModalTab($event, $event.currentTarget as HTMLElement)"
    >
      <section
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="frame-unsaved-title"
        aria-describedby="frame-unsaved-hint"
        class="w-full max-w-lg rounded-xl border border-dark-border bg-dark-surface p-6 shadow-xl"
        data-test="frame-unsaved-dialog"
      >
        <h2
          id="frame-unsaved-title"
          class="text-lg font-semibold text-white"
        >
          {{ t('magicWand.unsavedTitle') }}
        </h2>
        <p
          id="frame-unsaved-hint"
          class="mt-3 text-sm text-gray-400"
        >
          {{ t('magicWand.unsavedHint') }}
        </p>
        <p
          v-if="frameEditorError"
          class="mt-3 text-sm text-danger"
          role="alert"
        >
          {{ frameEditorError }}
        </p>
        <div class="mt-5 flex flex-wrap justify-end gap-2">
          <Button
            variant="primary"
            :loading="frameEditorSaving"
            @click="resolveFrameNavigation('save')"
          >
            {{ t('magicWand.saveContinue') }}
          </Button>
          <Button
            ref="stayButton"
            variant="secondary"
            :disabled="frameEditorSaving"
            @click="resolveFrameNavigation('stay')"
          >
            {{ t('magicWand.stay') }}
          </Button>
          <Button
            variant="danger"
            :disabled="frameEditorSaving"
            @click="resolveFrameNavigation('discard')"
          >
            {{ t('magicWand.discard') }}
          </Button>
        </div>
      </section>
    </div>
    <Dialog
      v-if="postProcessingResetOpen"
      :open="true"
      class="fixed inset-0 z-50"
      @close="closePostProcessingReset"
    >
      <div
        class="absolute inset-0 bg-black/70"
        aria-hidden="true"
      />
      <div class="relative grid h-full place-items-center overflow-y-auto p-4">
        <DialogPanel
          class="w-full max-w-lg rounded-xl border border-dark-border bg-dark-surface p-6 shadow-xl"
          data-test="step3-reset-dialog"
        >
          <DialogTitle class="text-lg font-semibold text-white">
            {{ postProcessingResetTitle }}
          </DialogTitle>
          <DialogDescription class="mt-3 text-sm text-gray-400">
            {{ t(postProcessingResetMode === 'last' ? 'step3.undoProcessingHint' : 'step3.resetAllHint') }}
          </DialogDescription>
          <p
            v-if="postProcessingResetError"
            class="mt-3 text-sm text-danger"
            role="alert"
          >
            {{ postProcessingResetError }}
          </p>
          <div class="mt-5 flex flex-wrap justify-end gap-2">
            <Button
              variant="secondary"
              :disabled="resettingPostProcessing"
              @click="closePostProcessingReset"
            >
              {{ t('common.cancel') }}
            </Button>
            <Button
              variant="danger"
              :loading="resettingPostProcessing"
              data-test="step3-reset-confirm"
              @click="resetPostProcessing"
            >
              {{ postProcessingResetTitle }}
            </Button>
          </div>
        </DialogPanel>
      </div>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { onBeforeRouteLeave, useRouter, useRoute } from 'vue-router';
import { storeToRefs } from 'pinia';
import { useI18n } from 'vue-i18n';
import { Film } from 'lucide-vue-next';
import { Dialog, DialogDescription, DialogPanel, DialogTitle } from '@headlessui/vue';
import { useProjectStore } from '@/stores/project';
import { useProcessStore } from '@/stores/process';
import { usePlayerStore } from '@/stores/player';
import { api } from '@/api';
import type { HiddenFramePreview, HiddenFramesResponse } from '@/types';
import { trapModalTab } from '@/modal-focus';
import Header from '@/components/layout/Header.vue';
import StepNavigator from '@/components/layout/StepNavigator.vue';
import FramePlayer from '@/components/player/FramePlayer.vue';
import FramePicker from '@/components/player/FramePicker.vue';
import HiddenFramesPanel from '@/components/player/HiddenFramesPanel.vue';
import PlayerControls from '@/components/player/PlayerControls.vue';
import { extractionFrameIndices } from '@/components/player/timelineMath';
import Button from '@/components/common/Button.vue';
import Step1Extract from './Step1Extract.vue';
import Step2Background from './Step2Background.vue';
import Step3PostProcess from './Step3PostProcess.vue';
import SeedreamImageEraser from '@/components/seedream/SeedreamImageEraser.vue';
import { logEvent } from '@/debug/request-log';

const router = useRouter();
const route = useRoute();
const projectStore = useProjectStore();
const processStore = useProcessStore();
const playerStore = usePlayerStore();
const { t } = useI18n();

const { currentProject } = storeToRefs(projectStore);
const { currentStep, s1Params } = storeToRefs(processStore);

const frameViewport = ref<HTMLElement | null>(null);
const framePicker = ref<{
  baseFrame: number;
  currentFrame: number;
  minFrame: number;
  maxFrame: number;
  candidate: number;
  showCurrent: boolean;
} | null>(null);
const previewFrameIndex = computed(() => {
  const picker = framePicker.value;
  return picker?.showCurrent ? picker.currentFrame : picker?.candidate;
});
const readyPreviewFrame = ref<number>();
const canReplaceFrame = computed(() => {
  const picker = framePicker.value;
  return !!picker && !picker.showCurrent && picker.candidate !== picker.currentFrame
    && picker.candidate === readyPreviewFrame.value;
});
let pickerAnchor: HTMLButtonElement | undefined;

function openFramePicker(baseFrame: number, anchor?: HTMLButtonElement) {
  const { startFrame, endFrame, totalFrames } = playerStore;
  const { frame_interval: interval, frame_overrides: overrides } = s1Params.value;
  if (currentStep.value !== 1 || processStore.isProcessing || interval <= 1) return;
  const slot = (baseFrame - startFrame) / interval;
  const selected = extractionFrameIndices(totalFrames, startFrame, endFrame, interval, overrides);
  if (!Number.isInteger(slot) || slot < 0 || slot >= selected.length) return;
  playerStore.pause();
  pickerAnchor = anchor;
  framePicker.value = {
    baseFrame,
    currentFrame: selected[slot],
    minFrame: slot > 0 ? selected[slot - 1] + 1 : startFrame,
    maxFrame: slot + 1 < selected.length ? selected[slot + 1] - 1 : endFrame,
    candidate: selected[slot],
    showCurrent: false,
  };
}

function setCandidateFrame(frame: number) {
  const picker = framePicker.value;
  if (!picker || !Number.isInteger(frame) || frame < picker.minFrame || frame > picker.maxFrame) return;
  picker.candidate = frame;
  picker.showCurrent = false;
}

function stepCandidateFrame(delta: number) {
  const picker = framePicker.value;
  if (picker) setCandidateFrame(picker.candidate + delta);
}

function closeFramePicker(restoreFocus = false) {
  framePicker.value = null;
  readyPreviewFrame.value = undefined;
  if (restoreFocus) pickerAnchor?.focus({ preventScroll: true });
  pickerAnchor = undefined;
}

function selectReplacementFrame() {
  const picker = framePicker.value;
  if (!picker || !canReplaceFrame.value || currentStep.value !== 1 || processStore.isProcessing) return;
  const { baseFrame, candidate } = picker;
  const overrides = { ...s1Params.value.frame_overrides };
  if (candidate === baseFrame) delete overrides[baseFrame];
  else overrides[baseFrame] = candidate;
  closeFramePicker();
  s1Params.value.frame_overrides = overrides;
  playerStore.goToFrame(candidate);
  frameViewport.value?.focus({ preventScroll: true });
}

watch(
  () => [currentProject.value?.id, currentStep.value, playerStore.frames, playerStore.startFrame,
    playerStore.endFrame, s1Params.value.frame_interval, s1Params.value.frame_overrides, processStore.isProcessing],
  () => closeFramePicker(),
);
// Playback may finish preloading after the picker has paused it.
watch(() => playerStore.isPlaying, (playing) => {
  if (playing && framePicker.value) playerStore.pause();
}, { flush: 'sync' });

// Params loaded state
const paramsLoaded = ref(false);
const hiddenFrames = ref<string[]>([]);
const hiddenFramePreviews = ref<HiddenFramePreview[]>([]);
const frameVisibilityError = ref('');
const previewLoadFailed = ref(false);
const timelineFrameCount = ref(0);
const visibilityUpdating = ref(false);
let frameLoadRequestId = 0;
const frameEditor = ref<{ projectId: string; filename: string; imageUrl: string; originalImageUrl: string; initialRestoreUnsupported: boolean; revision: string; step: number } | null>(null);
const frameEditorLoading = ref(false);
const frameEditorSaving = ref(false);
const frameEditorError = ref('');
const frameEditorTool = ref<'wand' | 'brush' | 'browse'>('browse');
const frameToolbar = ref<HTMLElement | null>(null);
const frameEditorRef = ref<InstanceType<typeof SeedreamImageEraser> | null>(null);
const stayButton = ref<InstanceType<typeof Button> | null>(null);
const navigationPending = ref(false);
const postProcessingResetMode = ref<'all' | 'last' | null>(null);
const postProcessingResetOpen = computed(() => postProcessingResetMode.value !== null);
const postProcessingResetTitle = computed(() => t(postProcessingResetMode.value === 'last' ? 'step3.undoProcessing' : 'step3.resetAll'));
const resettingPostProcessing = ref(false);
const postProcessingResetError = ref('');
let resolveNavigation: ((allowed: boolean) => void) | null = null;

function openPostProcessingReset(mode: 'all' | 'last' = 'all') {
  if (currentStep.value !== 3 || !projectStore.isStepCompleted(2) || processStore.isProcessing
    || visibilityUpdating.value || frameEditorLoading.value || frameEditorSaving.value || navigationPending.value
    || postProcessingResetOpen.value || frameEditorRef.value?.busy
    || (mode === 'last' && !currentProject.value?.steps?.['3']?.can_undo_processing)) return;
  postProcessingResetError.value = '';
  postProcessingResetMode.value = mode;
}

function closePostProcessingReset() {
  if (!resettingPostProcessing.value) postProcessingResetMode.value = null;
}

async function resetPostProcessing() {
  const project = currentProject.value;
  if (!project || !postProcessingResetOpen.value || resettingPostProcessing.value) return;
  resettingPostProcessing.value = true;
  const undoing = postProcessingResetMode.value === 'last';
  postProcessingResetError.value = '';
  playerStore.pause();
  try {
    const success = await (undoing ? api.process.undoPostProcessing(project.id) : api.process.resetPostProcessing(project.id));
    if (!success) throw new Error('Step 3 restore failed');
    closeFrameEditor();
    if (processStore.taskStatus?.step === 3) {
      processStore.currentTask = null;
      processStore.taskStatus = null;
    }
    const updated = await projectStore.loadProject(project.id);
    processStore.applyStepParams(3, { processed: Boolean(updated?.steps?.['3']?.completed), processing_time: 0 });
    postProcessingResetMode.value = null;
  } catch {
    postProcessingResetError.value = t(undoing ? 'step3.undoProcessingFailed' : 'step3.resetAllFailed');
  } finally {
    resettingPostProcessing.value = false;
  }
}

function beforeFrameNavigation(): boolean | Promise<boolean> {
  if (visibilityUpdating.value || frameEditorLoading.value || frameEditorSaving.value || navigationPending.value
    || postProcessingResetOpen.value || frameEditorRef.value?.busy) return false;
  closeFramePicker();
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
  if (event.defaultPrevented || postProcessingResetOpen.value) return;
  if (frameRetouchEnabled.value && frameEditor.value && frameEditorTool.value !== 'browse'
    && (event.ctrlKey || event.metaKey) && !event.altKey && !event.shiftKey && !event.isComposing
    && event.key.toLowerCase() === 's') {
    event.preventDefault();
    if (event.repeat || frameEditorLoading.value || frameEditorSaving.value || navigationPending.value
      || processStore.isProcessing || frameEditorRef.value?.busy || !frameEditorRef.value?.dirty) return;
    const imageData = frameEditorRef.value.getImageData();
    if (imageData) return saveCurrentFrameEdit(imageData);
    return;
  }
  if (event.repeat || event.ctrlKey || event.metaKey || event.altKey
    || processStore.isProcessing || frameEditorRef.value?.busy) return;
  if (event.target instanceof Element
    && event.target.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="textbox"]')) return;
  const key = event.key.toLowerCase();
  if (key === 'v') {
    if (frameEditorLoading.value || frameEditorSaving.value || navigationPending.value) return;
    event.preventDefault();
    selectFrameTool('browse');
    return;
  }
  if (!frameRetouchEnabled.value) return;
  const tool = key === 'w' ? 'wand' : key === 'e' ? 'brush' : null;
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
  if (visibilityUpdating.value || frameEditorSaving.value || frameEditorLoading.value || navigationPending.value) return;
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
    frameEditor.value = { projectId: project.id, filename: frame.filename, imageUrl: editable.image_data_url, originalImageUrl: editable.initial_image_data_url ?? '', initialRestoreUnsupported: editable.initial_image_data_url === undefined, revision: editable.revision, step };
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
    await projectStore.loadProject(editing.projectId);
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
  && (projectStore.isStepCompleted(2) || projectStore.isStepCompleted(currentStep.value))
));

const frameRetouchEnabled = computed(() => currentStep.value === 3
  && (projectStore.isStepCompleted(2) || projectStore.isStepCompleted(3)));

watch([() => currentProject.value?.id, currentStep], ([projectId], [previousProjectId]) => {
  if (projectId !== previousProjectId) hiddenFrames.value = [];
  hiddenFramePreviews.value = [];
  frameVisibilityError.value = '';
});

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
  previewLoadFailed.value = false;
  playerStore.loadFrames([]);
  timelineFrameCount.value = 0;
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
    const nextHiddenFrames = step > 1 ? await api.frame.getHiddenFrames(project.id) : [];
    if (!isCurrentRequest()) return false;
    hiddenFrames.value = nextHiddenFrames;
    const response = await api.frame.getFrames(
      project.id,
      sourceStep,
      1,
      500, // Increase page size to see more frames in sequence
      !(step === 2 && sourceStep === 1), // Disable cache only if previewing Step 1 results in Step 2
      step === 1,
    );

    if (!isCurrentRequest()) return false;
    if (response.success) {
      hiddenFramePreviews.value = response.hidden_previews ?? [];
      const frames = [...response.frames];
      for (let page = 2; page <= response.total_pages; page++) {
        const next = await api.frame.getFrames(project.id, sourceStep, page, 500, !(step === 2 && sourceStep === 1));
        if (!isCurrentRequest()) return false;
        if (!next.success) throw new Error('Failed to load frame page');
        frames.push(...next.frames);
      }
      playerStore.loadFrames(frames);
      timelineFrameCount.value = response.timeline_total ?? response.total;

      if (step === 1 && s1Params.value) {
        // Sync playback range from Step1 params ONLY for Step 1.
        // s1Params.start_frame/end_frame 是源帧空间（cache 索引）。
        const total = frames.length;
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
        playerStore.setPlaybackRange(0, frames.length - 1, 1);
      }
      return isCurrentRequest();
    }
  } catch (e) {
    if (!isCurrentRequest()) return false;
    logEvent(['Failed to load frames:', e].join(' '), 'error');
    playerStore.loadFrames([]);
    timelineFrameCount.value = 0;
  }
  if (step === 1) previewLoadFailed.value = true;
  return false;
}

function hideCurrentFrame() {
  const frame = playerStore.currentFrame;
  if (frame) return updateFrameVisibility(projectId => api.frame.setFrameHidden(projectId, frame.filename, true));
}

function restoreHiddenFrame(filename: string) {
  if (hiddenFrames.value.includes(filename)) {
    return updateFrameVisibility(projectId => api.frame.setFrameHidden(projectId, filename, false), filename);
  }
}

function restoreAllHiddenFrames() {
  if (hiddenFrames.value.length) {
    return updateFrameVisibility(projectId => api.frame.restoreHiddenFrames(projectId));
  }
}

async function updateFrameVisibility(
  update: (projectId: string) => Promise<HiddenFramesResponse>,
  restoredFilename?: string,
) {
  const project = currentProject.value;
  const step = currentStep.value;
  const isCurrentView = () => currentProject.value?.id === project?.id && currentStep.value === step;
  if (!project || !frameVisibilityEnabled.value || processStore.isProcessing || !await beforeFrameNavigation()
    || !isCurrentView() || visibilityUpdating.value || processStore.isProcessing) return;

  const index = playerStore.currentIndex;
  const preferredFilename = restoredFilename ?? playerStore.currentFrame?.filename;
  let nextIndex: number | undefined;
  visibilityUpdating.value = true;
  frameVisibilityError.value = '';
  playerStore.pause();
  try {
    const result = await update(project.id);
    if (!result.success) throw new Error('Failed to save frame visibility');
    if (!isCurrentView()) return;
    hiddenFrames.value = result.hidden_frames;
    if (!await loadFramesForStep(currentStep.value)) throw new Error('Failed to refresh frame visibility');
    const preferredIndex = playerStore.frames.findIndex(frame => frame.filename === preferredFilename);
    nextIndex = preferredIndex >= 0 ? preferredIndex : Math.min(index, playerStore.frames.length - 1);
  } catch (error) {
    logEvent(['Failed to update frame visibility:', error].join(' '), 'error');
    if (isCurrentView()) frameVisibilityError.value = t('frameVisibility.updateFailed');
  } finally {
    visibilityUpdating.value = false;
  }

  if (isCurrentView() && nextIndex !== undefined && nextIndex >= 0) playerStore.goToFrame(nextIndex);
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

  // Load parameters even when a project has no published result yet.
  const projectId = currentProject.value.id;
  await Promise.all([1, 2, 3].map((step) => processStore.loadStepParams(projectId, step)));

  // Mark params as loaded so child components can render
  paramsLoaded.value = true;

  // The initial watcher can run before Step 1 parameters arrive.
  const loaded = await loadFramesForStep(currentStep.value);
  if (loaded) signalEditorReady();
});
</script>
