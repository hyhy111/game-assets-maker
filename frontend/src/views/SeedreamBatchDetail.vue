<template>
  <SeedreamShell>
    <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-xl font-semibold text-white">{{ t('aiCreation.imageDetailTitle') }}</h1>
      <button
        type="button"
        class="ml-auto flex w-fit items-center gap-2 rounded-lg px-1 py-2 text-base text-gray-400 transition-colors hover:text-white focus:outline-none focus:ring-2 focus:ring-primary/60"
        data-test="seedream-detail-back"
        @click="backToTasks"
      >
        <ArrowLeft :size="22" aria-hidden="true" />
        {{ t('aiCreation.backToWorkspace') }}
      </button>
    </div>

    <div v-if="loadError" class="mb-4 rounded-xl border border-danger/30 bg-danger/10 p-4 text-danger">
      {{ loadError }}
    </div>

    <template v-if="batch">
      <section
        class="rounded-xl border border-dark-border bg-[#252525] p-4 sm:p-5"
        data-test="seedream-detail-stage"
      >
        <div class="mb-4 flex flex-wrap items-center justify-start gap-2">
          <Button
            v-if="selectedSucceededAttempt"
            variant="primary"
            data-test="seedream-create-video"
            @click="createVideo(selectedSucceededAttempt.index)"
          >
            {{ t('seedream.detail.createVideo') }}
          </Button>
          <Button
            v-if="canRegenerate"
            variant="primary"
            data-test="seedream-regenerate"
            @click="regenerate"
          >
            {{ t('seedream.detail.regenerate') }}
          </Button>
          <Button
            v-if="selectedSucceededAttempt"
            variant="primary"
            data-test="seedream-download"
            @click="download(selectedSucceededAttempt.index)"
          >
            <Download :size="16" aria-hidden="true" />
            {{ t('seedream.detail.download') }}
          </Button>
          <Button
            v-if="retryingDownloads || retryableAttempts.length > 1"
            variant="secondary"
            :loading="retryingDownloads"
            data-test="seedream-retry-all-downloads"
            @click="retryAllDownloads"
          >
            {{ t('seedream.detail.retryAllDownloads') }}
          </Button>
          <Button
            variant="danger"
            class="ml-auto"
            :disabled="!canDelete || retryingDownloads"
            data-test="seedream-delete"
            @click="openDeleteConfirmation"
          >
            {{ t('seedream.detail.delete') }}
          </Button>
        </div>

        <div
          v-if="selectedSucceededAttempt"
          class="mb-4"
          :data-test="`seedream-attempt-${selectedSucceededAttempt.index}`"
        >
          <div class="relative mx-auto w-fit">
            <img
              :src="attemptImageUrl(selectedSucceededAttempt)"
              :alt="t('seedream.detail.candidateImage')"
              class="block max-h-[60vh] max-w-full rounded-lg"
              :data-test="`seedream-image-${selectedSucceededAttempt.index}`"
            />
            <RecentMediaFavoriteButton
              class="absolute right-3 top-3 z-[2]"
              :favorite="isFavorite(imageMediaKey(batch.local_id, selectedSucceededAttempt.local_id))"
              :data-test="`seedream-detail-favorite-${selectedSucceededAttempt.local_id}`"
              @toggle="toggleFavorite(imageMediaKey(batch.local_id, selectedSucceededAttempt.local_id))"
            />
          </div>
          <div
            v-if="selectedSucceededAttempt.image_width && selectedSucceededAttempt.image_height"
            class="mt-2 flex flex-wrap items-center justify-center gap-4 text-sm"
            :data-test="`seedream-dimensions-${selectedSucceededAttempt.index}`"
          >
            <span class="text-gray-400">{{ t('seedream.detail.dimensions') }}:</span>
            <span class="ml-1 text-gray-100">{{ selectedSucceededAttempt.image_width }} × {{ selectedSucceededAttempt.image_height }}</span>
          </div>
          <div
            v-if="succeededAttempts.length > 1"
            class="mt-3 flex justify-center gap-2 overflow-x-auto pb-1"
            data-test="seedream-image-thumbnails"
          >
            <button
              v-for="attempt in succeededAttempts"
              :key="attempt.local_id"
              type="button"
              class="shrink-0 overflow-hidden rounded-md border-2 transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
              :class="attempt.index === selectedSucceededAttempt.index ? 'border-primary' : 'border-transparent hover:border-gray-500'"
              :aria-label="`${t('seedream.detail.candidateImage')} ${attempt.index + 1}`"
              :aria-pressed="attempt.index === selectedSucceededAttempt.index"
              :data-test="`seedream-thumbnail-${attempt.index}`"
              @click="selectSucceededAttempt(attempt.index)"
            >
              <img :src="attemptImageUrl(attempt)" alt="" class="h-16 w-16 object-cover" />
            </button>
          </div>
          <div class="mt-3 flex justify-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              :data-test="`seedream-edit-image-${selectedSucceededAttempt.index}`"
              @click="openImageEditor(selectedSucceededAttempt.index)"
            >
              {{ t('seedream.detail.imageEditor') }}
            </Button>
          </div>
          <p v-if="editorFeedback[selectedSucceededAttempt.index]" class="mt-2 text-center text-sm text-success">
            {{ editorFeedback[selectedSucceededAttempt.index] }}
          </p>
        </div>

        <div class="space-y-4">
          <div
            v-for="attempt in nonSucceededAttempts"
            :key="attempt.local_id"
            :data-test="`seedream-attempt-${attempt.index}`"
          >
            <!-- Loading placeholder -->
            <div
              v-if="isAttemptActive(attempt)"
              class="flex flex-col items-center justify-center rounded-xl border border-dark-border bg-dark-surface p-8"
              :data-test="`seedream-loading-${attempt.index}`"
            >
              <div class="h-8 w-8 animate-spin rounded-full border-b-2 border-primary" />
              <p class="mt-3 text-sm text-gray-400">{{ attemptLoadingMessage(attempt) }}</p>
            </div>

            <!-- Unknown (generation result unknown, may have been billed) -->
            <div
              v-else-if="attempt.status === 'unknown'"
              class="rounded-xl border border-warning/30 bg-warning/10 p-4"
              :data-test="`seedream-unknown-${attempt.index}`"
            >
              <p class="text-warning font-medium text-sm">{{ t('seedream.batch.unknown') }}</p>
              <p v-if="attempt.error" class="mt-1 text-sm text-gray-400">{{ attempt.error.message }}</p>
              <p class="mt-1 text-xs text-gray-500" data-test="seedream-unknown-hint">{{ t('seedream.detail.unknownHint') }}</p>
            </div>

            <!-- Failed (server error, including 429) -->
            <div
              v-else-if="attempt.status === 'failed'"
              class="rounded-xl border border-danger/30 bg-danger/10 p-4"
              :data-test="`seedream-failed-${attempt.index}`"
            >
              <p class="text-danger font-medium text-sm">{{ t('seedream.detail.failed') }}</p>
              <p v-if="attempt.error" class="mt-1 text-sm text-gray-400">{{ attempt.error.message }}</p>
              <p v-if="isRateLimited(attempt)" class="mt-1 text-xs text-gray-500" data-test="seedream-rate-limit-hint">{{ t('seedream.detail.rateLimitHint') }}</p>
            </div>

            <!-- Download failed (response persisted, can retry download) -->
            <div
              v-else-if="attempt.status === 'download_failed'"
              class="rounded-xl border border-warning/30 bg-warning/10 p-4"
              :data-test="`seedream-download-failed-${attempt.index}`"
            >
              <p class="text-warning font-medium text-sm">{{ t('seedream.detail.downloadFailed') }}</p>
              <p v-if="attempt.error" class="mt-1 text-sm text-gray-400">{{ attempt.error.message }}</p>
              <div v-if="attempt.url_expired" class="mt-2" data-test="seedream-url-expired">
                <p class="text-xs text-gray-500">{{ t('seedream.detail.urlExpired') }}</p>
              </div>
              <div v-else-if="retryableAttempts.length === 1 && !retryingDownloads" class="mt-2">
                <Button variant="secondary" size="sm" :data-test="`seedream-retry-download-${attempt.index}`" @click="retryDownload(attempt.index)">
                  {{ t('seedream.detail.retryDownload') }}
                </Button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <SeedreamPanel class="mt-5" :title="t('seedream.detail.configuration')">
        <div class="mb-3">
          <span
            class="inline-flex items-center rounded-full px-3 py-1 text-xs font-medium"
            :class="statusBadgeClass"
            data-test="seedream-batch-status"
          >
            {{ statusLabel }}
          </span>
        </div>
        <dl class="grid gap-2 text-sm sm:grid-cols-2">
          <div><dt class="inline text-gray-400">{{ t('seedream.create.model') }}:</dt> <dd class="inline text-gray-100">{{ modelLabel }}</dd></div>
          <div><dt class="inline text-gray-400">{{ t('seedream.create.resolution') }}:</dt> <dd class="inline text-gray-100">{{ batch.request.resolution }}</dd></div>
          <div><dt class="inline text-gray-400">{{ t('seedream.create.ratio') }}:</dt> <dd class="inline text-gray-100">{{ batch.request.ratio }}</dd></div>
          <div><dt class="inline text-gray-400">{{ t('seedream.create.count') }}:</dt> <dd class="inline text-gray-100">{{ batch.attempts.length }}</dd></div>
        </dl>
        <div
          v-if="batch.reference_image_url"
          class="mt-3 flex items-center gap-3"
        >
          <img
            :src="batch.reference_image_url"
            :alt="t('seedream.create.referenceImage')"
            class="h-20 w-20 rounded-lg border border-dark-border bg-black/30 object-cover"
            data-test="seedream-reference-thumbnail"
          >
          <p class="text-xs text-gray-400">{{ t('seedream.create.referenceImage') }}</p>
        </div>
        <div class="mt-3">
          <div class="flex items-center gap-2">
            <p class="text-xs text-gray-400">{{ t('seedream.detail.prompt') }}</p>
            <button
              type="button"
              class="rounded p-1 text-gray-400 transition-colors hover:bg-dark-border hover:text-white"
              :title="copyTitle"
              data-test="seedream-copy-prompt"
              @click="copyPrompt"
            >
              <Check
                v-if="copied"
                :size="14"
                aria-hidden="true"
              />
              <Copy
                v-else
                :size="14"
                aria-hidden="true"
              />
            </button>
          </div>
          <p class="mt-1 rounded-lg border border-dark-border p-3 text-sm text-gray-100">{{ batch.request.prompt }}</p>
        </div>
        <div v-if="selectedSucceededAttempt" class="mt-3 flex flex-wrap items-center justify-end gap-4 text-sm">
          <div>
            <span class="text-gray-400">{{ t('seedream.detail.totalTokens') }}:</span>
            <span class="ml-1 text-gray-100" data-test="seedream-total-tokens-summary">{{ tokensLabel(selectedSucceededAttempt) }}</span>
          </div>
          <div v-if="selectedSucceededAttempt.elapsed_seconds">
            <span class="text-gray-400">{{ t('seedream.detail.elapsed') }}:</span>
            <span class="ml-1 text-gray-100">{{ formatElapsed(selectedSucceededAttempt.elapsed_seconds) }}</span>
          </div>
        </div>
      </SeedreamPanel>
    </template>

    <SeedreamImageEraser
      v-if="currentImageEditorAttempt"
      :key="attemptImageUrl(currentImageEditorAttempt)"
      :image-url="attemptImageUrl(currentImageEditorAttempt)"
      :edit-source-url="attemptEditSourceUrl(currentImageEditorAttempt)"
      :title="t('seedream.detail.imageEditor')"
      :saving="imageEditorSaving"
      :error="imageEditorError"
      :generation-layout="currentImageEditorAttempt.generation_layout"
      :external-restore-available="currentImageEditorAttempt.has_original_backup || !!restorableAttempts[currentImageEditorAttempt.index]"
      resize-enabled
      @cancel="closeImageEditor"
      @restore="restoreOriginalFromEditor"
      @apply="applyImageEditor"
    />

    <div
      v-if="showDeleteConfirm"
      ref="deleteModalRoot"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="seedream-delete-title"
      aria-describedby="seedream-delete-description"
      @keydown="onDeleteKeydown"
      @click.self="closeDeleteConfirmation"
    >
      <div class="max-w-md rounded-xl border border-dark-border bg-dark-surface p-6">
        <h2 id="seedream-delete-title" class="text-lg font-semibold text-white">
          {{ t('seedream.detail.delete') }}
        </h2>
        <p id="seedream-delete-description" class="mt-3 text-gray-300" data-test="seedream-delete-confirmation">
          {{ t('seedream.detail.deleteConfirmation') }}
        </p>
        <p v-if="deleteError" class="mt-2 text-sm text-danger" data-test="seedream-delete-error">{{ deleteError }}</p>
        <div class="mt-5 flex justify-end gap-3">
          <Button variant="secondary" :disabled="deleting" @click="closeDeleteConfirmation">
            {{ t('common.cancel') }}
          </Button>
          <Button variant="danger" :loading="deleting" :disabled="deleting" data-test="seedream-delete-confirm" @click="confirmDelete">
            {{ t('seedream.detail.delete') }}
          </Button>
        </div>
      </div>
    </div>
  </SeedreamShell>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { ArrowLeft, Check, Copy, Download } from 'lucide-vue-next';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';
