/**
 * 开发期诊断：请求 / 激活日志
 *
 * 为什么会有这个：pywebview 在 Windows 上刻意关闭了 devtools
 * （`backend/main.py`：`debug=True` 会卡死 WebView2），所以排查"什么时候发了什么请求、
 * 结果如何、以及**为什么没发**"时，浏览器控制台这条路是不通的。这个模块提供一条
 * 屏上通道，配合 `DebugLogPanel.vue` 显示。
 *
 * 生产构建的实际代价（实测 `npm run build` 后 grep 产物确认，勿凭直觉推断）：
 *   - 本模块 `logEvent` 的**调用点会被消除** —— `import.meta.env.DEV` 静态替换为 false
 *     后打包器判定为空操作，连同传入的消息字符串一并去掉；
 *   - 但 `DebugLogPanel.vue` **仍会被打包**（App.vue 是静态 import，`v-if="false"`
 *     摇不掉它），只有模板文本那点体量，且不会渲染。
 * 换句话说：近乎零成本，但不是零。
 *
 * 用法：在需要留痕的地方调 `logEvent('...')`；面板会自动显示，最新在最上面。
 */
import { ref } from 'vue';

export type LogLevel = 'info' | 'ok' | 'warn' | 'error';

export interface RequestLogEntry {
  id: number;
  at: Date;
  text: string;
  level: LogLevel;
}

const MAX_ENTRIES = 300;
const ENABLED = import.meta.env.DEV;

let seq = 0;

/** 最新的在前 */
export const requestLogEntries = ref<RequestLogEntry[]>([]);

export function logEvent(text: string, level: LogLevel = 'info'): void {
  if (!ENABLED) return;
  requestLogEntries.value = [
    { id: ++seq, at: new Date(), text, level },
    ...requestLogEntries.value,
  ].slice(0, MAX_ENTRIES);
}

export function clearRequestLog(): void {
  requestLogEntries.value = [];
}
