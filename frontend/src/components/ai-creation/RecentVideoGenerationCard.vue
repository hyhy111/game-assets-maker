<template>
  <article
    class="group cursor-pointer overflow-hidden rounded-xl border border-dark-border bg-dark-surface transition hover:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/60"
    :class="{ 'recent-generation-card-active': active }"
    :data-test="`recent-video-${task.local_id}`"
    tabindex="0"
    role="button"
    @click="emit('open', task.local_id)"
    @mouseenter="startPreview"
    @mouseleave="stopPreview"
    @keydown.enter="emit('open', task.local_id)"
    @keydown.space.prevent="emit('open', task.local_id)"
  >
    <div class="relative aspect-video overflow-hidden bg-black/20">
      <video
        v-if="isPreviewing && videoUrl"
        ref="previewVideo"
        :src="videoUrl"
        class="h-full w-full object-cover"
        data-test="recent-video-preview"
        muted
        playsinline
        preload="metadata"
        @loadedmetadata="initializePreview"
        @seeked="scheduleNextPreviewFrame"
        @error="stopPreview"
      />
      <img
        v-else-if="previewUrl"
        :src="previewUrl"
        alt=""
        class="h-full w-full object-cover transition duration-300 group-hover:brightness-105"
        data-test="recent-video-poster"
      >
      <div v-else class="grid h-full place-items-center text-gray-600"><Video :size="32" aria-hidden="true" /></div>
      <div class="absolute left-3 top-3 flex items-center gap-1.5">
        <span class="rounded-full px-3 py-1 text-xs font-medium shadow-sm" :class="statusClass">
          {{ statusText }}
        </span>
        <PlatformSourceBadge :source="task.source" />
      </div>
      <div v-if="$slots['top-right']" class="absolute right-3 top-3 z-[2]">
        <slot name="top-right" />
      </div>
    </div>

    <div class="p-4">
      <div class="flex flex-nowrap gap-1.5 overflow-hidden whitespace-nowrap text-xs text-gray-400" data-test="recent-video-metadata">
        <span class="shrink-0 rounded-md bg-black/20 px-2 py-1">{{ modelName(task.request.model, 'video') }}</span>
        <span class="shrink-0 rounded-md bg-black/20 px-2 py-1">{{ task.request.resolution }}</span>
        <span class="shrink-0 rounded-md bg-black/20 px-2 py-1">{{ ratio }}</span>
        <span class="shrink-0 rounded-md bg-black/20 px-2 py-1">{{ duration }}</span>
      </div>
      <dl class="mt-4 grid grid-cols-2 gap-3 border-t border-dark-border pt-4 text-xs">
        <div>
          <dt class="text-gray-500">{{ t('aiCreation.recent.createdAt') }}</dt>
          <dd class="mt-1 text-gray-300">{{ createdAt }}</dd>
        </div>
        <div class="text-right">
          <dt class="text-gray-500">{{ t('aiCreation.recent.elapsed') }}</dt>
          <dd class="mt-1 text-gray-300">{{ active ? t('aiCreation.recent.generating') : formatElapsed(task.elapsed_seconds) }}</dd>
        </div>
      </dl>
      <div v-if="$slots['bottom-right']" class="mt-3 flex justify-end">
        <slot name="bottom-right" />
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue';
import { Video } from 'lucide-vue-next';
import { useI18n } from 'vue-i18n';
import { useModelDisplayName } from '@/composables/useModelDisplayName';
import PlatformSourceBadge from '@/components/ai-creation/PlatformSourceBadge.vue';
import { formatElapsed, seedanceTaskPhase } from '@/seedance-ui';
import type { SeedanceTask } from '@/types';

const props = defineProps<{ task: SeedanceTask }>();
const emit = defineEmits<{ open: [localId: string] }>();
const { t, locale } = useI18n();
const { modelName } = useModelDisplayName();
const activePhases = new Set(['submitting', 'queued', 'running', 'unknown', 'cancelling', 'downloading']);
const SOURCE_FRAME_INTERVAL = 4;
const SOURCE_FRAME_LIMIT = 80;
const PREVIEW_FRAME_LIMIT = 20;
const FALLBACK_SOURCE_FPS = 24;

const isPreviewing = ref(false);
const previewVideo = ref<HTMLVideoElement | null>(null);
let previewTimer: number | null = null;
let previewFrameIndex = 0;
let previewFrameCount = 0;

const phase = computed(() => seedanceTaskPhase(props.task));
const active = computed(() => activePhases.has(phase.value));
const previewUrl = computed(() => props.task.output_urls.thumbnail || props.task.input_urls.first_frame || '');
const videoUrl = computed(() => props.task.output_urls.video || '');
const sourceFps = computed(() => {
  const outputFps = props.task.remote.output?.fps;
  const fps = typeof outputFps === 'number' ? outputFps : props.task.remote.fps;
  return typeof fps === 'number' && Number.isFinite(fps) && fps > 0 ? fps : FALLBACK_SOURCE_FPS;
});
const ratio = computed(() => props.task.request.ratio === 'adaptive' ? t('seedance.create.adaptive') : props.task.request.ratio);
const duration = computed(() => props.task.request.duration === -1 ? t('seedance.ui.smart') : `${props.task.request.duration}s`);
const createdAt = computed(() => {
  const date = new Date(props.task.created_at);
  return Number.isNaN(date.getTime()) ? props.task.created_at : date.toLocaleString(locale.value);
});
const statusText = computed(() => active.value ? t('aiCreation.recent.generating') : t(`seedance.status.${phase.value}`));
const statusClass = computed(() => {
  if (active.value) return 'bg-primary/20 text-white';
  if (phase.value === 'succeeded') return 'bg-success/20 text-black';
  if (phase.value === 'failed') return 'bg-danger/20 text-danger';
  return 'bg-gray-500/30 text-gray-200';
});

function clearPreviewTimer() {
  if (previewTimer !== null) {
    window.clearTimeout(previewTimer);
    previewTimer = null;
  }
}

function startPreview() {
  if (videoUrl.value) {
    isPreviewing.value = true;
  }
}

function initializePreview() {
  const video = previewVideo.value;
  if (!video || !isPreviewing.value) return;

  const availableFrames = Number.isFinite(video.duration)
    ? Math.max(1, Math.floor(video.duration * sourceFps.value))
    : SOURCE_FRAME_LIMIT;
  previewFrameCount = Math.min(
    PREVIEW_FRAME_LIMIT,
    Math.ceil(Math.min(SOURCE_FRAME_LIMIT, availableFrames) / SOURCE_FRAME_INTERVAL),
  );
  previewFrameIndex = 0;
  video.currentTime = 0;
  scheduleNextPreviewFrame();
}

function scheduleNextPreviewFrame() {
  clearPreviewTimer();
  if (!isPreviewing.value || previewFrameCount <= 1) return;

  const frameDuration = (SOURCE_FRAME_INTERVAL / sourceFps.value) * 1000;
  previewTimer = window.setTimeout(() => {
    const video = previewVideo.value;
    if (!video || !isPreviewing.value) return;

    previewFrameIndex = (previewFrameIndex + 1) % previewFrameCount;
    const targetFrame = previewFrameIndex * SOURCE_FRAME_INTERVAL;
    video.currentTime = Math.min(
      targetFrame / sourceFps.value,
      Math.max(0, video.duration - 0.001),
    );
  }, frameDuration);
}

function stopPreview() {
  clearPreviewTimer();
  isPreviewing.value = false;
  previewFrameIndex = 0;
  previewFrameCount = 0;
}

onBeforeUnmount(stopPreview);
</script>
