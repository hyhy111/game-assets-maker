/**
 * Player Store - Manages frame player state
 */
import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { useProcessStore } from './process';
import { api } from '@/api';
import type { Frame } from '@/types';

export const usePlayerStore = defineStore('player', () => {
  // State
  const frames = ref<Frame[]>([]);
  const currentIndex = ref(0);
  const isPlaying = ref(false);
  const zoom = ref(1);
  const panX = ref(0);
  const panY = ref(0);
  const useNearest = ref(true); // true = NEAREST (pixel), false = LANCZOS (smooth)
  const isDragging = ref(false);
  const currentImage = ref<string>('');

  // Canvas background color for transparent image preview
  const canvasBgColor = ref<string>('gray'); // gray, green, magenta, white
  const canvasBgColors: Record<string, string> = {
    gray: '#808080',
    green: '#00FF00',
    magenta: '#FF00FF',
    white: '#FFFFFF',
    black: '#000000'
  };

  // Playback settings
  const playbackFps = ref(30);
  let rafId: number | null = null;
  let playStartTime = 0;
  let playStartIndex = 0;

  // 音画同步（票 04）：连续播放（tick）实际推进帧时的回调 hook。
  // 仅 tick() 调用；goToFrame/nextFrame/prevFrame 不触发，故 scrub/步进静音。
  // null = 未注册（默认），不影响既有播放行为。
  let onFrameAdvance: ((prevIndex: number, nextIndex: number) => void) | null = null;

  function setFrameAdvanceHook(fn: ((prevIndex: number, nextIndex: number) => void) | null): void {
    onFrameAdvance = fn;
  }

  // Playback range (from Step1)
  const startFrame = ref(0);
  const endFrame = ref(0);
  const frameInterval = ref(1);

  // Image cache for frame playback
  const imageElementCache = new Map<string, HTMLImageElement>();
  const loadingPaths = new Set<string>();

  // Getters
  const currentFrame = computed(() => frames.value[currentIndex.value]);
  const totalFrames = computed(() => frames.value.length);
  const progress = computed(() =>
    totalFrames.value > 0 ? (currentIndex.value / (totalFrames.value - 1)) * 100 : 0
  );

  // Within range navigation
  const canGoNext = computed(() => currentIndex.value + frameInterval.value <= endFrame.value && currentIndex.value + frameInterval.value < frames.value.length);
  const canGoPrev = computed(() => currentIndex.value - frameInterval.value >= startFrame.value && currentIndex.value - frameInterval.value >= 0);

  // Cache helpers
  async function preloadFrame(frame: Frame) {
    const path = frame.path;
    if (imageElementCache.has(path) || loadingPaths.has(path)) return;
    loadingPaths.add(path);
    try {
      const url = frame.url || await api.frame.getFrameUrl(path);
      const img = new Image();
      img.crossOrigin = 'anonymous';
      await new Promise<void>((resolve, reject) => {
        img.onload = () => resolve();
        img.onerror = () => reject();
        img.src = url;
      });
      imageElementCache.set(path, img);
    } catch {
      // ignore preload errors
    } finally {
      loadingPaths.delete(path);
    }
  }

  async function preloadFrames(framesToLoad: Frame[], concurrency = 3) {
    let idx = 0;
    const running = new Set<Promise<void>>();

    while (idx < framesToLoad.length || running.size > 0) {
      while (running.size < concurrency && idx < framesToLoad.length) {
        const frame = framesToLoad[idx++];
        if (imageElementCache.has(frame.path) || loadingPaths.has(frame.path)) continue;
        const task = preloadFrame(frame);
        running.add(task);
        task.then(() => running.delete(task));
      }
      if (running.size > 0) {
        await Promise.race(running);
      }
    }
  }

  function isFrameCached(path: string) {
    return imageElementCache.has(path);
  }

  // Actions
  function loadFrames(newFrames: Frame[]) {
    // Clear stale image cache to prevent displaying old frames after re-processing
    imageElementCache.clear();
    loadingPaths.clear();
    frames.value = newFrames;
    currentIndex.value = 0;
    currentImage.value = '';
    // Enter project and immediately preload first 12 frames in background
    if (newFrames.length > 0) {
      const silent = newFrames.slice(0, 12);
      preloadFrames(silent, 3);
    }
  }

  function tick() {
    if (!isPlaying.value) return;
    const elapsed = performance.now() - playStartTime;
    const stepDuration = 1000 / playbackFps.value;
    const baseStep = Math.floor((playStartIndex - startFrame.value) / frameInterval.value);
    const stepCount = baseStep + Math.floor(elapsed / stepDuration);
    const totalStepsInRange = Math.ceil((endFrame.value - startFrame.value + 1) / frameInterval.value);
    const loopedStep = totalStepsInRange > 0 ? stepCount % totalStepsInRange : 0;
    const targetIndex = startFrame.value + loopedStep * frameInterval.value;

    const targetPath = frames.value[targetIndex]?.path;
    if (targetPath && imageElementCache.has(targetPath)) {
      // Target frame is cached, so it is safe to advance.
      const prevIndex = currentIndex.value;
      currentIndex.value = targetIndex;
      // 音画同步 hook：仅在连续播放（tick）实际推进帧时触发。
      if (onFrameAdvance && targetIndex !== prevIndex) {
        onFrameAdvance(prevIndex, targetIndex);
      }
    } else if (targetIndex === currentIndex.value) {
      // Playback is already on the target frame.
    } else {
      // Target frame is not cached; consume a small time slice to avoid severe lag.
      playStartTime += stepDuration;
    }

    rafId = requestAnimationFrame(tick);
  }

  async function play() {
    if (isPlaying.value) return;
    // Hard guard: don't auto-play while any processing task is running
    const processStore = useProcessStore();
    if (processStore.isProcessing) return;
    // Discard any preview image so playback shows actual frames
    currentImage.value = '';

    // Urgent preload: ensure current frame and next 5 frames are cached before starting tick
    const urgent: Frame[] = [];
    const maxIdx = Math.min(currentIndex.value + 5, frames.value.length - 1, endFrame.value);
    for (let i = currentIndex.value; i <= maxIdx; i++) {
      urgent.push(frames.value[i]);
    }
    if (urgent.length > 0) {
      await preloadFrames(urgent, 3);
    }

    playStartTime = performance.now();
    playStartIndex = currentIndex.value;
    isPlaying.value = true;
    tick();
  }

  function clearPlayTimer() {
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
  }

  function pause() {
    isPlaying.value = false;
    clearPlayTimer();
  }

  function togglePlay() {
    if (isPlaying.value) {
      pause();
    } else {
      play();
    }
  }

  function stop() {
    pause();
    currentIndex.value = startFrame.value;
  }

  function goToFrame(index: number) {
    // Manual navigation should preempt any scheduled auto-play frame
    clearPlayTimer();
    // Clamp to valid range and playback range
    const clamped = Math.max(startFrame.value, Math.min(endFrame.value, index));
    if (clamped >= 0 && clamped < frames.value.length) {
      currentIndex.value = clamped;
      // Clear preview image when switching frames
      currentImage.value = '';
    }
  }

  function nextFrame() {
    clearPlayTimer();
    const next = currentIndex.value + 1;
    if (next <= endFrame.value && next < frames.value.length) {
      currentIndex.value = next;
    } else {
      currentIndex.value = startFrame.value;
    }
    // Clear preview image
    currentImage.value = '';
  }

  function prevFrame() {
    clearPlayTimer();
    const prev = currentIndex.value - 1;
    if (prev >= startFrame.value && prev >= 0) {
      currentIndex.value = prev;
    } else {
      currentIndex.value = endFrame.value;
    }
    // Clear preview image
    currentImage.value = '';
  }

  function setZoom(newZoom: number) {
    zoom.value = Math.max(0.1, Math.min(newZoom, 5));
  }

  function zoomIn() {
    setZoom(zoom.value * 1.2);
  }

  function zoomOut() {
    setZoom(zoom.value / 1.2);
  }

  function setPan(x: number, y: number) {
    panX.value = x;
    panY.value = y;
  }

  function resetView() {
    zoom.value = 1;
    panX.value = 0;
    panY.value = 0;
  }

  function setDragging(dragging: boolean) {
    isDragging.value = dragging;
  }

  function setCurrentImage(base64Image: string) {
    currentImage.value = base64Image;
  }

  function setPlaybackFps(fps: number) {
    playbackFps.value = Math.max(1, Math.min(fps, 60));
    // Restart RAF so new FPS takes effect immediately without resetting position
    if (isPlaying.value) {
      clearPlayTimer();
      playStartIndex = currentIndex.value;
      playStartTime = performance.now();
      tick();
    }
  }

  function setInterpolation(nearest: boolean) {
    useNearest.value = nearest;
  }

  function setPlaybackRange(start: number, end: number, interval: number = 1) {
    const maxIdx = Math.max(0, frames.value.length - 1);
    let s = Math.max(0, Math.min(start, maxIdx));
    let e = Math.max(0, Math.min(end, maxIdx));
    // 防御：start > end（如切换步骤后加载到 output 而 s1Params 仍是源帧空间，或 end 被压到 start 之下）
    // 时回退到播放全部已加载帧，避免非法范围导致 tick 的 totalStepsInRange 为负、无法播放。
    if (s > e) {
      s = 0;
      e = maxIdx;
    }
    startFrame.value = s;
    endFrame.value = e;
    frameInterval.value = Math.max(1, interval);

    // Reset to start of range
    currentIndex.value = s;
  }

  function setCanvasBgColor(color: string) {
    if (canvasBgColors[color]) {
      canvasBgColor.value = color;
    }
  }

  const canvasBgColorValue = computed(() => canvasBgColors[canvasBgColor.value]);

  return {
    // State
    frames,
    currentIndex,
    isPlaying,
    zoom,
    panX,
    panY,
    useNearest,
    isDragging,
    currentImage,
    playbackFps,
    startFrame,
    endFrame,
    frameInterval,
    canvasBgColor,
    canvasBgColors,
    // Cache (exposed for FramePlayer rendering)
    imageElementCache,
    loadingPaths,
    preloadFrames,
    isFrameCached,
    // Getters
    currentFrame,
    totalFrames,
    progress,
    canGoNext,
    canGoPrev,
    canvasBgColorValue,
    // Actions
    loadFrames,
    play,
    pause,
    togglePlay,
    stop,
    goToFrame,
    nextFrame,
    prevFrame,
    setZoom,
    zoomIn,
    zoomOut,
    setPan,
    resetView,
    setDragging,
    setCurrentImage,
    setPlaybackFps,
    setInterpolation,
    setPlaybackRange,
    setCanvasBgColor,
    clearPlayTimer,
    setFrameAdvanceHook
  };
});
