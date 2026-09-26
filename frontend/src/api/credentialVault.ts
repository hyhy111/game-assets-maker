/**
 * Credential Vault - 记住账号密码的加密存取
 * 经 pywebview 桥调用 Python 侧 DPAPI 加解密，密文存 localStorage
 */
import type { PyWebViewWindow } from '@/types/api';
import { logEvent } from '@/debug/request-log';

declare const window: PyWebViewWindow;

const STORAGE_KEY = 'gam:auth:credentials';

export interface SavedCredentials {
  email: string;
  password: string;
}

function getBridgeNow() {
  return window.pywebview?.api ?? null;
}

/**
 * 轮询等待 pywebview 桥注入完成；超时（浏览器 dev）返回 null
 * 真实环境实测:页面脚本执行时桥尚不存在,pywebviewready 事件时序不可靠,轮询最稳
 */
function waitForBridge(timeoutMs = 5000): Promise<ReturnType<typeof getBridgeNow>> {
  return new Promise((resolve) => {
    const startedAt = Date.now();
    const check = () => {
      const api = getBridgeNow();
      if (api) {
        resolve(api);
      } else if (Date.now() - startedAt >= timeoutMs) {
        resolve(null);
      } else {
        setTimeout(check, 50);
      }
    };
    check();
  });
}

/**
 * 加密保存账号密码；桥不可用时静默跳过，返回是否保存成功
 */
export async function saveCredentials(email: string, password: string): Promise<boolean> {
  const api = await waitForBridge();
  if (!api) {
    logEvent('凭证保存失败：pywebview 桥超时未就绪', 'error');
    return false;
  }
  try {
    const ciphertext = await api.encrypt_credential(JSON.stringify({ email, password }));
    localStorage.setItem(STORAGE_KEY, ciphertext);
    return true;
  } catch (e) {
    // 桥在、但加密本身失败（如 Python 侧缺 win32crypt / cryptography）。
    // 这两种成因完全不同，必须分开写清楚，否则排查会被带偏。
    logEvent(`凭证保存失败：加密调用出错（${e instanceof Error ? e.message : String(e)}）`, 'error');
    return false;
  }
}

/**
 * 读取并解密保存的凭证；不存在、桥不可用或解密失败均返回 null。
 * 解密失败（异机拷贝/密钥轮换/密文损坏）时清除残留密文。
 */
export async function loadCredentials(): Promise<SavedCredentials | null> {
  const ciphertext = localStorage.getItem(STORAGE_KEY);
  if (!ciphertext) return null;
  const api = await waitForBridge();
  if (!api) return null;
  try {
    const plaintext = await api.decrypt_credential(ciphertext);
    const parsed = JSON.parse(plaintext) as Partial<SavedCredentials>;
    if (typeof parsed.email !== 'string' || typeof parsed.password !== 'string') {
      throw new Error('invalid credential payload');
    }
    return { email: parsed.email, password: parsed.password };
  } catch {
    localStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export function clearCredentials(): void {
  localStorage.removeItem(STORAGE_KEY);
}

export function hasStoredCredentials(): boolean {
  return localStorage.getItem(STORAGE_KEY) !== null;
}

// ---------- 「已登出」标记 ----------
//
// 与凭证密文分开存放，且刻意不加密：它不含敏感信息，而读取它的地方是启动路径
// （决定要不要自动登录）——那条路径不能去等 pywebview 桥解密。
// 语义：置位 = 用户主动登出过，凭证保留（供登录页回填）但不得自动登录。

const LOGGED_OUT_KEY = 'gam:auth:logged-out';

export function markLoggedOut(): void {
  localStorage.setItem(LOGGED_OUT_KEY, '1');
}

export function clearLoggedOutMark(): void {
  localStorage.removeItem(LOGGED_OUT_KEY);
}

export function isLoggedOut(): boolean {
  return localStorage.getItem(LOGGED_OUT_KEY) === '1';
}
