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
    <div class="flex items-center justify-between">
      <label class="text-sm font-medium text-gray-300">{{ t('step2.alphaMatting') }}</label>
      <Switch v-model="s2Params.alpha_matting" />
    </div>

    <!-- Alpha Matting settings (conditional) -->
    <div
      v-if="s2Params.alpha_matting"
      class="space-y-4 pl-4 border-l-2 border-dark-border"
    >
      <!-- Reset button -->
      <div class="flex justify-end">
        <button
          class="text-xs text-gray-400 hover:text-primary transition-colors flex items-center gap-1"
          @click="resetAlphaMattingParams"
        >
          <RefreshCw class="w-3 h-3" />
          {{ t('step2.resetParams') }}
        </button>
      </div>
      <!-- Alpha matting erode size -->
      <div class="space-y-2">
        <div class="flex justify-between items-center">
          <label class="block text-sm font-medium text-gray-400">{{ t('step2.erodeSize') }}</label>
          <Input
            v-model.number="s2Params.alpha_matting_erode_size"
            type="number"
            min="0"
            max="20"
            class="w-20"
            @keydown="onInputKeydown"
          />
        </div>
        <input
          v-model.number="s2Params.alpha_matting_erode_size"
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
            type="number"
            min="0"
            max="255"
            class="w-20"
            @keydown="onInputKeydown"
          />
        </div>
        <input
          v-model.number="s2Params.alpha_matting_background_threshold"
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
            type="number"
            min="100"
            max="250"
            class="w-20"
            @keydown="onInputKeydown"
          />
        </div>
        <input
          v-model.number="s2Params.alpha_matting_foreground_threshold"
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

    <ModelStatusCard
      v-if="!isProcessing"
      :status="modelStatus"
      @retry="processStore.retryModel($event)"
    />

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

    <!-- Error Message -->
    <div
      v-if="taskStatus?.error"
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
        {{ t('step2.processedCount', { count: stepStatus?.count ?? 0 }) }}{{ processingTimeText }}
      </p>
    </div>

    <!-- Action buttons -->
    <div class="space-y-3 pt-4">
      <Button
        block
        :loading="isProcessing"
        :disabled="!canProcess"
        @click="startProcessing"
      >
        <Wand2 class="w-4 h-4 mr-2" />
        {{ isStepCompleted ? t('step2.reProcess') : t('step2.startProcessing') }}
      </Button>
      <p
        v-if="step1Completed && !canProcess"
        class="text-center text-xs text-gray-500"
      >
        {{ t('modelStatus.step2Blocked') }}
      </p>

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
import { computed, onMounted, watch } from 'vue';
import { storeToRefs } from 'pinia';
import { useI18n } from 'vue-i18n';
import { Wand2, CheckCircle, X, RefreshCw } from 'lucide-vue-next';
import { useProjectStore } from '@/stores/project';
import { useProcessStore } from '@/stores/process';
import { usePlayerStore } from '@/stores/player';
import Button from '@/components/common/Button.vue';
import Switch from '@/components/common/Switch.vue';
import Input from '@/components/common/Input.vue';
import ModelStatusCard from '@/components/editor/ModelStatusCard.vue';
import { canStartStep2 } from '@/model-status';

const projectStore = useProjectStore();
const processStore = useProcessStore();
const { t } = useI18n();
const playerStore = usePlayerStore();

const { s2Params, isProcessing, progress, taskStatus, modelStatus } = storeToRefs(processStore);

const isStepCompleted = computed(() => projectStore.isStepCompleted(2));

const step1Completed = computed(() => projectStore.isStepCompleted(1));
const stepStatus = computed(() => projectStore.currentProject?.steps?.['2']);
const selectedModel = computed(() => s2Params.value.model ?? 'u2net');

const canProcess = computed(() => canStartStep2(step1Completed.value, modelStatus.value, selectedModel.value));

onMounted(() => {
  void processStore.preloadModel(selectedModel.value);
});

watch(selectedModel, (model) => {
  void processStore.preloadModel(model);
});

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

  // Mark as processed
  s2Params.value.processed = true;

  // Pass all step 2 parameters
  const params = {
    model: s2Params.value.model,
    alpha_matting: s2Params.value.alpha_matting,
    alpha_matting_erode_size: s2Params.value.alpha_matting_erode_size,
    alpha_matting_background_threshold: s2Params.value.alpha_matting_background_threshold,
    alpha_matting_foreground_threshold: s2Params.value.alpha_matting_foreground_threshold,
    fps: s2Params.value.fps,
    processed: true
  };

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
