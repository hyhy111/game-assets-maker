<template>
  <article
    class="group cursor-pointer overflow-hidden rounded-[14px] border border-[var(--seedance-border)] bg-[var(--seedance-surface)] transition hover:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/60"
    tabindex="0"
    role="button"
    @click="openTask"
    @keydown.enter.self="openTask"
    @keydown.space.self.prevent="openTask"
  >
    <div class="relative aspect-video bg-black/25">
      <img v-if="previewUrl" :src="previewUrl" alt="" class="h-full w-full object-cover">
      <div v-else class="grid h-full place-items-center text-gray-600">
        <Video :size="32" aria-hidden="true" />
      </div>
      <div class="absolute left-3 top-3 flex items-center gap-1.5">
        <SeedanceStatusBadge :task="task" />
        <PlatformSourceBadge :source="task.source" />
      </div>
      <span
        v-if="sequence"
        class="absolute bottom-3 left-3 rounded-full bg-black/70 px-2.5 py-1 text-xs text-gray-200"
      >
        {{ sequence }}
      </span>
      <span
        v-if="task.protected"
        class="absolute right-3 top-3 rounded-full bg-black/70 px-2.5 py-1 text-xs text-gray-200"
      >
        {{ t('seedance.tasks.protected') }}
      </span>
    </div>

    <div class="p-4">
      <div class="flex flex-wrap gap-1.5 text-xs text-gray-400">
        <span v-for="tag in tags" :key="tag" class="rounded-md bg-black/20 px-2 py-1">{{ tag }}</span>
      </div>

      <dl class="mt-4 grid grid-cols-2 gap-3 border-t border-[var(--seedance-border)] pt-4 text-xs">
        <div>
          <dt class="text-[var(--seedance-muted)]">{{ t('seedance.tasks.createdAt') }}</dt>
          <dd class="mt-1 text-gray-300">{{ createdAt }}</dd>
        </div>
        <div>
          <dt class="text-[var(--seedance-muted)]">{{ t('seedance.tasks.elapsed') }}</dt>
          <dd class="mt-1 text-gray-300">{{ formatElapsed(task.elapsed_seconds) }}</dd>
        </div>
      </dl>

      <p v-if="task.cache_status === 'cleared'" class="mt-3 text-xs leading-5 text-warning">
        {{ t('seedance.ui.clearedNotice') }}
      </p>
      <p v-else-if="task.error" class="mt-3 line-clamp-2 text-xs leading-5 text-danger">
        {{ task.error.message }}
      </p>
      <p v-if="downloadLinkMayBeExpired" class="mt-3 text-xs leading-5 text-warning">
        {{ t('seedance.ui.downloadUrlMayBeExpired') }}
      </p>

      <div class="mt-4 flex flex-wrap gap-2">
        <button
          v-for="action in actions"
          :key="action"
          type="button"
          class="rounded-lg px-3 py-2 text-xs font-medium transition"
          :class="actionClass(action)"
          @click.stop="handleAction(action)"
        >
          {{ t(actionLabelKeys[action]) }}
        </button>
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { Video } from 'lucide-vue-next';
import { useI18n } from 'vue-i18n';
import { useModelDisplayName } from '@/composables/useModelDisplayName';
import {
  downloadUrlMayBeExpired,
  formatElapsed,
  seedanceTaskActions,
  type SeedanceTaskAction,
} from '@/seedance-ui';
import type { SeedanceTask } from '@/types';
import PlatformSourceBadge from '@/components/ai-creation/PlatformSourceBadge.vue';
import SeedanceStatusBadge from './SeedanceStatusBadge.vue';

const props = defineProps<{ task: SeedanceTask; sequence?: string }>();
const emit = defineEmits<{
  open: [id: string];
  cancel: [id: string];
  'retry-generation': [id: string];
  'retry-download': [id: string];
  regenerate: [id: string];
  continue: [id: string];
  delete: [id: string];
}>();
const { t, locale } = useI18n();
const { modelName } = useModelDisplayName();

const actions = computed(() => seedanceTaskActions(props.task));
const downloadLinkMayBeExpired = computed(() => (
  actions.value.includes('retry-download') && downloadUrlMayBeExpired(props.task)
));
const previewUrl = computed(() => (
  props.task.output_urls.thumbnail || props.task.input_urls.first_frame || ''
));
const createdAt = computed(() => (
  new Date(props.task.created_at).toLocaleString(locale.value)
));
const tags = computed(() => [
  modelName(props.task.request.model, 'video'),
  props.task.request.resolution,
  props.task.request.ratio === 'adaptive' ? t('seedance.create.adaptive') : props.task.request.ratio,
  props.task.request.duration === -1 ? t('seedance.ui.smart') : `${props.task.request.duration}s`,
]);

const actionLabelKeys: Record<SeedanceTaskAction, string> = {
  cancel: 'seedance.tasks.cancel',
  view: 'seedance.tasks.viewDetails',
  continue: 'seedance.ui.continueGeneration',
  regenerate: 'seedance.tasks.regenerate',
  'retry-generation': 'seedance.tasks.retry',
  'retry-download': 'seedance.ui.redownload',
  delete: 'seedance.tasks.delete',
};

function handleAction(action: SeedanceTaskAction) {
  if (action === 'view') {
    emit('open', props.task.local_id);
    return;
  }
  if (action === 'continue') {
    emit('continue', props.task.local_id);
    return;
  }
  if (action === 'cancel') emit('cancel', props.task.local_id);
  else if (action === 'regenerate') emit('regenerate', props.task.local_id);
  else if (action === 'retry-generation') emit('retry-generation', props.task.local_id);
  else if (action === 'retry-download') emit('retry-download', props.task.local_id);
  else emit('delete', props.task.local_id);
}

function openTask() {
  emit('open', props.task.local_id);
}

function actionClass(action: SeedanceTaskAction) {
  if (action === 'view' || action === 'continue') return 'bg-primary text-dark-bg hover:bg-primary-600';
  if (action === 'delete') return 'text-gray-400 hover:bg-danger/10 hover:text-danger';
  return 'bg-white/[0.06] text-gray-200 hover:bg-white/[0.1]';
}
</script>
