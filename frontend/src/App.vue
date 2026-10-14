<template>
  <router-view v-slot="{ Component }">
    <transition
      name="fade"
      mode="out-in"
    >
      <component :is="Component" />
    </transition>
  </router-view>
  <SeedreamCloseWarning
    :open="showCloseWarning"
    :count="closeWarningCount"
    @continue="showCloseWarning = false"
    @exit="confirmExit"
  />
  <!--
    开发期诊断面板（仅开发构建，见 src/debug/request-log.ts 的说明）。
    刻意挂在这里而不是 Header 里：Header 带 backdrop-blur，backdrop-filter 会让祖先
    成为 position:fixed 的包含块，面板会被压在 header 那个几十像素高的盒子里。
    Teleport 到 body 则彻底不受任何祖先样式影响。
  -->
  <Teleport
    v-if="showDebugPanel"
    to="body"
  >
    <DebugLogPanel />
  </Teleport>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue';
import { useConfigStore } from '@/stores/config';
import { useAuthStore } from '@/stores/auth';
import { useAgentControl } from '@/composables/useAgentControl';
import { api } from '@/api';
import SeedreamCloseWarning from '@/components/seedream/SeedreamCloseWarning.vue';
import DebugLogPanel from '@/components/layout/DebugLogPanel.vue';

/** Keep the diagnostic panel and its shortcut limited to development builds. */
const showDebugPanel = ref(import.meta.env.DEV);

function handleDebugPanelShortcut(event: KeyboardEvent) {
  if (
    event.defaultPrevented ||
    event.isComposing ||
    !event.metaKey ||
    event.ctrlKey ||
    event.altKey ||
    event.shiftKey ||
    event.key.toLowerCase() !== 'b'
  ) return;

  event.preventDefault();
  if (!event.repeat) showDebugPanel.value = !showDebugPanel.value;
}

const configStore = useConfigStore();
const authStore = useAuthStore();
useAgentControl();

const showCloseWarning = ref(false);
const closeWarningCount = ref(0);

function handleCloseRequested(event: Event) {
  const detail = (event as CustomEvent<{ count: number }>).detail;
  closeWarningCount.value = typeof detail?.count === 'number' ? detail.count : 0;
  showCloseWarning.value = true;
}

async function confirmExit() {
  showCloseWarning.value = false;
  await api.seedream.confirmExit();
}

onMounted(() => {
  configStore.loadConfig();
  authStore.init();
  window.addEventListener('seedream-close-requested', handleCloseRequested);
  if (import.meta.env.DEV) window.addEventListener('keydown', handleDebugPanelShortcut);
});

onUnmounted(() => {
  window.removeEventListener('seedream-close-requested', handleCloseRequested);
  if (import.meta.env.DEV) window.removeEventListener('keydown', handleDebugPanelShortcut);
});
</script>

<style>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
