<template>
  <section
    class="rounded-lg border p-3"
    :class="toneClasses"
    aria-live="polite"
  >
    <div class="flex items-start gap-3">
      <Loader2
        v-if="presentation.busy"
        class="mt-0.5 h-4 w-4 shrink-0 animate-spin"
      />
      <CheckCircle
        v-else-if="status.phase === 'ready'"
        class="mt-0.5 h-4 w-4 shrink-0"
      />
      <AlertCircle
        v-else-if="status.phase === 'failed'"
        class="mt-0.5 h-4 w-4 shrink-0"
      />

      <div class="min-w-0 flex-1">
        <p class="text-sm font-medium">
          {{ t(presentation.messageKey, { model: status.model }) }}
        </p>
        <p class="mt-1 text-xs text-gray-400">
          {{ detailText }}
        </p>

        <div
          v-if="status.phase === 'downloading'"
          class="mt-2 h-1.5 overflow-hidden rounded-full bg-black/20"
        >
          <div
            v-if="progress !== null"
            class="h-full bg-primary transition-all"
            :style="{ width: `${progress}%` }"
          />
          <div
            v-else
            class="h-full w-1/3 animate-pulse rounded-full bg-primary"
          />
        </div>

        <label
          v-if="status.phase === 'needs_download' || presentation.retryable"
          class="mt-3 block text-xs"
        >
          {{ t('modelStatus.downloadSource') }}
          <Select
            v-model="source"
            :options="sourceOptions"
            class="mt-1"
          />
        </label>
        <Button
          v-if="status.phase === 'needs_download' || presentation.retryable"
          class="mt-3"
          size="sm"
          variant="secondary"
          @click="$emit('retry', source)"
        >
          {{ t(status.phase === 'needs_download' ? 'modelStatus.download' : 'modelStatus.retry') }}
        </Button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { AlertCircle, CheckCircle, Loader2 } from 'lucide-vue-next';
import { useI18n } from 'vue-i18n';
import { modelApproximateSizeMb, modelProgressPercent, modelStatusPresentation } from '@/model-status';
import type { ModelStatus } from '@/types';
import Button from '@/components/common/Button.vue';
import Select from '@/components/common/Select.vue';

const props = defineProps<{ status: ModelStatus }>();
defineEmits<{ retry: [source: 'modelscope' | 'github'] }>();
const source = ref<'modelscope' | 'github'>('modelscope');

const { t } = useI18n();
const sourceOptions = computed(() => [
  { value: 'modelscope', label: t('modelStatus.modelscope') },
  { value: 'github', label: 'GitHub' },
]);
const presentation = computed(() => modelStatusPresentation(props.status));
const progress = computed(() => modelProgressPercent(props.status));
const toneClasses = computed(() => ({
  info: 'border-primary/30 bg-primary/10 text-primary',
  success: 'border-success-500/30 bg-success-500/10 text-success-500',
  danger: 'border-danger-500/30 bg-danger-500/10 text-danger-500',
}[presentation.value.tone]));
const detailText = computed(() => {
  if (props.status.phase === 'needs_download') {
    const size = modelApproximateSizeMb(props.status.model);
    return size === null
      ? t('modelStatus.firstUseHintUnknownSize')
      : t('modelStatus.firstUseHint', { size });
  }
  if (props.status.phase === 'downloading') {
    return progress.value === null
      ? t('modelStatus.indeterminateProgress')
      : t('modelStatus.progress', {
        downloaded: formatBytes(props.status.downloaded_bytes),
        total: formatBytes(props.status.total_bytes),
      });
  }
  if (props.status.phase === 'initializing') return t('modelStatus.initializingHint');
  if (props.status.phase === 'failed') {
    return t(`modelStatus.errors.${props.status.error?.code ?? 'UNKNOWN'}`);
  }
  return t('modelStatus.readyHint');
});

function formatBytes(bytes: number | null): string {
  return bytes === null ? '—' : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
</script>
