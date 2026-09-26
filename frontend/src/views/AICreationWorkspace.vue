<template>
  <div class="min-h-screen bg-dark-bg">
    <Header
      sticky
      page-aligned
    />
    <div
      v-if="prototypeVariant"
      class="mx-auto mt-4 w-[calc(100%-2rem)] max-w-[1272px] rounded-xl border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-warning"
      role="status"
    >
      UI 预览模式：使用本地模拟任务，不会发送图片或视频生成请求，也不会产生费用。
    </div>
    <main class="mx-auto w-full max-w-[1320px] px-4 py-6 sm:px-6">
      <div
        class="grid items-stretch gap-5"
        :class="workAreaColumns"
        data-test="ai-creation-work-area"
      >
        <div :class="prototypeVariant ? 'pointer-events-none select-none' : ''">
          <KeepAlive>
            <SeedreamCreate
              v-if="workspace.activeMode === 'image'"
              embedded
              :show-batch-list="false"
              :creation-mode="workspace.activeMode"
              @change-mode="workspace.activeMode = $event"
            />
            <SeedanceCreate
              v-else
              embedded
              :show-task-list="false"
              :creation-mode="workspace.activeMode"
              @change-mode="workspace.activeMode = $event"
            />
          </KeepAlive>
        </div>

        <ImageCurrentGenerationPanel
          v-if="currentImageBatch"
          :batch="currentImageBatch"
          :handoff-pending="workspace.candidateHandoffPending"
          :handoff-error="workspace.candidateHandoffError"
          @create-video="handoffCandidateToVideo"
        />
        <VideoCurrentGenerationPanel
          v-else-if="currentVideoTask"
          :task="currentVideoTask"
          @cancel="seedance.cancelTask"
          @retry-download="seedance.retryDownload"
          @open-detail="openVideoDetail"
        />
      </div>

      <RecentGenerations />
    </main>

    <div
      v-if="prototypeVariant"
      class="fixed bottom-5 left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 rounded-full border border-white/15 bg-black/90 p-2 text-white shadow-2xl backdrop-blur"
      aria-label="发送后 UI 预览状态"
    >
      <button type="button" class="grid h-9 w-9 place-items-center rounded-full hover:bg-white/10" aria-label="上一个预览状态" @click="cyclePrototype(-1)">←</button>
      <span class="min-w-36 px-2 text-center text-sm font-medium">{{ prototypeLabel }}</span>
      <button type="button" class="grid h-9 w-9 place-items-center rounded-full hover:bg-white/10" aria-label="下一个预览状态" @click="cyclePrototype(1)">→</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, watch } from 'vue';
import { onBeforeRouteLeave, useRoute } from 'vue-router';
import Header from '@/components/layout/Header.vue';
import ImageCurrentGenerationPanel from '@/components/ai-creation/ImageCurrentGenerationPanel.vue';
import VideoCurrentGenerationPanel from '@/components/ai-creation/VideoCurrentGenerationPanel.vue';
import RecentGenerations from '@/components/ai-creation/RecentGenerations.vue';
import { useAICreationStore } from '@/stores/aiCreation';
import { useSeedreamStore } from '@/stores/seedream';
import { useSeedanceStore } from '@/stores/seedance';
import { useRouter } from 'vue-router';
import SeedanceCreate from './SeedanceCreate.vue';
import SeedreamCreate from './SeedreamCreate.vue';
import type { SeedanceTask, SeedreamAttempt, SeedreamBatch } from '@/types';

type PrototypeVariant = 'image-partial' | 'image-complete' | 'video-running';

const prototypeVariants: Array<{ key: PrototypeVariant; label: string }> = [
  { key: 'image-partial', label: '图片 · 逐张返回' },
  { key: 'image-complete', label: '图片 · 全部完成' },
  { key: 'video-running', label: '视频 · 生成中' },
];

const route = useRoute();
const router = useRouter();
const workspace = useAICreationStore();
const seedream = useSeedreamStore();
const seedance = useSeedanceStore();
const isDevelopmentBuild = (import.meta as ImportMeta & { env?: { DEV?: boolean } }).env?.DEV === true;
if (route.query.mode === 'video') workspace.activeMode = 'video';
if (route.query.mode === 'image') workspace.activeMode = 'image';
const prototypeVariant = computed<PrototypeVariant | null>(() => {
  if (typeof window === 'undefined' || !isDevelopmentBuild || !['localhost', '127.0.0.1'].includes(window.location.hostname) || typeof route.query.prototype !== 'string') return null;
  return prototypeVariants.some(({ key }) => key === route.query.prototype)
    ? route.query.prototype as PrototypeVariant
    : null;
});
const prototypeLabel = computed(() => prototypeVariants.find(({ key }) => key === prototypeVariant.value)?.label ?? '');
const prototypeImageBatch = computed(() => prototypeVariant.value?.startsWith('image')
  ? makePrototypeImageBatch(prototypeVariant.value === 'image-complete')
  : null);
const prototypeVideoTask = computed(() => prototypeVariant.value === 'video-running' ? makePrototypeVideoTask() : null);
const currentImageBatch = computed(() => (
  prototypeImageBatch.value ?? (workspace.currentGeneration?.kind === 'image'
    ? seedream.batches.find((batch) => batch.local_id === workspace.currentGeneration?.localId) ?? null
    : null)
));
const currentVideoTask = computed(() => (
  prototypeVideoTask.value ?? (workspace.currentGeneration?.kind === 'video'
    ? seedance.tasks.find((task) => task.local_id === workspace.currentGeneration?.localId) ?? null
    : null)
));
const currentGenerationAvailable = computed(() => Boolean(currentImageBatch.value || currentVideoTask.value));
const workAreaColumns = computed(() => {
  if (!currentGenerationAvailable.value) return 'grid-cols-1';
  return 'lg:grid-cols-[minmax(0,65fr)_minmax(280px,35fr)]';
});

