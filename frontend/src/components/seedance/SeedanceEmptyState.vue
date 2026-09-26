<template>
  <div class="flex min-h-64 flex-col items-center justify-center px-6 py-12 text-center">
    <span class="grid h-14 w-14 place-items-center rounded-2xl bg-white/[0.04] text-gray-400">
      <Video v-if="icon === 'video'" :size="26" aria-hidden="true" />
      <ListVideo v-else-if="icon === 'tasks'" :size="26" aria-hidden="true" />
      <AlertCircle v-else :size="26" aria-hidden="true" />
    </span>
    <h2 class="mt-5 text-lg font-semibold text-white">{{ title }}</h2>
    <p class="mt-2 max-w-lg text-sm leading-6 text-[var(--seedance-muted)]">{{ description }}</p>
    <div v-if="$slots.actions" class="mt-6 flex flex-wrap justify-center gap-3">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { AlertCircle, ListVideo, Video } from 'lucide-vue-next';

withDefaults(defineProps<{
  title: string;
  description: string;
  icon?: 'video' | 'tasks' | 'error';
}>(), {
  icon: 'video',
});
</script>
