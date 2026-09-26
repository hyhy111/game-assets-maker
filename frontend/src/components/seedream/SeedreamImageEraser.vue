<template>
  <div
    class="fixed inset-0 z-50 flex flex-col bg-black/90 p-4"
    role="dialog"
    aria-modal="true"
    :aria-label="title || t('seedream.detail.eraserTitle')"
    data-test="seedream-eraser-editor"
  >
    <div class="mx-auto flex w-full max-w-6xl flex-wrap items-center gap-3 rounded-xl border border-dark-border bg-dark-surface p-3">
      <h2 class="mr-auto text-base font-semibold text-white">{{ title || t('seedream.detail.eraserTitle') }}</h2>
      <div class="flex items-center gap-2 text-sm text-gray-300">
        <span>{{ t('seedream.detail.backgroundColor') }}</span>
        <span class="h-5 w-5 rounded border border-white/30" :style="{ backgroundColor: backgroundCss }" />
        <span class="font-mono text-xs">{{ backgroundCss }}</span>
      </div>
      <Button
        variant="secondary"
        size="sm"
        :disabled="undoStack.length === 0"
        data-test="seedream-eraser-undo"
        @click="undo"
      >
        <Undo2 :size="16" /> {{ t('common.undo') }}
      </Button>
      <Button
        variant="secondary"
        size="sm"
        :disabled="redoStack.length === 0"
        data-test="seedream-eraser-redo"
        @click="redo"
      >
        <Redo2 :size="16" /> {{ t('common.redo') }}
      </Button>
      <span class="min-w-14 text-center text-sm text-gray-400" data-test="seedream-eraser-zoom">
        {{ Math.round(zoom * 100) }}%
      </span>
      <Button variant="secondary" size="sm" :disabled="saving" @click="emit('cancel')">
        {{ t('common.cancel') }}
      </Button>
      <button
        v-if="resizeEnabled"
        type="button"
        class="inline-flex h-8 items-center justify-center rounded-lg bg-success px-3 text-sm font-medium text-white transition-colors hover:bg-success/80 disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="saving || loading || (undoStack.length === 0 && !externalRestoreAvailable)"
        data-test="image-editor-restore-original"
        @click="restoreOriginal"
      >
        {{ t('seedream.detail.restoreOriginal') }}
      </button>
      <Button
        variant="primary"
        size="sm"
        :loading="saving"
        :disabled="saving || loading || undoStack.length === 0"
        data-test="seedream-eraser-apply"
        @click="apply"
      >
        {{ t('seedream.detail.applyEraser') }}
      </Button>
    </div>

    <div class="mx-auto mt-3 grid w-full max-w-6xl gap-3 lg:grid-cols-[220px_minmax(0,1fr)]">
      <aside class="rounded-xl border border-dark-border bg-dark-surface p-4">
        <p
          v-if="imageWidth > 0 && imageHeight > 0"
          class="mb-4 text-xs text-gray-500"
          data-test="image-editor-original-resolution"
        >
          {{ t('seedream.detail.originalResolution') }}：{{ imageWidth }} × {{ imageHeight }} px
        </p>
        <Slider
          v-model="brushSize"
          :min="5"
          :max="200"
          :step="1"
          :label="t('seedream.detail.eraserSize')"
          :value-formatter="(value) => `${value}px`"
          data-test="seedream-eraser-size"
        />
        <div v-if="resizeEnabled" class="mt-5 border-t border-dark-border pt-4">
          <div class="space-y-3" data-test="image-editor-resize-controls">
            <label class="block text-xs text-gray-300">
              {{ t('seedream.detail.targetHeight') }}
              <input
                v-model.number="resizeTargetRatio"
                type="number"
                min="1"
                :max="100"
                step="1"
                class="mt-1 w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-white"
                data-test="image-editor-target-height-ratio"
              />
              <span class="mt-1 block text-gray-500" data-test="image-editor-measured-height-px">
                {{ t('seedream.detail.measuredHeight') }}：{{ guideMeasuredHeight }} px
              </span>
              <span
                v-if="targetHeightPixels > 0"
                class="mt-1 block text-gray-500"
                data-test="image-editor-estimated-video-heights"
              >
                <span class="block">{{ t('seedream.detail.estimatedVideoHeight') }}</span>
                <span
                  v-for="estimate in estimatedVideoHeights"
                  :key="estimate.resolution"
                  class="block"
                >
                  {{ estimate.resolution }}：≈ {{ estimate.height }}px
                </span>
              </span>
            </label>
            <label class="block text-xs text-gray-300">
              {{ t('seedream.detail.bottomDistance') }}
              <input
                v-model.number="resizeBottomMarginRatio"
                type="number"
                min="0"
                :max="Math.max(0, 100 - (resizeTargetRatio ?? 0))"
                step="1"
                class="mt-1 w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-white"
                data-test="image-editor-bottom-distance-ratio"
              />
            </label>
            <p class="text-xs leading-5 text-gray-500">{{ t('seedream.detail.resizeCharacterHint') }}</p>
            <p v-if="resizeError" class="text-xs text-danger" role="alert">{{ resizeError }}</p>
            <Button
              variant="primary"
              size="sm"
              class="w-full"
              :disabled="!canApplyResize"
              data-test="image-editor-apply-resize"
              @click="applyResize"
            >
              {{ t('seedream.detail.applyResize') }}
            </Button>
          </div>
        </div>
        <p v-if="error || loadError" class="mt-3 text-sm text-danger" role="alert">{{ error || loadError }}</p>
      </aside>

      <div
        ref="viewportRef"
        class="relative flex min-h-0 items-center justify-center overflow-hidden rounded-xl border border-dark-border bg-dark-bg p-3"
        :class="{ 'cursor-grabbing': panning }"
        data-test="seedream-eraser-viewport"
        @wheel.prevent="zoomCanvas"
        @pointerdown="startPan"
        @pointermove="movePan"
        @pointerup="finishPan"
        @pointercancel="finishPan"
        @auxclick.prevent
      >
        <div v-if="loading" class="absolute inset-0 z-10 flex items-center justify-center text-sm text-gray-400">{{ t('common.loading') }}</div>
        <div
          class="relative max-h-[calc(100vh-9rem)] max-w-full"
          :class="{ invisible: loading }"
          :style="canvasTransformStyle"
        >
          <canvas
            ref="canvasRef"
            class="block max-h-[calc(100vh-9rem)] max-w-full touch-none rounded-lg cursor-none"
            data-test="seedream-eraser-canvas"
            @pointerdown="startStroke"
            @pointermove="moveStroke"
            @pointerup="finishStroke"
            @pointercancel="finishStroke"
            @pointerenter="showCursor = true"
            @pointerleave="onPointerLeave"
          />
          <template v-if="resizeEnabled && imageHeight > 0">
            <div
              class="pointer-events-none absolute left-0 right-0 z-10 border-t border-dashed border-primary"
              :style="guideStyle(resizeTop)"
            />
            <button
              type="button"
              role="slider"
              class="absolute right-0 z-20 h-5 w-5 translate-x-1/2 -translate-y-1/2 cursor-ns-resize rounded-full border-2 border-white bg-primary shadow"
              :style="guideStyle(resizeTop)"
              :aria-label="t('seedream.detail.characterTop')"
              aria-valuemin="0"
              :aria-valuemax="resizeBottom - 1"
              :aria-valuenow="resizeTop"
              data-test="image-editor-top-guide"
              @pointerdown.stop="captureGuide"
              @pointermove.stop="dragGuide($event, 'top')"
              @pointerup.stop="releaseGuide"
              @keydown="moveGuide($event, 'top')"
            />
            <div
              class="pointer-events-none absolute left-0 right-0 z-10 border-t border-dashed border-warning"
              :style="guideStyle(resizeBottom)"
            />
            <button
              type="button"
              role="slider"
              class="absolute right-0 z-20 h-5 w-5 translate-x-1/2 -translate-y-1/2 cursor-ns-resize rounded-full border-2 border-white bg-warning shadow"
              :style="guideStyle(resizeBottom)"
              :aria-label="t('seedream.detail.characterBottom')"
              :aria-valuemin="resizeTop + 1"
              :aria-valuemax="imageHeight"
              :aria-valuenow="resizeBottom"
              data-test="image-editor-bottom-guide"
              @pointerdown.stop="captureGuide"
              @pointermove.stop="dragGuide($event, 'bottom')"
              @pointerup.stop="releaseGuide"
              @keydown="moveGuide($event, 'bottom')"
            />
          </template>
        </div>
        <div
          v-if="showCursor && !panning"
          class="pointer-events-none absolute rounded-full border border-white shadow-[0_0_0_1px_rgba(0,0,0,0.8)]"
          :style="cursorStyle"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { Redo2, Undo2 } from 'lucide-vue-next';
