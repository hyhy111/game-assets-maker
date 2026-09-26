<template>
  <div class="space-y-2">
    <div
      v-if="label || $slots.label"
      class="flex justify-between items-center"
    >
      <label class="text-sm font-medium text-gray-300">
        <slot name="label">{{ label }}</slot>
      </label>
      <span
        v-if="showValue"
        class="text-sm text-gray-400"
      >{{ displayValue }}</span>
    </div>
    <input
      :value="modelValue"
      :min="min"
      :max="max"
      :step="step"
      :disabled="disabled"
      type="range"
      class="w-full h-2 bg-dark-border rounded-lg appearance-none cursor-pointer disabled:opacity-50 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:cursor-pointer hover:[&::-webkit-slider-thumb]:bg-primary-400 [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:bg-primary [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:cursor-pointer [&::-moz-range-thumb]:border-0"
      @input="onInput"
    >
    <div
      v-if="showTicks && ticks.length > 0"
      class="flex justify-between text-xs text-gray-500 px-1"
    >
      <span
        v-for="tick in ticks"
        :key="tick"
      >{{ tick }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = withDefaults(defineProps<{
  modelValue: number;
  min?: number;
  max?: number;
  step?: number;
  label?: string;
  showValue?: boolean;
  valueFormatter?: (value: number) => string;
  showTicks?: boolean;
  ticks?: string[];
  disabled?: boolean;
}>(), {
  min: 0,
  max: 100,
  step: 1,
  showValue: true,
  showTicks: false,
  ticks: () => []
});

const emit = defineEmits<{
  'update:modelValue': [value: number];
}>();

const displayValue = computed(() => {
  if (props.valueFormatter) {
    return props.valueFormatter(props.modelValue);
  }
  return String(props.modelValue);
});

function onInput(event: Event) {
  const target = event.target as HTMLInputElement;
  emit('update:modelValue', Number(target.value));
}
</script>
