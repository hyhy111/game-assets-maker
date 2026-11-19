<template>
  <div class="p-4 space-y-6">
    <div>
      <h2 class="text-lg font-semibold text-white mb-1">
        {{ t('step2.title') }}
      </h2>
      <p class="text-sm text-gray-500">
        {{ t('step2.description') }}
      </p>
    </div>

    <div class="space-y-2">
      <span class="block text-sm font-medium text-gray-300">{{ t('step2.model') }}</span>
      <div
        class="grid grid-cols-2 gap-1 rounded-xl bg-black/15 p-1"
        role="group"
        :aria-label="t('step2.model')"
      >
        <button
          v-for="option in modelOptions"
          :key="option.value"
          type="button"
          class="rounded-lg px-2 py-2 text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-30"
          :class="selectedModel === option.value
            ? 'bg-primary/20 text-primary-200 shadow-sm'
            : 'text-gray-400 hover:bg-white/[0.05] hover:text-gray-200'"
          :disabled="isProcessing"
          :aria-pressed="selectedModel === option.value"
          :data-test="`background-model-${option.value}`"
          @click="setModel(option.value)"
        >
          {{ option.label }}
        </button>
      </div>
    </div>

    <ModelStatusCard
      v-if="shouldShowModelStatus"
      :key="selectedModel"
      :status="modelStatus"
      @retry="processStore.retryModel($event)"
      @cancel="processStore.cancelModelDownload()"
    />

    <GpuRuntimeCard
      v-if="selectedModel.endsWith('-onnx')"
      :model="selectedModel"
      :model-ready="modelStatus.phase === 'ready'"
    />

    <!-- Canvas Background Color Selector -->
    <div class="space-y-2">
      <label class="block text-sm font-medium text-gray-300">{{ t('step2.previewBgColor') }}</label>
      <div class="flex gap-2">
        <button
          v-for="(colorValue, colorKey) in playerStore.canvasBgColors"
          :key="colorKey"
          :class="[
            'w-8 h-8 rounded-lg border-2 transition-all',
            playerStore.canvasBgColor === colorKey ? 'border-primary scale-110' : 'border-dark-border hover:border-gray-500'
          ]"
          :style="{ backgroundColor: colorValue }"
          :title="colorKey"
          @click="playerStore.setCanvasBgColor(colorKey)"
        />
      </div>
      <p class="text-xs text-gray-500">
        {{ t('step2.previewBgHint') }}
      </p>
    </div>

    <!-- Alpha Matting toggle -->
    <div
      v-if="selectedModel === 'u2net'"
      class="flex items-center justify-between"
    >
      <label class="text-sm font-medium text-gray-300">{{ t('step2.alphaMatting') }}</label>
      <Switch
        v-model="s2Params.alpha_matting"
        :aria-label="t('step2.alphaMatting')"
      />
    </div>

    <!-- Alpha Matting settings (conditional) -->
    <div
      v-if="selectedModel === 'u2net' && s2Params.alpha_matting"
      class="space-y-4 pl-4 border-l-2 border-dark-border"
    >
      <!-- Reset button -->
      <div class="flex justify-end">
        <button
          class="text-xs text-gray-400 hover:text-primary transition-colors flex items-center gap-1 icon-button control-tooltip"
          :aria-label="t('buttonHints.resetMatting')"
          :data-tooltip="t('buttonHints.resetMatting')"
          @click="resetAlphaMattingParams"
        >
          <RotateCcw
            class="h-5 w-5"
            aria-hidden="true"
          />
        </button>
      </div>
      <!-- Alpha matting erode size -->
      <div class="space-y-2">
        <div class="flex justify-between items-center">
          <label class="block text-sm font-medium text-gray-400">{{ t('step2.erodeSize') }}</label>
          <Input
            v-model.number="s2Params.alpha_matting_erode_size"
            :aria-label="t('step2.erodeSize')"
            type="number"
            min="0"
            max="20"
            class="w-20"
            @keydown="onInputKeydown"
          />
        </div>
        <input
          v-model.number="s2Params.alpha_matting_erode_size"
          :aria-label="t('step2.erodeSize')"
          type="range"
          min="0"
          max="20"
          step="1"
          class="w-full h-2 bg-dark-border rounded-lg appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:rounded-full"
        >
        <p class="text-xs text-gray-500">
          {{ t('step2.erodeHint') }}
        </p>
      </div>

      <!-- Background threshold -->
      <div class="space-y-2">
        <div class="flex justify-between items-center">
          <label class="block text-sm font-medium text-gray-400">{{ t('step2.bgThreshold') }}</label>
          <Input
            v-model.number="s2Params.alpha_matting_background_threshold"
            :aria-label="t('step2.bgThreshold')"
            type="number"
            min="0"
            max="255"
            class="w-20"
            @keydown="onInputKeydown"
          />
        </div>
        <input
          v-model.number="s2Params.alpha_matting_background_threshold"
          :aria-label="t('step2.bgThreshold')"
          type="range"
          min="0"
          max="255"
          step="1"
          class="w-full h-2 bg-dark-border rounded-lg appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:rounded-full"
        >
        <p class="text-xs text-gray-500">
          {{ t('step2.bgThresholdHint') }}
        </p>
      </div>

      <!-- Foreground threshold -->
      <div class="space-y-2">
        <div class="flex justify-between items-center">
          <label class="block text-sm font-medium text-gray-400">{{ t('step2.fgThreshold') }}</label>
          <Input
            v-model.number="s2Params.alpha_matting_foreground_threshold"
            :aria-label="t('step2.fgThreshold')"
            type="number"
            min="100"
            max="250"
            class="w-20"
            @keydown="onInputKeydown"
          />
        </div>
        <input
          v-model.number="s2Params.alpha_matting_foreground_threshold"
          :aria-label="t('step2.fgThreshold')"
          type="range"
          min="100"
          max="250"
          step="5"
          class="w-full h-2 bg-dark-border rounded-lg appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:rounded-full"
        >
        <p class="text-xs text-gray-500">
          {{ t('step2.fgThresholdHint') }}
        </p>
      </div>
    </div>

    <!-- Edge Defringe -->
    <div
      v-if="isBiRefNet(selectedModel)"
      class="space-y-4"
    >
      <div class="flex items-center justify-between">
        <label class="text-sm font-medium text-gray-300">{{ t('step2.defringe') }}</label>
        <Switch
          v-model="s2Params.defringe_enabled"
          :aria-label="t('step2.defringe')"
        />
      </div>
      <div
        v-if="s2Params.defringe_enabled"
        class="space-y-4 pl-4 border-l-2 border-dark-border"
      >
        <label
          v-for="field in defringeFields"
          :key="field.key"
          class="flex items-center justify-between gap-3 text-sm text-gray-400"
        >
          <span>{{ t(field.label) }}</span>
          <input
            v-model.number="s2Params[field.key]"
            type="number"
            :min="field.min"
            :max="field.max"
            :step="field.step"
            :aria-label="t(field.label)"
            class="w-20 rounded-lg border border-dark-border bg-dark-surface px-2 py-1.5 text-center text-gray-100"
            @keydown="onInputKeydown"
          >
        </label>
      </div>
      <p class="text-xs text-gray-500">
        {{ t('step2.defringeHint') }}
      </p>
    </div>

    <!-- Processing Progress -->
    <div
      v-if="isProcessing"
      class="space-y-2"
    >
      <div class="flex justify-between items-center text-sm">
        <span class="text-gray-300">{{ t('step2.processingProgress') }}</span>
        <span class="text-primary font-medium">{{ Math.round(progress) }}%</span>
      </div>
      <div class="w-full h-2 bg-dark-border rounded-full overflow-hidden">
        <div
          class="h-full bg-primary transition-all duration-300 ease-out"
          :style="{ width: `${progress}%` }"
        />
      </div>
      <p class="text-xs text-gray-500">
        {{ t('step2.processedFrames', { current: taskStatus?.current ?? 0, total: taskStatus?.total ?? 0 }) }}
      </p>
    </div>

    <div
      v-if="taskStatus?.step === 2 && taskStatus.gpu_fallback"
      role="status"
      class="p-3 text-sm text-warning-400 border border-warning-400/30 rounded-lg"
    >
      <p>{{ t(`gpuTask.${taskStatus.gpu_fallback.code}`, t('gpuTask.unknown')) }}</p>
      <p>{{ t(`gpuTask.${taskStatus.status === 'pending' ? 'running' : taskStatus.status}`) }}</p>
    </div>

    <!-- Error Message -->
    <div
      v-if="taskStatus?.step === 2 && taskStatus.error"
      class="p-3 bg-danger-500/10 border border-danger-500/30 rounded-lg"
    >
      <div class="flex items-start gap-2 text-danger-500">
        <X class="w-5 h-5 mt-0.5 flex-shrink-0" />
        <div class="text-sm break-all">
          {{ taskStatus.error }}
        </div>
      </div>
    </div>

    <!-- Status -->
    <div
      v-else-if="isStepCompleted"
      class="p-3 bg-success-500/10 border border-success-500/30 rounded-lg"
    >
      <div class="flex items-center gap-2 text-success-500">
        <CheckCircle class="w-5 h-5" />
        <span class="text-sm">{{ t('step2.completed') }}</span>
      </div>
      <p class="text-xs text-gray-500 mt-1">
        {{ t('step2.resultCount', { count: stepStatus?.count ?? 0, model: backgroundModelName(stepStatus?.result_model ?? 'u2net') }) }}{{ processingTimeText }}
      </p>
    </div>

    <!-- Action buttons -->
    <div class="space-y-3 pt-4">
      <p
        v-if="isStepCompleted && !isProcessing"
        class="text-xs text-gray-400"
      >
        {{ t(projectStore.isStepCompleted(3) ? 'step2.replaceWithPostProcess' : 'step2.replaceResult') }}
      </p>
      <Button
        block
        :loading="isProcessing"
        :disabled="!canProcess"
        :tooltip="isStepCompleted ? t('buttonHints.reBackground') : t('buttonHints.background')"
        @click="startProcessing"
      >
        <Wand2 class="w-4 h-4 mr-2" />
        {{ isStepCompleted ? t('step2.reProcess') : t('step2.startProcessing') }}
      </Button>
      <p
        v-if="step1Completed && !canProcess && !isProcessing"
        class="text-center text-xs text-gray-500"
      >
        {{ t('modelStatus.step2Blocked') }}
      </p>

      <Button
        v-if="isProcessing"
        variant="danger"
        block
        :tooltip="t('common.cancelProcessing')"
        @click="cancelProcessing"
      >
        <Square
          class="mr-2 h-4 w-4"
          aria-hidden="true"
        />
        {{ t('common.cancelProcessing') }}
      </Button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue';
