<template>
  <SeedreamShell>
    <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
      <h1 class="flex flex-wrap items-center gap-3 text-xl font-semibold text-white">
        {{ t(item?.kind === 'video' ? 'aiCreation.sourceMedia.videoDetail' : 'aiCreation.sourceMedia.imageDetail') }}
        <span
          v-if="item"
          class="media-overlay-badge"
        >{{ t('aiCreation.sourceMedia.local') }}</span>
      </h1>
      <RouterLink
        to="/ai-creation"
        class="icon-button rounded-lg text-gray-400 transition hover:bg-white/5 hover:text-white focus-visible:outline focus-visible:outline-primary"
        :aria-label="t('aiCreation.backToWorkspace')"
      >
        <ArrowLeft
          class="h-5 w-5"
          aria-hidden="true"
        />
      </RouterLink>
    </div>

    <p
      v-if="loading"
      class="rounded-xl border border-dark-border p-4 text-gray-400"
      role="status"
    >
      {{ t('common.loading') }}
    </p>
    <p
      v-else-if="!item"
      class="rounded-xl border border-dark-border p-4 text-gray-400"
      role="alert"
    >
      {{ t('aiCreation.sourceMedia.unavailable') }}
    </p>
    <div
      v-else
      :class="{ 'grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(320px,400px)]': item.kind === 'video' }"
    >
      <section
        class="rounded-xl border border-dark-border bg-[#252525] p-4 sm:p-5"
        data-test="source-media-detail-stage"
      >
        <div class="mb-4 flex flex-wrap items-center gap-2">
          <template v-if="item.kind === 'image'">
            <Button
              :disabled="workspace.candidateHandoffPending"
              @click="useImage('first_frame')"
            >
              {{ t('seedream.detail.createVideo') }}
            </Button>
            <Button
              :disabled="workspace.candidateHandoffPending"
              @click="useImage('reference')"
            >
              {{ t('seedream.detail.useAsReference') }}
            </Button>
          </template>
          <div class="ml-auto flex items-center gap-2">
            <button
              type="button"
              class="rounded-lg p-2 text-gray-400 transition hover:bg-white/5 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              :title="t('aiCreation.openDirectory')"
              :aria-label="t('aiCreation.openDirectory')"
              @click="openDirectory"
            >
              <FolderOpen
                :size="20"
                aria-hidden="true"
              />
            </button>
            <button
              ref="deleteButton"
              type="button"
              class="rounded-lg p-2 text-gray-400 transition hover:bg-danger/15 hover:text-danger focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger"
              :title="t('aiCreation.sourceMedia.delete')"
              :aria-label="t('aiCreation.sourceMedia.delete')"
              :disabled="creatingProject || workspace.candidateHandoffPending"
              @click="openDeleteConfirmation"
            >
              <Trash2
                :size="20"
                aria-hidden="true"
              />
            </button>
          </div>
        </div>

        <p
          v-if="error"
          class="mb-3 text-sm text-danger"
          role="alert"
        >
          {{ error }}
        </p>
        <div
          class="relative"
          :class="{ 'mx-auto w-fit rounded-lg bg-black': item.kind === 'image' }"
          :draggable="item.kind === 'image'"
          @dragstart="dragImage"
        >
          <img
            v-if="item.kind === 'image'"
            :src="item.url"
            :alt="item.name"
            class="block max-h-[60vh] max-w-full rounded-lg"
            draggable="false"
            @error="previewFailed"
          >
          <video
            v-else
            :src="item.url"
            :poster="item.thumbnail_url"
            class="block aspect-video max-h-[48vh] w-full rounded-lg bg-black object-contain"
            controls
            playsinline
            preload="metadata"
            @error="previewFailed"
          />
          <RecentMediaFavoriteButton
            class="absolute right-2 top-2 z-[2]"
            :favorite="isFavorite(sourceMediaKey(item.id))"
            :data-test="`source-media-favorite-${item.id}`"
            @toggle="toggleFavorite(sourceMediaKey(item.id))"
          />
        </div>
        <div
          v-if="item.kind === 'image'"
          class="mt-3 flex justify-center"
        >
          <Button
            variant="secondary"
            size="sm"
            icon-only
            :tooltip="t('buttonHints.editImage')"
            data-test="source-media-edit"
            @click="openEditor"
          >
            <Pencil
              class="h-5 w-5"
              aria-hidden="true"
            />
          </Button>
        </div>
        <dl class="mt-4 flex flex-wrap justify-center gap-x-6 gap-y-2 text-sm">
          <div class="flex items-baseline gap-2">
            <dt class="text-gray-400">
              {{ t('aiCreation.sourceMedia.name') }}
            </dt>
            <dd class="break-all text-gray-100">
              {{ item.name }}
            </dd>
          </div>
          <div class="flex items-baseline gap-2">
            <dt class="text-gray-400">
              {{ t('seedream.detail.dimensions') }}
            </dt>
            <dd class="text-gray-100">
              {{ item.width }} × {{ item.height }}
            </dd>
          </div>
          <div
            v-if="item.duration !== null"
            class="flex items-baseline gap-2"
          >
            <dt class="text-gray-400">
              {{ t('aiCreation.sourceMedia.duration') }}
            </dt>
            <dd class="text-gray-100">
              {{ n(item.duration, { maximumFractionDigits: 2 }) }} s
            </dd>
          </div>
          <div class="flex items-baseline gap-2">
            <dt class="text-gray-400">
              {{ t('aiCreation.sourceMedia.fileSize') }}
            </dt>
            <dd class="text-gray-100">
              {{ n(item.size_bytes / 1024, { maximumFractionDigits: 1 }) }} KiB
            </dd>
          </div>
          <div class="flex items-baseline gap-2">
            <dt class="text-gray-400">
              {{ t('aiCreation.sourceMedia.importedAt') }}
            </dt>
            <dd class="text-gray-100">
              {{ d(new Date(item.imported_at), dateFormat) }}
            </dd>
          </div>
        </dl>
      </section>

      <aside
        v-if="item.kind === 'video'"
        class="source-media-handoff"
      >
        <SeedanceHandoffPanel
          :disabled="creatingProject || deleteOpen"
          :creating="creatingProject"
          :roles="projectStore.roles"
          @handoff="createAnimation"
        />
        <p
          v-if="projectError"
          class="mt-3 text-sm text-danger"
          role="alert"
        >
          {{ projectError }}
        </p>
      </aside>

      <SeedreamImageEraser
        v-if="editing && item.kind === 'image'"
        :key="item.url"
        :image-url="item.url"
        :edit-source-url="item.edit_source_url"
        :title="t('seedream.detail.imageEditor')"
        :saving="saving"
        :error="editorError"
        :generation-layout="item.generation_layout"
        :external-restore-available="!!item.edit_revision"
        resize-enabled
        @cancel="editing = false"
        @restore="restoreImage"
        @apply="applyImage"
      />

      <div
        v-if="deleteOpen"
        ref="deleteDialog"
        class="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="source-media-delete-title"
        aria-describedby="source-media-delete-hint"
        @keydown.esc.prevent="closeDeleteConfirmation"
        @keydown="trapModalTab($event, $event.currentTarget as HTMLElement)"
        @click.self="closeDeleteConfirmation"
      >
        <section class="w-full max-w-md rounded-xl border border-dark-border bg-dark-surface p-6">
          <h2
            id="source-media-delete-title"
            class="text-lg font-semibold text-white"
          >
            {{ t('aiCreation.sourceMedia.delete') }}
          </h2>
          <p
            id="source-media-delete-hint"
            class="mt-3 text-sm text-gray-400"
          >
            {{ t('aiCreation.sourceMedia.deleteConfirm', { name: item.name }) }}
          </p>
          <p
            v-if="deleteError"
            class="mt-3 text-sm text-danger"
            role="alert"
          >
            {{ deleteError }}
          </p>
          <div class="mt-5 flex justify-end gap-2">
            <Button
              variant="secondary"
              :disabled="deleting"
              @click="closeDeleteConfirmation"
            >
              {{ t('common.cancel') }}
            </Button>
            <Button
              variant="danger"
              :loading="deleting"
              @click="deleteMedia"
            >
              {{ t('aiCreation.sourceMedia.delete') }}
            </Button>
          </div>
        </section>
      </div>
    </div>
  </SeedreamShell>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { ArrowLeft, FolderOpen, Pencil, Trash2 } from 'lucide-vue-next';
