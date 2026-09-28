/**
 * Auth Store - C端用户登录态管理
 *
 * 启动恢复三段式(见 init):
 *   有 token 先校验 -> 失效则用加密保存的凭证自动登录 -> 否则游客态(不强制登录)
 * 半登录态: getInfo 网络错误时保留 token,status='unknown',后续请求成功自动补拉
 * 运行中恢复(见 silentRelogin): 401 时用加密凭证静默重登,成功则由 http 层重放原请求。
 *   恢复尝试期间不改 status —— 保持登录态外观不闪,确认不可恢复才回游客态。
 */
import { defineStore } from 'pinia';
import { computed, ref, watch } from 'vue';
import * as authApi from '@/api/auth';
import { api } from '@/api';
import {
  getToken,
  setToken,
  onUnauthorized,
  onAuthedSuccess,
  onUnauthorizedRecovery,
  NETWORK_ERROR
} from '@/api/http';
import {
  saveCredentials,
  clearCredentials,
  loadCredentials,
  hasStoredCredentials,
  markLoggedOut,
  clearLoggedOutMark,
  isLoggedOut,
} from '@/api/credentialVault';
import { logEvent } from '@/debug/request-log';
import type { CaptchaResult, UserInfo } from '@/types/auth';

export type AuthStatus = 'unknown' | 'guest' | 'authenticated';