import { useI18n } from 'vue-i18n';
import Button from '@/components/common/Button.vue';
import Slider from '@/components/common/Slider.vue';
import type { GenerationLayout } from '@/types';

interface EraseHistoryPatch {
  kind: 'erase';
  x: number;
  y: number;
  before: ImageData;
  after: ImageData;
}

interface LayoutHistoryPatch {
  kind: 'layout';
  beforeLayout: GenerationLayout | null;
  afterLayout: GenerationLayout | null;
}

type HistoryPatch = EraseHistoryPatch | LayoutHistoryPatch;

interface Point {
  x: number;
  y: number;
}

const props = withDefaults(defineProps<{
  imageUrl: string;
  editSourceUrl?: string;
  saving: boolean;
  error?: string;
  title?: string;
  resizeEnabled?: boolean;
  externalRestoreAvailable?: boolean;
  generationLayout?: GenerationLayout | null;
}>(), {
  error: '',
  editSourceUrl: '',
  title: '',
  resizeEnabled: false,
  externalRestoreAvailable: false,
  generationLayout: null,
});

const emit = defineEmits<{
  cancel: [];
  apply: [imageDataUrl: string, editSourceDataUrl: string, generationLayout: GenerationLayout | null];
  restore: [];
}>();

const { t } = useI18n();
const HISTORY_LIMIT = 20;
const MIN_ZOOM = 0.25;
const MAX_ZOOM = 8;
const viewportRef = ref<HTMLDivElement | null>(null);
const canvasRef = ref<HTMLCanvasElement | null>(null);
const loading = ref(true);
const loadError = ref('');
const brushSize = ref(40);
const backgroundColor = ref<[number, number, number]>([0, 0, 0]);
const undoStack = ref<HistoryPatch[]>([]);
const redoStack = ref<HistoryPatch[]>([]);
const drawing = ref(false);
const showCursor = ref(false);
const cursorX = ref(0);
const cursorY = ref(0);
const cursorDiameter = ref(0);
const zoom = ref(1);
const panX = ref(0);
const panY = ref(0);
const panning = ref(false);
const imageWidth = ref(0);
const imageHeight = ref(0);
const resizeTop = ref(0);
const resizeBottom = ref(0);
const sourceResizeTop = ref(0);
const sourceResizeBottom = ref(0);
const resizeTargetRatio = ref<number | null>(null);
const resizeBottomMarginRatio = ref<number | null>(null);
const currentGenerationLayout = ref<GenerationLayout | null>(null);
const resizeError = ref('');
let strokeBefore: ImageData | null = null;
let originalImageData: ImageData | null = null;
let editSourceCanvas: HTMLCanvasElement | null = null;
let strokeBounds: { left: number; top: number; right: number; bottom: number } | null = null;
let lastPoint: Point | null = null;
let panOrigin = { clientX: 0, clientY: 0, x: 0, y: 0 };

