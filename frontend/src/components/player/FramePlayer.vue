<template>
  <div
    ref="containerRef"
    class="relative w-full h-full rounded-lg overflow-hidden select-none"
    :style="{ backgroundColor: canvasBgColorValue }"
    @wheel="handleWheel"
    @mousedown="handleMouseDown"
    @mousemove="handleMouseMove"
    @mouseup="handleMouseUp"
    @mouseleave="handleMouseUp"
  >
    <!-- Canvas for frame display -->
    <canvas
      ref="canvasRef"
      class="absolute top-1/2 left-1/2 max-w-none max-h-none"
      :style="canvasStyle"
      @dragstart.prevent
    />

    <!-- Info overlay -->
    <div class="absolute top-4 left-4 px-3 py-1.5 bg-black/60 rounded-lg text-xs text-gray-300">
      <span>{{ currentIndex }} / {{ endFrame }}</span>
      <span class="mx-2">|</span>
      <span>{{ Math.round(zoom * 100) }}%</span>
    </div>

    <!-- Zoom controls (floating) -->
    <div class="absolute bottom-4 right-4 flex flex-col gap-2">
      <Button
        v-for="control in zoomControls"
        :key="control.action"
        variant="ghost"
        size="sm"
        class="bg-black/60 hover:bg-black/80 backdrop-blur-sm"
        @click="control.handler"
      >
        <component
          :is="control.icon"
          class="w-5 h-5"
        />
      </Button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import { storeToRefs } from 'pinia';
import { ZoomIn, ZoomOut, Maximize, Move } from 'lucide-vue-next';
import { usePlayerStore } from '@/stores/player';
import { api } from '@/api';
import Button from '../common/Button.vue';

const playerStore = usePlayerStore();
const { currentFrame, zoom, panX, panY, currentIndex, startFrame, endFrame, currentImage, isPlaying, canvasBgColorValue } = storeToRefs(playerStore);

// Refs
const containerRef = ref<HTMLDivElement>();
const canvasRef = ref<HTMLCanvasElement>();
const isDragging = ref(false);
const dragStart = ref({ x: 0, y: 0 });
const panStart = ref({ x: 0, y: 0 });

// Arrow key repeat for continuous frame stepping
let arrowRepeatTimer: ReturnType<typeof setInterval> | null = null;
let heldArrowKey: string | null = null;

// Canvas style for zoom and pan
const canvasStyle = computed(() => ({
  transform: `translate(-50%, -50%) translate(${panX.value}px, ${panY.value}px) scale(${zoom.value})`,
  imageRendering: 'auto' as const
}));

// Zoom controls
const zoomControls = [
  { action: 'zoomIn', icon: ZoomIn, handler: () => playerStore.zoomIn() },
  { action: 'zoomOut', icon: ZoomOut, handler: () => playerStore.zoomOut() },
  { action: 'reset', icon: Maximize, handler: () => playerStore.resetView() },
  { action: 'pan', icon: Move, handler: () => { /* Pan mode indicator */ } }
];

function drawCachedImage(img: HTMLImageElement) {
  const canvas = canvasRef.value;
  const ctx = canvas?.getContext('2d');
  if (!canvas || !ctx) return;
  if (canvas.width !== img.width) canvas.width = img.width;
  if (canvas.height !== img.height) canvas.height = img.height;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(img, 0, 0);
}

// Load and render frame
async function renderFrame() {
  if (!canvasRef.value) return;
  const canvas = canvasRef.value;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  // If currentImage is set (preview mode), render it
  if (playerStore.currentImage) {
    renderBase64Image(playerStore.currentImage);
    return;
  }

  if (!currentFrame.value) return;
  const framePath = currentFrame.value.path;

  // Fast path: already loaded and cached image element
  const cachedImg = playerStore.imageElementCache.get(framePath);
  if (cachedImg && cachedImg.complete && cachedImg.naturalWidth > 0) {
    drawCachedImage(cachedImg);
    return;
  }

  // Always load the current frame regardless of background preload state.
  // If preload got there first, we load it again to ensure onload triggers canvas draw.
  if (currentFrame.value.url) {
    playerStore.loadingPaths.add(framePath);
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      playerStore.imageElementCache.set(framePath, img);
      playerStore.loadingPaths.delete(framePath);
      // Only draw if this frame is still the current one
      if (currentFrame.value?.path === framePath) {
        drawCachedImage(img);
      }
    };
    img.onerror = () => {
      playerStore.loadingPaths.delete(framePath);
      loadFrameViaBase64();
    };
    img.src = currentFrame.value.url;
  }
}

// Preload surrounding frames so manual stepping is smooth
async function preloadNearbyFrames(centerIndex: number, radius: number) {
  const { frames, frameInterval } = playerStore;
  if (!frames.length) return;
  const nearby = [];
  for (let offset = 1; offset <= radius; offset++) {
    const idx = centerIndex + offset * frameInterval;
    if (idx < 0 || idx >= frames.length) continue;
    const frame = frames[idx];
    if (frame) nearby.push(frame);
  }
  if (nearby.length > 0) {
    playerStore.preloadFrames(nearby, 3);
  }
}

