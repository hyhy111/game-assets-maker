/**
 * 音频工具：波形峰值计算、Web Audio 解码、播放调度与音画同步（票 01–04）。
 *
 * - computePeaks / peaksToWavePath：无副作用的纯函数（可在 Node 中独立测试）。
 * - useAudioWaveform：组合式函数，fetch wav -> decodeAudioData -> 峰值，并保留
 *   解码后的 AudioBuffer 供播放复用（ADR 0001 决策 4：峰值与播放共用一次解码）。
 * - getTriggeredClips：纯函数，判定连续播放帧前进跨越了哪些片段的 Placement Frame。
 * - createAudioPlaybackEngine：可注入 AudioContext 工厂的播放引擎（便于测试 mock）。
 * - createAudioSyncController：纯逻辑同步控制器，把帧跨越事件映射为片段播放调度。
 */
import { ref, type Ref } from 'vue';
import type { AudioClip } from '@/types';

/**
 * 计算音频波形的峰值（纯函数）。
 *
 * 把单声道 PCM 采样（-1..1）均匀分成 bucketCount 个桶，
 * 每个桶取最大绝对幅值（clamp 到 0..1）。
 *
 * @param samples 单声道采样数据（-1..1 的 Float32Array）
 * @param bucketCount 要分成的桶数（对应渲染列数）
 * @returns 每个桶的最大绝对幅值（0..1）
 */
export function computePeaks(samples: Float32Array, bucketCount: number): number[] {
  if (bucketCount <= 0 || samples.length === 0) {
    return [];
  }
  const peaks: number[] = new Array(bucketCount).fill(0);
  const bucketSize = samples.length / bucketCount;
  for (let i = 0; i < bucketCount; i++) {
    const start = Math.floor(i * bucketSize);
    const end = Math.min(Math.floor((i + 1) * bucketSize), samples.length);
    let max = 0;
    for (let j = start; j < end; j++) {
      const abs = Math.abs(samples[j]);
      if (abs > max) max = abs;
    }
    peaks[i] = Math.min(max, 1);
  }
  return peaks;
}

export interface FrameAlignedPeaksOptions {
  sampleRate: number;
  sourceFps: number;
  /** 时间轴上显示的帧间隔数；总帧数为 N 时传 N - 1。 */
  timelineFrames: number;
  bucketsPerFrame?: number;
}

/**
 * 生成按源视频帧对齐的共享波形峰值。
 *
 * 原始音轨和片段音轨从同一数组取值，避免各自重新采样后出现形状歧义。
 */
export function computeFrameAlignedPeaks(
  samples: Float32Array,
  options: FrameAlignedPeaksOptions,
): number[] {
  const { sampleRate, sourceFps, timelineFrames } = options;
  const bucketsPerFrame = Math.max(1, Math.round(options.bucketsPerFrame ?? 10));
  if (samples.length === 0 || sampleRate <= 0 || sourceFps <= 0 || timelineFrames <= 0) {
    return [];
  }

  const frameIntervals = Math.max(0, Math.round(timelineFrames));
  const sampleCount = Math.min(
    samples.length,
    Math.ceil((frameIntervals / sourceFps) * sampleRate),
  );
  return computePeaks(
    samples.subarray(0, sampleCount),
    frameIntervals * bucketsPerFrame,
  );
}

/** 从共享波形中截取 Source Region 对应的峰值。 */
export function sliceFrameAlignedPeaks(
  peaks: number[],
  startFrame: number,
  endFrame: number,
  bucketsPerFrame: number = 10,
): number[] {
  const buckets = Math.max(1, Math.round(bucketsPerFrame));
  const start = Math.max(0, Math.round(startFrame * buckets));
  const end = Math.max(start, Math.round(endFrame * buckets));
  return peaks.slice(start, end);
}

/**
 * 把峰值数组转为 SVG path（上下镜像的竖线条波形）。
 *
 * @param peaks computePeaks 的输出（0..1）
 * @param width SVG viewBox 宽度
 * @param height SVG viewBox 高度
 * @returns SVG path 的 `d` 字符串
 */
export function peaksToWavePath(peaks: number[], width: number, height: number): string {
  if (peaks.length === 0) return '';
  const mid = height / 2;
  const stepX = width / peaks.length;
  let path = '';
  for (let i = 0; i < peaks.length; i++) {
    const x = i * stepX;
    const amplitude = peaks[i] * mid;
    path += `M ${x.toFixed(2)} ${(mid - amplitude).toFixed(2)} L ${x.toFixed(2)} ${(mid + amplitude).toFixed(2)}`;
  }
  return path;
}

