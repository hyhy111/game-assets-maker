<template>
  <section
    class="rounded-lg border border-white/10 p-3 space-y-2"
    aria-live="polite"
  >
    <p class="text-sm">
      {{ t(`gpuRuntime.${status.phase}`) }}
    </p>
    <p class="text-xs text-gray-400">
      {{ t('gpuRuntime.cpuHint') }}
    </p>
    <p
      v-if="status.total_bytes"
      class="text-xs text-gray-400"
    >
      {{ ((status.downloaded_bytes || 0) / 1000000).toFixed(1) }} MB / {{ (status.total_bytes / 1000000).toFixed(1) }} MB
    </p>
    <label
      v-if="status.phase !== 'ready'"
      class="block text-xs"
    >
      {{ t('gpuRuntime.source') }}
      <select
        v-model="source"
        :disabled="busy"
        class="ml-2 bg-dark-surface border border-white/10 rounded p-1"
      >
        <option value="aliyun">{{ t('gpuRuntime.aliyun') }}</option>
        <option value="pypi">{{ t('gpuRuntime.pypi') }}</option>
      </select>
    </label>
    <p
      v-if="status.error"
      class="text-xs text-danger-500"
    >
      {{ status.error.message }}
    </p>
    <Button
      v-if="busy"
      size="sm"
      variant="secondary"
      @click="cancel"
    >
      {{ t('common.cancel') }}
    </Button>
    <Button
      v-else-if="status.phase !== 'ready'"
      size="sm"
      variant="secondary"
      :disabled="!modelReady"
      @click="prepare"
    >
      {{ t(status.phase === 'paused' || status.phase === 'failed' ? 'gpuRuntime.resume' : 'gpuRuntime.prepare') }}
    </Button>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { processApi } from '@/api';
import type { GpuRuntimeStatus } from '@/types';
import Button from '@/components/common/Button.vue';

const props = defineProps<{ model: string; modelReady: boolean }>();
const { t } = useI18n();
const status = ref<GpuRuntimeStatus>({ phase: 'needs_download', error: null, total_bytes: 0 });
const source = ref<'aliyun' | 'pypi'>('aliyun');
const busy = computed(() => ['downloading', 'verifying', 'initializing'].includes(status.value.phase));
let timer: ReturnType<typeof setInterval> | undefined;
let sourceLoaded = false;
async function refresh() {
  status.value = await processApi.getGpuRuntimeStatus();
  if (!sourceLoaded && status.value.source) {
    source.value = status.value.source;
    sourceLoaded = true;
  }
}
async function prepare() {
  sourceLoaded = true;
  status.value = { ...status.value, phase: 'downloading' };
  try {
    await processApi.prepareGpuRuntime(props.model, source.value);
    await refresh();
  } catch (error) {
    status.value = { ...status.value, phase: 'failed', error: { code: 'GPU_DOWNLOAD_FAILED', message: String(error) } };
  }
}
async function cancel() { await processApi.cancelGpuRuntimePrepare(); await refresh(); }
onMounted(() => { void refresh(); timer = setInterval(() => { void refresh(); }, 1000); });
onUnmounted(() => { clearInterval(timer); });
</script>
