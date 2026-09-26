<template>
  <aside
    class="overflow-hidden rounded-[24px] border border-white/10 bg-[#1d1e24] shadow-2xl shadow-black/20"
    data-test="image-current-panel"
  >
    <div class="flex min-h-14 items-center gap-3 px-4 py-3">
      <div class="min-w-0 flex-1">
        <p class="text-sm font-medium text-white">{{ t('aiCreation.currentGeneration') }}</p>
        <p class="mt-0.5 text-xs text-gray-400" data-test="image-current-summary">
          {{ batchStatusLabel }} · {{ succeededAttempts.length }}/{{ batch.attempts.length }}
        </p>
      </div>
    </div>

    <div class="border-t border-white/[0.06] p-4">
      <div class="grid grid-cols-2 gap-3">
        <button
          v-for="attempt in batch.attempts"
          :key="attempt.local_id"
          type="button"
          class="relative flex aspect-square min-h-0 overflow-hidden rounded-xl border bg-black/20 text-left transition-colors"
          :class="attemptButtonClass(attempt)"
          :disabled="!isSucceeded(attempt)"
          :aria-pressed="isSucceeded(attempt) ? selectedAttempt?.index === attempt.index : undefined"
          :data-test="`image-current-attempt-${attempt.index}`"
          @click="selectAttempt(attempt)"
        >
          <img
            v-if="isSucceeded(attempt)"
            :src="attemptImageUrl(attempt)"
            :alt="`${t('seedream.detail.candidateImage')} ${attempt.index + 1}`"
            class="h-full w-full object-cover"
          />
          <span v-else class="m-auto px-2 text-center text-xs text-gray-400">
            {{ attemptStatusLabel(attempt) }}
          </span>
          <span class="absolute left-2 top-2 rounded-md bg-black/60 px-1.5 py-0.5 text-[11px] text-white">
            {{ attempt.index + 1 }}
          </span>
        </button>
      </div>

      <button
        v-if="selectedAttempt"
        type="button"
        class="mt-4 flex h-10 w-full items-center justify-center rounded-xl bg-primary px-4 text-sm font-medium text-dark-bg transition-colors hover:bg-primary-600 disabled:cursor-wait disabled:opacity-60"
        :disabled="handoffPending"
        data-test="image-current-create-video"
        @click="emit('create-video', selectedAttempt.index)"
      >
        {{ t('aiCreation.useImageForVideo') }}
      </button>

      <p v-if="handoffError" class="mt-2 text-sm text-danger" role="alert">
        {{ handoffError }}
      </p>

      <RouterLink
        :to="`/image-generation/batches/${encodeURIComponent(batch.local_id)}`"
        class="mt-4 flex h-10 w-full items-center justify-center rounded-xl border border-white/10 text-sm text-gray-300 transition-colors hover:border-white/20 hover:bg-white/[0.05] hover:text-white"
        data-test="image-current-view-detail"
      >
        {{ t('seedream.board.viewDetail') }}
      </RouterLink>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { batchStatus } from '@/seedream-ui';
import type { SeedreamAttempt, SeedreamBatch } from '@/types';

const props = defineProps<{
  batch: SeedreamBatch;
  handoffPending?: boolean;
  handoffError?: string;
}>();

const emit = defineEmits<{
  'create-video': [attemptIndex: number];
}>();

const { t } = useI18n();
const selectedAttemptIndex = ref<number | null>(null);
const succeededAttempts = computed(() => props.batch.attempts.filter(isSucceeded));
const selectedAttempt = computed(() => (
  succeededAttempts.value.find((attempt) => attempt.index === selectedAttemptIndex.value)
  ?? succeededAttempts.value[0]
  ?? null
));

const batchStatusLabel = computed(() => {
  const status = batchStatus(props.batch);
  return t(`seedream.batch.${status}`);
});

watch(() => props.batch.local_id, () => {
  selectedAttemptIndex.value = null;
});

function isSucceeded(attempt: SeedreamAttempt): boolean {
  return attempt.status === 'succeeded' && Boolean(attempt.image_url);
}

function selectAttempt(attempt: SeedreamAttempt) {
  if (isSucceeded(attempt)) selectedAttemptIndex.value = attempt.index;
}

function attemptImageUrl(attempt: SeedreamAttempt): string {
  return attempt.image_url;
}

function attemptButtonClass(attempt: SeedreamAttempt): string {
  if (!isSucceeded(attempt)) return 'cursor-default border-white/[0.06]';
  return selectedAttempt.value?.index === attempt.index
    ? 'border-primary ring-1 ring-primary/40'
    : 'border-white/10 hover:border-white/30';
}

function attemptStatusLabel(attempt: SeedreamAttempt): string {
  switch (attempt.status) {
    case 'queued': return t('seedream.detail.queued');
    case 'generating': return t('seedream.batch.generating');
    case 'downloading': return t('aiCreation.candidateDownloading');
    case 'failed': return t('seedream.detail.failed');
    case 'unknown': return t('seedream.batch.unknown');
    case 'download_failed': return t('seedream.detail.downloadFailed');
    default: return '';
  }
}
</script>
