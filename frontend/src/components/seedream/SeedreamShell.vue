<template>
  <div class="seedream-workspace min-h-screen bg-dark-bg">
    <SeedreamTopNav />
    <slot name="page-bar" />
    <main class="mx-auto w-full max-w-[1320px] px-4 py-6 sm:px-6">
      <slot />
    </main>
  </div>
</template>

<script setup lang="ts">
import SeedreamTopNav from './SeedreamTopNav.vue';
</script>