const backgroundCss = computed(() => `rgb(${backgroundColor.value.join(', ')})`);
const cursorStyle = computed(() => ({
  left: `${cursorX.value - cursorDiameter.value / 2}px`,
  top: `${cursorY.value - cursorDiameter.value / 2}px`,
  width: `${cursorDiameter.value}px`,
  height: `${cursorDiameter.value}px`,
}));
const canvasTransformStyle = computed(() => ({
  transform: `translate(${panX.value}px, ${panY.value}px) scale(${zoom.value})`,
  transformOrigin: 'center center',
}));
const sourceMeasuredHeight = computed(() => Math.max(0, sourceResizeBottom.value - sourceResizeTop.value));
const guideMeasuredHeight = computed(() => Math.max(0, resizeBottom.value - resizeTop.value));
const targetHeightPixels = computed(() => (
  typeof resizeTargetRatio.value === 'number'
    ? Math.round(imageHeight.value * resizeTargetRatio.value / 100)
    : 0
));
const estimatedVideoHeights = computed(() => [480, 720, 1080].map((videoHeight) => ({
  resolution: `${videoHeight}p`,
  height: imageHeight.value > 0
    ? Math.round(videoHeight * targetHeightPixels.value / imageHeight.value)
    : 0,
})));
const bottomDistancePixels = computed(() => (
  typeof resizeBottomMarginRatio.value === 'number'
    ? Math.round(imageHeight.value * resizeBottomMarginRatio.value / 100)
    : 0
));
const canApplyResize = computed(() => (
  typeof resizeTargetRatio.value === 'number'
  && resizeTargetRatio.value > 0
  && resizeTargetRatio.value <= 100
  && typeof resizeBottomMarginRatio.value === 'number'
  && resizeBottomMarginRatio.value >= 0
  && resizeBottomMarginRatio.value <= 100
  && sourceMeasuredHeight.value > 0
  && (
    targetHeightPixels.value !== (currentGenerationLayout.value?.target_height ?? sourceMeasuredHeight.value)
    || bottomDistancePixels.value !== (currentGenerationLayout.value?.bottom_distance ?? imageHeight.value - sourceResizeBottom.value)
    || sourceResizeTop.value !== (currentGenerationLayout.value?.measured_top ?? Math.round(imageHeight.value * 0.1))
    || sourceResizeBottom.value !== (currentGenerationLayout.value?.measured_bottom ?? Math.round(imageHeight.value * 0.9))
  )
  && bottomDistancePixels.value + targetHeightPixels.value <= imageHeight.value
));