import Button from '@/components/common/Button.vue';
import RecentMediaFavoriteButton from '@/components/ai-creation/RecentMediaFavoriteButton.vue';
import SeedreamImageEraser from '@/components/seedream/SeedreamImageEraser.vue';
import SeedreamPanel from '@/components/seedream/SeedreamPanel.vue';
import SeedreamShell from '@/components/seedream/SeedreamShell.vue';
import { trapModalTab } from '@/modal-focus';
import { useRecentMediaFavorites } from '@/recent-media-favorites';
import { batchStatus, formatElapsed, isBatchDeletable, MODEL_LABELS } from '@/seedream-ui';
import { useSeedreamStore } from '@/stores/seedream';
import type { GenerationLayout, SeedreamAttempt, SeedreamBatch, SeedreamBatchStatus } from '@/types';

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const store = useSeedreamStore();
const { imageMediaKey, isFavorite, toggleFavorite } = useRecentMediaFavorites();

const loadError = ref('');
const showDeleteConfirm = ref(false);
const deleting = ref(false);
const deleteError = ref('');
const deleteModalRoot = ref<HTMLElement | null>(null);
let deleteTrigger: HTMLElement | null = null;
const copied = ref(false);
const retryingDownloads = ref(false);
const imageRevisions = ref<Record<number, number>>({});
const editorFeedback = ref<Record<number, string>>({});
const restorableAttempts = ref<Record<number, boolean>>({});
const imageEditorAttemptIndex = ref<number | null>(null);
const imageEditorSaving = ref(false);
const imageEditorError = ref('');
const copyTitle = computed(() => copied.value ? t('common.copied') : t('common.copy'));
const currentImageEditorAttempt = computed(() => (
  imageEditorAttemptIndex.value === null
    ? null
    : batch.value?.attempts.find((attempt) => attempt.index === imageEditorAttemptIndex.value) ?? null
));