// ---------------------------------------------------------------------------
// 自动检测：从音频采样中找出「有声音」的连续段（用于自动创建 Audio Clip）
// ---------------------------------------------------------------------------

/** 检测到的一段有声音的区间（采样索引，左闭右开，相对输入 samples）。 */
export interface SoundSegment {
  startSample: number;
  endSample: number;
}

export interface DetectSegmentsOptions {
  sampleRate: number;
  /** 幅值阈值（0..1）。不传则自适应：max(0.05, 0.10 * 区间内峰值包络最大值)。 */
  threshold?: number;
  /** 包络窗口毫秒（默认 20）。 */
  windowMs?: number;
  /** 最短片段毫秒，短于此丢弃（默认 50）。 */
  minSegmentMs?: number;
  /** 间隔小于此毫数的片段合并（默认 80，避免短促静音切碎）。 */
  mergeGapMs?: number;
}

/**
 * 纯函数：在给定采样上检测有声音的连续段。
 *
 * 1. 按 windowMs 分桶取每桶峰值幅值（包络）。
 * 2. 高于 threshold 的连续桶构成候选段；threshold 自适应为区间峰值最大值的 10%（下限 0.05）。
 * 3. 间隔小于 mergeGapMs 的候选段合并（消除短促静音造成的抖动）。
 * 4. 丢弃短于 minSegmentMs 的弱音段；峰值达到区间最大峰值 50% 的强音段不受此限制。
 *
 * 返回段为采样索引（相对输入 samples），左闭右开。
 */
export function detectSoundSegments(samples: Float32Array, opts: DetectSegmentsOptions): SoundSegment[] {
  const { sampleRate } = opts;
  if (samples.length === 0 || sampleRate <= 0) return [];
  const window = Math.max(1, Math.floor(((opts.windowMs ?? 20) / 1000) * sampleRate));
  const minLen = Math.floor(((opts.minSegmentMs ?? 50) / 1000) * sampleRate);
  const mergeGap = Math.floor(((opts.mergeGapMs ?? 80) / 1000) * sampleRate);

  // 逐窗口峰值包络
  const envelope: number[] = [];
  let maxEnv = 0;
  for (let i = 0; i < samples.length; i += window) {
    const end = Math.min(i + window, samples.length);
    let peak = 0;
    for (let j = i; j < end; j++) {
      const a = Math.abs(samples[j]);
      if (a > peak) peak = a;
    }
    envelope.push(peak);
    if (peak > maxEnv) maxEnv = peak;
  }
  const threshold = opts.threshold ?? Math.max(0.05, 0.10 * maxEnv);

  // 高于阈值的连续桶 -> 候选段
  const runs: SoundSegment[] = [];
  let runStart = -1;
  let runEnd = 0;
  for (let i = 0; i < envelope.length; i++) {
    const sStart = i * window;
    const sEnd = Math.min((i + 1) * window, samples.length);
    if (envelope[i] >= threshold) {
      if (runStart < 0) runStart = sStart;
      runEnd = sEnd;
    } else if (runStart >= 0) {
      runs.push({ startSample: runStart, endSample: runEnd });
      runStart = -1;
    }
  }
  if (runStart >= 0) runs.push({ startSample: runStart, endSample: runEnd });

  // 合并小间隔
  const merged: SoundSegment[] = [];
  for (const run of runs) {
    const last = merged[merged.length - 1];
    if (last && run.startSample - last.endSample <= mergeGap) {
      last.endSample = run.endSample;
    } else {
      merged.push({ startSample: run.startSample, endSample: run.endSample });
    }
  }
  // 过滤弱且过短的候选；强冲击音即使短于最小时长也保留。
  const strongPeakThreshold = 0.5 * maxEnv;
  return merged.filter((segment) => {
    if (segment.endSample - segment.startSample >= minLen) return true;
    let segmentPeak = 0;
    for (let i = segment.startSample; i < segment.endSample; i++) {
      segmentPeak = Math.max(segmentPeak, Math.abs(samples[i]));
    }
    return segmentPeak >= strongPeakThreshold;
  });
}

/** useAudioWaveform 的返回类型 */
export interface AudioWaveformState {
  peaks: Ref<number[]>;
  /** 解码后的 AudioBuffer（峰值与播放共用，ADR 0001 决策 4）；未解码/失败时为 null */
  audioBuffer: Ref<AudioBuffer | null>;
  loading: Ref<boolean>;
  error: Ref<string | null>;
  load: (wavUrl: string, bucketCount?: number) => Promise<void>;
}

