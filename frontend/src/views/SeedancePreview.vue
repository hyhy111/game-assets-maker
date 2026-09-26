<template>
  <SeedanceShell>
    <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-xl font-semibold text-white">{{ t('aiCreation.videoDetailTitle') }}</h1>
      <button
        type="button"
        class="ml-auto flex w-fit items-center gap-2 rounded-lg px-1 py-2 text-base text-gray-400 transition-colors hover:text-white focus:outline-none focus:ring-2 focus:ring-primary/60"
        data-test="seedance-preview-back"
        @click="backToTasks"
      >
        <ArrowLeft :size="22" aria-hidden="true" />
        {{ t('aiCreation.backToWorkspace') }}
      </button>
    </div>

    <SeedancePanel v-if="store.loading && !task && !notFound">
      <div class="flex min-h-72 items-center justify-center text-[var(--seedance-muted)]" role="status">
        {{ t('common.loading') }}
      </div>
    </SeedancePanel>

    <SeedancePanel v-else-if="notFound || !task">
      <SeedanceEmptyState
        :title="t('seedance.preview.notFoundTitle')"
        :description="t('seedance.preview.notFoundDescription')"
        icon="error"
      >
        <template #actions>
          <RouterLink to="/video-generation/create" class="btn-secondary">
            {{ t('seedance.nav.create') }}
          </RouterLink>
        </template>
      </SeedanceEmptyState>
    </SeedancePanel>

    <template v-else>
      <section
        class="rounded-xl border border-dark-border bg-[#252525] p-4 sm:p-5"
        data-test="seedance-preview-stage-frame"
      >
        <div class="mb-4 flex flex-wrap items-center gap-2">
          <Button
            v-if="canCancel"
            variant="secondary"
            @click="cancelTask"
          >
            {{ t('seedance.tasks.cancel') }}
          </Button>
          <Button
            v-if="canRetryDownload"
            variant="secondary"
            @click="retryDownload"
          >
            {{ t('seedance.ui.redownload') }}
          </Button>
          <Button
            v-if="task.cache_status === 'complete'"
            variant="primary"
            @click="regenerate"
          >
            {{ t('seedance.tasks.regenerate') }}
          </Button>
          <Button
            v-if="canContinue"
            variant="primary"
            @click="continueFromReturnedFrame"
          >
            {{ t('seedance.ui.continueGeneration') }}
          </Button>
          <Button
            v-if="hasMedia(task) && task.output_urls.video"
            variant="primary"
            :loading="savingVideo"
            @click="downloadVideo"
          >
            <Download :size="16" aria-hidden="true" />
            {{ t('seedance.preview.saveVideo') }}
          </Button>
          <Button
            class="ml-auto"
            variant="danger"
            @click="requestDelete"
          >
            {{ t('seedance.tasks.delete') }}
          </Button>
        </div>

        <p v-if="downloadLinkMayBeExpired" class="mb-4 rounded-lg border border-warning/30 bg-warning/10 p-3 text-sm text-warning">
          {{ t('seedance.ui.downloadUrlMayBeExpired') }}
        </p>

        <div class="relative">
          <SeedanceVideoStage
            :phase="phase"
            :video-url="task.output_urls.video"
          />
          <RecentMediaFavoriteButton
            v-if="task.output_urls.video"
            class="absolute right-3 top-3 z-[2]"
            :favorite="isFavorite(videoMediaKey(task.local_id))"
            :data-test="`seedance-detail-favorite-${task.local_id}`"
            @toggle="toggleFavorite(videoMediaKey(task.local_id))"
          />
        </div>
      </section>

      <div class="mt-5 grid gap-5 xl:grid-cols-[minmax(0,2fr)_minmax(340px,.95fr)]">
        <section class="space-y-5">
          <SeedanceMediaStrip :task="task" />
          <SeedanceGenerationInfo :task="task" :output="output" />
        </section>

        <aside class="space-y-5 xl:sticky xl:top-24 xl:self-start">
          <SeedanceHandoffPanel
            :disabled="!hasMedia(task)"
            :creating="handoffCreating"
            :roles="projectStore.roles"
            @handoff="handoff"
          />
          <p v-if="handoffResult" class="rounded-lg border border-success/30 bg-success/10 p-3 text-sm text-success">
            {{ t('seedance.handoff.success', { id: handoffResult }) }}
          </p>
        </aside>
      </div>
    </template>

    <div
      v-if="confirmProtected"
      ref="modalRoot"
      class="seedance-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="protected-title"
      aria-describedby="protected-description"
      @keydown="onModalKeydown"
      @click.self="closeConfirmation"
    >
      <div>
        <h2 id="protected-title">{{ t('seedance.tasks.delete') }}</h2>
        <p id="protected-description">
          {{ task?.protected ? t('seedance.ui.protectedDeleteWarning') : t('seedance.tasks.deleteConfirmation') }}
        </p>
        <div class="mt-5 flex justify-end gap-2">
          <Button variant="secondary" @click="closeConfirmation">{{ t('common.cancel') }}</Button>
          <Button variant="danger" @click="deleteTask(!!task?.protected)">{{ t('seedance.tasks.delete') }}</Button>
        </div>
      </div>
    </div>

    <div
      v-if="pendingPaidAction"
      ref="modalRoot"
      class="seedance-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="paid-action-title"
      aria-describedby="paid-action-description"
      @keydown="onModalKeydown"
      @click.self="closeConfirmation"
    >
      <div>
        <h2 id="paid-action-title">
          {{ pendingPaidAction === 'retry' ? t('seedance.tasks.retry') : t('seedance.ui.continueGeneration') }}
        </h2>
        <p id="paid-action-description">
          {{ t(pendingPaidAction === 'retry' ? 'seedance.ui.retryBillingWarning' : 'seedance.ui.continueBillingWarning') }}
        </p>
        <div class="mt-5 flex justify-end gap-2">
          <Button variant="secondary" @click="closeConfirmation">{{ t('common.cancel') }}</Button>
          <Button :loading="confirmingPaidAction" :disabled="confirmingPaidAction" @click="confirmPaidAction">
            {{ t('common.confirm') }}
          </Button>
        </div>
      </div>
    </div>
  </SeedanceShell>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import { ArrowLeft, Download } from 'lucide-vue-next';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';