const batchId = computed(() => {
  const id = route.params.batchId;
  return typeof id === 'string' ? id : '';
});

const batch = computed<SeedreamBatch | null>(() => {
  if (store.currentBatch?.local_id === batchId.value) return store.currentBatch;
  return store.batches.find((b) => b.local_id === batchId.value) ?? null;
});

const status = computed<SeedreamBatchStatus>(() => batch.value ? batchStatus(batch.value) : 'generating');

const statusLabel = computed(() => {
  switch (status.value) {
    case 'generating': return t('seedream.batch.generating');
    case 'completed': return t('seedream.batch.completed');
    case 'partially_complete': return t('seedream.batch.partially_complete');
    case 'failed': return t('seedream.batch.failed');
    case 'unknown': return t('seedream.batch.unknown');
    default: return '';
  }
});

const statusBadgeClass = computed(() => {
  switch (status.value) {
    case 'completed': return 'bg-success/20 text-success';
    case 'generating': return 'bg-primary/20 text-primary';
    case 'partially_complete': return 'bg-warning/20 text-warning';
    case 'failed': return 'bg-danger/20 text-danger';
    case 'unknown': return 'bg-warning/20 text-warning';
    default: return 'bg-gray-500/20 text-gray-400';
  }
});

const modelLabel = computed(() => {
  const model = batch.value?.request.model;
  return model ? (MODEL_LABELS[model] ?? model) : '';
});

