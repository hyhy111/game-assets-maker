/**
 * HTTP layer - 直连 ruoyi-app C端服务的轻量 fetch 封装
 *
 * 与 src/api/index.ts（pywebview 桥）相互独立，仅用于访问 RuoYi HTTP 接口。
 * 统一处理 AjaxResult {code, msg, ...}：code !== 200 时抛出 Error(msg)。
 */

import { logEvent } from '@/debug/request-log';

const BASE_URL: string = import.meta.env.VITE_APP_API_BASE_URL ?? 'http://localhost:8081';
const TOKEN_KEY = 'gam:auth:token';

/** 网络层错误（ fetch 拒绝 / 非 JSON 响应）使用的标记 message，视图层映射为 i18n 文案 */
export const NETWORK_ERROR = '__network_error__';

let unauthorizedCallback: (() => void) | null = null;
let authedSuccessCallback: (() => void) | null = null;
let reloginHandler: (() => Promise<boolean>) | null = null;

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

/** 注册 401 回调（由 auth store 在模块作用域注册，避免循环依赖） */
export function onUnauthorized(cb: () => void): void {
  unauthorizedCallback = cb;
}

/** 注册已认证请求成功回调（半登录态恢复用，由 auth store 注册） */
export function onAuthedSuccess(cb: () => void): void {
  authedSuccessCallback = cb;
}

/**
 * 注册静默重登处理器（由 auth store 注册，避免循环依赖）
 *
 * 401 时调用，返回是否恢复成功；成功则本层重放原请求，调用方无感。
 */
export function onUnauthorizedRecovery(cb: () => Promise<boolean>): void {
  reloginHandler = cb;
}

interface AjaxBody {
  code?: number;
  msg?: string;
  [key: string]: unknown;
}

export interface RequestOptions {
  /** 跳过静默恢复。认证接口（登录/取用户信息）用：用"重登"去救一次登录，定义上就是错的 */
  noRecovery?: boolean;
}

interface InternalOptions extends RequestOptions {
  /** 本次是否为重放（单请求最多重放一次） */
  retried?: boolean;
}

async function request<T>(path: string, init: RequestInit, options: InternalOptions = {}): Promise<T> {
  const { retried = false, noRecovery = false } = options;
  const method = init.method ?? 'GET';
  const label = `${method} ${path}${retried ? ' (重放)' : ''}`;
  const headers = new Headers(init.headers);
  headers.set('Content-Type', 'application/json');
  const token = getToken();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, { ...init, headers });
  } catch {
    logEvent(`${label} → 网络错误`, 'error');
    throw new Error(NETWORK_ERROR);
  }

  let body: AjaxBody;
  try {
    body = (await res.json()) as AjaxBody;
  } catch {
    logEvent(`${label} → 响应非 JSON`, 'error');
    throw new Error(NETWORK_ERROR);
  }

  if (res.status === 401 || body.code === 401) {
    setToken(null);

    // 两道防递归：认证接口显式豁免（noRecovery），且只对"确实带着 token 发出"的
    // 请求尝试恢复 —— 重登本身走的是登录接口且此时 token 已被清空，两重都够不着。
    // 单个请求最多重放一次（retried），避免重放再失败时的无限循环。
    const recoverable = !noRecovery && Boolean(token) && !retried && reloginHandler !== null;
    if (recoverable) {
      logEvent(`${label} → 401，尝试静默恢复`, 'warn');
      if (await reloginHandler!()) {
        logEvent('静默重登成功，重放原请求', 'ok');
        return request<T>(path, init, { retried: true, noRecovery });
      }
      logEvent('静默恢复失败 → 回游客态', 'error');
    } else {
      logEvent(`${label} → 401${noRecovery ? '（认证接口，不尝试恢复）' : ''}`, 'warn');
    }

    unauthorizedCallback?.();
    throw new Error(body.msg || 'Unauthorized');
  }

  if (body.code !== 200) {
    logEvent(`${label} → ${body.code} ${body.msg ?? ''}`.trim(), 'error');
    throw new Error(body.msg || `Request failed (${body.code ?? res.status})`);
  }

  logEvent(`${label} → 200`, 'ok');

  if (token) {
    authedSuccessCallback?.();
  }

  return body as T;
}

export function httpGet<T>(path: string, options: RequestOptions = {}): Promise<T> {
  return request<T>(path, { method: 'GET' }, options);
}

export function httpPost<T>(path: string, body?: unknown, options: RequestOptions = {}): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    body: body === undefined ? undefined : JSON.stringify(body)
  }, options);
}
