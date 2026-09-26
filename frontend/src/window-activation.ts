/**
 * 窗口激活刷新决策
 *
 * 桌面端"用户切走又切回"是最可靠的"账户数据可能已过时"信号。触发条件与是否绕过
 * 节流在这里集中判定，使其可被单测覆盖 —— 组件里只保留事件订阅与响应。
 */

/** 订阅窗打开后至少隔这么久才算"付完款回来了"，避免开窗瞬间的 focus 误判 */
export const SUBSCRIPTION_RETURN_MS = 4000;

export interface ActivationContext {
  isLoggedIn: boolean;
  /** document.visibilityState */
  visibilityState: string;
  /** 订阅落地页窗口的打开时刻（0 表示没开过） */
  subOpenedAt: number;
  now: number;
}

export type ActivationDecision =
  | { refresh: false }
  | { refresh: true; force: boolean };

/**
 * 判定本次窗口激活是否要刷新账户数据，以及是否绕过节流。
 *
 * - 游客态不刷新（没有账户数据可拉，也不该触发 401）
 * - visibilitychange 转为隐藏时不刷新，只处理"变为可见"
 * - 从订阅窗回来属于"刚付完款"，必须立即生效，故 force 绕过节流；
 *   其余激活一律交给节流，避免频繁切窗重复请求
 */
export function decideActivationRefresh(ctx: ActivationContext): ActivationDecision {
  if (!ctx.isLoggedIn) return { refresh: false };
  if (ctx.visibilityState === 'hidden') return { refresh: false };

  const fromSubscription = ctx.subOpenedAt > 0 && ctx.now - ctx.subOpenedAt > SUBSCRIPTION_RETURN_MS;
  return { refresh: true, force: fromSubscription };
}
