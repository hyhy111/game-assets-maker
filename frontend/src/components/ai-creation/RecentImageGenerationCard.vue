<template>
  <article
    class="overflow-hidden rounded-xl border border-dark-border bg-dark-surface transition hover:border-primary/50"
    :data-test="`recent-image-${batch.local_id}`"
  >
    <div class="relative bg-[#18191c]">
      <button
        type="button"
        class="group/preview relative block aspect-video w-full overflow-hidden bg-black/25 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70"
        data-test="recent-image-main-preview"
        @click="emit('open', batch.local_id)"
      >
        <img
          v-if="selectedAttempt"
          :src="imageUrl(selectedAttempt.image_url)"
          :alt="`${t('seedream.detail.candidateImage')} ${selectedAttempt.index + 1}`"
          class="h-full w-full object-cover transition duration-300 group-hover/preview:brightness-105"
        >
        <span v-else class="grid h-full place-items-center text-sm text-gray-500">{{ statusText }}</span>
        <span class="absolute left-3 top-3 rounded-full px-3 py-1 text-xs font-medium shadow-sm" :class="statusClass">
          {{ statusText }}
        </span>
      </button>
      <div v-if="$slots['top-right']" class="absolute right-3 top-3 z-[2]">
        <slot name="top-right" :attempt="selectedAttempt" />
      </div>

      <div
        v-if="succeededAttempts.length"
        class="flex max-w-full justify-center gap-2 overflow-x-auto px-3 py-3"
        data-test="recent-image-thumbnails"
      >
        <button
          v-for="(attempt, index) in succeededAttempts"
          :key="attempt.local_id"
          type="button"
          draggable="true"
          class="h-14 w-14 shrink-0 overflow-hidden rounded-md border-2 bg-black/20 p-0.5 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70"
          :class="selectedAttempt?.index === attempt.index ? 'border-primary' : 'border-transparent hover:border-white/30'"
          :aria-label="`${t('seedream.detail.candidateImage')} ${index + 1}`"
          :aria-pressed="selectedAttempt?.index === attempt.index"
          :title="t('aiCreation.recent.dragImageToVideoFrame')"
          :data-test="`recent-image-thumbnail-${attempt.index}`"
          @click="selectedAttemptIndex = attempt.index"
          @dragstart="startImageDrag($event, attempt)"
        >
          <img
            :src="imageUrl(attempt.image_url)"
            alt=""
            draggable="false"
            class="h-full w-full rounded-[3px] object-cover"
          >
        </button>
      </div>
    </div>

    <div class="p-4">
      <div class="flex flex-wrap gap-1.5 text-xs text-gray-400">
        <span class="rounded-md bg-black/20 px-2 py-1">{{ modelLabel }}</span>
        <span class="rounded-md bg-black/20 px-2 py-1">{{ batch.request.resolution }}</span>
        <span class="rounded-md bg-black/20 px-2 py-1">{{ batch.request.ratio }}</span>
      </div>
      <dl class="mt-4 grid grid-cols-2 gap-3 border-t border-dark-border pt-4 text-xs">
        <div>
          <dt class="text-gray-500">{{ t('aiCreation.recent.createdAt') }}</dt>
          <dd class="mt-1 text-gray-300">{{ createdAt }}</dd>
        </div>
        <div class="text-right">
          <dt class="text-gray-500">{{ t('aiCreation.recent.elapsed') }}</dt>
          <dd class="mt-1 text-gray-300">{{ active ? t('aiCreation.recent.generating') : totalElapsed }}</dd>
        </div>
      </dl>
      <div v-if="$slots['bottom-right']" class="mt-3 flex justify-end">
        <slot name="bottom-right" />
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { batchStatus, formatElapsed, MODEL_LABELS } from '@/seedream-ui';
import { writeSeedreamImageDrag } from '@/seedream-image-drag';
import type { SeedreamAttempt, SeedreamBatch, SeedreamBatchStatus } from '@/types';

const props = defineProps<{ batch: SeedreamBatch }>();
const emit = defineEmits<{ open: [localId: string] }>();
const { t, locale } = useI18n();

const status = computed(() => batchStatus(props.batch));
const active = computed(() => status.value === 'generating');
const succeededAttempts = computed(() => props.batch.attempts.filter(
  (attempt) => attempt.status === 'succeeded' && attempt.image_url,
));
const selectedAttemptIndex = ref<number | null>(null);
const selectedAttempt = computed(() => (
  succeededAttempts.value.find((attempt) => attempt.index === selectedAttemptIndex.value)
  ?? succeededAttempts.value[0]
  ?? null
));
const modelLabel = computed(() => MODEL_LABELS[props.batch.request.model] ?? props.batch.request.model);
const createdAt = computed(() => formatDate(props.batch.created_at));
const totalElapsed = computed(() => {
  const started = Date.parse(props.batch.created_at);
  const terminalTimes = props.batch.attempts
    .map((attempt) => Date.parse(attempt.finished_at || ''))
    .filter(Number.isFinite);
  const fallback = Date.parse(props.batch.updated_at);
  const finished = terminalTimes.length ? Math.max(...terminalTimes) : fallback;
  return formatElapsed(Number.isFinite(started) && Number.isFinite(finished) ? (finished - started) / 1000 : 0);
});
const statusText = computed(() => t(statusLabelKey(status.value)));
const statusClass = computed(() => {
  switch (status.value) {
    case 'completed': return 'bg-success/20 text-black';
    case 'generating': return 'bg-primary/20 text-primary';
    case 'partially_complete': return 'bg-warning/20 text-warning';
    case 'failed': return 'bg-danger/20 text-danger';
    default: return 'bg-warning/20 text-warning';
  }
});

function imageUrl(url: string): string {
  return url;
}

function startImageDrag(event: DragEvent, attempt: SeedreamAttempt) {
  writeSeedreamImageDrag(event.dataTransfer, {
    localId: props.batch.local_id,
    attemptIndex: attempt.index,
  });
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(locale.value === 'zh-CN' ? 'zh-CN' : 'en-US', {
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}

function statusLabelKey(value: SeedreamBatchStatus): string {
  return {
    generating: 'aiCreation.recent.generating',
    completed: 'seedream.batch.completed',
    partially_complete: 'seedream.batch.partially_complete',
    failed: 'seedream.batch.failed',
    unknown: 'seedream.batch.unknown',
  }[value];
}
</script>
