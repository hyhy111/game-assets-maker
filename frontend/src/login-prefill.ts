/**
 * 登录页回填决策
 *
 * 凭证解密要经 pywebview 桥、最长等 5 秒，所以回填是异步到达的。这段延迟里用户
 * 完全可能已经开始输入——因此"填哪些字段"必须是个显式判断，而不是无脑覆盖。
 * 抽成纯函数以便单测覆盖（组件里只留事件订阅与赋值）。
 */

export interface PrefillFields {
  email: string;
  password: string;
}

export interface SavedCredential {
  email: string;
  password: string;
}

/**
 * 计算回填后各字段应取的值：只填空字段，已有内容原样保留。
 *
 * @param current 回填到达时表单里的当前值（可能已被用户输入）
 * @param creds   解密得到的已保存凭证
 */
export function applyPrefill(current: PrefillFields, creds: SavedCredential): PrefillFields {
  return {
    email: current.email || creds.email,
    password: current.password || creds.password,
  };
}

/** 是否有字段确实需要回填（用于日志与"是否发生了回填"的判断） */
export function hasPrefillableFields(current: PrefillFields, creds: SavedCredential): boolean {
  const next = applyPrefill(current, creds);
  return next.email !== current.email || next.password !== current.password;
}
