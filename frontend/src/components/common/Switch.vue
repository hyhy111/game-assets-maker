<template>
  <label
    class="inline-flex items-center cursor-pointer"
    :class="[
      { 'opacity-50 cursor-not-allowed': disabled },
      compact && 'min-h-9 gap-2 rounded-lg px-2',
      compact && !disabled && 'hover:bg-white/5',
    ]"
  >
    <input
      type="checkbox"
      :checked="modelValue"
      :aria-label="ariaLabel || label"
      :disabled="disabled"
      class="sr-only peer"
      @change="onChange"
    >
    <span
      aria-hidden="true"
      class="relative shrink-0 rounded-full bg-dark-border after:absolute after:left-0.5 after:top-0.5 after:rounded-full after:content-['']"
      :class="compact
        ? 'h-[18px] w-8 border border-white/25 after:h-3 after:w-3 after:bg-gray-300 after:transition after:duration-150 motion-reduce:after:transition-none peer-checked:border-primary/50 peer-checked:bg-primary/[0.17] peer-checked:after:translate-x-3.5 peer-checked:after:bg-primary peer-focus-visible:ring-2 peer-focus-visible:ring-primary'
        : 'h-6 w-11 after:h-5 after:w-5 after:border after:border-gray-300 after:bg-white after:transition-all peer-checked:bg-primary peer-checked:after:translate-x-full peer-checked:after:border-white peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-primary'"
    />
    <span
      v-if="label"
      class="font-medium text-gray-300"
      :class="compact ? 'order-first whitespace-nowrap text-[13px]' : 'ml-3 text-sm'"
    >{{ label }}</span>
  </label>
</template>

<script setup lang="ts">
const props = defineProps<{
  modelValue: boolean;
  label?: string;
  ariaLabel?: string;
  disabled?: boolean;
  compact?: boolean;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
}>();

function onChange(event: Event) {
  const target = event.target as HTMLInputElement;
  const requested = target.checked;
  // Keep the native input consistent until its owner accepts the new value.
  target.checked = props.modelValue;
  emit('update:modelValue', requested);
}
</script>