const isTerminal = computed(() => batch.value ? !['generating'].includes(batchStatus(batch.value)) : false);
const canRegenerate = computed(() => isTerminal.value);
const canDelete = computed(() => batch.value ? isBatchDeletable(batch.value) : false);
const selectedAttemptIndex = ref<number | null>(null);
const succeededAttempts = computed(() => batch.value?.attempts.filter((attempt) => (
  attempt.status === 'succeeded' && attemptImageUrl(attempt)
)) ?? []);
const selectedSucceededAttempt = computed(() => (
  succeededAttempts.value.find((attempt) => attempt.index === selectedAttemptIndex.value)
  ?? succeededAttempts.value[0]
  ?? null
));
const nonSucceededAttempts = computed(() => batch.value?.attempts.filter((attempt) => (
  attempt.status !== 'succeeded' || !attemptImageUrl(attempt)
)) ?? []);
const retryableAttempts = computed(() => batch.value?.attempts.filter((attempt) => (
  attempt.status === 'download_failed' && !attempt.url_expired
)) ?? []);

function isAttemptActive(attempt: SeedreamAttempt): boolean {
  return attempt.status === 'queued' || attempt.status === 'generating' || attempt.status === 'downloading';
}

function isRateLimited(attempt: SeedreamAttempt): boolean {
  return attempt.status === 'failed' && attempt.error?.status === 429;
}

