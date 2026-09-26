/**
 * Billing Store - 积分账户与订阅状态（顶栏账户簇共用）
 *
 * - 集中管理积分账户/桶明细与订阅状态摘要，Header 余额、订阅按钮、积分弹层共用一份数据
 * - 任一接口失败独立降级：积分失败 -> totalAvailable 保持 null（显示 '-'）；
 *   订阅状态失败 -> subscriptionStatus 保持 null（按钮回退"订阅"）
 * - in-flight 去重：重复触发复用同一 Promise（focus 刷新与弹层打开可能撞车）
 * - 登出时调用 reset() 清零
 */
import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import {
  fetchCreditAccount,
  fetchSubscriptionStatus,
  type CreditAccount,
  type CreditBucket,
  type SubscriptionStatus,
} from '@/api/billing';
import { logEvent } from '@/debug/request-log';

/** 剩余有效期（天），≤ 此值视为临期，到期时间醒目展示 */
export const EXPIRING_DAYS = 7;

/**
 * 窗口激活刷新的最小间隔：避免频繁切窗产生重复请求。
 * 实测 30 秒在桌面端体感过钝——用户切回来常常正好落在窗口内、什么都不发生，
 * 从外面看就是"刷新时灵时不灵"。5 秒足以折叠掉瞬间连点/连切，又不影响正常使用。
 */
export const ACTIVATION_REFRESH_INTERVAL_MS = 5_000;

export const useBillingStore = defineStore('billing', () => {
  const account = ref<CreditAccount | null>(null);
  const subscriptionStatus = ref<SubscriptionStatus | null>(null);

  /** 可用总积分；未加载/失败为 null */
  const totalAvailable = computed(() => account.value?.totalAvailable ?? null);

  /** 桶是否生效中（待生效桶 = 续费排队，进度条置灰展示） */
  function isBucketActive(b: CreditBucket): boolean {
    const eff = new Date(String(b.effectiveFrom || '').replace(' ', 'T'));
    return !isNaN(eff.getTime()) && eff.getTime() <= Date.now();
  }

  /**
   * 有效桶明细（含待生效）：生效中按到期升序在前，待生效按生效日升序在后
   */
  const buckets = computed<CreditBucket[]>(() => {
    const list = account.value?.buckets ?? [];
    const t = (s?: string | null) => new Date(String(s || '').replace(' ', 'T')).getTime() || 0;
    const active = list.filter(isBucketActive).sort((a, b) => t(a.expireTime) - t(b.expireTime));
    const pending = list.filter((b) => !isBucketActive(b)).sort((a, b) => t(a.effectiveFrom) - t(b.effectiveFrom));
    return [...active, ...pending];
  });

  let accountInflight: Promise<void> | null = null;
  let statusInflight: Promise<void> | null = null;
  let lastActivationRefreshAt = 0;

  async function refreshAccount(): Promise<void> {
    if (!accountInflight) {
      accountInflight = fetchCreditAccount()
        .then((data) => {
          account.value = data;
        })
        .catch(() => {
          // 未登录/网络错误：保持现状（null 或旧值），由视图层展示 '-'
        })
        .finally(() => {
          accountInflight = null;
        });
    }
    return accountInflight;
  }

  async function refreshSubscriptionStatus(): Promise<void> {
    if (!statusInflight) {
      statusInflight = fetchSubscriptionStatus()
        .then((data) => {
          subscriptionStatus.value = data;
        })
        .catch(() => {
          // 接口未部署/网络错误：保持 null，订阅按钮回退"订阅"原状
        })
        .finally(() => {
          statusInflight = null;
        });
    }
    return statusInflight;
  }

  /** 登录后一次性拉齐（并发触发，任一失败独立降级） */
  async function refreshAll(): Promise<void> {
    await Promise.allSettled([refreshAccount(), refreshSubscriptionStatus()]);
  }

  /**
   * 窗口重新激活（focus / visibilitychange）时的刷新。
   *
   * 默认受最小间隔节流，使频繁切窗不产生重复请求；force 用于"刚付完款回到主窗"
   * 这类必须立即生效的信号，绕过节流。与 accountInflight/statusInflight 的去重
   * 是两层不同的保护：节流管"隔多久才允许再发"，去重管"同一时刻只发一个"。
   */
  async function refreshOnActivation(options: { force?: boolean; source?: string } = {}): Promise<void> {
    const now = Date.now();
    const elapsedMs = now - lastActivationRefreshAt;
    const via = options.source ? `(${options.source})` : '';

    if (!options.force && elapsedMs < ACTIVATION_REFRESH_INTERVAL_MS) {
      const wait = Math.ceil((ACTIVATION_REFRESH_INTERVAL_MS - elapsedMs) / 1000);
      logEvent(`窗口激活${via} → 节流跳过（距上次 ${Math.round(elapsedMs / 1000)}s，还需 ${wait}s）`);
      return;
    }

    lastActivationRefreshAt = now;
    logEvent(`窗口激活${via} → 刷新账户数据${options.force ? '（付完款回来，绕过节流）' : ''}`);
    await refreshAll();
  }

  function reset(): void {
    account.value = null;
    subscriptionStatus.value = null;
  }

  return {
    account,
    subscriptionStatus,
    totalAvailable,
    buckets,
    isBucketActive,
    refreshAccount,
    refreshSubscriptionStatus,
    refreshAll,
    refreshOnActivation,
    reset,
  };
});
