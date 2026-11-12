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
      <Switch
        v-model="s3Params.enabled"
        :aria-label="t('step3.holePunch')"
      />
    </div>

    <!-- Hole Punch Settings (collapsible) -->
    <div
      v-if="s3Params.enabled"
      class="space-y-4 pl-4 border-l-2 border-dark-border"
    >
      <!-- Background color tolerance; retain the saved field name for compatibility. -->
      <div class="space-y-3">
        <div class="flex justify-between items-center">
          <label class="block text-sm font-medium text-gray-400">{{ t('step3.greenIntensity') }}</label>
          <span class="text-xs text-gray-400 px-2 py-1 bg-dark-border rounded">{{ intensityLabel }}</span>
        </div>
        <input
          v-model.number="s3Params.green_intensity"
          :aria-label="t('step3.greenIntensity')"
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
            :aria-label="t('step3.featherRadius')"
            type="number"
            min="0"
            max="10"
            class="w-20"
            @keydown="onInputKeydown"
          />
        </div>
        <input
          v-model.number="s3Params.feather_radius"
          :aria-label="t('step3.featherRadius')"
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
            :aria-label="t('step3.minHoleSize')"
            type="number"
            min="0"
            max="500"
            class="w-20"
            @keydown="onInputKeydown"
          />
        </div>
        <input
          v-model.number="s3Params.min_hole_size"
          :aria-label="t('step3.minHoleSize')"
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

    <div class="flex items-center justify-between pt-2 border-t border-dark-border">
      <label class="text-sm font-medium text-gray-300">{{ t('step3.edgeShrink') }}</label>
      <Switch
        v-model="s3Params.edge_shrink_enabled"
        :aria-label="t('step3.edgeShrink')"
      />
    </div>

    <div
      v-if="s3Params.edge_shrink_enabled"
      class="space-y-3 pl-4 border-l-2 border-dark-border"
    >
      <p class="text-xs text-gray-500">
        {{ t('step3.edgeShrinkHint') }}
      </p>
      <label
        v-for="field in edgeFields"
        :key="field.key"
        class="flex items-center justify-between gap-3 text-sm text-gray-400"
      >
        <span>{{ t(field.label) }}</span>
        <input
          v-model.number="s3Params[field.key]"
          type="number"
          min="0"
          max="100"
          :step="field.step"
          class="w-20 rounded-lg border border-dark-border bg-dark-surface px-2 py-1.5 text-center text-gray-100"
          @keydown="onInputKeydown"
        >
      </label>
    </div>

    <!-- Alignment Settings Toggle -->
    <div class="flex items-center justify-between pt-2 border-t border-dark-border">
      <label class="text-sm font-medium text-gray-300">{{ t('step3.frameAlignment') }}</label>
      <Switch
        v-model="s3Params.align_enabled"
        :aria-label="t('step3.frameAlignment')"
      />
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
        <Switch
          v-model="s3Params.align_h"
          :aria-label="t('step3.horizontalCenter')"
        />
      </div>

      <!-- Vertical Bottom Alignment -->
      <div class="flex items-center justify-between">
        <div class="flex flex-col">
          <label class="text-sm font-medium text-gray-400">{{ t('step3.bottomAlign') }}</label>
          <span class="text-xs text-gray-500">{{ t('step3.bottomAlignDesc') }}</span>
        </div>
        <Switch
          v-model="s3Params.align_v"
          :aria-label="t('step3.bottomAlign')"
        />
      </div>
    </div>

    <p
      v-if="taskStatus?.step === 3 && taskStatus.error"
      class="rounded-lg border border-danger-500/30 bg-danger-500/10 p-3 text-sm text-danger-500"
    >
      {{ taskStatus.error }}
    </p>

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

const { s3Params, isProcessing, taskStatus } = storeToRefs(processStore);

const isStepCompleted = computed(() => projectStore.isStepCompleted(3));
const step2Completed = computed(() => projectStore.isStepCompleted(2));
const stepStatus = computed(() => projectStore.currentProject?.steps?.['3']);

const edgeFields = [
  { key: 'edge_shrink_px', label: 'step3.edgeShrinkPx', step: 1 },
  { key: 'edge_feather_px', label: 'step3.edgeFeatherPx', step: 0.5 },
] as const;
const canProcess = computed(() => {
  if (!step2Completed.value || isProcessing.value) return false;
  if (!s3Params.value.edge_shrink_enabled) return true;
  const { edge_shrink_px: shrink, edge_feather_px: feather } = s3Params.value;
  return Number.isInteger(shrink) && shrink >= 0 && shrink <= 100
    && Number.isFinite(feather) && feather >= 0 && feather <= 100;
});

const intensityLabel = computed(() => t(`step3.intensityLabels.${s3Params.value.green_intensity}`));
const intensityDescription = computed(() => t(`step3.intensityDescriptions.${s3Params.value.green_intensity}`));

async function startProcessing() {
  if (!projectStore.currentProject || !canProcess.value) return;

  // Stop playback before processing
  playerStore.pause();

  await processStore.startProcessing(projectStore.currentProject.id, 3, { processed: true });
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