export const useAuthStore = defineStore('auth', () => {
  // State
  const token = ref<string | null>(getToken());
  const userInfo = ref<UserInfo | null>(null);
  const status = ref<AuthStatus>(token.value ? 'unknown' : 'guest');
  const loading = ref(false);
  const error = ref<string | null>(null);
  /** 因会话失效（而非主动登出）落到游客态，顶栏据此提示"登录已过期" */
  const sessionExpired = ref(false);

  // Getters
  const isLoggedIn = computed(() => status.value === 'authenticated');

  // 平台源（ForFuner AI）配置随 token 变化实时推送进 Python 内存：
  // 登录/静默重登/登出/会话失效都经过 token 这一个出口，watch 全覆盖。
  // 桥不可用时静默忽略——下次 token 变化会再推；token 本身不落盘不入日志。
  watch(token, (value) => {
    void api.platform
      .setConfig(import.meta.env.VITE_APP_API_BASE_URL ?? '', value)
      .catch(() => { /* bridge not ready yet; next token change retries */ });
  }, { immediate: true });

  let retryingUserInfo = false;

  /** 静默重登冷却期：恢复失败后这段时间内不再尝试，避免每个 401 都重登一次 */
  const RELOGIN_COOLDOWN_MS = 5 * 60 * 1000;
  let reloginPromise: Promise<boolean> | null = null;
  let reloginBlockedUntil = 0;

  function toMessage(e: unknown): string {
    return e instanceof Error ? e.message : String(e);
  }

  function isNetworkError(e: unknown): boolean {
    return e instanceof Error && e.message === NETWORK_ERROR;
  }

  // Actions
  async function fetchCaptcha(): Promise<CaptchaResult> {
    return authApi.fetchCaptcha();
  }

  async function sendEmailCode(email: string, code: string, uuid: string): Promise<void> {
    await authApi.sendEmailCode({ email, code, uuid });
  }

  async function register(email: string, password: string, emailCode: string, code: string, uuid: string): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      await authApi.register({ email, password, emailCode, code, uuid });
    } catch (e) {
      error.value = toMessage(e);
      throw e;
    } finally {
      loading.value = false;
    }
  }

  /**
   * 登录；remember 为 true 时加密保存凭证，false 时清除历史凭证
   */
  async function login(email: string, password: string, remember = false): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      const newToken = await authApi.login({ username: email, password });
      setToken(newToken);
      token.value = newToken;
      sessionExpired.value = false;
      // 重新登录即恢复自动登录资格（登出时置的标记在此清除）
      clearLoggedOutMark();
      if (remember) {
        // 保存失败时 saveCredentials 只返回 false、不抛错；不记一笔的话，
        // 用户以为记住了，直到 token 失效那天才发现无法自动恢复。
        const saved = await saveCredentials(email, password);
        logEvent(
          saved
            ? '已勾选记住账号密码 → 凭证已加密保存'
            : '勾了记住账号密码但未保存成功（原因见上一行）→ 静默恢复将不可用',
          saved ? 'ok' : 'error',
        );
      } else {
        clearCredentials();
        logEvent('未勾选记住账号密码 → 已清除历史凭证（静默恢复将不可用）', 'warn');
      }
      const ok = await fetchUserInfo();
      status.value = ok ? 'authenticated' : 'unknown';
    } catch (e) {
      error.value = toMessage(e);
      throw e;
    } finally {
      loading.value = false;
    }
  }

  /**
   * 拉取用户信息；返回是否成功。网络错误保留 token 置半登录态，401 由 http 层处理
   */
  async function fetchUserInfo(): Promise<boolean> {
    if (!token.value) return false;
    try {
      userInfo.value = await authApi.getInfo();
      return true;
    } catch (e) {
      if (isNetworkError(e)) {
        status.value = 'unknown';
      }
      return false;
    }
  }

  /**
   * 用本地加密凭证静默登录；失败(密码已改/账号异常)清凭证回游客态
   */
  async function autoLogin(): Promise<void> {
    const creds = await loadCredentials();
    if (!creds) {
      status.value = 'guest';
      return;
    }
    try {
      await login(creds.email, creds.password, true);
    } catch {
      clearCredentials();
      setToken(null);
      token.value = null;
      userInfo.value = null;
      status.value = 'guest';
    }
  }

  async function logout(): Promise<void> {
    try {
      if (token.value) {
        await authApi.logout();
      }
    } catch (e) {
      console.error('Logout request failed:', e);
    } finally {
      // 主动登出：清 token 并置"已登出"标记，使重启后不会自动登录。
      // 凭证密文**刻意保留**——它用于登录页回填（见 login-prefill）。
      // "不要自动登录"与"不要记住我是谁"是两件事，这里只做前者。
      markLoggedOut();
      setToken(null);
      token.value = null;
      userInfo.value = null;
      status.value = 'guest';
      sessionExpired.value = false;
    }
  }

  /** 落到游客态；expired 标记本次是被会话失效打下来的（区别于主动登出/未登录） */
  function toGuest(expired: boolean): void {
    setToken(null);
    token.value = null;
    userInfo.value = null;
    status.value = 'guest';
    sessionExpired.value = expired;
  }

  /**
   * 401 后的静默恢复：用本地加密凭证重新登录，成功返回 true。
   *
   * - 并发 401 复用同一 Promise，只重登一次
   * - 无凭证（未勾选"记住账号密码"）直接返回 false
   * - 重登失败（密码已改/账号异常）清凭证并进入冷却期，避免 401 风暴
   * - 本函数不改 status：是否回游客态由 http 层在确认恢复失败后经 onUnauthorized 决定
   *
   * 刻意**不走 store 的 login()**：login() 会再拉一次 getInfo，那是一个带新 token 的
   * 已认证请求，若它同样 401 就会回头再触发本函数、与飞行中的 reloginPromise 互等而死锁。
   * 这里只取 token，userInfo 保持原样 —— 用户没变，恢复期间本就不该动它。
   */
  async function silentRelogin(): Promise<boolean> {
    if (Date.now() < reloginBlockedUntil) return false;
    if (reloginPromise) return reloginPromise;

    reloginPromise = (async () => {
      const creds = await loadCredentials();
      if (!creds) {
        logEvent('静默恢复：本地无保存凭证，直接回游客态', 'warn');
        return false;
      }
      try {
        const newToken = await authApi.login({ username: creds.email, password: creds.password });
        setToken(newToken);
        token.value = newToken;
        sessionExpired.value = false;
        return true;
      } catch {
        clearCredentials();
        reloginBlockedUntil = Date.now() + RELOGIN_COOLDOWN_MS;
        logEvent('静默恢复：重登失败，已清凭证并进入冷却', 'error');
        return false;
      }
    })().finally(() => {
      reloginPromise = null;
    });

    return reloginPromise;
  }

  function clearError(): void {
    error.value = null;
  }

  /** 应用启动时调用：token 校验 -> 保存凭证自动登录 -> 游客态 */
  async function init(): Promise<void> {
    const loggedOut = isLoggedOut();
    logEvent(
      `启动恢复：本地${token.value ? '有' : '无'} token，${hasStoredCredentials() ? '有' : '无'}保存凭证${loggedOut ? '，且处于已登出状态' : ''}`,
    );

    if (loggedOut) {
      // 用户主动登出过：凭证仍在（供登录页回填），但 MUST NOT 自动登录。
      // 这是"登出"与"忘记我是谁"两件事被拆开后的落点。
      setToken(null);
      token.value = null;
      userInfo.value = null;
      status.value = 'guest';
      return;
    }

    if (token.value) {
      const ok = await fetchUserInfo();
      if (ok) {
        status.value = 'authenticated';
        return;
      }
      if (status.value === 'unknown') {
        // 网络错误：保留 token，半登录态，后续请求成功自动补拉
        return;
      }
      // 401：token 已被 http 层清除，继续尝试自动登录
    }
    await autoLogin();
  }

  /** 半登录态修复：任意已认证请求成功后补拉用户信息 */
  async function retryUserInfoIfNeeded(): Promise<void> {
    if (status.value !== 'unknown' || !token.value || retryingUserInfo) return;
    retryingUserInfo = true;
    try {
      const ok = await fetchUserInfo();
      // 补拉在途期间用户可能已登出（token 被清空）。此时若还按结果翻成登录态，
      // 界面会在登出之后又变回已登录——必须复查 token 是否仍在。
      if (ok && token.value) {
        status.value = 'authenticated';
      }
    } finally {
      retryingUserInfo = false;
    }
  }

  return {
    // State
    token,
    userInfo,
    status,
    loading,
    error,
    sessionExpired,
    // Getters
    isLoggedIn,
    // Actions
    fetchCaptcha,
    sendEmailCode,
    register,
    login,
    fetchUserInfo,
    autoLogin,
    logout,
    clearError,
    init,
    retryUserInfoIfNeeded,
    silentRelogin,
    toGuest
  };
});

// 401 的最终归宿：http 层在"无法静默恢复"（无凭证/重登失败/单请求已重放过）时才调这里。
// 恢复尝试期间不经过本回调，因此顶栏不会先闪游客态再翻回来。
onUnauthorized(() => {
  useAuthStore().toGuest(true);
});

// 半登录态下任意已认证请求成功即补拉用户信息
onAuthedSuccess(() => {
  void useAuthStore().retryUserInfoIfNeeded();
});

// 静默重登（http 层 401 时调用；懒取 store，避免循环依赖）
onUnauthorizedRecovery(() => useAuthStore().silentRelogin());