import { storeToRefs } from 'pinia';
import { useI18n } from 'vue-i18n';
import { Wand2, CheckCircle, X, RotateCcw, Square } from 'lucide-vue-next';
import { useProjectStore } from '@/stores/project';
import { useProcessStore, step2Defaults } from '@/stores/process';
import { usePlayerStore } from '@/stores/player';
import Button from '@/components/common/Button.vue';
import Switch from '@/components/common/Switch.vue';
import Input from '@/components/common/Input.vue';
import ModelStatusCard from '@/components/editor/ModelStatusCard.vue';
import GpuRuntimeCard from '@/components/editor/GpuRuntimeCard.vue';
import { useConfigStore } from '@/stores/config';
import { backgroundModelName, canStartStep2, isBiRefNet } from '@/model-status';

const projectStore = useProjectStore();
const processStore = useProcessStore();
const { t } = useI18n();
const playerStore = usePlayerStore();

const { s2Params, isProcessing, progress, taskStatus, modelStatus, selectedModel } = storeToRefs(processStore);

const isStepCompleted = computed(() => projectStore.isStepCompleted(2));

const step1Completed = computed(() => projectStore.isStepCompleted(1));
const stepStatus = computed(() => projectStore.currentProject?.steps?.['2']);
const configStore = useConfigStore();
const modelOptions = computed(() => [...(configStore.config?.background_models ?? ['u2net', 'birefnet-comfy'])]
  .reverse().map(value => ({ value, label: backgroundModelName(value) })));

