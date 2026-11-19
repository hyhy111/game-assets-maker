<template>
  <section class="space-y-2 rounded-lg border border-white/10 p-3">
    <div role="status">
      <p class="flex items-center gap-2 text-sm font-medium">
        <CheckCircle
          v-if="ready"
          class="h-4 w-4 shrink-0 text-success"
          aria-hidden="true"
        />
        <Loader2
          v-else-if="busy || detecting"
          class="h-4 w-4 shrink-0 text-primary motion-safe:animate-spin"
          aria-hidden="true"
        />
        {{ t(ready ? 'gpuRuntime.ready' : eligible ? `gpuRuntime.${status.phase}` : 'gpuRuntime.needs_download') }}
      </p>
      <p
        v-if="ready && cpuRunning"
        class="mt-1 pl-6 text-xs text-gray-400"
      >
        {{ t('gpuRuntime.cpuRunning') }}
      </p>
      <template v-if="!ready">
        <p
          v-if="deviceLabel"
          class="mt-1 text-xs text-gray-400"
        >
          {{ deviceLabel }}
        </p>
        <p
          v-if="detail"
          class="mt-1 text-xs text-gray-400"
        >
          {{ detail }}
        </p>
      </template>
    </div>

    <div v-if="showProgress">
      <div
        role="progressbar"
        :aria-label="t('gpuRuntime.progress')"
        :aria-valuenow="progress"
        class="h-1.5 overflow-hidden rounded-full bg-white/10"
      >
        <div
          class="h-full bg-primary"
          :style="{ width: `${progress}%` }"
        />
      </div>
      <p class="mt-1.5 text-xs tabular-nums text-gray-400">
        {{ formatMb(status.downloaded_bytes ?? 0) }} / {{ formatMb(status.total_bytes) }}
      </p>
    </div>

    <p
      v-if="eligible && status.phase === 'failed' && status.error"
      class="break-words text-xs text-danger-500"
    >
      {{ status.error.message }}
    </p>

    <Button
      v-if="busy"
      size="sm"
      variant="ghost"
      :disabled="changing"
      @click="cancel"
    >
      {{ t('common.cancel') }}
    </Button>
    <Button
      v-else-if="canRecheck"
      size="sm"
      variant="secondary"
      @click="detect"
    >
      {{ t('gpuRuntime.recheck') }}
    </Button>
    <div
      v-else-if="canPrepare"
      class="flex flex-wrap items-end gap-2 border-t border-white/10 pt-2"
    >
      <label class="min-w-0 text-xs text-gray-400">
        {{ t('gpuRuntime.source') }}
        <select
          v-model="source"
          :disabled="changing"
          class="mt-1 block h-8 max-w-full rounded-md border border-dark-border bg-dark-bg px-2 text-xs text-white focus:border-primary"
        >
          <option
            v-for="option in sources"
            :key="option"
            :value="option"
          >
            {{ t(`gpuRuntime.${option}`) }}
          </option>
        </select>
      </label>
      <Button
        size="sm"
        :loading="changing"
        @click="prepare"
      >
        {{ t(status.phase === 'paused' ? 'gpuRuntime.resume' : status.phase === 'failed' ? 'gpuRuntime.retry' : 'gpuRuntime.prepare') }}
      </Button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { CheckCircle, Loader2 } from 'lucide-vue-next';
import { processApi } from '@/api';
import type { GpuCompatibility, GpuDownloadSource, GpuRuntimeStatus } from '@/types';
import Button from '@/components/common/Button.vue';

