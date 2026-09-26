<!--
  开发期诊断面板（仅开发构建）

  pywebview 在 Windows 上关闭了 devtools，这个面板是观察"请求/激活"行为的屏上通道。
  由 App.vue 用 import.meta.env.DEV 守卫、并 Teleport 到 body 挂载（见 App.vue 中的
  说明：不能放在 Header 里，backdrop-filter 会成为 position:fixed 的包含块）。
  生产构建不会渲染它，也没有运行时开销。
-->
<script setup lang="ts">
import { computed, ref } from 'vue';
import { clearRequestLog, requestLogEntries, type LogLevel } from '@/debug/request-log';

const open = ref(true);
const entries = computed(() => requestLogEntries.value);

const LEVEL_CLASS: Record<LogLevel, string> = {
  info: 'text-gray-400',
  ok: 'text-green-400',
  warn: 'text-amber-400',
  error: 'text-red-400',
};

function fmt(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

defineExpose({ open });
</script>

<template>
  <div
    class="fixed bottom-3 left-3 z-[9999] flex w-[900px] max-w-[calc(100vw-1.5rem)] flex-col rounded-lg border border-dark-border bg-black/95 shadow-2xl"
    data-test="debug-log-panel"
  >
    <div class="flex items-center gap-3 border-b border-dark-border px-3 py-2">
      <span class="text-sm font-medium text-gray-200">请求 / 激活日志</span>
      <span class="text-xs text-gray-500">{{ entries.length }} 条</span>
      <button
        type="button"
        class="ml-auto rounded px-2 py-0.5 text-xs text-gray-400 hover:bg-dark-border hover:text-white"
        @click="clearRequestLog()"
      >
        清空
      </button>
      <button
        type="button"
        class="rounded px-2 py-0.5 text-xs text-gray-400 hover:bg-dark-border hover:text-white"
        @click="open = !open"
      >
        {{ open ? '收起' : '展开' }}
      </button>
    </div>

    <div
      v-if="open"
      class="max-h-[70vh] overflow-y-auto px-3 py-2"
    >
      <p
        v-if="entries.length === 0"
        class="py-3 text-xs text-gray-500"
      >
        暂无记录
      </p>
      <div
        v-for="e in entries"
        :key="e.id"
        class="flex gap-3 py-1 font-mono text-xs leading-snug"
      >
        <span class="shrink-0 text-gray-600">{{ fmt(e.at) }}</span>
        <span
          class="break-all"
          :class="LEVEL_CLASS[e.level]"
        >{{ e.text }}</span>
      </div>
    </div>
  </div>
</template>