import Button from '@/components/common/Button.vue';
import RecentMediaFavoriteButton from '@/components/ai-creation/RecentMediaFavoriteButton.vue';
import SeedanceEmptyState from '@/components/seedance/SeedanceEmptyState.vue';
import SeedanceGenerationInfo from '@/components/seedance/SeedanceGenerationInfo.vue';
import SeedanceHandoffPanel from '@/components/seedance/SeedanceHandoffPanel.vue';
import SeedanceMediaStrip from '@/components/seedance/SeedanceMediaStrip.vue';
import SeedancePanel from '@/components/seedance/SeedancePanel.vue';
import SeedanceShell from '@/components/seedance/SeedanceShell.vue';
import SeedanceVideoStage from '@/components/seedance/SeedanceVideoStage.vue';
import { trapModalTab } from '@/modal-focus';
import { runConfirmedPaidAction, type PaidGenerationAction } from '@/paid-action-confirmation';
import { useRecentMediaFavorites } from '@/recent-media-favorites';
import { actualOutputParameters, downloadUrlMayBeExpired, hasMedia, seedanceTaskActions, seedanceTaskPhase } from '@/seedance-ui';
import { useProjectStore } from '@/stores/project';
import { useSeedanceStore } from '@/stores/seedance';

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const store = useSeedanceStore();
const projectStore = useProjectStore();
const { videoMediaKey, isFavorite, toggleFavorite } = useRecentMediaFavorites();
const task = computed(() => store.currentTask);
const output = computed(() => task.value
  ? actualOutputParameters(task.value)
  : { resolution: '—', ratio: '—', duration: '—', fps: '—' });