import { api } from '@/api';
import Button from '@/components/common/Button.vue';
import RecentMediaFavoriteButton from '@/components/ai-creation/RecentMediaFavoriteButton.vue';
import SeedanceHandoffPanel from '@/components/seedance/SeedanceHandoffPanel.vue';
import SeedreamImageEraser from '@/components/seedream/SeedreamImageEraser.vue';
import SeedreamShell from '@/components/seedream/SeedreamShell.vue';
import { trapModalTab } from '@/modal-focus';
import { useRecentMediaFavorites } from '@/recent-media-favorites';
import { writeSourceImageDrag } from '@/seedream-image-drag';
import { useAICreationStore } from '@/stores/aiCreation';
import { useProjectStore } from '@/stores/project';
import type { GenerationLayout, SourceMedia } from '@/types';

const route = useRoute();
const router = useRouter();
const { t, d, n } = useI18n();
const workspace = useAICreationStore();
const projectStore = useProjectStore();
const { sourceMediaKey, isFavorite, toggleFavorite } = useRecentMediaFavorites();
const dateFormat = { dateStyle: 'medium', timeStyle: 'short' } as const;
const item = ref<SourceMedia | null>(null);
const loading = ref(true);
const error = ref('');
const editing = ref(false);
const saving = ref(false);
const editorError = ref('');
const creatingProject = ref(false);
const projectError = ref('');
const deleteOpen = ref(false);
const deleting = ref(false);
const deleteError = ref('');
const deleteButton = ref<HTMLElement | null>(null);
const deleteDialog = ref<HTMLElement | null>(null);

