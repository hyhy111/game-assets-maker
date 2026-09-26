<template>
  <div class="p-4 space-y-6">
    <div>
      <h2 class="text-lg font-semibold text-white mb-1">
        {{ t('step3.title') }}
      </h2>
      <p class="text-sm text-gray-500">
        {{ t('step3.description') }}
      </p>
    </div>

    <!-- Canvas Background Color Selector -->
    <div class="space-y-2">
      <label class="block text-sm font-medium text-gray-300">{{ t('step3.previewBgColor') }}</label>
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
        {{ t('step3.previewBgHint') }}
      </p>
    </div>

    <!-- Hole Punch Settings Toggle -->
    <div class="flex items-center justify-between">
      <label class="text-sm font-medium text-gray-300">{{ t('step3.holePunch') }}</label>
      <Switch v-model="s3Params.enabled" />
    </div>

    <!-- Hole Punch Settings (collapsible) -->
    <div
      v-if="s3Params.enabled"
      class="space-y-4 pl-4 border-l-2 border-dark-border"
    >
      <!-- Green Intensity Slider -->
      <div class="space-y-3">
        <div class="flex justify-between items-center">
          <label class="block text-sm font-medium text-gray-400">{{ t('step3.greenIntensity') }}</label>
          <span class="text-xs text-gray-400 px-2 py-1 bg-dark-border rounded">{{ intensityLabel }}</span>
        </div>
        <input
          v-model.number="s3Params.green_intensity"
          type="range"
          min="1"
          max="5"
          step="1"
          class="w-full h-2 bg-dark-border rounded-lg appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:rounded-full"
        >
        <div class="flex justify-between text-xs text-gray-500 px-1">
          <span :class="{ 'text-primary font-medium': s3Params.green_intensity === 1 }">{{ t('step3.vibrant') }}</span>
          <span :class="{ 'text-primary font-medium': s3Params.green_intensity === 3 }">{{ t('step3.standard') }}</span>
          <span :class="{ 'text-primary font-medium': s3Params.green_intensity === 5 }">{{ t('step3.dark') }}</span>
        </div>
        <p class="text-xs text-gray-500">
          {{ intensityDescription }}
        </p>
      </div>

      <!-- Feather Radius Slider -->
      <div class="space-y-2">
        <div class="flex justify-between items-center">
          <label class="block text-sm font-medium text-gray-400">{{ t('step3.featherRadius') }}</label>
          <Input
            v-model.number="s3Params.feather_radius"
            type="number"
            min="0"
            max="10"
            class="w-20"
            @keydown="onInputKeydown"
          />
        </div>
        <input
          v-model.number="s3Params.feather_radius"
          type="range"
          min="0"
          max="10"
          step="1"
          class="w-full h-2 bg-dark-border rounded-lg appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:rounded-full"
        >
        <div class="flex justify-between text-xs text-gray-500">
          <span>{{ t('step3.hardEdge') }}</span>
          <span>5</span>
          <span>{{ t('step3.softEdge') }}</span>
        </div>
        <p class="text-xs text-gray-500">
          {{ t('step3.featherHint') }}
        </p>
      </div>

      <!-- Min Hole Size Input -->
      <div class="space-y-2">
        <div class="flex justify-between items-center">
          <label class="block text-sm font-medium text-gray-400">{{ t('step3.minHoleSize') }}</label>
          <Input
            v-model.number="s3Params.min_hole_size"
            type="number"
            min="0"
            max="500"
            class="w-20"
            @keydown="onInputKeydown"
          />
        </div>
        <input
          v-model.number="s3Params.min_hole_size"
          type="range"
          min="0"
          max="100"
          step="1"
          class="w-full h-2 bg-dark-border rounded-lg appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:rounded-full"
        >
        <div class="flex justify-between text-xs text-gray-500">
          <span>0</span>
          <span>50</span>
          <span>100+</span>
        </div>
        <p class="text-xs text-gray-500">
          {{ t('step3.minHoleHint') }}
        </p>
      </div>
    </div>

    <!-- Alignment Settings Toggle -->
    <div class="flex items-center justify-between pt-2 border-t border-dark-border">
      <label class="text-sm font-medium text-gray-300">{{ t('step3.frameAlignment') }}</label>
      <Switch v-model="s3Params.align_enabled" />
    </div>

    <!-- Alignment Settings (collapsible) -->
    <div
      v-if="s3Params.align_enabled"
      class="space-y-4 pl-4 border-l-2 border-dark-border"
    >
      <!-- Horizontal Centering -->
      <div class="flex items-center justify-between">
        <div class="flex flex-col">
          <label class="text-sm font-medium text-gray-400">{{ t('step3.horizontalCenter') }}</label>
          <span class="text-xs text-gray-500">{{ t('step3.horizontalCenterDesc') }}</span>
        </div>
        <Switch v-model="s3Params.align_h" />
      </div>

      <!-- Vertical Bottom Alignment -->
      <div class="flex items-center justify-between">
        <div class="flex flex-col">
          <label class="text-sm font-medium text-gray-400">{{ t('step3.bottomAlign') }}</label>
          <span class="text-xs text-gray-500">{{ t('step3.bottomAlignDesc') }}</span>
        </div>
        <Switch v-model="s3Params.align_v" />
      </div>
    </div>

    <!-- Status -->
    <div
      v-if="isStepCompleted"
      class="p-3 bg-success-500/10 border border-success-500/30 rounded-lg"
    >
      <div class="flex items-center gap-2 text-success-500">
        <CheckCircle class="w-5 h-5" />
        <span class="text-sm">{{ t('step3.completed') }}</span>
      </div>
      <p class="text-xs text-gray-500 mt-1">
        {{ t('step3.processedCount', { count: stepStatus?.count ?? 0 }) }}
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
        {{ isStepCompleted ? t('step3.reProcess') : t('step3.startProcessing') }}
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
import { computed } from 'vue';
import { storeToRefs } from 'pinia';
import { useI18n } from 'vue-i18n';
import { Wand2, CheckCircle, X } from 'lucide-vue-next';
import Switch from '@/components/common/Switch.vue';
import Input from '@/components/common/Input.vue';
import { useProjectStore } from '@/stores/project';
import { useProcessStore } from '@/stores/process';
import { usePlayerStore } from '@/stores/player';
import Button from '@/components/common/Button.vue';

