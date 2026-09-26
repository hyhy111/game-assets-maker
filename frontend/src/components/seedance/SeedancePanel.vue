<template>
  <section class="seedance-panel" :class="toneClass">
    <header v-if="title || description" class="mb-4">
      <h2 v-if="title" class="text-base font-semibold text-white">{{ title }}</h2>
      <p v-if="description" class="mt-1 text-sm leading-6 text-[var(--seedance-muted)]">
        {{ description }}
      </p>
    </header>
    <slot />
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = withDefaults(defineProps<{
  title?: string;
  description?: string;
  tone?: 'default' | 'success' | 'warning';
}>(), {
  title: '',
  description: '',
  tone: 'default',
});

const toneClass = computed(() => ({
  default: '',
  success: 'seedance-panel-success',
  warning: 'seedance-panel-warning',
}[props.tone]));
</script>
