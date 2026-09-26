<template>
  <section class="mx-auto w-full max-w-[1320px] px-4 pt-6 sm:px-6">
    <div class="flex flex-col gap-3 rounded-[14px] border border-dark-border bg-dark-surface px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 class="text-lg font-semibold text-white">{{ title }}</h1>
        <p v-if="subtitle" class="mt-1 text-sm text-gray-400">{{ subtitle }}</p>
      </div>
      <div v-if="$slots.actions" class="flex flex-wrap gap-2">
        <slot name="actions" />
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
defineProps<{
  title: string;
  subtitle?: string;
}>();
</script>