/**
 * 组合式函数：fetch wav -> decodeAudioData -> 峰值。
 *
 * 解码后的 AudioBuffer 被保留并通过 `audioBuffer` 暴露，供播放引擎复用
 * （ADR 0001 决策 4：峰值与播放共用一次解码）。解码用的 AudioContext 在解码
 * 后即关闭；AudioBuffer 是独立数据，可在另一持久 AudioContext 上播放。
 * 在非浏览器环境（SSR/测试）中 fetch 或 AudioContext 不可用时安全失败。
 */
export function useAudioWaveform(): AudioWaveformState {
  const peaks = ref<number[]>([]);
  const audioBuffer = ref<AudioBuffer | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);

  async function load(wavUrl: string, bucketCount: number = 800): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      const AudioCtx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!AudioCtx) {
        throw new Error('当前环境不支持 Web Audio');
      }
      const response = await fetch(wavUrl);
      if (!response.ok) {
        throw new Error(`音频文件加载失败: ${response.status}`);
      }
      const arrayBuffer = await response.arrayBuffer();
      const audioCtx = new AudioCtx();
      const decoded = await audioCtx.decodeAudioData(arrayBuffer);
      audioCtx.close();
      audioBuffer.value = decoded;
      const channelData = decoded.getChannelData(0);
      peaks.value = computePeaks(channelData, bucketCount);
    } catch (e) {
      peaks.value = [];
      audioBuffer.value = null;
      error.value = e instanceof Error ? e.message : '音频解码失败';
    } finally {
      loading.value = false;
    }
  }

  return { peaks, audioBuffer, loading, error, load };
}

// ---------------------------------------------------------------------------
// 票 04：音画同步 —— 帧驱动触发 + 源 fps 对齐（ADR 0001 决策 5）
// ---------------------------------------------------------------------------

/**
 * 纯函数：判定连续播放时，帧从 prevFrame 前进到 currentFrame 跨越了哪些片段。
 *
 * 一个片段被触发当且仅当 `prevFrame < placementFrame <= currentFrame`（严格向前跨越）。
 * - 帧未前进（prevFrame === currentFrame）或后退（prevFrame > currentFrame，如 scrub 回拖
 *   或循环 wrap）时不触发任何片段；后退后的新一轮正向播放会自然重新跨越并触发。
 * - 一次连续播放过程中，每个 placementFrame 被单调前进的帧恰好跨越一次，故「每片段每次
 *   播放过程只触发一次」由本函数的向前跨越语义天然保证，无需额外去重状态。
 */
export function getTriggeredClips(
  prevFrame: number,
  currentFrame: number,
  clips: AudioClip[],
): AudioClip[] {
  if (currentFrame <= prevFrame) return [];
  return clips.filter((c) => prevFrame < c.placementFrame && c.placementFrame <= currentFrame);
}

/** 播放引擎：用解码好的 AudioBuffer 按 offset/duration 播放片段（裁剪虚拟播放）。 */
export interface AudioPlaybackEngine {
  setBuffer(buffer: AudioBuffer | null): void;
  hasBuffer(): boolean;
  playClip(clip: AudioClip, sourceFps: number): void;
  /** 确保 AudioContext 处于运行态（WKWebView 等需在用户手势后 resume 才出声）。 */
  resume(): void;
  stopAll(): void;
  dispose(): void;
}

/** 创建 AudioContext 的工厂类型（便于注入 mock）。 */
export type AudioContextFactory = () => AudioContext;

/**
 * 创建播放引擎。AudioContext 懒创建并持久持有（供 AudioBufferSourceNode 复用）。
 *
 * @param contextFactory 可选的 AudioContext 工厂；不传时在浏览器用 window.AudioContext，
 *   测试可注入 mock。工厂仅在首次播放时被调用。
 */
