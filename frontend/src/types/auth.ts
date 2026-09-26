/**
 * Auth types - C端用户认证（ruoyi-app @ :8081）
 */

/** 图形验证码 */
export interface CaptchaResult {
  captchaEnabled: boolean;
  uuid: string;
  /** base64 编码的 jpg（不含 data: 前缀） */
  img: string;
}

/** 当前登录用户信息（后端已脱敏，不含密码） */
export interface UserInfo {
  userId: string;
  userName: string;
  email: string;
  nickName?: string;
  avatar?: string;
}

/** 登录请求体（username 承载邮箱；服务端已不再要求验证码） */
export interface LoginBody {
  username: string;
  password: string;
}

/** 注册请求体 */
export interface RegisterBody {
  email: string;
  password: string;
  emailCode: string;
  code: string;
  uuid: string;
}

/** 发送邮箱验证码请求体 */
export interface EmailCodeBody {
  email: string;
  code: string;
  uuid: string;
}
