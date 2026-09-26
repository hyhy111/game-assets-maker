<template>
  <SeedancePanel v-if="items.length" :title="t('seedance.preview.referenceFrames')">
    <div class="grid gap-3 sm:grid-cols-3">
      <figure v-for="item in items" :key="item.key" class="overflow-hidden rounded-xl bg-black/20">
        <img :src="item.url" :alt="item.label" class="aspect-video w-full object-contain">
        <figcaption class="border-t border-[var(--seedance-border)] px-3 py-2 text-xs text-gray-400">
          {{ item.label }}
        </figcaption>
      </figure>
    </div>
  </SeedancePanel>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type { SeedanceTask } from '@/types';
import SeedancePanel from './SeedancePanel.vue';

const props = defineProps<{ task: SeedanceTask }>();
const { t } = useI18n();
const items = computed(() => [
  { key: 'first', label: t('seedance.preview.inputFirstFrame'), url: props.task.input_urls.first_frame },
  { key: 'last', label: t('seedance.preview.inputLastFrame'), url: props.task.input_urls.last_frame },
  { key: 'returned', label: t('seedance.preview.returnedLastFrame'), url: props.task.output_urls.returned_last_frame },
].filter((item): item is { key: string; label: string; url: string } => Boolean(item.url)));
</script>