const props = defineProps<{ model: string; modelReady: boolean; cpuRunning?: boolean }>();
const { t } = useI18n();
const sources: GpuDownloadSource[] = ['aliyun', 'huawei', 'pypi'];
const source = ref<GpuDownloadSource>('aliyun');
const status = ref<GpuRuntimeStatus>({ phase: 'needs_download', error: null, total_bytes: 0 });
const device = ref<GpuCompatibility | null>(null);
const detecting = ref(false);
const changing = ref(false);
const ready = computed(() => status.value.phase === 'ready');
const busy = computed(() => ['downloading', 'verifying', 'initializing'].includes(status.value.phase));
const eligible = computed(() => busy.value || device.value?.state === 'compatible');
const canPrepare = computed(() =>
  props.modelReady && status.value.total_bytes > 0 && eligible.value && !ready.value && !busy.value && !detecting.value,
);
const canRecheck = computed(() =>
  !ready.value && !busy.value && !detecting.value && ['driver', 'unknown'].includes(device.value?.state ?? ''),
);
const deviceLabel = computed(() => {
  if (ready.value || busy.value) return '';
  if (detecting.value || !device.value) return t('gpuRuntime.checking');
  if (device.value.state === 'compatible' && device.value.name) {
    return t('gpuRuntime.compatibleName', { name: device.value.name });
  }
  return t(`gpuRuntime.${device.value.state}`);
});
const detail = computed(() => {
  if (ready.value || detecting.value || !props.modelReady) return '';
  if (status.value.phase === 'initializing') return t('gpuRuntime.verificationHint');
  if (status.value.phase === 'verifying') return '';
  if (status.value.phase === 'downloading' || !eligible.value) return t('gpuRuntime.cpuAvailable');
  if (status.value.phase === 'needs_download' && status.value.total_bytes > 0) {
    return t('gpuRuntime.downloadHint', { size: (status.value.total_bytes / 1_000_000_000).toFixed(1) });
  }
  return '';
});
const showProgress = computed(() => status.value.total_bytes > 0 && (
  status.value.phase === 'downloading'
  || (device.value?.state === 'compatible' && status.value.phase === 'paused' && (status.value.downloaded_bytes ?? 0) > 0)
));
const progress = computed(() => Math.min(100, Math.floor((status.value.downloaded_bytes ?? 0) / status.value.total_bytes * 100)));
const formatMb = (bytes: number) => `${(bytes / 1_000_000).toFixed(1)} MB`;

let timer: ReturnType<typeof setInterval> | undefined;
let sourceLoaded = false;
let refreshing = false;
let actionRevision = 0;

function applyStatus(next: GpuRuntimeStatus) {
  status.value = next;
  if (next.device) device.value = next.device;
  if (!sourceLoaded && next.source) {
    source.value = next.source;
    sourceLoaded = true;
  }
}

async function refresh() {
  if (refreshing || changing.value) return;
  refreshing = true;
  const revision = actionRevision;
  try {
    const next = await processApi.getGpuRuntimeStatus();
    if (revision === actionRevision) applyStatus(next);
  } catch {
    // A transient bridge failure can be retried by the next poll.
  } finally {
    refreshing = false;
  }
}

async function detect() {
  detecting.value = true;
  try {
    device.value = await processApi.detectGpuCompatibility();
  } catch {
    device.value = { state: 'unknown' };
  } finally {
    detecting.value = false;
  }
}

async function prepare() {
  if (!canPrepare.value || changing.value) return;
  sourceLoaded = true;
  await changeStatus(() => processApi.prepareGpuRuntime(props.model, source.value));
}

async function cancel() {
  await changeStatus(() => processApi.cancelGpuRuntimePrepare());
}

async function changeStatus(request: () => Promise<GpuRuntimeStatus>) {
  changing.value = true;
  actionRevision++;
  try {
    applyStatus(await request());
  } catch (error) {
    status.value = { ...status.value, phase: 'failed', error: { code: 'GPU_DOWNLOAD_FAILED', message: String(error) } };
  } finally {
    changing.value = false;
  }
}

onMounted(() => {
  void refresh();
  void detect();
  timer = setInterval(() => { void refresh(); }, 1000);
});

onUnmounted(() => { clearInterval(timer); });
</script>