function attemptImageUrl(attempt: SeedreamAttempt): string {
  if (!attempt.image_url) return '';
  const url = attempt.image_url;
  const revision = imageRevisions.value[attempt.index];
  return revision ? `${url}${url.includes('?') ? '&' : '?'}revision=${revision}` : url;
}

function attemptEditSourceUrl(attempt: SeedreamAttempt): string {
  if (!attempt.image_url) return '';
  const url = attempt.image_url.replace('/image/', '/edit-source/');
  const revision = imageRevisions.value[attempt.index];
  return revision ? `${url}${url.includes('?') ? '&' : '?'}revision=${revision}` : url;
}

function selectSucceededAttempt(attemptIndex: number) {
  selectedAttemptIndex.value = attemptIndex;
}

function openImageEditor(attemptIndex: number) {
  imageEditorError.value = '';
  imageEditorAttemptIndex.value = attemptIndex;
}

function closeImageEditor() {
  if (imageEditorSaving.value) return;
  imageEditorAttemptIndex.value = null;
  imageEditorError.value = '';
}

async function applyImageEditor(
  imageDataUrl: string,
  editSourceDataUrl: string,
  generationLayout: GenerationLayout | null
) {
  const attemptIndex = imageEditorAttemptIndex.value;
  if (!batchId.value || attemptIndex === null || imageEditorSaving.value) return;
  imageEditorSaving.value = true;
  imageEditorError.value = '';
  const result = await store.applyEraser(
    batchId.value, attemptIndex, imageDataUrl, editSourceDataUrl, generationLayout
  );
  imageEditorSaving.value = false;
  if (!result) {
    imageEditorError.value = store.error?.message ?? t('seedream.detail.eraserSaveFailed');
    return;
  }
  if (currentImageEditorAttempt.value) {
    currentImageEditorAttempt.value.generation_layout = result.generation_layout;
  }
  imageRevisions.value[attemptIndex] = Date.now();
  restorableAttempts.value[attemptIndex] = true;
  editorFeedback.value[attemptIndex] = t('seedream.detail.imageEditorSaved');
  imageEditorAttemptIndex.value = null;
}

