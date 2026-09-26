<template>
  <div class="mb-4 flex items-center justify-end">
    <button
      type="button"
      class="flex items-center gap-1.5 rounded-lg border border-dark-border bg-dark-surface px-3 py-2 text-sm text-gray-400 transition-colors hover:border-gray-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
      :disabled="store.loading"
      data-test="seedream-board-refresh"
      @click="load"
    >
      <RefreshCw class="h-4 w-4" />
      {{ t('common.refresh') }}
    </button>
  </div>

  <p v-if="store.error" class="mb-4 rounded-lg border border-danger/30 bg-danger/10 p-3 text-sm text-danger">
    {{ store.error.message }}
  </p>

  <SeedreamPanel v-if="store.loading && !batches.length">
    <div class="flex min-h-56 items-center justify-center text-sm text-gray-400" role="status">
      {{ t('common.loading') }}
    </div>
  </SeedreamPanel>

  <SeedreamPanel v-else-if="!batches.length">
    <div class="flex min-h-56 flex-col items-center justify-center gap-3 text-center" data-test="seedream-board-empty">
      <p class="text-sm text-gray-400">{{ t('seedream.board.empty') }}</p>
    </div>
  </SeedreamPanel>

  <div v-else class="grid grid-cols-1 gap-4 md:grid-cols-2">
    <article
      v-for="batch in batches"
      :key="batch.local_id"
      class="group cursor-pointer overflow-hidden rounded-xl border border-dark-border bg-dark-surface transition hover:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/60"
      :data-test="`seedream-board-card-${batch.local_id}`"
      tabindex="0"
      role="button"
      @click="openBatch(batch.local_id)"
      @keydown.enter="openBatch(batch.local_id)"
      @keydown.space.prevent="openBatch(batch.local_id)"
    >
      <div class="relative aspect-[16/9] overflow-hidden bg-black/20">
        <div
          v-if="thumbnailAttempts(batch).length"
          class="grid h-full gap-px bg-dark-border"
          :class="thumbnailAttempts(batch).length === 1 ? 'grid-cols-1' : 'grid-cols-4'"
          :style="thumbnailGridStyle(batch)"
        >
          <img
            v-for="(attempt, index) in thumbnailAttempts(batch)"
            :key="attempt.local_id"
            :src="attemptImageUrl(attempt)"
            :alt="`${t('seedream.detail.candidateImage')} ${index + 1}`"
            class="h-full min-h-0 w-full object-cover transition duration-300 group-hover:brightness-105"
            :class="thumbnailItemClass(batch, index)"
            :data-test="`seedream-board-thumbnail-${batch.local_id}-${attempt.index}`"
          />
        </div>
        <div v-else class="flex h-full items-center justify-center text-sm text-gray-500">
          {{ statusLabel(batch) }}
        </div>
        <span
          class="absolute right-3 top-3 inline-flex items-center rounded-full px-3 py-1 text-xs font-medium shadow-sm"
          :class="statusBadgeClass(batch)"
          :data-test="`seedream-board-status-${batch.local_id}`"
        >
          {{ statusLabel(batch) }}
        </span>
        <span
          v-if="sequenceOf(batch)"
          class="seedream-sequence absolute left-3 top-3"
          :data-test="`seedream-board-sequence-${batch.local_id}`"
        >{{ sequenceOf(batch) }}</span>
      </div>
      <div class="p-4">
        <div class="flex flex-wrap gap-1.5 text-xs text-gray-400">
          <span class="rounded-md bg-black/20 px-2 py-1" :data-test="`seedream-board-model-${batch.local_id}`">{{ modelLabel(batch) }}</span>
          <span class="rounded-md bg-black/20 px-2 py-1" :data-test="`seedream-board-resolution-${batch.local_id}`">{{ batch.request.resolution }}</span>
          <span class="rounded-md bg-black/20 px-2 py-1" :data-test="`seedream-board-ratio-${batch.local_id}`">{{ batch.request.ratio }}</span>
          <span class="rounded-md bg-black/20 px-2 py-1" :data-test="`seedream-board-count-${batch.local_id}`">{{ t('seedream.board.countLabel', { count: batch.attempts.length }) }}</span>
        </div>
        <div class="mt-3 border-t border-dark-border pt-2 text-xs text-gray-500">
          <span :data-test="`seedream-board-created-${batch.local_id}`">{{ formatCreated(batch.created_at) }}</span>
        </div>
      </div>
    </article>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
import { RefreshCw } from 'lucide-vue-next';
import SeedreamPanel from '@/components/seedream/SeedreamPanel.vue';
import { batchStatus, duplicateBatchSequence, MODEL_LABELS } from '@/seedream-ui';
import { useSeedreamStore } from '@/stores/seedream';
import type { SeedreamAttempt, SeedreamBatch, SeedreamBatchStatus } from '@/types';

const { t, locale } = useI18n();
const router = useRouter();
const store = useSeedreamStore();
const batches = computed(() => store.batches);

onMounted(load);

function load() {
  return store.loadBatches();
}

function openBatch(localId: string) {
  router.push(`/image-generation/batches/${encodeURIComponent(localId)}`);
}

function sequenceOf(batch: SeedreamBatch): string {
  return duplicateBatchSequence(batch, batches.value);
}

function modelLabel(batch: SeedreamBatch): string {
  return MODEL_LABELS[batch.request.model] ?? batch.request.model;
}

function thumbnailAttempts(batch: SeedreamBatch): SeedreamAttempt[] {
  return batch.attempts.filter((attempt) => !!attempt.image_url);
}

function attemptImageUrl(attempt: SeedreamAttempt): string {
  return attempt.image_url;
}

function thumbnailGridStyle(batch: SeedreamBatch): Record<string, string> {
  const count = thumbnailAttempts(batch).length;
  return {
    gridTemplateRows: `repeat(${Math.ceil(count / 2)}, minmax(0, 1fr))`,
  };
}

function thumbnailItemClass(batch: SeedreamBatch, index: number): string {
  const count = thumbnailAttempts(batch).length;
  if (count === 1) return '';
  return count % 2 === 1 && index === count - 1 ? 'col-span-2 col-start-2' : 'col-span-2';
}

function statusLabel(batch: SeedreamBatch): string {
  const status = batchStatus(batch);
  switch (status) {
    case 'generating': return t('seedream.batch.generating');
    case 'completed': return t('seedream.batch.completed');
    case 'partially_complete': return t('seedream.batch.partially_complete');
    case 'failed': return t('seedream.batch.failed');
    case 'unknown': return t('seedream.batch.unknown');
    default: return '';
  }
}

function statusBadgeClass(batch: SeedreamBatch): string {
  const status: SeedreamBatchStatus = batchStatus(batch);
  switch (status) {
    case 'completed': return 'bg-success/20 text-black';
    case 'generating': return 'bg-primary/20 text-primary';
    case 'partially_complete': return 'bg-warning/20 text-warning';
    case 'failed': return 'bg-danger/20 text-danger';
    case 'unknown': return 'bg-warning/20 text-warning';
    default: return 'bg-gray-500/20 text-gray-400';
  }
}

function formatCreated(iso: string): string {
  try {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return iso;
    return date.toLocaleString(locale.value === 'zh-CN' ? 'zh-CN' : 'en-US', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}
</script>
