<template>
  <span
    class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium backdrop-blur"
    :class="badgeClass"
  >
    <span class="h-1.5 w-1.5 rounded-full bg-current" />
    {{ label }}
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type { SeedanceTask } from '@/types';
import { seedanceTaskPhase } from '@/seedance-ui';

const props = defineProps<{ task: SeedanceTask }>();
const { t } = useI18n();
const phase = computed(() => seedanceTaskPhase(props.task));
const label = computed(() => t(`seedance.status.${phase.value}`));
const badgeClass = computed(() => {
  if (phase.value === 'succeeded') return 'border-success/30 bg-success/15 text-success';
  if (phase.value === 'failed' || phase.value === 'expired') return 'border-danger/30 bg-danger/15 text-danger';
  if (phase.value === 'cleared' || phase.value === 'cancelled') return 'border-gray-500/30 bg-black/60 text-gray-300';
  return 'border-primary/30 bg-primary/15 text-primary-300';
});
</script>