const projectStore = useProjectStore();
const processStore = useProcessStore();
const playerStore = usePlayerStore();
const { t } = useI18n();

const { s3Params, isProcessing } = storeToRefs(processStore);

const isStepCompleted = computed(() => projectStore.isStepCompleted(3));
const step2Completed = computed(() => projectStore.isStepCompleted(2));
const stepStatus = computed(() => projectStore.currentProject?.steps?.['3']);

const canProcess = computed(() => step2Completed.value);

const intensityLabel = computed(() => t(`step3.intensityLabels.${s3Params.value.green_intensity}`));
const intensityDescription = computed(() => t(`step3.intensityDescriptions.${s3Params.value.green_intensity}`));

async function startProcessing() {
  if (!projectStore.currentProject) return;

  // Stop playback before processing
  playerStore.pause();

  // Mark as processed
  s3Params.value.processed = true;

  // Pass all parameters including alignment
  const params = {
    enabled: s3Params.value.enabled,
    green_intensity: s3Params.value.green_intensity,
    feather_radius: s3Params.value.feather_radius,
    min_hole_size: s3Params.value.min_hole_size,
    align_enabled: s3Params.value.align_enabled,
    align_h: s3Params.value.align_h,
    align_v: s3Params.value.align_v,
    use_padding: s3Params.value.use_padding,
    padding_bottom: s3Params.value.padding_bottom,
    fps: s3Params.value.fps,
    processed: true
  };

  await processStore.startProcessing(projectStore.currentProject.id, 3, params);
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
</script>