async function restoreOriginalFromEditor() {
  const attemptIndex = imageEditorAttemptIndex.value;
  if (!batchId.value || attemptIndex === null || imageEditorSaving.value) return;
  imageEditorSaving.value = true;
  imageEditorError.value = '';
  const success = await store.restoreCharacter(batchId.value, attemptIndex);
  imageEditorSaving.value = false;
  if (!success) {
    imageEditorError.value = store.error?.message ?? t('seedream.detail.restoreFailed');
    return;
  }
  const attempt = currentImageEditorAttempt.value;
  if (attempt) attempt.generation_layout = null;
  imageRevisions.value[attemptIndex] = Date.now();
  editorFeedback.value[attemptIndex] = t('seedream.detail.restoreSucceeded');
}

function attemptLoadingMessage(attempt: SeedreamAttempt): string {
  switch (attempt.status) {
    case 'queued': return t('seedream.detail.queued');
    case 'generating': return t('seedream.detail.generating');
    case 'downloading': return t('seedream.detail.downloading');
    default: return t('seedream.detail.waiting');
  }
}

function tokensLabel(attempt: SeedreamAttempt): string {
  const tokens = attempt.total_tokens;
  return typeof tokens === 'number'
    ? tokens.toLocaleString('en-US')
    : t('seedream.detail.tokensUnavailable');
}

async function download(attemptIndex: number) {
  if (!batchId.value) return;
  await store.saveImage(batchId.value, attemptIndex);
}

async function retryDownload(attemptIndex: number) {
  if (!batchId.value) return;
  await store.retryDownload(batchId.value, attemptIndex);
}

async function retryAllDownloads() {
  if (!batchId.value || retryingDownloads.value || retryableAttempts.value.length < 2) return;
  const localId = batchId.value;
  const indices = retryableAttempts.value.map((attempt) => attempt.index);
  retryingDownloads.value = true;
  try {
    for (const index of indices) {
      await store.retryDownload(localId, index);
    }
    await store.loadBatch(localId);
  } finally {
    retryingDownloads.value = false;
  }
}

function createVideo(attemptIndex: number) {
  if (!batchId.value) return;
  router.push({
    path: '/video-generation/create',
    query: { handoff: batchId.value, attempt: String(attemptIndex) },
  });
}

function regenerate() {
  if (!batchId.value) return;
  router.push({
    path: '/image-generation/create',
    query: { regenerate: batchId.value },
  });
}

function backToTasks() {
  router.push('/ai-creation');
}

async function copyPrompt() {
  const text = batch.value?.request.prompt.trim();
  if (!text || copied.value) return;
  try {
    await navigator.clipboard.writeText(text);
    copied.value = true;
    setTimeout(() => {
      copied.value = false;
    }, 1500);
  } catch {
    // Ignore clipboard errors in restricted environments.
  }
}

function openDeleteConfirmation() {
  if (!canDelete.value) return;
  deleteError.value = '';
  deleteTrigger = document.activeElement as HTMLElement;
  showDeleteConfirm.value = true;
  nextTick(() => {
    deleteModalRoot.value?.querySelector<HTMLElement>('button:not([disabled])')?.focus();
  });
}

function closeDeleteConfirmation() {
  if (deleting.value) return;
  showDeleteConfirm.value = false;
  deleteTrigger?.focus();
  deleteTrigger = null;
}

function onDeleteKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    closeDeleteConfirmation();
    return;
  }
  if (deleteModalRoot.value) trapModalTab(event, deleteModalRoot.value);
}

async function confirmDelete() {
  if (!batchId.value || deleting.value) return;
  deleting.value = true;
  deleteError.value = '';
  try {
    const success = await store.deleteBatch(batchId.value);
    if (success) {
      showDeleteConfirm.value = false;
      await router.push('/ai-creation');
    } else {
      deleteError.value = store.error?.message ?? t('seedream.detail.deleteFailed');
    }
  } finally {
    deleting.value = false;
  }
}

onBeforeUnmount(() => {
  showDeleteConfirm.value = false;
  imageEditorAttemptIndex.value = null;
});

async function loadBatch() {
  loadError.value = '';
  if (!batchId.value) return;
  const result = await store.loadBatch(batchId.value);
  if (!result) {
    loadError.value = store.error?.message ?? t('seedream.detail.loadFailed');
  }
}

onMounted(() => {
  loadBatch();
});

watch(batchId, () => {
  loadBatch();
});
</script>