// Fallback: Load frame via base64
async function loadFrameViaBase64() {
  if (!currentFrame.value || !canvasRef.value) return;

  const canvas = canvasRef.value;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  const framePath = currentFrame.value.path;

  try {
    const imageData = await api.frame.getFrameImage(framePath);
    renderBase64Image(imageData, framePath);
  } catch (e) {
    console.error('Failed to load frame via base64:', e);
  }
}

// Render base64 image data
function renderBase64Image(base64Data: string, intendedPath?: string) {
  if (!canvasRef.value) return;

  const canvas = canvasRef.value;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  const img = new Image();
  img.onload = () => {
    if (intendedPath && currentFrame.value?.path !== intendedPath) return;
    if (canvas.width !== img.width) canvas.width = img.width;
    if (canvas.height !== img.height) canvas.height = img.height;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0);
  };
  img.onerror = () => {
    if (intendedPath && currentFrame.value?.path !== intendedPath) return;
    console.error('Failed to render base64 image');
  };
  // Ensure proper data URI format
  if (base64Data.startsWith('data:')) {
    img.src = base64Data;
  } else {
    img.src = `data:image/png;base64,${base64Data}`;
  }
}

// Watch for frame changes
watch(
  currentFrame,
  () => {
    renderFrame();
    preloadNearbyFrames(currentIndex.value, 5);
  },
  { immediate: true }
);

// Watch for currentImage changes (preview mode)
watch(currentImage, (newImage) => {
  if (newImage) {
    renderFrame();
  }
}, { immediate: true });

// Watch for playback start to aggressively preload upcoming frames
watch(isPlaying, (playing) => {
  if (playing) {
    const range = playerStore.frames.slice(startFrame.value, endFrame.value + 1);
    playerStore.preloadFrames(range, 3);
  }
});

// Mouse wheel zoom
function handleWheel(e: WheelEvent) {
  e.preventDefault();
  const delta = e.deltaY > 0 ? 0.9 : 1.1;
  playerStore.setZoom(zoom.value * delta);
}

// Drag panning
function handleMouseDown(e: MouseEvent) {
  // Left button or middle button
  if (e.button === 0 || e.button === 1) {
    isDragging.value = true;
    dragStart.value = { x: e.clientX, y: e.clientY };
    panStart.value = { x: panX.value, y: panY.value };
    playerStore.setDragging(true);
    e.preventDefault();
  }
}

function handleMouseMove(e: MouseEvent) {
  if (!isDragging.value) return;

  const dx = e.clientX - dragStart.value.x;
  const dy = e.clientY - dragStart.value.y;

  playerStore.setPan(panStart.value.x + dx, panStart.value.y + dy);
}

function handleMouseUp() {
  isDragging.value = false;
  playerStore.setDragging(false);
}

// Keyboard shortcuts
function startArrowRepeat(key: string) {
  if (arrowRepeatTimer) {
    clearInterval(arrowRepeatTimer);
  }
  heldArrowKey = key;
  arrowRepeatTimer = setInterval(() => {
    if (key === 'ArrowRight') {
      playerStore.nextFrame();
    } else if (key === 'ArrowLeft') {
      playerStore.prevFrame();
    }
  }, 180);
}

function stopArrowRepeat() {
  if (arrowRepeatTimer) {
    clearInterval(arrowRepeatTimer);
    arrowRepeatTimer = null;
  }
  heldArrowKey = null;
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === ' ' && !e.repeat) {
    e.preventDefault();
    playerStore.togglePlay();
  } else if (e.key === 'ArrowRight') {
    e.preventDefault();
    if (heldArrowKey !== 'ArrowRight') {
      playerStore.nextFrame();
      startArrowRepeat('ArrowRight');
    }
  } else if (e.key === 'ArrowLeft') {
    e.preventDefault();
    if (heldArrowKey !== 'ArrowLeft') {
      playerStore.prevFrame();
      startArrowRepeat('ArrowLeft');
    }
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    playerStore.zoomIn();
  } else if (e.key === 'ArrowDown') {
    e.preventDefault();
    playerStore.zoomOut();
  } else if (e.key === '0' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault();
    playerStore.resetView();
  }
}

function handleKeyup(e: KeyboardEvent) {
  if ((e.key === 'ArrowRight' || e.key === 'ArrowLeft') && heldArrowKey === e.key) {
    stopArrowRepeat();
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown);
  document.addEventListener('keyup', handleKeyup);
  // Ensure we render the first frame once mounted
  setTimeout(() => {
    renderFrame();
  }, 100);
});

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown);
  document.removeEventListener('keyup', handleKeyup);
  stopArrowRepeat();
});
</script>