function setModel(value: string | number) {
  if ((value === 'u2net' || value === 'birefnet-comfy' || value === 'birefnet-lite-onnx' || value === 'birefnet-standard-onnx')
    && modelOptions.value.some(option => option.value === value)) s2Params.value.model = value;
}

const canProcess = computed(() => !isProcessing.value && visibleParamsValid.value
  && canStartStep2(step1Completed.value, modelStatus.value, selectedModel.value));
const shouldShowModelStatus = computed(() => !isProcessing.value && modelStatus.value.phase !== 'ready');

const defringeFields = [
  { key: 'defringe_px', label: 'step2.defringePx', min: 0, max: 20, step: 1 },
  { key: 'defringe_amount', label: 'step2.defringeAmount', min: 0, max: 1, step: 0.05 },
] as const;

const visibleParamsValid = computed(() => {
  if (selectedModel.value === 'u2net') return true;
  const p = s2Params.value;
  return Number.isInteger(p.defringe_px) && p.defringe_px >= 0 && p.defringe_px <= 20
    && Number.isFinite(p.defringe_amount) && p.defringe_amount >= 0 && p.defringe_amount <= 1;
});

watch(selectedModel, (model) => {
  void processStore.preloadModel(model);
}, { immediate: true });

// Format processing time for display
const processingTimeText = computed(() => {
  const time = s2Params.value.processing_time;
  if (!time || time <= 0) return '';
  if (time < 60) return t('step2.processingTime', { seconds: Math.round(time) });
  const minutes = Math.floor(time / 60);
  const seconds = Math.round(time % 60);
  return t('step2.processingTimeMinutes', { minutes, seconds });
});

