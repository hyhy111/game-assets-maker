/**
 * useSubscriptionPage - 打开订阅落地页隔离窗口
 *
 * 流程：
 * 1. GET /app/config/subscription-page-url 拿到真实落地页地址（字典驱动，运营可换）
 * 2. token 拼进 URL fragment（#token=xxx）——fragment 不随请求发送到服务器，
 *    不会留在服务端日志；pywebview 隔离窗无 window.opener，postMessage 不可达，
 *    所以不用握手，落地页直接从 location.hash 读取 token
 * 3. 通过 pywebview 桥调 backend/main.py 的 open_subscription_window(url)
 *    以 js_api=None 开隔离窗（落地页拿不到 pywebview 桥，安全）
 *
 * 支付成功后的余额刷新：隔离窗与主窗无 postMessage 通道，由 Header.vue 在主窗
 * 重新聚焦时刷新（见 subOpenedAt + focus 监听）。
 *
 * 依赖 backend/main.py 暴露 open_subscription_window(url: str) -> bool。
 */
import { fetchSubscriptionPageUrl } from '@/api/billing';
import { getToken } from '@/api/http';
import { isApiAvailable } from '@/api';

/** pywebview 桥动态调用（隔离窗开窗函数） */
async function callOpenWindow(url: string): Promise<void> {
  if (!isApiAvailable()) {
    throw new Error('PyWebView bridge not available');
  }
  const w = window as unknown as {
    pywebview?: { api?: Record<string, (...args: unknown[]) => Promise<unknown>> };
  };
  const api = w.pywebview?.api;
  const fn = api?.['open_subscription_window'];
  if (typeof fn !== 'function') {
    throw new Error('open_subscription_window not exposed by backend');
  }
  await fn(url);
}

/** 打开订阅落地页（隔离窗）；token 经 URL fragment 交给落地页 */
export async function openSubscriptionPage(): Promise<void> {
  const url = await fetchSubscriptionPageUrl();
  if (!url) {
    throw new Error('订阅页地址未配置');
  }
  const token = getToken();
  if (!token) {
    throw new Error('请先登录');
  }

  // fragment 传 token：不发送到服务器；落地页 location.hash 解析
  const target = url + (url.includes('#') ? '&' : '#') + 'token=' + encodeURIComponent(token);
  await callOpenWindow(target);
}
