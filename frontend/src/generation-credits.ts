import type { SeedanceModel, SeedanceResolution, SeedreamModel, SeedreamResolution } from './types';

// 首版按产品提供的价格表固定计价：1 元 = 100 积分。
// 这里只计算平台预估，不参与 API Key 请求或实际扣费。
const IMAGE_CREDITS: Record<SeedreamModel, Partial<Record<SeedreamResolution, number>>> = {
  pro: { '1K': 30, '1.5K': 30, '2K': 60 },
  flash: {},
  lite: { '2K': 22 },
};

const VIDEO_CREDITS: Record<SeedanceModel, Partial<Record<SeedanceResolution, Partial<Record<number, number>>>>> = {
  standard: {
    '480p': { 4: 185, 5: 231, 6: 277 },
    '720p': { 4: 397, 5: 497, 6: 596 },
    '1080p': { 4: 991, 5: 1239, 6: 1487 },
  },
  fast: {
    '480p': { 4: 149, 5: 186, 6: 223 },
    '720p': { 4: 320, 5: 400, 6: 480 },
  },
  mini: {
    '480p': { 4: 92, 5: 112, 6: 139 },
    '720p': { 4: 199, 5: 248, 6: 298 },
  },
};

export function imageGenerationCredits(model: string, resolution: SeedreamResolution, count: number): number | null {
  // 本地静态表只覆盖直连短键；平台源的 model 是上游 ID，查不到即返回 null（由服务端报价负责）。
  const credits = IMAGE_CREDITS[model as SeedreamModel]?.[resolution];
  if (credits === undefined || !Number.isInteger(count) || count < 1 || count > 4) return null;
  return credits * count;
}

export function videoGenerationCredits(model: string, resolution: SeedanceResolution, duration: number): number | null {
  return VIDEO_CREDITS[model as SeedanceModel]?.[resolution]?.[duration] ?? null;
}
