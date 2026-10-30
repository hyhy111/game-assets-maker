<template>
  <div
    :class="embedded ? 'absolute inset-0' : 'fixed inset-0 z-50 flex flex-col bg-black/90 p-4'"
    :role="embedded ? 'group' : 'dialog'"
    :aria-modal="embedded ? undefined : true"
    :aria-label="title || t('seedream.detail.eraserTitle')"
    data-test="seedream-eraser-editor"
  >
    <Teleport :to="toolbarTarget || 'body'" :disabled="!embedded">
    <div :class="embedded ? 'flex h-11 items-center gap-2 px-3' : 'mx-auto flex w-full max-w-6xl flex-wrap items-center gap-3 rounded-xl border border-dark-border bg-dark-surface p-3'">
      <h2 class="mr-auto min-w-0 truncate text-sm font-semibold text-white">{{ title || t('seedream.detail.eraserTitle') }}</h2>
      <div v-if="!magicWandEnabled" class="flex items-center gap-2 text-sm text-gray-300">
        <span>{{ t('seedream.detail.backgroundColor') }}</span>
        <span class="h-5 w-5 rounded border border-white/30" :style="{ backgroundColor: backgroundCss }" />
        <span class="font-mono text-xs">{{ backgroundCss }}</span>
      </div>
      <Button
        variant="secondary"
        size="sm"
        :disabled="saving || loading || undoStack.length === 0"
        data-test="seedream-eraser-undo"
        @click="undo"
      >
        <Undo2 :size="16" /> {{ t('common.undo') }}
      </Button>
      <Button
        variant="secondary"
        size="sm"
        :disabled="saving || loading || redoStack.length === 0"
        data-test="seedream-eraser-redo"
        @click="redo"
      >
        <Redo2 :size="16" /> {{ t('common.redo') }}
      </Button>
      <span v-if="!embedded" class="min-w-14 text-center text-sm text-gray-400" data-test="seedream-eraser-zoom">
        {{ Math.round(zoom * 100) }}%
      </span>
      <Button variant="secondary" size="sm" :disabled="saving" @click="emit('cancel')">
        {{ t('common.cancel') }}
      </Button>
      <button
        v-if="resizeEnabled"
        type="button"
        class="inline-flex h-8 items-center justify-center rounded-lg bg-success px-3 text-sm font-medium text-white transition-colors hover:bg-success/80 disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="saving || loading || (!dirty && !externalRestoreAvailable)"
        data-test="image-editor-restore-original"
        @click="restoreOriginal"
      >
        {{ t('seedream.detail.restoreOriginal') }}
      </button>
      <Button
        variant="primary"
        size="sm"
        :loading="saving"
        :disabled="saving || loading || !dirty"
        data-test="seedream-eraser-apply"
        @click="apply"
      >
        {{ magicWandEnabled ? t('magicWand.save') : t('seedream.detail.applyEraser') }}
      </Button>
    </div>

    <fieldset v-if="embedded" :disabled="saving || loading || suspended"
      class="flex h-20 min-w-0 items-center gap-4 overflow-x-auto border-t border-dark-border px-3" data-test="frame-tool-options">
      <template v-if="tool === 'wand'">
        <Slider v-model="wandTolerance" class="w-36 shrink-0" :min="0" :max="100" :step="1" :label="`${t('magicWand.tolerance')} (+/-)`" :value-formatter="v => `${v}%`" />
        <Slider v-model="wandFeather" class="w-36 shrink-0" :min="0" :max="12" :step="1" :label="t('magicWand.feather')" :value-formatter="v => `${v}px`" />
        <label class="flex shrink-0 items-center gap-2 text-xs text-gray-300"><input v-model="wandContiguous" type="checkbox" />{{ t('magicWand.contiguous') }}</label>
        <span class="shrink-0 text-xs text-gray-400">{{ t('magicWand.selected', { count: selectedCount }) }}</span>
        <Button variant="danger" size="sm" :disabled="!selectedCount" @click="deleteWandSelection">{{ t('magicWand.delete') }}</Button>
        <Button variant="secondary" size="sm" :disabled="!selectedCount" @click="clearWandSelection">{{ t('magicWand.clear') }}</Button>
      </template>
      <template v-else-if="tool === 'brush'">
        <Slider v-model="brushSize" class="w-56 shrink-0" :min="1" :max="200" :step="1" :label="magicWandEnabled ? `${t('seedream.detail.eraserSize')} (+/-)` : t('seedream.detail.eraserSize')" :value-formatter="v => `${v}px`" data-test="frame-eraser-size" />
        <Slider v-model="brushFeather" class="w-36 shrink-0" :min="0" :max="12" :step="1" :label="t('magicWand.feather')" :value-formatter="v => `${v}px`" data-test="frame-eraser-feather" />
      </template>
      <span v-else class="text-xs text-gray-400">{{ t('magicWand.browseHint') }}</span>
    </fieldset>
    </Teleport>

    <div :class="embedded ? 'h-full' : 'mx-auto mt-3 grid w-full max-w-6xl gap-3 lg:grid-cols-[220px_minmax(0,1fr)]'">
      <aside v-if="!embedded" class="rounded-xl border border-dark-border bg-dark-surface p-4">
        <p
          v-if="imageWidth > 0 && imageHeight > 0"
          class="mb-4 text-xs text-gray-500"
          data-test="image-editor-original-resolution"
        >
          {{ t('seedream.detail.originalResolution') }}：{{ imageWidth }} × {{ imageHeight }} px
        </p>
        <div v-if="magicWandEnabled" class="mb-4 space-y-3">
          <div class="flex gap-2">
            <Button size="sm" :variant="tool === 'wand' ? 'primary' : 'secondary'" data-test="magic-wand-tool" @click="tool = 'wand'">{{ t('magicWand.wand') }}</Button>
            <Button size="sm" :variant="tool === 'brush' ? 'primary' : 'secondary'" @click="tool = 'brush'">{{ t('magicWand.eraser') }}</Button>
          </div>
          <p class="text-xs leading-5 text-gray-400">{{ t('magicWand.hint') }}</p>
          <template v-if="tool === 'wand'">
            <Slider v-model="wandTolerance" :min="0" :max="100" :step="1" :label="`${t('magicWand.tolerance')} (+/-)`" :value-formatter="(v) => `${v}%`" data-test="magic-wand-tolerance" />
            <Slider v-model="wandFeather" :min="0" :max="12" :step="1" :label="t('magicWand.feather')" :value-formatter="(v) => `${v}px`" data-test="magic-wand-feather" />
            <label class="flex gap-2 text-sm text-gray-300"><input v-model="wandContiguous" type="checkbox" data-test="magic-wand-contiguous" />{{ t('magicWand.contiguous') }}</label>
            <p class="text-xs text-gray-400">{{ t('magicWand.selected', { count: selectedCount }) }}</p>
            <Button class="w-full" variant="danger" size="sm" :disabled="!selectedCount || saving || loading" data-test="magic-wand-delete" @click="deleteWandSelection">{{ t('magicWand.delete') }}</Button>
            <Button class="w-full" variant="secondary" size="sm" :disabled="!selectedCount" @click="clearWandSelection">{{ t('magicWand.clear') }}</Button>
          </template>
          <label class="block text-xs text-gray-400">{{ t('magicWand.preview') }}
            <select v-model="previewBackground" class="mt-1 w-full rounded border border-dark-border bg-dark-bg p-2 text-white">
              <option value="checker">{{ t('magicWand.checker') }}</option>
              <option value="white">{{ t('magicWand.white') }}</option>
              <option value="dark">{{ t('magicWand.dark') }}</option>
            </select>
          </label>
        </div>
        <Slider
          v-if="!magicWandEnabled || tool === 'brush'"
          v-model="brushSize"
          :min="1"
          :max="200"
          :step="1"
          :label="magicWandEnabled ? `${t('seedream.detail.eraserSize')} (+/-)` : t('seedream.detail.eraserSize')"
          :value-formatter="(value) => `${value}px`"
          data-test="seedream-eraser-size"
        />
        <Slider
          v-if="magicWandEnabled && tool === 'brush'"
          v-model="brushFeather"
          class="mt-3"
          :min="0" :max="12" :step="1"
          :label="t('magicWand.feather')"
          :value-formatter="v => `${v}px`"
          data-test="seedream-eraser-feather"
        />
        <div v-if="resizeEnabled" class="mt-5 border-t border-dark-border pt-4">
          <div class="space-y-3" data-test="image-editor-resize-controls">
            <label class="block text-xs text-gray-300">
              {{ t('seedream.detail.targetHeight') }}
              <input
                :value="resizeTargetRatio"
                type="number"
                min="1"
                :max="100"
                step="1"
                class="mt-1 w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-white"
                data-test="image-editor-target-height-ratio"
                @input="updateResizeRatio($event, 'height')"
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
                :value="resizeBottomMarginRatio"
                type="number"
                min="0"
                :max="Math.max(0, 100 - (resizeTargetRatio ?? 0))"
                step="1"
                class="mt-1 w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-white"
                data-test="image-editor-bottom-distance-ratio"
                @input="updateResizeRatio($event, 'margin')"
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
        :class="[embedded ? 'relative h-full overflow-hidden' : 'relative flex min-h-0 items-center justify-center overflow-hidden rounded-xl border border-dark-border bg-dark-bg p-3', { 'cursor-grabbing': panning }]"
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
          :class="[embedded ? 'absolute left-1/2 top-1/2' : 'relative max-h-[calc(100vh-9rem)] max-w-full', { invisible: loading }]"
          :style="canvasTransformStyle"
        >
          <canvas
            ref="canvasRef"
            :tabindex="magicWandEnabled ? 0 : undefined"
            class="block touch-none focus:outline-none"
            :class="[embedded ? 'max-w-none' : 'max-h-[calc(100vh-9rem)] max-w-full rounded-lg', tool === 'browse' ? 'cursor-grab' : magicWandEnabled && tool === 'wand' ? 'cursor-crosshair' : 'cursor-none']"
            data-test="seedream-eraser-canvas"
            @pointerdown="startStroke"
            @pointermove="moveStroke"
            @pointerup="finishStroke"
            @pointercancel="finishStroke"
            @pointerenter="showCursor = true"
            @pointerleave="onPointerLeave"
          />
          <canvas v-if="magicWandEnabled" ref="selectionCanvasRef" class="pointer-events-none absolute inset-0 h-full w-full" data-test="magic-wand-selection" />
          <svg
            v-if="magicWandEnabled && selectionOutlinePath"
            class="pointer-events-none absolute inset-0 h-full w-full overflow-visible"
            :viewBox="`0 0 ${imageWidth} ${imageHeight}`"
            aria-hidden="true"
            data-test="magic-wand-outline"
          >
            <path
              v-for="(color, index) in ['#111', '#fff']"
              :key="color"
              :d="selectionOutlinePath"
              fill="none"
              :stroke="color"
              :stroke-width="1.5 / selectionOutlineScale"
              :stroke-dasharray="`${4 / selectionOutlineScale} ${4 / selectionOutlineScale}`"
              :stroke-dashoffset="index * 4 / selectionOutlineScale"
              vector-effect="non-scaling-stroke"
            />
          </svg>
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
        <p v-if="embedded" class="pointer-events-none absolute bottom-4 left-4 right-20 z-10 w-fit max-w-[calc(100%-6rem)] rounded-lg bg-black/50 px-3 py-2 text-xs leading-5 text-gray-200" data-test="frame-tool-hint">
          {{ t(tool === 'wand' ? 'magicWand.wandHint' : tool === 'brush' ? 'magicWand.eraserHint' : 'magicWand.browseHint') }}
        </p>
        <p v-if="embedded && (error || loadError)" class="absolute left-4 right-20 top-16 rounded bg-black/80 p-3 text-sm text-danger" role="alert">{{ error || loadError }}</p>
        <div v-if="embedded && (saving || suspended)" class="absolute inset-0 z-10 cursor-wait" />
        <div
          v-if="showCursor && !panning && (!magicWandEnabled || tool === 'brush')"
          class="pointer-events-none absolute rounded-full border border-white shadow-[0_0_0_1px_rgba(0,0,0,0.8)]"
          :style="cursorStyle"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { Redo2, Undo2 } from 'lucide-vue-next';
