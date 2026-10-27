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
      <p
        v-if="updates.state?.release_notes"
        class="mt-3 whitespace-pre-wrap break-words text-sm text-gray-300"
      >
        {{ updates.state.release_notes }}
      </p>
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
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { ArrowTopRightOnSquareIcon, StarIcon } from '@heroicons/vue/24/outline';
import { api } from '@/api';
import Button from '@/components/common/Button.vue';
import SeedancePanel from '@/components/seedance/SeedancePanel.vue';
import { useUpdateStore } from '@/stores/updates';

const { t } = useI18n();
const updates = useUpdateStore();
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
