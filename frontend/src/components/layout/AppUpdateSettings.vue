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
  </SeedancePanel>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import Button from '@/components/common/Button.vue';
import SeedancePanel from '@/components/seedance/SeedancePanel.vue';
import { useUpdateStore } from '@/stores/updates';

const { t } = useI18n();
const updates = useUpdateStore();
</script>
