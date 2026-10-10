<template>
  <label
    class="inline-flex items-center cursor-pointer"
    :class="{ 'opacity-50 cursor-not-allowed': disabled }"
  >
    <input
      type="checkbox"
      :checked="modelValue"
      :disabled="disabled"
      class="sr-only peer"
      @change="onChange"
    >
    <div class="relative w-11 h-6 bg-dark-border peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-primary rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary" />
    <span
      v-if="label"
      class="ml-3 text-sm font-medium text-gray-300"
    >{{ label }}</span>
  </label>
</template>

<script setup lang="ts">
const props = defineProps<{
  modelValue: boolean;
  label?: string;
  disabled?: boolean;
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