onMounted(() => {
  window.addEventListener('keydown', onKeydown);
  loadImage();
});

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown);
});

async function loadImage() {
  loading.value = true;
  loadError.value = '';
  try {
    const [image, editSourceImage] = await Promise.all([
      loadHtmlImage(props.imageUrl),
      loadHtmlImage(props.editSourceUrl || props.imageUrl),
    ]);
    const canvas = canvasRef.value;
    if (!canvas) return;
    if (
      image.naturalWidth !== editSourceImage.naturalWidth
      || image.naturalHeight !== editSourceImage.naturalHeight
    ) throw new Error('Edit source dimensions do not match the image');
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    imageWidth.value = canvas.width;
    imageHeight.value = canvas.height;
    const context = canvas.getContext('2d', { willReadFrequently: true });
    if (!context) return;
    context.drawImage(image, 0, 0);
    editSourceCanvas = document.createElement('canvas');
    editSourceCanvas.width = canvas.width;
    editSourceCanvas.height = canvas.height;
    const sourceContext = editSourceCanvas.getContext('2d', { willReadFrequently: true });
    if (!sourceContext) return;
    sourceContext.drawImage(editSourceImage, 0, 0);
    originalImageData = sourceContext.getImageData(0, 0, canvas.width, canvas.height);
    backgroundColor.value = sampleCornerColor(sourceContext, canvas.width, canvas.height);
    zoom.value = 1;
    panX.value = 0;
    panY.value = 0;
    resetResizeGuides();
    loading.value = false;
  } catch {
    loadError.value = t('seedream.detail.eraserLoadFailed');
    loading.value = false;
  }
}

function loadHtmlImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.crossOrigin = 'anonymous';
    image.onload = () => resolve(image);
    image.onerror = reject;
    image.src = url;
  });
}

function sampleCornerColor(context: CanvasRenderingContext2D, width: number, height: number): [number, number, number] {
  const size = Math.max(1, Math.round(Math.min(width, height) * 0.05));
  const positions = [[0, 0], [width - size, 0], [0, height - size], [width - size, height - size]];
  const histograms = [new Uint32Array(256), new Uint32Array(256), new Uint32Array(256)];
  let count = 0;
  for (const [x, y] of positions) {
    const pixels = context.getImageData(x, y, size, size).data;
    for (let index = 0; index < pixels.length; index += 4) {
      histograms[0][pixels[index]] += 1;
      histograms[1][pixels[index + 1]] += 1;
      histograms[2][pixels[index + 2]] += 1;
      count += 1;
    }
  }
  return histograms.map((histogram) => histogramMedian(histogram, count)) as [number, number, number];
}

