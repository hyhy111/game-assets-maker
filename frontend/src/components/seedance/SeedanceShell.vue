<template>
  <div class="seedance-workspace">
    <SeedanceTopNav />
    <slot name="page-bar" />
    <main class="seedance-container">
      <slot />
    </main>
  </div>
</template>

<script setup lang="ts">
import SeedanceTopNav from './SeedanceTopNav.vue';
</script>