import { useI18n } from 'vue-i18n';
import Button from '@/components/common/Button.vue';
import Slider from '@/components/common/Slider.vue';
import type { GenerationLayout } from '@/types';
import { deleteSelection, eraseBrushSegment, selectColorRegion, selectionBounds, selectionOutline } from '@/utils/magic-wand';

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
  embedded?: boolean;
  toolbarTarget?: HTMLElement | null;
  activeTool?: 'wand' | 'brush' | 'browse';
  viewZoom?: number;
  viewPanX?: number;
  viewPanY?: number;
  suspended?: boolean;
  editSourceUrl?: string;
  saving: boolean;
  error?: string;
  title?: string;
  resizeEnabled?: boolean;
  magicWandEnabled?: boolean;
  externalRestoreAvailable?: boolean;
  generationLayout?: GenerationLayout | null;
}>(), {
  embedded: false,
  toolbarTarget: null,
  viewZoom: 1,
  viewPanX: 0,
  viewPanY: 0,
  suspended: false,
  error: '',
  editSourceUrl: '',
  title: '',
  resizeEnabled: false,
  magicWandEnabled: false,
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
const selectionCanvasRef = ref<HTMLCanvasElement | null>(null);
const tool = ref<'wand' | 'brush' | 'browse'>(props.magicWandEnabled ? 'wand' : 'brush');
watch(() => props.activeTool, value => { if (value) tool.value = value; }, { immediate: true });
const wandTolerance = ref(20);
const wandFeather = ref(1);
const wandContiguous = ref(true);
const previewBackground = ref('checker');
const selection = ref<Uint8Array>(new Uint8Array(0));
const selectionOutlinePath = ref('');
let wandSeeds: Point[] = [];
const selectedCount = computed(() => selection.value.reduce((sum, value) => sum + value, 0));
watch([wandTolerance, wandContiguous], () => updateWandSelection());
watch(tool, () => clearWandSelection());
const loading = ref(true);
const loadError = ref('');
const brushSize = ref(5);
const brushFeather = ref(0);
const backgroundColor = ref<[number, number, number]>([0, 0, 0]);
const undoStack = ref<HistoryPatch[]>([]);
const redoStack = ref<HistoryPatch[]>([]);
const historyTruncated = ref(false);
const dirty = computed(() => historyTruncated.value || undoStack.value.length > 0);
const drawing = ref(false);
const showCursor = ref(false);
const cursorX = ref(0);
const cursorY = ref(0);
const cursorDiameter = ref(0);
const zoom = ref(1);
// CSS zoom on the canvas wrapper also scales SVG strokes and dash lengths.
const selectionOutlineScale = computed(() => props.embedded ? props.viewZoom : zoom.value);
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
let strokeAfter: ImageData | null = null;
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
const canvasTransformStyle = computed(() => props.embedded ? {
  width: `${imageWidth.value}px`, height: `${imageHeight.value}px`,
  transform: `translate(-50%, -50%) translate(${props.viewPanX}px, ${props.viewPanY}px) scale(${props.viewZoom})`,
} : ({
  transform: `translate(${panX.value}px, ${panY.value}px) scale(${zoom.value})`,
  transformOrigin: 'center center',
  ...(props.magicWandEnabled ? {
    backgroundColor: previewBackground.value === 'white' ? '#fff' : '#25282c',
    backgroundImage: previewBackground.value === 'checker'
      ? 'conic-gradient(#41464d 25%, #292d32 0 50%, #41464d 0 75%, #292d32 0)' : 'none',
    backgroundSize: '20px 20px',
  } : {}),
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
    ? Math.min(
      Math.round(imageHeight.value * resizeBottomMarginRatio.value / 100),
      imageHeight.value - targetHeightPixels.value
    )
    : 0
));
const canApplyResize = computed(() => (
  Number.isInteger(resizeTargetRatio.value)
  && typeof resizeTargetRatio.value === 'number'
  && resizeTargetRatio.value > 0
  && resizeTargetRatio.value <= 100
  && Number.isInteger(resizeBottomMarginRatio.value)
  && typeof resizeBottomMarginRatio.value === 'number'
  && resizeBottomMarginRatio.value >= 0
  && resizeBottomMarginRatio.value <= 100
  && resizeTargetRatio.value + resizeBottomMarginRatio.value <= 100
  && targetHeightPixels.value > 0
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

function normalizeResizeRatios(height: number | null, margin: number | null) {
  resizeTargetRatio.value = typeof height === 'number' && Number.isFinite(height)
    ? Math.min(100, Math.max(1, Math.round(height)))
    : null;
  resizeBottomMarginRatio.value = typeof margin === 'number' && Number.isFinite(margin)
    ? Math.min(100 - (resizeTargetRatio.value ?? 0), Math.max(0, Math.round(margin)))
    : null;
}

function updateResizeRatio(event: Event, field: 'height' | 'margin') {
  const input = event.target as HTMLInputElement;
  const value = input.valueAsNumber;
  normalizeResizeRatios(
    field === 'height' ? value : resizeTargetRatio.value,
    field === 'margin' ? value : resizeBottomMarginRatio.value
  );
  // Keep the DOM normalized even when rounding leaves the reactive value unchanged.
  input.value = String((field === 'height' ? resizeTargetRatio.value : resizeBottomMarginRatio.value) ?? '');
}

function resetResizeGuides() {
  const height = imageHeight.value;
  const saved = props.generationLayout;
  if (saved && saved.source_height === height) {
    sourceResizeTop.value = saved.measured_top;
    sourceResizeBottom.value = saved.measured_bottom;
    resizeTop.value = height - saved.bottom_distance - saved.target_height;
    resizeBottom.value = height - saved.bottom_distance;
    normalizeResizeRatios(saved.character_height_ratio * 100, saved.bottom_margin_ratio * 100);
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
  if (undoStack.value.length > HISTORY_LIMIT) { undoStack.value.shift(); historyTruncated.value = true; }
  redoStack.value = [];
  resizeTop.value = Math.max(0, targetBottom - targetHeight);
  resizeBottom.value = targetBottom;
  normalizeResizeRatios(targetHeight / canvas.height * 100, bottomDistance / canvas.height * 100);
  resizeError.value = '';
}

function restoreOriginal() {
  if (props.externalRestoreAvailable) {
    emit('restore');
    return;
  }
  const canvas = canvasRef.value;
  const sourceContext = editSourceCanvas?.getContext('2d');
  if (!canvas || !sourceContext || !originalImageData || !dirty.value) return;
  sourceContext.putImageData(originalImageData, 0, 0);
  undoStack.value = [];
  redoStack.value = [];
  historyTruncated.value = false;
  strokeBefore = null;
  strokeAfter = null;
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
  if (props.embedded || !viewport || loading.value || drawing.value) return;
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
  if (props.embedded || event.button !== 1) return;
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
  if (tool.value === 'browse' || event.button !== 0 || props.saving || props.suspended || loading.value) return;
  if (props.magicWandEnabled) canvasRef.value?.focus({ preventScroll: true });
  if (props.magicWandEnabled && tool.value === 'wand') {
    const point = canvasPoint(event);
    if (!point) return;
    if (!event.shiftKey) wandSeeds = [];
    wandSeeds.push(point);
    updateWandSelection();
    event.preventDefault();
    return;
  }
  const canvas = canvasRef.value;
  const sourceContext = editSourceCanvas?.getContext('2d', { willReadFrequently: true });
  const displayPoint = canvasPoint(event);
  if (!canvas || !sourceContext || !displayPoint) return;
  canvas.setPointerCapture(event.pointerId);
  drawing.value = true;
  showCursor.value = true;
  strokeBefore = sourceContext.getImageData(0, 0, canvas.width, canvas.height);
  if (props.magicWandEnabled) {
    strokeAfter = sourceContext.createImageData(strokeBefore.width, strokeBefore.height);
    strokeAfter.data.set(strokeBefore.data);
  }
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
    strokeAfter = null;
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
    if (undoStack.value.length > HISTORY_LIMIT) { undoStack.value.shift(); historyTruncated.value = true; }
    redoStack.value = [];
  }
  strokeBefore = null;
  strokeAfter = null;
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
  if (props.magicWandEnabled) {
    drawLine(context, point, point, sourceBrushSize);
    return;
  }
  context.fillStyle = backgroundCss.value;
  context.beginPath();
  context.arc(point.x, point.y, sourceBrushSize / 2, 0, Math.PI * 2);
  if (props.magicWandEnabled) context.globalCompositeOperation = 'destination-out';
  context.fill();
  context.globalCompositeOperation = 'source-over';
}

function drawLine(context: CanvasRenderingContext2D, from: Point, to: Point, sourceBrushSize: number) {
  if (props.magicWandEnabled && strokeBefore && strokeAfter) {
    const feather = brushFeather.value / (currentGenerationLayout.value?.scale ?? 1);
    const bounds = eraseBrushSegment(strokeAfter, strokeBefore, from, to, sourceBrushSize, feather);
    context.putImageData(strokeAfter, 0, 0, bounds.x, bounds.y, bounds.width, bounds.height);
    return;
  }
  context.strokeStyle = backgroundCss.value;
  context.lineWidth = sourceBrushSize;
  context.lineCap = 'round';
  context.lineJoin = 'round';
  context.beginPath();
  context.moveTo(from.x, from.y);
  context.lineTo(to.x, to.y);
  if (props.magicWandEnabled) context.globalCompositeOperation = 'destination-out';
  context.stroke();
  context.globalCompositeOperation = 'source-over';
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
  if (props.saving || loading.value) return;
  clearWandSelection();
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
  if (props.saving || loading.value) return;
  clearWandSelection();
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
  normalizeResizeRatios(layout.character_height_ratio * 100, layout.bottom_margin_ratio * 100);
}

function onKeydown(event: KeyboardEvent) {
  if (props.saving || props.suspended || loading.value || event.defaultPrevented) return;
  if (event.target instanceof Element && event.target.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="textbox"]')) return;
  if (props.magicWandEnabled && !event.ctrlKey && !event.metaKey && !event.altKey
    && !event.isComposing && !drawing.value && tool.value !== 'browse') {
    const delta = event.key === '+' || event.key === '=' ? 1 : event.key === '-' || event.key === '_' ? -1 : 0;
    if (delta) {
      event.preventDefault();
      if (tool.value === 'wand') wandTolerance.value = Math.max(0, Math.min(100, wandTolerance.value + delta));
      else brushSize.value = Math.max(1, Math.min(200, brushSize.value + delta));
      return;
    }
  }
  if (props.magicWandEnabled && (event.key === 'Delete' || event.key === 'Backspace')) {
    event.preventDefault();
    deleteWandSelection();
    return;
  }
  if (event.key === 'Escape' && selectedCount.value) {
    event.preventDefault();
    clearWandSelection();
    return;
  }
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

function clearWandSelection() {
  wandSeeds = [];
  selection.value = new Uint8Array(0);
  selectionOutlinePath.value = '';
  const canvas = selectionCanvasRef.value;
  if (canvas) canvas.getContext('2d')?.clearRect(0, 0, canvas.width, canvas.height);
}

function updateWandSelection() {
  const source = editSourceCanvas;
  const context = source?.getContext('2d', { willReadFrequently: true });
  const overlay = selectionCanvasRef.value;
  if (!source || !context || !overlay || !wandSeeds.length) return;
  const pixels = context.getImageData(0, 0, source.width, source.height);
  const mask = new Uint8Array(source.width * source.height);
  for (const point of wandSeeds) {
    const added = selectColorRegion(pixels, point.x, point.y, wandTolerance.value, wandContiguous.value);
    for (let index = 0; index < mask.length; index++) if (added[index]) mask[index] = 1;
  }
  selection.value = mask;
  selectionOutlinePath.value = selectionOutline(mask, source.width, source.height);
  overlay.width = source.width;
  overlay.height = source.height;
  const overlayContext = overlay.getContext('2d');
  if (!overlayContext) return;
  const tint = overlayContext.createImageData(source.width, source.height);
  for (let index = 0; index < mask.length; index++) {
    if (!mask[index]) continue;
    tint.data.set([190, 95, 255, 115], index * 4);
  }
  overlayContext.putImageData(tint, 0, 0);
}

function deleteWandSelection() {
  const source = editSourceCanvas;
  const context = source?.getContext('2d', { willReadFrequently: true });
  if (!source || !context || !selectedCount.value || props.saving) return;
  const before = context.getImageData(0, 0, source.width, source.height);
  const bounds = selectionBounds(selection.value, source.width, source.height);
  if (!bounds) return;
  const pixels = deleteSelection(before, selection.value, wandFeather.value);
  const after = context.createImageData(source.width, source.height);
  after.data.set(pixels);
  context.putImageData(after, 0, 0);
  undoStack.value.push({
    kind: 'erase', x: bounds.x, y: bounds.y,
    before: cropImageData(context, before, bounds.x, bounds.y, bounds.width, bounds.height),
    after: context.getImageData(bounds.x, bounds.y, bounds.width, bounds.height),
  });
  if (undoStack.value.length > HISTORY_LIMIT) { undoStack.value.shift(); historyTruncated.value = true; }
  redoStack.value = [];
  clearWandSelection();
  renderFromSource();
}

function markSaved() {
  undoStack.value = [];
  redoStack.value = [];
  historyTruncated.value = false;
  clearWandSelection();
}

function getImageData() {
  return canvasRef.value?.toDataURL('image/png');
}

defineExpose({ dirty, busy: computed(() => loading.value || drawing.value), markSaved, getImageData });

function apply() {
  const canvas = canvasRef.value;
  if (!canvas || !editSourceCanvas || !dirty.value) return;
  emit(
    'apply',
    canvas.toDataURL('image/png'),
    editSourceCanvas.toDataURL('image/png'),
    currentGenerationLayout.value
  );
}
</script>
