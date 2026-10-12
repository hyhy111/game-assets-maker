<template>
  <SeedancePanel :title="t('seedance.preview.generationInfo')">
    <div class="grid gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(260px,.8fr)]">
      <div>
        <div class="flex items-center gap-2">
          <h3 class="text-xs font-medium uppercase tracking-wide text-[var(--seedance-muted)]">
            {{ t('seedance.preview.prompt') }}
          </h3>
          <button
            type="button"
            class="rounded p-1 text-[var(--seedance-muted)] transition hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
            :aria-label="t('seedance.preview.copyPrompt')"
            :title="t('seedance.preview.copyPrompt')"
            :disabled="!task.request.prompt"
            @click="copyPrompt"
          >
            <Check v-if="copied" :size="15" aria-hidden="true" />
            <Copy v-else :size="15" aria-hidden="true" />
          </button>
          <span v-if="copied" class="text-xs text-success" role="status">{{ t('seedance.preview.promptCopied') }}</span>
          <span v-else-if="copyFailed" class="text-xs text-danger" role="status">{{ t('seedance.preview.copyFailed') }}</span>
        </div>
        <p class="mt-2 whitespace-pre-wrap text-sm leading-6 text-gray-200">
          {{ task.request.prompt || t('seedance.ui.noPrompt') }}
        </p>
        <p v-if="safeError" class="mt-4 rounded-lg border border-danger/30 bg-danger/10 p-3 text-sm text-danger">
          {{ safeError }}
        </p>
      </div>
      <dl class="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
        <template v-for="item in items" :key="item.label">
          <dt class="text-[var(--seedance-muted)]">{{ item.label }}</dt>
          <dd class="break-all text-right text-gray-200">{{ item.value }}</dd>
        </template>
      </dl>
    </div>
  </SeedancePanel>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { Check, Copy } from 'lucide-vue-next';
import { useI18n } from 'vue-i18n';
import { useModelDisplayName } from '@/composables/useModelDisplayName';
import { formatBytes, formatElapsed } from '@/seedance-ui';
import type { SeedanceTask } from '@/types';
import SeedancePanel from './SeedancePanel.vue';

const props = defineProps<{
  task: SeedanceTask;
  output: Record<'resolution' | 'ratio' | 'duration' | 'fps', string>;
}>();
const { t, locale } = useI18n();
const { modelName } = useModelDisplayName();
const copied = ref(false);
const copyFailed = ref(false);
const safeError = computed(() => (
  props.task.error?.message
  || props.task.remote.error?.message
  || props.task.sync_status.error?.message
  || ''
));
const items = computed(() => {
  const totalTokens = props.task.remote.usage?.total_tokens;
  return [
  {
    label: t('seedance.preview.mode'),
    value: props.task.input_urls.last_frame ? t('seedance.preview.firstLastMode') : t('seedance.preview.firstFrameMode'),
  },
  { label: t('seedance.create.model'), value: modelName(props.task.request.model, 'video') },
  { label: t('seedance.create.resolution'), value: props.output.resolution },
  { label: t('seedance.create.ratio'), value: props.output.ratio },
  { label: t('seedance.create.duration'), value: props.output.duration },
  { label: 'FPS', value: props.output.fps },
  {
    label: t('seedance.create.audio'),
    value: props.task.request.generate_audio ? t('seedance.create.generateAudio') : t('seedance.ui.audioOff'),
  },
  { label: t('seedance.preview.elapsed'), value: formatElapsed(props.task.elapsed_seconds) },
  { label: t('seedance.preview.fileSize'), value: formatBytes(props.task.file_size_bytes) },
  { label: t('seedance.preview.taskId'), value: props.task.remote_id || '—' },
  {
    label: t('seedance.preview.totalTokens'),
    value: typeof totalTokens === 'number' ? totalTokens.toLocaleString(locale.value) : t('seedance.preview.tokensUnavailable'),
  },
  ];
});

async function copyPrompt() {
  const prompt = props.task.request.prompt;
  if (!prompt) return;

  copied.value = false;
  copyFailed.value = false;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(prompt);
    } else {
      const textarea = document.createElement('textarea');
      textarea.value = prompt;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.append(textarea);
      textarea.select();
      const copiedWithFallback = document.execCommand('copy');
      textarea.remove();
      if (!copiedWithFallback) throw new Error('Clipboard copy failed');
    }
    copied.value = true;
    window.setTimeout(() => { copied.value = false; }, 1600);
  } catch {
    copyFailed.value = true;
  }
}
</script>