async function startProcessing() {
  if (!projectStore.currentProject || !canProcess.value) return;

  // Stop playback before processing
  playerStore.pause();

  // Pass all step 2 parameters
  const params = {
    model: selectedModel.value,
    alpha_matting: s2Params.value.alpha_matting,
    alpha_matting_erode_size: s2Params.value.alpha_matting_erode_size,
    alpha_matting_background_threshold: s2Params.value.alpha_matting_background_threshold,
    alpha_matting_foreground_threshold: s2Params.value.alpha_matting_foreground_threshold,
    alpha_contrast: s2Params.value.alpha_contrast,
    alpha_threshold: s2Params.value.alpha_threshold,
    defringe_enabled: s2Params.value.defringe_enabled,
    defringe_px: s2Params.value.defringe_px,
    defringe_amount: s2Params.value.defringe_amount,
    min_foreground_area: s2Params.value.min_foreground_area,
    fill_holes_max_size: s2Params.value.fill_holes_max_size,
    fps: s2Params.value.fps,
    processed: true
  };

  // Hidden controls must not leak stale development-session values into processing.
  params.alpha_contrast = step2Defaults.alpha_contrast;
  params.alpha_threshold = step2Defaults.alpha_threshold;
  params.min_foreground_area = step2Defaults.min_foreground_area;
  params.fill_holes_max_size = step2Defaults.fill_holes_max_size;
  if (isBiRefNet(selectedModel.value)) {
    params.alpha_matting = step2Defaults.alpha_matting;
    params.alpha_matting_erode_size = step2Defaults.alpha_matting_erode_size;
    params.alpha_matting_background_threshold = step2Defaults.alpha_matting_background_threshold;
    params.alpha_matting_foreground_threshold = step2Defaults.alpha_matting_foreground_threshold;
  } else {
    params.defringe_enabled = step2Defaults.defringe_enabled;
    params.defringe_px = step2Defaults.defringe_px;
    params.defringe_amount = step2Defaults.defringe_amount;
  }

  await processStore.startProcessing(projectStore.currentProject.id, 2, params);
}

async function cancelProcessing() {
  await processStore.cancelProcessing();
}

function onInputKeydown(event: KeyboardEvent) {
  // Blur input on Enter key to confirm input
  if (event.key === 'Enter') {
    const target = event.target as HTMLInputElement;
    target.blur();
  }
}

function resetAlphaMattingParams() {
  // Reset to default values
  s2Params.value.alpha_matting_erode_size = 5;
  s2Params.value.alpha_matting_background_threshold = 120;
  s2Params.value.alpha_matting_foreground_threshold = 240;
}
</script>
