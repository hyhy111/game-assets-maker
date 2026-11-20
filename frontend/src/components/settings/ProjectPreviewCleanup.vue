<template>
  <SeedancePanel
    :title="t('previewCleanup.title')"
    :description="t('previewCleanup.description')"
  >
    <fieldset
      :disabled="disabled || cleaning || !!confirmed"
      class="mt-4"
    >
      <legend class="mb-2 text-sm font-medium text-gray-200">
        {{ t('previewCleanup.createdRange') }}
      </legend>
      <div class="flex flex-wrap gap-3">
        <label
          v-for="days in ageOptions"
          :key="days"
          class="flex items-center gap-2 rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-sm text-gray-100"
        >
          <input
            v-model="ageDays"
            type="radio"
            name="preview-cleanup-age"
            :value="days"
            class="accent-primary"
          >
          {{ t('previewCleanup.daysAgo', { days }) }}
        </label>
      </div>
    </fieldset>

    <div class="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2">
      <Button
        ref="cleanButton"
        type="button"
        variant="danger"
        :disabled="disabled || scanning || cleaning || !plan?.project_ids.length"
        :loading="cleaning"
        data-test="preview-cleanup-open"
        @click="openConfirmation"
      >
        {{ t('previewCleanup.title') }}
      </Button>
      <p
        class="text-sm text-gray-300"
        role="status"
      >
        {{ scanning ? t('previewCleanup.scanning') : estimate }}
      </p>
    </div>
    <p
      v-if="plan?.skipped || plan?.failed"
      class="mt-2 text-sm text-gray-400"
    >
      {{ t('previewCleanup.skipped', { count: plan.skipped + plan.failed }) }}
    </p>
    <p
      v-if="result"
      role="status"
      class="mt-2 text-sm text-gray-300"
    >
      {{ t('previewCleanup.result', { count: result.frame_count, size: formatBytes(result.bytes) }) }}
      {{ result.skipped || result.failed ? t('previewCleanup.partial', { count: result.skipped + result.failed }) : '' }}
    </p>
    <p
      v-if="error && !confirmed"
      class="mt-2 text-sm text-danger"
      role="alert"
    >
      {{ error }}
    </p>

    <Teleport to="body">
      <div
        v-if="confirmed"
        ref="dialog"
        class="seedance-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="preview-cleanup-title"
        aria-describedby="preview-cleanup-description"
        @click.self="closeConfirmation"
        @keydown="onConfirmationKeydown"
      >
        <div>
          <h2
            id="preview-cleanup-title"
            class="text-lg font-semibold text-white"
          >
            {{ t('previewCleanup.title') }}
          </h2>
          <div
            id="preview-cleanup-description"
            class="mt-3 space-y-2 text-sm text-gray-300"
          >
            <p>{{ estimate }}</p>
            <p>{{ t('previewCleanup.scope') }}</p>
            <p>{{ t('previewCleanup.rebuild') }}</p>
          </div>
          <p
            v-if="error"
            role="alert"
            class="mt-3 text-sm text-danger"
          >
            {{ error }}
          </p>
          <div class="mt-5 flex justify-end gap-2">
            <Button
              type="button"
              variant="secondary"
              :disabled="cleaning"
              @click="closeConfirmation"
            >
              {{ t('common.cancel') }}
            </Button>
            <Button
              type="button"
              variant="danger"
              :loading="cleaning"
              :disabled="disabled || cleaning"
              data-test="preview-cleanup-confirm"
              @click="clean"
            >
              {{ t('previewCleanup.confirm') }}
            </Button>
          </div>
        </div>
      </div>
    </Teleport>
  </SeedancePanel>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { onBeforeRouteLeave } from 'vue-router';
import { api } from '@/api';
import Button from '@/components/common/Button.vue';
import SeedancePanel from '@/components/seedance/SeedancePanel.vue';
import { trapModalTab } from '@/modal-focus';
import { formatBytes } from '@/seedance-ui';
import type { PreviewCleanupSummary } from '@/types';

const props = defineProps<{ disabled?: boolean }>();
const { t } = useI18n();
const ageOptions = [3, 7, 30];
const ageDays = ref(30);
const plan = ref<(PreviewCleanupSummary & { createdThrough: string }) | null>(null);
const result = ref<PreviewCleanupSummary | null>(null);
const scanning = ref(false);
const cleaning = ref(false);
const error = ref('');
const dialog = ref<HTMLElement | null>(null);
const cleanButton = ref<InstanceType<typeof Button> | null>(null);
const confirmed = ref<{ createdThrough: string; ids: string[] } | null>(null);
let scanVersion = 0;

const estimate = computed(() => {
  if (!plan.value) return '';
  if (!plan.value.project_ids.length) return t('previewCleanup.none');
  return t('previewCleanup.estimate', {
    projects: plan.value.project_ids.length,
    frames: plan.value.frame_count,
    size: formatBytes(plan.value.bytes),
  });
});

async function scan() {
  const version = ++scanVersion;
  plan.value = null;
  error.value = '';
  scanning.value = true;
  try {
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - ageDays.value);
    const month = String(cutoff.getMonth() + 1).padStart(2, '0');
    const day = String(cutoff.getDate()).padStart(2, '0');
    const createdThrough = `${cutoff.getFullYear()}-${month}-${day}`;
    const next = await api.project.getPreviewCleanupPlan('', createdThrough);
    if (version === scanVersion) plan.value = { ...next, createdThrough };
  } catch {
    if (version === scanVersion) error.value = t('previewCleanup.scanFailed');
  } finally {
    if (version === scanVersion) scanning.value = false;
  }
}

async function openConfirmation() {
  if (!plan.value?.project_ids.length || props.disabled || scanning.value || cleaning.value) return;
  error.value = '';
  confirmed.value = { createdThrough: plan.value.createdThrough, ids: [...plan.value.project_ids] };
  await nextTick();
  dialog.value?.querySelector<HTMLElement>('button')?.focus();
}

function closeConfirmation() {
  if (cleaning.value) return;
  confirmed.value = null;
  cleanButton.value?.$el.focus();
}

function onConfirmationKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault();
    closeConfirmation();
  } else if (dialog.value) trapModalTab(event, dialog.value);
}

async function clean() {
  if (!confirmed.value || props.disabled || cleaning.value) return;
  const selection = confirmed.value;
  error.value = '';
  cleaning.value = true;
  try {
    result.value = await api.project.cleanPreviewFrames('', selection.createdThrough, selection.ids);
  } catch (caught) {
    const message = caught instanceof Error ? caught.message : '';
    error.value = t(message.includes('PREVIEW_CLEANUP_BUSY') ? 'previewCleanup.busy' : 'previewCleanup.cleanFailed');
    return;
  } finally {
    cleaning.value = false;
  }
  closeConfirmation();
  await scan();
}

onMounted(scan);
watch(ageDays, () => {
  result.value = null;
  void scan();
});
onBeforeRouteLeave(() => !cleaning.value);
</script>
