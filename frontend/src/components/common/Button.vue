<template>
  <button
    :type="type"
    :disabled="disabled || loading"
    :class="buttonClasses"
    @click="$emit('click', $event)"
  >
    <span
      v-if="loading"
      class="mr-2"
    >
      <svg
        class="animate-spin h-4 w-4"
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
      >
        <circle
          class="opacity-25"
          cx="12"
          cy="12"
          r="10"
          stroke="currentColor"
          stroke-width="4"
        />
        <path
          class="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
        />
      </svg>
    </span>
    <slot />
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = withDefaults(defineProps<{
  type?: 'button' | 'submit' | 'reset';
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  disabled?: boolean;
  loading?: boolean;
  block?: boolean;
}>(), {
  type: 'button',
  variant: 'primary',
  size: 'md',
  disabled: false,
  loading: false,
  block: false
});

defineEmits<{
  click: [event: MouseEvent];
}>();

const buttonClasses = computed(() => {
  const baseClasses = 'inline-flex items-center justify-center whitespace-nowrap font-medium rounded-lg transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-dark-bg disabled:opacity-50 disabled:cursor-not-allowed';

  const variantClasses = {
    primary: 'bg-primary hover:bg-primary-600 text-dark-bg focus:ring-primary hover:shadow-lg hover:shadow-primary/25',
    secondary: 'bg-dark-surface border border-dark-border hover:bg-dark-border text-gray-200 focus:ring-gray-500',
    danger: 'bg-danger hover:bg-danger-600 text-white focus:ring-danger hover:shadow-lg hover:shadow-danger/25',
    ghost: 'bg-transparent hover:bg-dark-surface text-gray-300 hover:text-white focus:ring-gray-500'
  };

  const sizeClasses = {
    sm: 'px-3 py-1.5 text-sm',
    md: 'px-4 py-2 text-sm',
    lg: 'px-6 py-3 text-base'
  };

  const blockClass = props.block ? 'w-full' : '';

  return `${baseClasses} ${variantClasses[props.variant]} ${sizeClasses[props.size]} ${blockClass}`;
});
</script>
