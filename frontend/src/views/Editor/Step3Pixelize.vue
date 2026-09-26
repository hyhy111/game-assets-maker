<template>
  <div class="p-4 space-y-6">
    <div>
      <h2 class="text-lg font-semibold text-white mb-1">
        步骤 3: 像素化
      </h2>
      <p class="text-sm text-gray-500">
        生成像素艺术效果
      </p>
    </div>

    <!-- Target sizes -->
    <div class="space-y-2">
      <label class="block text-sm font-medium text-gray-300">目标尺寸</label>
      <div class="flex gap-2">
        <button
          v-for="size in availableSizes"
          :key="size"
          :class="[
            'px-3 py-1.5 rounded-lg text-sm border transition-all',
            s3Params.target_sizes.includes(size)
              ? 'bg-primary border-primary text-dark-bg'
              : 'bg-dark-bg border-dark-border text-gray-400 hover:border-gray-500'
          ]"
          @click="toggleSize(size)"
        >
          {{ size }}px
        </button>
      </div>
    </div>

    <!-- Outline thickness -->
    <div class="space-y-2">
      <label class="block text-sm font-medium text-gray-300">外描边粗细</label>
      <input
        v-model.number="s3Params.outline_thickness"
        type="range"
        min="0"
        max="5"
        class="w-full h-2 bg-dark-border rounded-lg appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:rounded-full"
      >
      <div class="text-xs text-gray-500">
        {{ s3Params.outline_thickness === 0 ? '无描边' : `${s3Params.outline_thickness}px` }}
      </div>
    </div>

    <!-- Inner outline toggle -->
    <div class="flex items-center justify-between">
      <label class="text-sm font-medium text-gray-300">内描边</label>
      <Switch v-model="s3Params.enable_inner_outline" />
    </div>

    <!-- Inner outline thickness (conditional) -->
    <div
      v-if="s3Params.enable_inner_outline"
      class="space-y-2"
    >
      <label class="block text-sm font-medium text-gray-300">内描边粗细</label>
      <input
        v-model.number="s3Params.inner_outline_thickness"
        type="range"
        min="1"
        max="5"
        class="w-full h-2 bg-dark-border rounded-lg appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:rounded-full"
      >
    </div>

    <!-- Canvas Background Color Selector -->
    <div class="space-y-2">
      <label class="block text-sm font-medium text-gray-300">预览背景色</label>
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
        更换播放器背景色以更好地查看透明效果
      </p>
    </div>

    <!-- Status -->
    <div
      v-if="isStepCompleted"
      class="p-3 bg-success-500/10 border border-success-500/30 rounded-lg"
    >
      <div class="flex items-center gap-2 text-success-500">
        <CheckCircle class="w-5 h-5" />
        <span class="text-sm">已完成</span>
      </div>
      <p class="text-xs text-gray-500 mt-1">
        已生成 {{ stepStatus.count }} 帧
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
        <Sparkles class="w-4 h-4 mr-2" />
        {{ isStepCompleted ? '重新生成' : '开始生成' }}
      </Button>

      <Button
        v-if="isProcessing"
        variant="danger"
        block
        @click="cancelProcessing"
      >
        <X class="w-4 h-4 mr-2" />
        取消
      </Button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { storeToRefs } from 'pinia';
import { Sparkles, CheckCircle, X } from 'lucide-vue-next';
import { useProjectStore } from '@/stores/project';
import { useProcessStore } from '@/stores/process';
import { usePlayerStore } from '@/stores/player';
import Button from '@/components/common/Button.vue';
import Switch from '@/components/common/Switch.vue';

const projectStore = useProjectStore();
const processStore = useProcessStore();
const playerStore = usePlayerStore();

const { s3Params, isProcessing } = storeToRefs(processStore);

const isStepCompleted = computed(() => projectStore.isStepCompleted(3));
const step2Completed = computed(() => projectStore.isStepCompleted(2));
const stepStatus = computed(() => projectStore.currentProject?.steps?.['3']);

const canProcess = computed(() => step2Completed.value);

const availableSizes = [64, 128, 256, 512];

function toggleSize(size: number) {
  const index = s3Params.value.target_sizes.indexOf(size);
  if (index > -1) {
    // Don't remove if it's the only one
    if (s3Params.value.target_sizes.length > 1) {
      s3Params.value.target_sizes.splice(index, 1);
    }
  } else {
    s3Params.value.target_sizes.push(size);
    s3Params.value.target_sizes.sort((a, b) => a - b);
  }
}

async function startProcessing() {
  if (!projectStore.currentProject) return;

  // Stop playback before processing
  playerStore.pause();

  // Mark as processed
  s3Params.value.processed = true;

  await processStore.startProcessing(projectStore.currentProject.id, 3, { processed: true });
}

async function cancelProcessing() {
  await processStore.cancelProcessing();
}
</script>