onMounted(async () => {
  window.addEventListener('keydown', onPrototypeKeydown);
  await nextTick();
  window.scrollTo({ top: workspace.workspaceScrollY, behavior: 'auto' });
});

onBeforeUnmount(() => window.removeEventListener('keydown', onPrototypeKeydown));

watch(prototypeVariant, (variant) => {
  if (variant) workspace.activeMode = variant === 'video-running' ? 'video' : 'image';
}, { immediate: true });

onBeforeRouteLeave(() => {
  workspace.rememberWorkspaceScroll(window.scrollY);
});

function openVideoDetail(localId: string) {
  return router.push(`/video-generation/tasks/${encodeURIComponent(localId)}`);
}

function handoffCandidateToVideo(attemptIndex: number) {
  if (prototypeVariant.value) {
    void router.replace({ path: '/ai-creation', query: { prototype: 'video-running' } });
    return Promise.resolve(true);
  }
  if (!currentImageBatch.value) return Promise.resolve(false);
  return workspace.handoffCandidateToVideo(currentImageBatch.value.local_id, attemptIndex);
}

function cyclePrototype(direction: number) {
  const index = prototypeVariants.findIndex(({ key }) => key === prototypeVariant.value);
  const next = prototypeVariants[(index + direction + prototypeVariants.length) % prototypeVariants.length];
  void router.replace({ path: '/ai-creation', query: { prototype: next.key } });
}

function onPrototypeKeydown(event: KeyboardEvent) {
  if (!prototypeVariant.value || ['INPUT', 'TEXTAREA', 'SELECT'].includes((event.target as HTMLElement)?.tagName)) return;
  if (event.key === 'ArrowLeft') cyclePrototype(-1);
  if (event.key === 'ArrowRight') cyclePrototype(1);
}

function prototypeSvg(label: string, from: string, to: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="640"><defs><linearGradient id="g" x2="1" y2="1"><stop stop-color="${from}"/><stop offset="1" stop-color="${to}"/></linearGradient></defs><rect width="640" height="640" rx="36" fill="url(#g)"/><circle cx="320" cy="270" r="112" fill="rgba(255,255,255,.14)"/><path d="M220 430c48-78 152-78 200 0" fill="none" stroke="rgba(255,255,255,.45)" stroke-width="28" stroke-linecap="round"/><text x="320" y="570" text-anchor="middle" fill="white" font-family="sans-serif" font-size="32">${label}</text></svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

function makePrototypeAttempt(index: number, status: SeedreamAttempt['status'], imageUrl = ''): SeedreamAttempt {
  const now = '2026-08-14T02:10:00Z';
  return {
    local_id: `prototype-attempt-${index}`, index, status,
    request: { prompt: '像素风弓箭手拉弓瞄准，光箭划出清晰轨迹', model: 'pro', resolution: '1K', ratio: '16:9', count: 4 },
    response: {}, usage: {}, total_tokens: null,
    image_url: imageUrl, image_width: imageUrl ? 1024 : null, image_height: imageUrl ? 1024 : null,
    local_path: imageUrl ? `prototype/${index}.png` : null, url_expired: false, created_at: now, updated_at: now,
    finished_at: status === 'succeeded' ? now : null, elapsed_seconds: status === 'succeeded' ? 38 + index * 4 : 0, error: null,
  };
}

function makePrototypeImageBatch(complete: boolean): SeedreamBatch {
  const images = [
    prototypeSvg('候选 1', '#3156d9', '#9c3fd6'), prototypeSvg('候选 2', '#126b68', '#51b56d'),
    prototypeSvg('候选 3', '#b54a31', '#d69c3f'), prototypeSvg('候选 4', '#4c3f91', '#397cc5'),
  ];
  return {
    local_id: 'prototype-image-batch', request: { prompt: '像素风弓箭手拉弓瞄准，光箭划出清晰轨迹', model: 'pro', resolution: '1K', ratio: '16:9', count: 4 },
    status: complete ? 'completed' : 'generating', sequence: '', created_at: '2026-08-14T02:09:20Z', updated_at: '2026-08-14T02:10:00Z',
    attempts: complete
      ? images.map((url, index) => makePrototypeAttempt(index, 'succeeded', url))
      : [makePrototypeAttempt(0, 'succeeded', images[0]), makePrototypeAttempt(1, 'succeeded', images[1]), makePrototypeAttempt(2, 'downloading'), makePrototypeAttempt(3, 'generating')],
  };
}

function makePrototypeVideoTask(): SeedanceTask {
  return {
    local_id: 'prototype-video-task', remote_id: 'preview-only', remote_status: 'running', sync_status: {}, download_status: 'pending', cache_status: 'complete', protected: false,
    request: { prompt: '角色缓慢抬弓，镜头轻微推进，动作自然连贯', model: 'standard', resolution: '720p', ratio: '16:9', duration: 4, generate_audio: false, return_last_frame: false, priority: 0, execution_expires_after: 3600 },
    input_urls: {}, output_urls: {}, created_at: '2026-08-14T02:09:20Z', updated_at: '2026-08-14T02:10:00Z', finished_at: null, download_url_received_at: null, elapsed_seconds: 40,
    remote: {}, error: null, retry_of: null, handoffs: [],
  };
}

</script>
