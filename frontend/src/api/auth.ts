/**
 * Auth API - ruoyi-app C端认证接口
 */
import { httpGet, httpPost } from './http';
import type {
  CaptchaResult,
  EmailCodeBody,
  LoginBody,
  RegisterBody,
  ResetCodeBody,
  ResetPasswordBody,
  UserInfo
} from '@/types/auth';

/** 获取图形验证码 */
export async function fetchCaptcha(): Promise<CaptchaResult> {
  return httpGet<CaptchaResult>('/captchaImage');
}

/** 发送邮箱验证码（注册用，会先校验图形验证码） */
export async function sendEmailCode(body: EmailCodeBody): Promise<void> {
  await httpPost('/emailCode', body);
}

/** 注册 */
export async function register(body: RegisterBody): Promise<void> {
  await httpPost('/register', body);
}

/** 发送重置密码验证码（服务端对本接口会一次性消费图形验证码） */
export async function sendResetEmailCode(body: ResetCodeBody): Promise<void> {
  await httpPost('/resetPassword/code', body);
}

/** 提交重置密码；成功后服务端会吊销该账号的全部会话 */
export async function resetPassword(body: ResetPasswordBody): Promise<void> {
  await httpPost('/resetPassword', body);
}

// 认证接口一律不走静默恢复：登录失败就是登录失败，不该拿保存的凭证再去登一次
const NO_RECOVERY = { noRecovery: true } as const;

/** 登录（username 承载邮箱），成功返回 token */
export async function login(body: LoginBody): Promise<string> {
  const res = await httpPost<{ token: string }>('/login', body, NO_RECOVERY);
  return res.token;
}

/** 获取当前登录用户信息 */
export async function getInfo(): Promise<UserInfo> {
  const res = await httpGet<{ user: UserInfo }>('/getInfo', NO_RECOVERY);
  return res.user;
}

/** 注销 */
export async function logout(): Promise<void> {
  await httpPost('/logout', undefined, NO_RECOVERY);
}
