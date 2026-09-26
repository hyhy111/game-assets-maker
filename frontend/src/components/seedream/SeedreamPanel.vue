<template>
  <section class="rounded-xl border border-dark-border bg-dark-surface p-5">
    <header v-if="title || description" class="mb-4">
      <h2 v-if="title" class="text-base font-semibold text-white">{{ title }}</h2>
      <p v-if="description" class="mt-1 text-sm leading-6 text-gray-400">
        {{ description }}
      </p>
    </header>
    <slot />
  </section>
</template>

<script setup lang="ts">
defineProps<{
  title?: string;
  description?: string;
}>();
</script>
