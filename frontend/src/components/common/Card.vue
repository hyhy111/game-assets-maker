<template>
  <div class="bg-dark-surface border border-dark-border rounded-xl overflow-hidden">
    <div
      v-if="$slots.header"
      class="px-6 py-4 border-b border-dark-border"
    >
      <slot name="header" />
    </div>
    <div :class="bodyClasses">
      <slot />
    </div>
    <div
      v-if="$slots.footer"
      class="px-6 py-4 border-t border-dark-border bg-dark-surface/50"
    >
      <slot name="footer" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = withDefaults(defineProps<{
  padding?: 'none' | 'sm' | 'md' | 'lg';
}>(), {
  padding: 'md'
});

const bodyClasses = computed(() => {
  const paddingClasses = {
    none: '',
    sm: 'p-4',
    md: 'p-6',
    lg: 'p-8'
  };
  return paddingClasses[props.padding];
});
</script>
