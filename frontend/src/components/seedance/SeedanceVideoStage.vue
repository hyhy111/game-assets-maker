<template>
  <section
    class="overflow-hidden rounded-[14px] border border-[var(--seedance-border)] bg-black/35"
    :class="fill ? 'lg:h-full' : ''"
  >
    <div v-if="phase === 'succeeded' && videoUrl" :class="fill ? 'lg:h-full' : ''">
      <video
        :controls="showControls"
        preload="metadata"
        :src="videoUrl"
        class="aspect-video w-full bg-black object-contain"
        :class="fill ? 'lg:h-full lg:aspect-auto' : ''"
        @play="hideControls"
        @pause="showControls = true"
        @ended="showControls = true"
        @click="showControls = true"
      />
      <p v-if="summary" class="border-t border-[var(--seedance-border)] px-4 py-3 text-sm text-gray-400">
        {{ summary }}
      </p>
    </div>
    <SeedanceEmptyState
      v-else-if="phase === 'cleared'"
      :title="t('seedance.ui.mediaUnavailable')"
      :description="t('seedance.ui.clearedNotice')"
      icon="error"
    />
    <SeedanceEmptyState
      v-else-if="phase === 'failed' || phase === 'expired' || phase === 'cancelled'"
      :title="t('seedance.preview.unavailableTitle')"
      :description="t('seedance.preview.unavailableDescription')"
      icon="error"
    />
    <div
      v-else
      class="flex aspect-video flex-col items-center justify-center gap-3 text-gray-400"
      :class="fill ? 'lg:h-full lg:aspect-auto' : ''"
      role="status"
    >
      <Loader :size="28" class="animate-spin text-primary" aria-hidden="true" />
      <p class="text-sm">{{ t(`seedance.status.${phase}`) }}</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Loader } from 'lucide-vue-next';
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
import type { SeedanceTaskPhase } from '@/seedance-ui';
import SeedanceEmptyState from './SeedanceEmptyState.vue';

defineProps<{
  phase: SeedanceTaskPhase;
  videoUrl?: string;
  summary?: string;
  fill?: boolean;
}>();

const { t } = useI18n();
const showControls = ref(true);

function hideControls() {
  showControls.value = false;
}
</script>
