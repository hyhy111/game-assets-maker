<template>
  <div class="mb-4 flex items-center justify-end">
    <button
      type="button"
      class="flex items-center gap-1.5 rounded-lg border border-dark-border bg-dark-surface px-3 py-2 text-sm text-gray-400 transition-colors hover:border-gray-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
      :disabled="store.loading"
      data-test="seedance-tasks-refresh"
      @click="load"
    >
      <RefreshCw class="h-4 w-4" />
      {{ t('common.refresh') }}
    </button>
  </div>

  <p v-if="store.error" class="mb-4 rounded-lg border border-danger/30 bg-danger/10 p-3 text-sm text-danger">
    {{ store.error.message }}
  </p>

  <SeedancePanel v-if="store.loading && !tasks.length">
    <div class="flex min-h-56 items-center justify-center text-sm text-[var(--seedance-muted)]" role="status">
      {{ t('common.loading') }}
    </div>
  </SeedancePanel>

  <SeedancePanel v-else-if="!tasks.length">
    <SeedanceEmptyState
      :title="t('seedance.tasks.empty')"
      :description="t('seedance.tasks.emptyDescription')"
      icon="tasks"
    />
  </SeedancePanel>

  <div v-else class="seedance-task-grid grid gap-4 md:grid-cols-2">
    <SeedanceTaskCard
      v-for="task in tasks"
      :key="task.local_id"
      :task="task"
      :sequence="duplicateTaskSequence(task, tasks)"
      @open="open"
      @cancel="store.cancelTask"
      @retry-generation="retryGeneration"
      @retry-download="store.retryDownload"
      @regenerate="regenerate"
      @continue="continueFromReturnedFrame"
      @delete="remove"
    />
  </div>

  <div
    v-if="taskToDelete"
    ref="deleteModalRoot"
    class="seedance-modal"
    role="dialog"
    aria-modal="true"
    aria-labelledby="delete-task-title"
    aria-describedby="delete-task-description"
    @keydown="onDeleteKeydown"
    @click.self="closeDeleteConfirmation"
  >
    <div>
      <h2 id="delete-task-title">{{ t('seedance.tasks.delete') }}</h2>
      <p id="delete-task-description">
        {{ taskToDelete.protected ? t('seedance.ui.protectedDeleteWarning') : t('seedance.tasks.deleteConfirmation') }}
      </p>
      <div class="mt-5 flex justify-end gap-2">
        <Button variant="secondary" @click="closeDeleteConfirmation">{{ t('common.cancel') }}</Button>
        <Button variant="danger" :loading="deleting" :disabled="deleting" @click="deleteTask">
          {{ t('seedance.tasks.delete') }}
        </Button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import { RefreshCw } from 'lucide-vue-next';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
import Button from '@/components/common/Button.vue';
import { trapModalTab } from '@/modal-focus';
import { runConfirmedPaidAction } from '@/paid-action-confirmation';
import { duplicateTaskSequence } from '@/seedance-ui';
import { useSeedanceStore } from '@/stores/seedance';
import type { SeedanceTask } from '@/types';
import SeedanceEmptyState from './SeedanceEmptyState.vue';
import SeedancePanel from './SeedancePanel.vue';
import SeedanceTaskCard from './SeedanceTaskCard.vue';

const { t } = useI18n();
const router = useRouter();
const store = useSeedanceStore();
const tasks = computed(() => store.tasks);
const taskToDelete = ref<SeedanceTask | null>(null);
const deleteModalRoot = ref<HTMLElement | null>(null);
const deleting = ref(false);
let deleteTrigger: HTMLElement | null = null;

onMounted(load);
onBeforeUnmount(closeDeleteConfirmation);

function load() {
  return store.loadTasks();
}

function open(id: string) {
  return router.push(`/video-generation/tasks/${encodeURIComponent(id)}`);
}

function regenerate(id: string) {
  return router.push({ path: '/video-generation/create', query: { regenerate: id } });
}

function continueFromReturnedFrame(id: string) {
  return router.push({ path: '/video-generation/create', query: { continue: id } });
}

async function retryGeneration(id: string) {
  const action = window.confirm(t('seedance.ui.retryBillingWarning')) ? 'retry' : null;
  const result = await runConfirmedPaidAction(action, () => store.retryTask(id));
  if (result) await router.push(`/video-generation/tasks/${result.local_id}`);
}

async function remove(id: string) {
  const task = store.tasks.find((item) => item.local_id === id);
  if (!task) return;
  deleteTrigger = document.activeElement as HTMLElement;
  taskToDelete.value = task;
  await nextTick();
  deleteModalRoot.value?.querySelector<HTMLElement>('button:not([disabled])')?.focus();
}

function closeDeleteConfirmation() {
  taskToDelete.value = null;
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

async function deleteTask() {
  const task = taskToDelete.value;
  if (!task || deleting.value) return;
  deleting.value = true;
  const deleted = await store.deleteTask(task.local_id, task.protected);
  deleting.value = false;
  if (deleted) closeDeleteConfirmation();
}
</script>