watch(() => String(route.params.id ?? ''), async (id, _previousId, onCleanup) => {
  let active = true;
  onCleanup(() => { active = false; });
  item.value = null;
  loading.value = true;
  error.value = '';
  projectError.value = '';
  editing.value = false;
  deleteOpen.value = false;
  try {
    const result = await api.sourceMedia.get(id);
    if (active) {
      item.value = result;
      if (result?.kind === 'video') void projectStore.loadProjects();
    }
  } catch {
    if (active) item.value = null;
  } finally {
    if (active) loading.value = false;
  }
}, { immediate: true });

function previewFailed() {
  error.value = t('aiCreation.sourceMedia.previewFailed');
}

async function openDirectory() {
  const id = item.value?.id;
  if (!id) return;
  error.value = '';
  try {
    if (await api.sourceMedia.openDirectory(id)) return;
  } catch {
    // The same message covers missing folders and an unavailable file manager.
  }
  if (item.value?.id === id) error.value = t('aiCreation.sourceMedia.directoryFailed');
}

function dragImage(event: DragEvent) {
  if (item.value?.kind === 'image') {
    writeSourceImageDrag(event.dataTransfer, item.value.id, event.currentTarget as HTMLElement);
  }
}

async function useImage(field: 'first_frame' | 'reference') {
  const id = item.value?.id;
  if (!id) return;
  error.value = '';
  if (await workspace.handoffSourceImage(id, field)) {
    if (item.value?.id === id) await router.push('/ai-creation');
  } else if (item.value?.id === id) {
    error.value = t('aiCreation.imageUnavailable');
  }
}

function openEditor() {
  editorError.value = '';
  editing.value = true;
}

async function persistImage(change: (id: string) => Promise<SourceMedia>, failureKey: string, close: boolean) {
  const id = item.value?.id;
  if (!id || saving.value) return;
  saving.value = true;
  editorError.value = '';
  try {
    const updated = await change(id);
    if (item.value?.id === id) {
      item.value = updated;
      if (close) editing.value = false;
    }
  } catch {
    if (item.value?.id === id) editorError.value = t(failureKey);
  } finally {
    saving.value = false;
  }
}

function applyImage(image: string, source: string, layout: GenerationLayout | null) {
  return persistImage(id => api.sourceMedia.editImage(id, image, source, layout), 'seedream.detail.eraserSaveFailed', true);
}

function restoreImage() {
  return persistImage(api.sourceMedia.restoreImage, 'seedream.detail.restoreFailed', false);
}

async function createAnimation({ role, action }: { role: string; action: string }) {
  const id = item.value?.id;
  if (!id || creatingProject.value) return;
  creatingProject.value = true;
  projectError.value = '';
  try {
    const project = await api.sourceMedia.createProject(id, role, action);
    if (item.value?.id === id) {
      projectStore.setCurrentProject(project);
      await router.push('/editor');
    }
  } catch (caught) {
    if (item.value?.id === id) {
      projectError.value = caught instanceof Error ? caught.message : t('seedance.handoff.failed');
    }
  } finally {
    creatingProject.value = false;
  }
}

async function openDeleteConfirmation() {
  deleteOpen.value = true;
  deleteError.value = '';
  await nextTick();
  deleteDialog.value?.querySelector('button')?.focus();
}

function closeDeleteConfirmation() {
  if (deleting.value) return;
  deleteOpen.value = false;
  deleteButton.value?.focus();
}

async function deleteMedia() {
  const id = item.value?.id;
  if (!id || deleting.value) return;
  deleting.value = true;
  deleteError.value = '';
  try {
    if (!await api.sourceMedia.delete(id)) throw new Error('Could not delete media');
    if (item.value?.id === id) await router.push('/ai-creation');
  } catch {
    if (item.value?.id === id) deleteError.value = t('aiCreation.sourceMedia.deleteFailed');
  } finally {
    deleting.value = false;
  }
}
</script>

<style scoped>
.source-media-handoff {
  --seedance-border: theme('colors.dark.border');
  --seedance-surface: theme('colors.dark.bg');
  --seedance-muted: theme('colors.gray.400');
}
</style>
