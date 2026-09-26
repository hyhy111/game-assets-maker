/**
 * Billing API - 订阅落地页 / 积分余额 / 生效并发
 *
 * 订阅落地页地址由 ruoyi-app 字典接口下发（运营改字典即可换地址，无需发版客户端）。
 * 积分余额与并发来自 ruoyi-app 的 /app/credit/*（需登录）。
 */
import { httpGet } from './http';

/** 订阅落地页地址响应 */
export interface SubscriptionPageUrlResult {
  url: string;
}

/** 积分桶明细 */
export interface CreditBucket {
  bucketId: string;
  sourceType: string;
  totalAmount: number;
  remainAmount: number;
  effectiveFrom: string;
  expireTime: string;
  status: string;
  /** 积分名字（后端联查来源订单 sku_name 快照，订单缺失时为通用名） */
  skuName?: string;
}

/** 积分账户 */
export interface CreditAccount {
  totalAvailable: number;
  buckets: CreditBucket[];
}

/** 生效并发 */
export interface ConcurrencyResult {
  concurrency: number;
}

/** 订阅状态摘要（后端 /app/credit/subscription-status） */
export interface SubscriptionStatus {
  hasSubscription: boolean;
  levelRank: number | null;
  concurrency: number;
  /** 生效中期段到期；无生效中段时取最近排队段；均无 null */
  currentPeriodEnd: string | null;
  /** 所有未结束期段的链尾到期（续费锚点） */
  queueEnd: string | null;
  activePeriods: number;
  queuedPeriods: number;
}

/** 获取订阅落地页 URL（匿名） */
export async function fetchSubscriptionPageUrl(): Promise<string> {
  const res = await httpGet<{ url: string }>('/app/config/subscription-page-url');
  return res.url;
}

/** 积分账户（需登录）。http 层返回完整 AjaxResult，取 .data 解包 */
export async function fetchCreditAccount(): Promise<CreditAccount> {
  const res = await httpGet<{ data: CreditAccount }>('/app/credit/account');
  return res.data;
}

/** 当前生效并发（需登录）。同上，取 .data 解包 */
export async function fetchConcurrency(): Promise<number> {
  const res = await httpGet<{ data: ConcurrencyResult }>('/app/credit/concurrency');
  return res.data.concurrency;
}

/** 订阅状态摘要（需登录）。接口未部署/失败时由调用方降级处理 */
export async function fetchSubscriptionStatus(): Promise<SubscriptionStatus> {
  const res = await httpGet<{ data: SubscriptionStatus }>('/app/credit/subscription-status');
  return res.data;
}