function histogramMedian(histogram: Uint32Array, count: number): number {
  const middle = Math.floor(count / 2);
  let seen = 0;
  for (let value = 0; value < histogram.length; value += 1) {
    seen += histogram[value];
    if (seen > middle) return value;
  }
  return 0;
}

function resetResizeGuides() {
  const height = imageHeight.value;
  const saved = props.generationLayout;
  if (saved && saved.source_height === height) {
    sourceResizeTop.value = saved.measured_top;
    sourceResizeBottom.value = saved.measured_bottom;
    resizeTop.value = height - saved.bottom_distance - saved.target_height;
    resizeBottom.value = height - saved.bottom_distance;
    resizeTargetRatio.value = saved.character_height_ratio * 100;
    resizeBottomMarginRatio.value = saved.bottom_margin_ratio * 100;
    currentGenerationLayout.value = saved;
  } else {
    resizeTop.value = Math.round(height * 0.1);
    resizeBottom.value = Math.round(height * 0.9);
    sourceResizeTop.value = resizeTop.value;
    sourceResizeBottom.value = resizeBottom.value;
    resizeTargetRatio.value = null;
    resizeBottomMarginRatio.value = null;
    currentGenerationLayout.value = null;
  }
  resizeError.value = '';
}

function guideStyle(pixel: number) {
  return { top: `${(pixel / imageHeight.value) * 100}%` };
}

