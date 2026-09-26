<template>
  <div class="space-y-2">
    <label
      v-if="label"
      :for="inputId"
      class="block text-sm font-medium text-gray-300"
    >
      {{ label }}
    </label>
    <div class="relative">
      <input
        :id="inputId"
        ref="inputRef"
        :type="type"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        :readonly="readonly"
        :list="list"
        :min="min"
        :max="max"
        :autocomplete="autocomplete"
        :class="[
          'w-full px-3 py-2 bg-dark-surface border border-dark-border rounded-lg text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed',
          type === 'number' ? 'pr-7 text-center' : ''
        ]"
        @input="onInput"
        @change="$emit('change', $event)"
        @blur="$emit('blur', $event)"
        @focus="$emit('focus', $event)"
        @keydown="onKeydown"
      >
      <!-- Custom number spinner -->
      <div
        v-if="type === 'number' && !disabled && !readonly"
        class="absolute inset-y-1 right-1 w-5 flex flex-col border-l border-dark-border"
      >
        <button
          type="button"
          class="flex-1 flex items-center justify-center hover:bg-dark-border rounded-tr text-gray-400 hover:text-white transition-colors"
          @mousedown.prevent="step(1)"
        >
          <ChevronUp class="w-3 h-3" />
        </button>
        <button
          type="button"
          class="flex-1 flex items-center justify-center hover:bg-dark-border rounded-br text-gray-400 hover:text-white transition-colors"
          @mousedown.prevent="step(-1)"
        >
          <ChevronDown class="w-3 h-3" />
        </button>
      </div>
      <div
        v-if="$slots.suffix"
        class="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none"
      >
        <slot name="suffix" />
      </div>
    </div>
    <p
      v-if="error"
      class="text-sm text-danger"
    >
      {{ error }}
    </p>
    <p
      v-else-if="hint"
      class="text-sm text-gray-500"
    >
      {{ hint }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { ChevronUp, ChevronDown } from 'lucide-vue-next';

const props = defineProps<{
  modelValue: string | number;
  type?: string;
  label?: string;
  placeholder?: string;
  hint?: string;
  error?: string;
  disabled?: boolean;
  readonly?: boolean;
  list?: string;
  min?: string | number;
  max?: string | number;
  autocomplete?: string;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: string | number];
  change: [event: Event];
  blur: [event: Event];
  focus: [event: Event];
}>();

const inputId = computed(() => `input-${Math.random().toString(36).substr(2, 9)}`);
const inputRef = ref<HTMLInputElement | null>(null);

function onInput(event: Event) {
  const target = event.target as HTMLInputElement;
  let value: string | number = target.value;

  if (props.type === 'number') {
    value = value === '' ? '' : Number(value);
  }

  emit('update:modelValue', value);
}

function onKeydown(event: KeyboardEvent) {
  // Blur input on Enter key to confirm input
  if (event.key === 'Enter') {
    const target = event.target as HTMLInputElement;
    target.blur();
  }
}

function step(delta: number) {
  if (!inputRef.value) return;
  inputRef.value.stepUp(delta);
  inputRef.value.dispatchEvent(new Event('input'));
  inputRef.value.dispatchEvent(new Event('change'));
  // Update v-model
  let value: string | number = inputRef.value.value;
  if (props.type === 'number') {
    value = value === '' ? '' : Number(value);
  }
  emit('update:modelValue', value);
}
</script>

<style scoped>
/* Hide default number spinner arrows */
input[type="number"]::-webkit-inner-spin-button,
input[type="number"]::-webkit-outer-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

/* Firefox */
input[type="number"] {
  -moz-appearance: textfield;
}
</style>
