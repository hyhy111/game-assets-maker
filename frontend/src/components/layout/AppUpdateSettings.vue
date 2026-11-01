<template>
  <SeedancePanel
    class="mb-5"
    :title="t('updates.title')"
    data-test="app-update-settings"
  >
    <div class="flex flex-wrap items-center justify-between gap-4">
      <div>
        <p class="text-sm text-gray-200">
          {{ t('updates.currentVersion', { version: updates.currentVersion || '—' }) }}
        </p>
        <p
          v-if="updates.checking"
          class="mt-2 text-sm text-gray-400"
          role="status"
        >
          {{ t('updates.checking') }}
        </p>
        <p
          v-else-if="updates.hasUpdate"
          class="mt-2 text-sm text-primary"
          role="status"
        >
          {{ t('updates.available', { version: updates.state?.latest_version }) }}
        </p>
        <p
          v-else-if="updates.state?.status === 'up_to_date'"
          class="mt-2 text-sm text-gray-400"
        >
          {{ t('updates.upToDate') }}
        </p>
        <p
          v-else-if="updates.state?.status === 'ignored'"
          class="mt-2 text-sm text-gray-400"
        >
          {{ t('updates.ignored', { version: updates.state.latest_version }) }}
        </p>
        <p
          v-else-if="updates.state?.status === 'error'"
          class="mt-2 text-sm text-gray-400"
          role="status"
        >
          {{ t(`updates.errors.${updates.state.error || 'NETWORK_ERROR'}`) }}
        </p>
      </div>
      <div
        v-if="updates.canUpdate"
        class="flex flex-wrap items-center gap-2"
      >
        <Button
          type="button"
          :disabled="updates.actionPending"
          data-test="app-update-open"
          @click="updates.openUpdate"
        >
          {{ t('updates.update') }}
        </Button>
        <Button
          v-if="updates.hasUpdate"
          type="button"
          variant="ghost"
          :disabled="updates.actionPending"
          data-test="app-update-ignore"
          @click="updates.ignoreCurrentVersion"
        >
          {{ t('updates.ignore') }}
        </Button>
      </div>
    </div>
    <div
      v-if="updates.canUpdate"
      class="mt-4 border-t border-dark-border pt-4"
    >
      <p class="text-xs text-gray-400">
        {{ t('updates.manualInstall') }}
      </p>
      <details
        v-if="updates.state?.release_notes"
        :key="updates.state.latest_version"
        class="group mt-3"
        data-test="app-update-details"
      >
        <summary
          class="inline-flex cursor-pointer list-none items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-gray-200 hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary [&::-webkit-details-marker]:hidden"
          data-test="app-update-details-toggle"
        >
          <ChevronDown class="h-4 w-4 transition-transform group-open:rotate-180" aria-hidden="true" />
          <span class="group-open:hidden">{{ t('updates.showDetails') }}</span>
          <span class="hidden group-open:inline">{{ t('updates.hideDetails') }}</span>
        </summary>
        <div class="release-notes" data-test="app-update-release-notes" v-html="releaseNotesHtml" />
      </details>
    </div>
    <p
      v-if="updates.actionError"
      class="mt-3 text-sm text-danger"
      role="alert"
    >
      {{ t(`updates.${updates.actionError}`) }}
    </p>
    <div class="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-dark-border pt-4">
      <p class="text-sm text-gray-400">
        {{ t('updates.starHint') }}
      </p>
      <Button
        type="button"
        variant="primary"
        :loading="openingRepository"
        data-test="github-star-open"
        @click="openRepository"
      >
        <StarIcon
          class="mr-2 h-4 w-4"
          aria-hidden="true"
        />
        {{ t('updates.starAction') }}
        <ArrowTopRightOnSquareIcon
          class="ml-2 h-4 w-4"
          aria-hidden="true"
        />
      </Button>
    </div>
    <p
      v-if="repositoryError"
      class="mt-3 text-sm text-danger"
      role="alert"
    >
      {{ t('updates.starOpenFailed') }}
    </p>
  </SeedancePanel>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { ChevronDown } from 'lucide-vue-next';
import { useI18n } from 'vue-i18n';
import { renderReleaseNotes } from '@/release-notes';
import { ArrowTopRightOnSquareIcon, StarIcon } from '@heroicons/vue/24/outline';
import { api } from '@/api';
import Button from '@/components/common/Button.vue';
import SeedancePanel from '@/components/seedance/SeedancePanel.vue';
import { useUpdateStore } from '@/stores/updates';

const { t } = useI18n();
const updates = useUpdateStore();
const releaseNotesHtml = computed(() => renderReleaseNotes(updates.state?.release_notes ?? ''));
const openingRepository = ref(false);
const repositoryError = ref(false);

async function openRepository() {
  if (openingRepository.value) return;
  openingRepository.value = true;
  repositoryError.value = false;
  try {
    repositoryError.value = !await api.system.openGithubRepository();
  } catch {
    repositoryError.value = true;
  } finally {
    openingRepository.value = false;
  }
}
</script>

<style scoped>
.release-notes {
  @apply mt-3 overflow-x-auto break-words text-sm leading-6 text-gray-300;
}
.release-notes :deep(h1),
.release-notes :deep(h2),
.release-notes :deep(h3),
.release-notes :deep(h4),
.release-notes :deep(h5),
.release-notes :deep(h6) {
  @apply mb-2 mt-4 font-semibold text-white;
}
.release-notes :deep(h1) { @apply text-lg; }
.release-notes :deep(h2) { @apply text-base; }
.release-notes :deep(p),
.release-notes :deep(ul),
.release-notes :deep(ol),
.release-notes :deep(pre),
.release-notes :deep(blockquote),
.release-notes :deep(table) {
  @apply my-3;
}
.release-notes :deep(ul) { @apply list-disc pl-5; }
.release-notes :deep(ol) { @apply list-decimal pl-5; }
.release-notes :deep(li > ul),
.release-notes :deep(li > ol) { @apply my-1; }
.release-notes :deep(a) { @apply text-primary underline underline-offset-2; }
.release-notes :deep(code) { @apply rounded bg-white/10 px-1 py-0.5 font-mono text-xs; }
.release-notes :deep(pre) { @apply overflow-x-auto rounded-lg bg-black/30 p-3; }
.release-notes :deep(pre code) { @apply bg-transparent p-0; }
.release-notes :deep(blockquote) { @apply border-l-2 border-dark-border pl-3 text-gray-400; }
.release-notes :deep(table) { @apply w-full border-collapse text-left; }
.release-notes :deep(th),
.release-notes :deep(td) { @apply border border-dark-border px-3 py-2; }
.release-notes :deep(hr) { @apply my-4 border-dark-border; }
</style>