function captureGuide(event: PointerEvent) {
  (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
}

function releaseGuide(event: PointerEvent) {
  const handle = event.currentTarget as HTMLElement;
  if (handle.hasPointerCapture(event.pointerId)) handle.releasePointerCapture(event.pointerId);
}

function dragGuide(event: PointerEvent, guide: 'top' | 'bottom') {
  const handle = event.currentTarget as HTMLElement;
  if (!handle.hasPointerCapture(event.pointerId)) return;
  const rect = canvasRef.value?.getBoundingClientRect();
  if (!rect?.height) return;
  const pixel = Math.round(((event.clientY - rect.top) / rect.height) * imageHeight.value);
  setGuide(guide, pixel);
}

function moveGuide(event: KeyboardEvent, guide: 'top' | 'bottom') {
  if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return;
  event.preventDefault();
  const current = guide === 'top' ? resizeTop.value : resizeBottom.value;
  setGuide(guide, current + (event.key === 'ArrowUp' ? -1 : 1));
}

function setGuide(guide: 'top' | 'bottom', pixel: number) {
  if (guide === 'top') {
    resizeTop.value = Math.min(resizeBottom.value - 1, Math.max(0, pixel));
  } else {
    resizeBottom.value = Math.max(resizeTop.value + 1, Math.min(imageHeight.value, pixel));
  }
  const sourcePixel = displayToSourceY(guide === 'top' ? resizeTop.value : resizeBottom.value);
  if (guide === 'top') {
    sourceResizeTop.value = Math.min(sourceResizeBottom.value - 1, Math.max(0, sourcePixel));
  } else {
    sourceResizeBottom.value = Math.max(sourceResizeTop.value + 1, Math.min(imageHeight.value, sourcePixel));
  }
}

function displayToSourceY(pixel: number): number {
  const layout = currentGenerationLayout.value;
  if (!layout) return pixel;
  const targetBottom = imageHeight.value - layout.bottom_distance;
  const offsetY = targetBottom - layout.measured_bottom * layout.scale;
  return Math.round((pixel - offsetY) / layout.scale);
}

function displayToSourcePoint(point: Point): Point | null {
  const layout = currentGenerationLayout.value;
  if (!layout) return point;
  const canvas = canvasRef.value;
  if (!canvas) return null;
  const scaledWidth = canvas.width * layout.scale;
  const offsetX = (canvas.width - scaledWidth) / 2;
  const targetBottom = canvas.height - layout.bottom_distance;
  const offsetY = targetBottom - layout.measured_bottom * layout.scale;
  const sourcePoint = {
    x: (point.x - offsetX) / layout.scale,
    y: (point.y - offsetY) / layout.scale,
  };
  if (
    sourcePoint.x < 0 || sourcePoint.x > canvas.width
    || sourcePoint.y < 0 || sourcePoint.y > canvas.height
  ) return null;
  return sourcePoint;
}

function renderFromSource() {
  const canvas = canvasRef.value;
  const context = canvas?.getContext('2d');
  if (!canvas || !context || !editSourceCanvas) return;
  const layout = currentGenerationLayout.value;
  if (!layout) {
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.drawImage(editSourceCanvas, 0, 0);
    return;
  }

  context.fillStyle = backgroundCss.value;
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = 'high';
  const scaledWidth = Math.max(1, Math.round(canvas.width * layout.scale));
  const scaledHeight = Math.max(1, Math.round(canvas.height * layout.scale));
  const targetBottom = canvas.height - layout.bottom_distance;
  const offsetX = Math.round((canvas.width - scaledWidth) / 2);
  const offsetY = Math.round(targetBottom - layout.measured_bottom * layout.scale);
  context.drawImage(editSourceCanvas, offsetX, offsetY, scaledWidth, scaledHeight);
}

function applyResize() {
  const canvas = canvasRef.value;
  if (!canvas || !editSourceCanvas || !canApplyResize.value) return;
  const targetHeight = targetHeightPixels.value;
  const bottomDistance = bottomDistancePixels.value;

  const beforeLayout = currentGenerationLayout.value;
  const targetBottom = canvas.height - bottomDistance;
  const scale = targetHeight / sourceMeasuredHeight.value;

  const generationLayout: GenerationLayout = {
    source_width: canvas.width,
    source_height: canvas.height,
    measured_top: sourceResizeTop.value,
    measured_bottom: sourceResizeBottom.value,
    measured_height: sourceMeasuredHeight.value,
    target_height: targetHeight,
    character_height_ratio: targetHeight / canvas.height,
    bottom_distance: bottomDistance,
    bottom_margin_ratio: bottomDistance / canvas.height,
    scale,
  };
  currentGenerationLayout.value = generationLayout;
  renderFromSource();
  undoStack.value.push({
    kind: 'layout',
    beforeLayout,
    afterLayout: generationLayout,
  });
  if (undoStack.value.length > HISTORY_LIMIT) undoStack.value.shift();
  redoStack.value = [];
  resizeTop.value = Math.max(0, targetBottom - targetHeight);
  resizeBottom.value = targetBottom;
  resizeTargetRatio.value = targetHeight / canvas.height * 100;
  resizeBottomMarginRatio.value = bottomDistance / canvas.height * 100;
  resizeError.value = '';
}

function restoreOriginal() {
  if (props.externalRestoreAvailable) {
    emit('restore');
    return;
  }
  const canvas = canvasRef.value;
  const sourceContext = editSourceCanvas?.getContext('2d');
  if (!canvas || !sourceContext || !originalImageData || undoStack.value.length === 0) return;
  sourceContext.putImageData(originalImageData, 0, 0);
  undoStack.value = [];
  redoStack.value = [];
  strokeBefore = null;
  strokeBounds = null;
  lastPoint = null;
  drawing.value = false;
  resetResizeGuides();
  renderFromSource();
}

function canvasPoint(event: PointerEvent): Point | null {
  const canvas = canvasRef.value;
  const viewport = viewportRef.value;
  if (!canvas || !viewport) return null;
  const rect = canvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;
  const viewportRect = viewport.getBoundingClientRect();
  cursorX.value = event.clientX - viewportRect.left;
  cursorY.value = event.clientY - viewportRect.top;
  cursorDiameter.value = brushSize.value * rect.width / canvas.width;
  return {
    x: (event.clientX - rect.left) * canvas.width / rect.width,
    y: (event.clientY - rect.top) * canvas.height / rect.height,
  };
}

function zoomCanvas(event: WheelEvent) {
  const viewport = viewportRef.value;
  if (!viewport || loading.value || drawing.value) return;
  const rect = viewport.getBoundingClientRect();
  const oldZoom = zoom.value;
  const nextZoom = Math.min(
    MAX_ZOOM,
    Math.max(MIN_ZOOM, oldZoom * Math.exp(-event.deltaY * 0.0015))
  );
  if (nextZoom === oldZoom) return;

  const pointX = event.clientX - rect.left - rect.width / 2;
  const pointY = event.clientY - rect.top - rect.height / 2;
  const ratio = nextZoom / oldZoom;
  panX.value = pointX - (pointX - panX.value) * ratio;
  panY.value = pointY - (pointY - panY.value) * ratio;
  zoom.value = nextZoom;
}

function startPan(event: PointerEvent) {
  if (event.button !== 1) return;
  const viewport = viewportRef.value;
  if (!viewport) return;
  event.preventDefault();
  viewport.setPointerCapture(event.pointerId);
  panning.value = true;
  showCursor.value = false;
  panOrigin = {
    clientX: event.clientX,
    clientY: event.clientY,
    x: panX.value,
    y: panY.value,
  };
}

function movePan(event: PointerEvent) {
  if (!panning.value) return;
  panX.value = panOrigin.x + event.clientX - panOrigin.clientX;
  panY.value = panOrigin.y + event.clientY - panOrigin.clientY;
}

function finishPan(event: PointerEvent) {
  if (!panning.value) return;
  const viewport = viewportRef.value;
  panning.value = false;
  if (viewport?.hasPointerCapture(event.pointerId)) viewport.releasePointerCapture(event.pointerId);
}

function startStroke(event: PointerEvent) {
  if (event.button !== 0) return;
  const canvas = canvasRef.value;
  const sourceContext = editSourceCanvas?.getContext('2d', { willReadFrequently: true });
  const displayPoint = canvasPoint(event);
  if (!canvas || !sourceContext || !displayPoint) return;
  canvas.setPointerCapture(event.pointerId);
  drawing.value = true;
  showCursor.value = true;
  strokeBefore = sourceContext.getImageData(0, 0, canvas.width, canvas.height);
  strokeBounds = null;
  const point = displayToSourcePoint(displayPoint);
  lastPoint = point;
  if (!point) return;
  const sourceBrushSize = brushSize.value / (currentGenerationLayout.value?.scale ?? 1);
  extendBounds(point, sourceBrushSize);
  drawPoint(sourceContext, point, sourceBrushSize);
  renderFromSource();
}

function moveStroke(event: PointerEvent) {
  const displayPoint = canvasPoint(event);
  const point = displayPoint ? displayToSourcePoint(displayPoint) : null;
  showCursor.value = true;
  if (!drawing.value) return;
  if (!point) {
    lastPoint = null;
    return;
  }
  const sourceContext = editSourceCanvas?.getContext('2d');
  if (!sourceContext) return;
  const sourceBrushSize = brushSize.value / (currentGenerationLayout.value?.scale ?? 1);
  if (lastPoint) drawLine(sourceContext, lastPoint, point, sourceBrushSize);
  else drawPoint(sourceContext, point, sourceBrushSize);
  extendBounds(point, sourceBrushSize);
  lastPoint = point;
  renderFromSource();
}

function finishStroke(event: PointerEvent) {
  if (!drawing.value) return;
  const canvas = canvasRef.value;
  const sourceContext = editSourceCanvas?.getContext('2d', { willReadFrequently: true });
  drawing.value = false;
  lastPoint = null;
  if (canvas?.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
  if (!canvas || !sourceContext || !strokeBefore || !strokeBounds) {
    strokeBefore = null;
    strokeBounds = null;
    return;
  }
  const x = Math.max(0, Math.floor(strokeBounds.left));
  const y = Math.max(0, Math.floor(strokeBounds.top));
  const right = Math.min(canvas.width, Math.ceil(strokeBounds.right));
  const bottom = Math.min(canvas.height, Math.ceil(strokeBounds.bottom));
  const width = right - x;
  const height = bottom - y;
  if (width > 0 && height > 0) {
    undoStack.value.push({
      kind: 'erase',
      x,
      y,
      before: cropImageData(sourceContext, strokeBefore, x, y, width, height),
      after: sourceContext.getImageData(x, y, width, height),
    });
    if (undoStack.value.length > HISTORY_LIMIT) undoStack.value.shift();
    redoStack.value = [];
  }
  strokeBefore = null;
  strokeBounds = null;
}

function extendBounds(point: Point, sourceBrushSize: number) {
  const margin = sourceBrushSize / 2 + 2;
  const next = {
    left: point.x - margin,
    top: point.y - margin,
    right: point.x + margin,
    bottom: point.y + margin,
  };
  if (!strokeBounds) {
    strokeBounds = next;
    return;
  }
  strokeBounds.left = Math.min(strokeBounds.left, next.left);
  strokeBounds.top = Math.min(strokeBounds.top, next.top);
  strokeBounds.right = Math.max(strokeBounds.right, next.right);
  strokeBounds.bottom = Math.max(strokeBounds.bottom, next.bottom);
}

function drawPoint(context: CanvasRenderingContext2D, point: Point, sourceBrushSize: number) {
  context.fillStyle = backgroundCss.value;
  context.beginPath();
  context.arc(point.x, point.y, sourceBrushSize / 2, 0, Math.PI * 2);
  context.fill();
}

function drawLine(context: CanvasRenderingContext2D, from: Point, to: Point, sourceBrushSize: number) {
  context.strokeStyle = backgroundCss.value;
  context.lineWidth = sourceBrushSize;
  context.lineCap = 'round';
  context.lineJoin = 'round';
  context.beginPath();
  context.moveTo(from.x, from.y);
  context.lineTo(to.x, to.y);
  context.stroke();
}

function cropImageData(
  context: CanvasRenderingContext2D,
  source: ImageData,
  x: number,
  y: number,
  width: number,
  height: number
): ImageData {
  const output = context.createImageData(width, height);
  for (let row = 0; row < height; row += 1) {
    const sourceStart = ((y + row) * source.width + x) * 4;
    const sourceEnd = sourceStart + width * 4;
    output.data.set(source.data.subarray(sourceStart, sourceEnd), row * width * 4);
  }
  return output;
}

function undo() {
  const patch = undoStack.value.pop();
  if (!patch) return;
  if (patch.kind === 'erase') {
    editSourceCanvas?.getContext('2d')?.putImageData(patch.before, patch.x, patch.y);
  } else {
    currentGenerationLayout.value = patch.beforeLayout;
    syncGuidesFromLayout();
  }
  renderFromSource();
  redoStack.value.push(patch);
}

function redo() {
  const patch = redoStack.value.pop();
  if (!patch) return;
  if (patch.kind === 'erase') {
    editSourceCanvas?.getContext('2d')?.putImageData(patch.after, patch.x, patch.y);
  } else {
    currentGenerationLayout.value = patch.afterLayout;
    syncGuidesFromLayout();
  }
  renderFromSource();
  undoStack.value.push(patch);
}

function syncGuidesFromLayout() {
  const layout = currentGenerationLayout.value;
  if (!layout) {
    resizeTop.value = sourceResizeTop.value;
    resizeBottom.value = sourceResizeBottom.value;
    resizeTargetRatio.value = null;
    resizeBottomMarginRatio.value = null;
    return;
  }
  const targetBottom = imageHeight.value - layout.bottom_distance;
  sourceResizeTop.value = layout.measured_top;
  sourceResizeBottom.value = layout.measured_bottom;
  resizeTop.value = targetBottom - layout.target_height;
  resizeBottom.value = targetBottom;
  resizeTargetRatio.value = layout.character_height_ratio * 100;
  resizeBottomMarginRatio.value = layout.bottom_margin_ratio * 100;
}

function onKeydown(event: KeyboardEvent) {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'z') {
    event.preventDefault();
    if (event.shiftKey) redo(); else undo();
  } else if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'y') {
    event.preventDefault();
    redo();
  } else if (event.key === 'Escape' && !props.saving) {
    emit('cancel');
  }
}

function onPointerLeave() {
  if (!drawing.value) showCursor.value = false;
}

function apply() {
  const canvas = canvasRef.value;
  if (!canvas || !editSourceCanvas || undoStack.value.length === 0) return;
  emit(
    'apply',
    canvas.toDataURL('image/png'),
    editSourceCanvas.toDataURL('image/png'),
    currentGenerationLayout.value
  );
}
</script>
