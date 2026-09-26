<template>
  <div class="grid grid-cols-4 gap-1 rounded-xl bg-black/15 p-1" data-test="seedance-ratio">
    <button
      v-for="ratio in ratios"
      :key="ratio.value"
      type="button"
      class="rounded-lg px-2 py-2 text-xs transition-colors"
      :class="modelValue === ratio.value
        ? 'bg-primary/20 text-primary-200 shadow-sm'
        : 'text-gray-400 hover:bg-white/[0.05] hover:text-gray-200'"
      :aria-pressed="modelValue === ratio.value"
      @click="emit('update:modelValue', ratio.value)"
    >
      {{ ratio.value === 'adaptive' ? adaptiveLabel : ratio.value }}
    </button>
  </div>
</template>

<script setup lang="ts">
import type { SeedanceRatio } from '@/types';

defineProps<{
  modelValue: SeedanceRatio;
  adaptiveLabel: string;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: SeedanceRatio];
}>();

const ratios = [
  { value: '16:9' },
  { value: '1:1' },
  { value: '4:3' },
  { value: 'adaptive' },
] as const;
</script>
