<template>
  <div
    ref="sliderRef"
    class="relative w-full h-6 flex items-center select-none"
    :class="[simple ? '' : 'pt-4', { 'is-dragging': dragging !== null }]"
    @mousedown="onTrackClick"
    @pointermove="updateTickHover"
    @pointerleave="hoverX = null"
  >
    <!-- Track background -->
    <div class="absolute w-full h-2 bg-dark-border rounded-full" />

    <!-- Selected range highlight -->
    <div
      v-if="!simple"
      class="absolute h-2 bg-primary/50 rounded-full"
      :style="{
        left: `${startPercent}%`,
        width: `${endPercent - startPercent}%`
      }"
    />

    <!-- Extraction ticks share the source-frame axis with the range handles. -->
    <div
      v-if="extractionFrames.length"
      class="absolute inset-0 pointer-events-none"
      data-test="extraction-ticks"
    >
      <button
        v-for="(frame, index) in extractionFrames"
        :key="startFrame + index * (frameInterval ?? 1)"
        type="button"
        class="extraction-tick absolute top-0 h-4 w-2 -translate-x-1/2 pointer-events-auto rounded-sm cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary disabled:cursor-default"
        :disabled="!editable"
        :aria-label="t('step1.adjustFrame', { frame })"
        :title="t('step1.adjustFrame', { frame })"
        :style="{ left: `${timelineFramePercent(frame, totalFrames)}%` }"
        :data-frame="frame"
        @mousedown.stop
        @click.stop="emit('editFrame', startFrame + index * (frameInterval ?? 1))"
      >
        <span
          class="extraction-tick-mark absolute left-1/2 top-1.5 h-1.5 w-px rounded-full bg-current"
          :class="frame !== startFrame + index * (frameInterval ?? 1) ? 'text-white' : 'text-primary'"
          :style="tickHoverStyle(frame)"
          aria-hidden="true"
        />
      </button>
    </div>

    <!-- Start handle -->
    <div
      v-if="!simple"
      class="absolute w-4 h-4 bg-green-500 rounded-full cursor-ew-resize shadow-lg border-2 border-green-400 transform -translate-x-1/2 z-10 handle"
      :class="{
        'ring-2 ring-green-300': dragging === 'start',
        'hover:scale-110': dragging === null
      }"
      :style="{ left: `${startPercent}%` }"
      @mousedown.stop="onStartDrag"
    >
      <div
        class="handle-label absolute -top-6 left-1/2 transform -translate-x-1/2 text-xs text-green-400 whitespace-nowrap"
        :class="{ 'handle-label--visible': dragging === 'start' }"
      >
        {{ startFrame }}
      </div>
    </div>

    <!-- End handle -->
    <div
      v-if="!simple"
      class="absolute w-4 h-4 bg-red-500 rounded-full cursor-ew-resize shadow-lg border-2 border-red-400 transform -translate-x-1/2 z-10 handle end-handle"
      :class="{
        'ring-2 ring-red-300': dragging === 'end',
        'hover:scale-110': dragging === null
      }"
      :style="{ left: `${endPercent}%` }"
      @mousedown.stop="onEndDrag"
    >
      <div
        class="handle-label absolute -top-6 left-1/2 transform -translate-x-1/2 text-xs text-red-400 whitespace-nowrap"
        :class="{ 'handle-label--visible': dragging === 'end' }"
      >
        {{ endFrame }}
      </div>
    </div>

    <!-- Current position indicator (playback) -->
    <div
      class="absolute w-3 h-3 bg-white rounded-full shadow-md transform -translate-x-1/2 cursor-grab active:cursor-grabbing z-0"
      :style="{ left: `${currentPercent}%` }"
      @mousedown.stop="onCurrentDrag"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { extractionFrameIndices, frameFromTimelineRatio, timelineFramePercent } from './timelineMath';

const props = defineProps<{
  totalFrames: number;
  startFrame: number;
  endFrame: number;
  currentFrame: number;
  frameInterval?: number;
  frameOverrides?: Record<string, number>;
  editable?: boolean;
  simple?: boolean;
}>();

const emit = defineEmits<{
  'update:startFrame': [value: number];
  'update:endFrame': [value: number];
  'update:currentFrame': [value: number];
  editFrame: [baseFrame: number];
}>();

const { t } = useI18n();
const sliderRef = ref<HTMLDivElement>();
const dragging = ref<'start' | 'end' | 'current' | null>(null);
const hoverX = ref<number | null>(null);
const hoverTrackWidth = ref(0);

// Throttling control using requestAnimationFrame
let rafId: number | null = null;
let pendingFrame: number | null = null;
let pendingType: 'start' | 'end' | 'current' | null = null;

const startPercent = computed(() => {
  return timelineFramePercent(props.startFrame, props.totalFrames);
});

const endPercent = computed(() => {
  return props.totalFrames <= 1 ? 100 : timelineFramePercent(props.endFrame, props.totalFrames);
});

const currentPercent = computed(() => {
  return timelineFramePercent(props.currentFrame, props.totalFrames);
});

const extractionFrames = computed(() => {
  const interval = props.frameInterval ?? 1;
  if (props.simple || !Number.isInteger(interval) || interval <= 1 || props.totalFrames <= 0) return [];

  return extractionFrameIndices(props.totalFrames, props.startFrame, props.endFrame, interval, props.frameOverrides);
});

function updateTickHover(event: PointerEvent) {
  if (!sliderRef.value || dragging.value || !props.editable) {
    hoverX.value = null;
    return;
  }
  const rect = sliderRef.value.getBoundingClientRect();
  hoverTrackWidth.value = rect.width;
  hoverX.value = event.clientX - rect.left;
}