const phase = computed(() => task.value ? seedanceTaskPhase(task.value) : 'submitting');
const handoffResult = ref('');
const handoffCreating = ref(false);
const savingVideo = ref(false);
const confirmProtected = ref(false);
const pendingPaidAction = ref<PaidGenerationAction | null>(null);
const confirmingPaidAction = ref(false);
const notFound = ref(false);
const modalRoot = ref<HTMLElement | null>(null);
let trigger: HTMLElement | null = null;
const canContinue = computed(() => (
  !!task.value && hasMedia(task.value) && !!task.value.output_urls.returned_last_frame
));
const canCancel = computed(() => (
  !!task.value && seedanceTaskActions(task.value).includes('cancel')
));
const canRetryDownload = computed(() => (
  !!task.value && seedanceTaskActions(task.value).includes('retry-download')
));
const downloadLinkMayBeExpired = computed(() => (
  !!task.value && canRetryDownload.value && downloadUrlMayBeExpired(task.value)
));

onMounted(async () => {
  const [result] = await Promise.all([
    store.loadTask(String(route.params.localTaskId)),
    projectStore.loadProjects(),
  ]);
  notFound.value = result === null;
});
onBeforeUnmount(closeConfirmation);

async function openConfirmation(kind: PaidGenerationAction | 'delete') {
  trigger = document.activeElement as HTMLElement;
  confirmProtected.value = kind === 'delete';
  pendingPaidAction.value = kind === 'delete' ? null : kind;
  await nextTick();
  modalRoot.value?.querySelector<HTMLElement>('button')?.focus();
}

function closeConfirmation() {
  confirmProtected.value = false;
  pendingPaidAction.value = null;
  trigger?.focus();
  trigger = null;
}

function onModalKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    closeConfirmation();
    return;
  }
  if (modalRoot.value) trapModalTab(event, modalRoot.value);
}

function requestDelete() {
  if (task.value) void openConfirmation('delete');
}

function backToTasks() {
  void router.push('/ai-creation');
}

async function cancelTask() {
  if (task.value) await store.cancelTask(task.value.local_id);
}

async function retryDownload() {
  if (task.value) await store.retryDownload(task.value.local_id);
}

async function downloadVideo() {
  if (!task.value) return;
  savingVideo.value = true;
  await store.saveVideo(task.value.local_id);
  savingVideo.value = false;
}

function regenerate() {
  if (!task.value) return;
  void router.push({ path: '/video-generation/create', query: { regenerate: task.value.local_id } });
}

function continueFromReturnedFrame() {
  if (!task.value) return;
  void router.push({ path: '/video-generation/create', query: { continue: task.value.local_id } });
}

async function handoff(payload: { role: string; action: string }) {
  if (!task.value || handoffCreating.value) return;
  handoffCreating.value = true;
  try {
    const result = await store.handoff(task.value.local_id, payload.role, payload.action);
    if (!result || !('project_id' in result)) return;
    handoffResult.value = result.project_id;
    const project = await projectStore.loadProject(result.project_id);
    if (project) await router.push('/editor');
  } finally {
    handoffCreating.value = false;
  }
}

async function confirmPaidAction() {
  if (!task.value || confirmingPaidAction.value) return;
  confirmingPaidAction.value = true;
  const localId = task.value.local_id;
  try {
    const result = await runConfirmedPaidAction(pendingPaidAction.value, () => store.retryTask(localId));
    closeConfirmation();
    if (result) await router.push(`/video-generation/tasks/${result.local_id}`);
  } finally {
    confirmingPaidAction.value = false;
  }
}

async function deleteTask(allow: boolean) {
  if (task.value && await store.deleteTask(task.value.local_id, allow)) {
    closeConfirmation();
    await router.push('/ai-creation');
  }
}
</script>
