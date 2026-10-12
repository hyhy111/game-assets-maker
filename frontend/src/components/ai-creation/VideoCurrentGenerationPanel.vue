<template>
  <section
    class="flex h-full flex-col overflow-hidden rounded-[20px] border border-white/10 bg-[#1f1f1f] shadow-2xl shadow-black/20"
    data-test="video-current-generation-panel"
  >
    <header class="flex min-h-14 items-center gap-3 px-4 py-3">
      <h2 class="text-sm font-semibold text-white">{{ t('seedance.tasks.title') }}</h2>
      <SeedanceStatusBadge :task="task" />
      <PlatformSourceBadge :source="task.source" />
      <button
        type="button"
        class="ml-auto grid h-8 w-8 shrink-0 place-items-center rounded-lg text-gray-400 transition-colors hover:bg-white/[0.06] hover:text-white"
        :aria-label="t('aiCreation.dismissCurrent')"
        data-test="video-current-close"
        @click="emit('close')"
      >
        <svg class="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
          <path d="M3 3l10 10M13 3L3 13" />
        </svg>
      </button>
    </header>

    <div class="flex min-h-0 flex-1 flex-col border-t border-white/[0.06] p-4 sm:p-5">
      <SeedanceVideoStage
        class="min-h-0 flex-1"
        :phase="phase"
        :video-url="task.output_urls.video"
        fill
      />

      <p v-if="task.error" class="mt-4 text-sm leading-5 text-danger" role="alert">
        {{ task.error.message }}
      </p>
      <p v-if="downloadLinkMayBeExpired" class="mt-4 text-sm leading-5 text-warning">
        {{ t('seedance.ui.downloadUrlMayBeExpired') }}
      </p>

      <div class="mt-4 flex h-11 flex-nowrap items-center gap-2">
        <Button v-if="canCancel" variant="secondary" @click="emit('cancel', task.local_id)">
          {{ t('seedance.tasks.cancel') }}
        </Button>
        <Button v-if="canRetryDownload" variant="secondary" @click="emit('retry-download', task.local_id)">
          {{ t('seedance.ui.redownload') }}
        </Button>
        <Button class="ml-auto" @click="emit('open-detail', task.local_id)">
          {{ t('seedance.tasks.viewDetails') }}
        </Button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import Button from '@/components/common/Button.vue';
import PlatformSourceBadge from '@/components/ai-creation/PlatformSourceBadge.vue';
import SeedanceStatusBadge from '@/components/seedance/SeedanceStatusBadge.vue';
import SeedanceVideoStage from '@/components/seedance/SeedanceVideoStage.vue';
import { downloadUrlMayBeExpired, seedanceTaskActions, seedanceTaskPhase } from '@/seedance-ui';
import type { SeedanceTask } from '@/types';

const props = defineProps<{
  task: SeedanceTask;
}>();

const emit = defineEmits<{
  cancel: [localId: string];
  'retry-download': [localId: string];
  'open-detail': [localId: string];
  close: [];
}>();

const { t } = useI18n();
const phase = computed(() => seedanceTaskPhase(props.task));
const actions = computed(() => seedanceTaskActions(props.task));
const canCancel = computed(() => actions.value.includes('cancel'));
const canRetryDownload = computed(() => actions.value.includes('retry-download'));
const downloadLinkMayBeExpired = computed(() => canRetryDownload.value && downloadUrlMayBeExpired(props.task));
</script>
