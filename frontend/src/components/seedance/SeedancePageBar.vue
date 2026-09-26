<template>
  <section>
    <div class="seedance-container py-4">
      <div class="flex flex-col gap-3 rounded-[14px] border border-[var(--seedance-border)] bg-[#1d1e1d] px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div class="min-w-0 flex-1">
          <h1 class="truncate text-lg font-semibold text-white">{{ title }}</h1>
          <p v-if="subtitle" class="mt-1 truncate text-sm text-[var(--seedance-muted)]">{{ subtitle }}</p>
        </div>
        <div v-if="$slots.actions" class="flex flex-nowrap gap-2">
          <slot name="actions" />
        </div>
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