export function createAudioPlaybackEngine(contextFactory?: AudioContextFactory): AudioPlaybackEngine {
  let buffer: AudioBuffer | null = null;
  let ctx: AudioContext | null = null;
  const activeSources = new Set<AudioBufferSourceNode>();

  function defaultFactory(): AudioContext {
    const Ctor =
      typeof window !== 'undefined'
        ? window.AudioContext ??
          (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
        : undefined;
    if (!Ctor) throw new Error('当前环境不支持 Web Audio');
    return new Ctor();
  }

  function getCtx(): AudioContext {
    if (!ctx) ctx = (contextFactory ?? defaultFactory)();
    return ctx;
  }

  function stopAll(): void {
    for (const s of activeSources) {
      try {
        s.stop();
      } catch {
        // 已停止的 source 再 stop 会抛错，忽略
      }
    }
    activeSources.clear();
  }

  return {
    setBuffer(b) {
      buffer = b;
    },
    hasBuffer() {
      return buffer !== null;
    },
    playClip(clip, sourceFps) {
      if (!buffer || sourceFps <= 0) return;
      const offset = clip.srcStartFrame / sourceFps;
      const duration = Math.max(0, (clip.srcEndFrame - clip.srcStartFrame) / sourceFps);
      if (duration <= 0) return;
      const c = getCtx();
      // 防御性 resume：WKWebView 下 AudioContext 默认 suspended，需 resume 才出声
      if (c.state === 'suspended') void c.resume();
      const src = c.createBufferSource();
      src.buffer = buffer;
      src.connect(c.destination);
      src.onended = () => {
        activeSources.delete(src);
      };
      // start(when=0 即「现在」, offset, duration)：offset/duration 均按源 fps 换算（Frame-aligned）。
      src.start(0, offset, duration);
      activeSources.add(src);
    },
    resume() {
      // 尽力而为：无 AudioContext（测试/SSR）或 context 已关闭时忽略，不抛错
      try {
        const c = getCtx();
        if (c.state === 'suspended') void c.resume();
      } catch {
        // 忽略
      }
    },
    stopAll,
    dispose() {
      stopAll();
      if (ctx) {
        try {
          ctx.close();
        } catch {
          // 忽略
        }
        ctx = null;
      }
      buffer = null;
    },
  };
}

/** 同步控制器依赖的 audio store 形状（结构化类型，便于注入 store 或 mock）。 */
export interface AudioSyncStoreLike {
  clips: AudioClip[];
  sourceFps: number;
  loaded: boolean;
}

export interface AudioSyncControllerDeps {
  audioStore: AudioSyncStoreLike;
  engine: AudioPlaybackEngine;
}

export interface AudioSyncController {
  /** Trigger clips placed exactly on the frame where playback begins. */
  onPlaybackStart(currentFrame: number): void;
  /**
   * 连续播放帧推进回调（由 player store 的 frame-advance hook 调用）。
   * 跨越的片段以当前 sourceFps 触发播放。仅向前跨越才触发。
   */
  onFrameAdvance(prevFrame: number, currentFrame: number): void;
  /**
   * 帧变化回调（用于检测非 tick 来源的手动导航：scrub / 单帧步进）。
   * 当帧与上一次 tick 推进到的位置不一致时，视为手动导航并 stopAll（静音）。
   */
  onFrameChanged(currentFrame: number): void;
}

/**
 * 创建同步控制器（纯逻辑，无 Vue 依赖，便于测试）。
 *
 * - onFrameAdvance 用 getTriggeredClips 决定触发哪些片段，并记录 lastTickFrame。
 * - onFrameChanged 比对 lastTickFrame：不一致即手动导航 -> engine.stopAll()。
 *   （tick 推进会在同步设置 currentIndex 后立即调用 onFrameAdvance，故 lastTickFrame
 *   与 currentIndex 一致；手动导航不经过 onFrameAdvance，故不一致。）
 */
export function createAudioSyncController(deps: AudioSyncControllerDeps): AudioSyncController {
  let lastTickFrame = -1;

  function onPlaybackStart(currentFrame: number): void {
    lastTickFrame = currentFrame;
    if (!deps.audioStore.loaded || deps.audioStore.sourceFps <= 0) return;
    for (const clip of getTriggeredClips(currentFrame - 1, currentFrame, deps.audioStore.clips)) {
      deps.engine.playClip(clip, deps.audioStore.sourceFps);
    }
  }

  return {
    onPlaybackStart,
    onFrameAdvance(prevFrame, currentFrame) {
      if (currentFrame < prevFrame) {
        // Only continuous playback calls this hook; a backward tick is a loop.
        deps.engine.stopAll();
        onPlaybackStart(currentFrame);
        return;
      }
      lastTickFrame = currentFrame;
      if (!deps.audioStore.loaded) return;
      const triggered = getTriggeredClips(prevFrame, currentFrame, deps.audioStore.clips);
      const fps = deps.audioStore.sourceFps;
      if (fps > 0) {
        for (const clip of triggered) deps.engine.playClip(clip, fps);
      }
    },
    onFrameChanged(currentFrame) {
      if (currentFrame !== lastTickFrame) {
        // 非 tick 推进（scrub / 单帧步进）：静音正在响的音频
        deps.engine.stopAll();
      }
    },
  };
}