function tickHoverStyle(frame: number) {
  const tickX = timelineFramePercent(frame, props.totalFrames) / 100 * hoverTrackWidth.value;
  const distance = Math.abs(tickX - (hoverX.value ?? Infinity));
  const strength = Math.max(0, 1 - distance / 36);
  return {
    '--tick-lift': `${-4 * strength}px`,
    '--tick-scale': String(1 + 0.55 * strength),
    '--tick-glow': `${7 * strength}px`,
  };
}

function getFrameFromEvent(e: MouseEvent): number {
  if (!sliderRef.value) return 0;
  const rect = sliderRef.value.getBoundingClientRect();
  const ratio = rect.width > 0 ? (e.clientX - rect.left) / rect.width : 0;
  return frameFromTimelineRatio(ratio, props.totalFrames);
}

function onStartDrag() {
  dragging.value = 'start';
  document.addEventListener('mousemove', onDrag);
  document.addEventListener('mouseup', onDragEnd);
}

function onEndDrag() {
  dragging.value = 'end';
  document.addEventListener('mousemove', onDrag);
  document.addEventListener('mouseup', onDragEnd);
}

function onCurrentDrag() {
  dragging.value = 'current';
  document.addEventListener('mousemove', onDrag);
  document.addEventListener('mouseup', onDragEnd);
}

function onDrag(e: MouseEvent) {
  if (!dragging.value) return;

  const frame = getFrameFromEvent(e);

  // Save pending values for throttled update
  if (dragging.value === 'start') {
    pendingType = 'start';
    pendingFrame = Math.max(0, Math.min(frame, props.endFrame));
  } else if (dragging.value === 'end') {
    pendingType = 'end';
    pendingFrame = Math.min(props.totalFrames - 1, Math.max(frame, props.startFrame));
  } else if (dragging.value === 'current') {
    pendingType = 'current';
    pendingFrame = Math.max(0, Math.min(props.totalFrames - 1, frame));
  }

  // Use requestAnimationFrame for throttling
  if (rafId === null) {
    rafId = requestAnimationFrame(() => {
      rafId = null;
      if (pendingType === 'start' && pendingFrame !== null) {
        emit('update:startFrame', pendingFrame);
      } else if (pendingType === 'end' && pendingFrame !== null) {
        emit('update:endFrame', pendingFrame);
      } else if (pendingType === 'current' && pendingFrame !== null) {
        emit('update:currentFrame', pendingFrame);
      }
    });
  }
}

function onDragEnd() {
  // Cancel any pending RAF
  if (rafId !== null) {
    cancelAnimationFrame(rafId);
    rafId = null;
  }

  // Immediately emit the final update
  if (pendingType === 'start' && pendingFrame !== null) {
    emit('update:startFrame', pendingFrame);
  } else if (pendingType === 'end' && pendingFrame !== null) {
    emit('update:endFrame', pendingFrame);
  } else if (pendingType === 'current' && pendingFrame !== null) {
    emit('update:currentFrame', pendingFrame);
  }

  // Reset state
  pendingType = null;
  pendingFrame = null;
  dragging.value = null;

  document.removeEventListener('mousemove', onDrag);
  document.removeEventListener('mouseup', onDragEnd);
}

function onTrackClick(e: MouseEvent) {
  // Only handle clicks on the track itself, not on handles
  if ((e.target as HTMLElement).closest('.cursor-ew-resize, .cursor-grab')) return;
  emit('update:currentFrame', getFrameFromEvent(e));
}

onUnmounted(() => {
  document.removeEventListener('mousemove', onDrag);
  document.removeEventListener('mouseup', onDragEnd);
  // Clean up any pending RAF
  if (rafId !== null) {
    cancelAnimationFrame(rafId);
    rafId = null;
  }
});
</script>

<style scoped>
.extraction-tick-mark {
  transform: translateX(-50%) translateY(var(--tick-lift)) scale(var(--tick-scale));
  filter: drop-shadow(0 0 var(--tick-glow) currentColor);
  transition: transform 160ms ease-out, filter 160ms ease-out;
}

.extraction-tick:focus-visible .extraction-tick-mark {
  transform: translateX(-50%) translateY(-4px) scale(1.55);
  filter: drop-shadow(0 0 7px currentColor);
}

.handle-label {
  opacity: 0;
  visibility: hidden;
  pointer-events: none;
  transition: opacity 150ms ease-out, visibility 150ms ease-out;
}

.handle:hover .handle-label,
.handle-label--visible {
  opacity: 1;
  visibility: visible;
}

/* Default state: enable transitions for hover effects */
.handle {
  transition: transform 0.15s ease;
}

/* Dragging state: disable all transitions for better performance */
.is-dragging .handle {
  transition: none !important;
}

/* Glow effects - only applied when not dragging to reduce rendering burden */
.handle:not(.is-dragging) {
  box-shadow: 0 4px 12px rgba(34, 197, 94, 0.4), 0 0 20px rgba(34, 197, 94, 0.3);
}

.handle.end-handle:not(.is-dragging) {
  box-shadow: 0 4px 12px rgba(239, 68, 68, 0.4), 0 0 20px rgba(239, 68, 68, 0.3);
}

/* Simplified shadow during dragging for better performance */
.is-dragging .handle {
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3) !important;
}

@media (prefers-reduced-motion: reduce) {
  .extraction-tick-mark,
  .extraction-tick:focus-visible .extraction-tick-mark {
    transform: translateX(-50%);
    transition: none;
  }

  .handle-label {
    transition: none;
  }
}
</style>
