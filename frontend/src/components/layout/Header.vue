<template>
  <header
    :class="[
      'bg-dark-surface border-b border-dark-border',
      sticky ? 'sticky top-0 z-30' : '',
    ]"
  >
    <div
      :class="[
        fullWidth ? 'w-full' : pageAligned ? 'mx-auto w-full max-w-[1320px] sm:px-6' : 'container mx-auto',
        'flex items-center justify-between px-4',
        sticky ? 'h-16 gap-6' : 'h-14',
      ]"
    >
      <div
        v-if="!minimal"
        class="flex items-center gap-4"
      >
        <h1
          class="flex items-end gap-2 text-lg font-semibold leading-none text-white"
          aria-label="Game Assets Maker"
        >
          <img
            :src="logoUrl"
            alt=""
            aria-hidden="true"
            class="h-5 w-5 object-contain"
          >
          <span>Game Assets Maker</span>
        </h1>

        <div
          v-if="projectStore.currentProject"
          class="flex items-center gap-2 text-sm text-gray-400"
        >
          <span class="text-gray-600">/</span>
          <span class="text-gray-300">{{ projectStore.currentProject.role }} / {{ projectStore.currentProject.action || projectStore.currentProject.name }}</span>
        </div>
      </div>
      <div v-else />

      <div class="ml-auto flex items-center gap-2">
        <!-- 账户簇（仅登录后显示）：积分明细弹层 + 订阅入口 + 用户菜单 -->
        <div
          v-if="isLoggedIn"
          class="flex items-center gap-1 mr-1"
        >
          <CreditDetailPopover @subscribe="goSubscribe" />

          <button
            type="button"
            class="flex items-center gap-1.5 px-2 py-1 rounded-lg text-sm bg-primary/20 text-primary hover:bg-primary/30 transition-colors"
            :title="subscribeTitle"
            data-test="subscribe-button"
            @click="goSubscribe"
          >
            <span>{{ subscribeLabel }}</span>
            <span
              v-if="expiryText"
              class="text-[11px] font-normal text-primary/80 tabular-nums"
              data-test="subscribe-expiry"
            >
              {{ expiryText }}
            </span>
          </button>

          <span
            v-if="subscribeError"
            class="text-xs text-red-400 max-w-40 truncate"
            :title="subscribeError"
          >
            {{ subscribeError }}
          </span>
        </div>

        <!-- 会话失效被打回游客态（非主动登出/未登录）：给一句提示，否则用户会莫名 -->
        <span
          v-if="!isLoggedIn && sessionExpired"
          class="text-xs text-amber-400 whitespace-nowrap"
          data-test="session-expired"
        >
          {{ t('header.sessionExpired') }}
        </span>

        <!-- Auth entry / user menu -->
        <button
          v-if="!isLoggedIn"
          type="button"
          class="rounded-lg p-2 text-[#ffbd5c] transition-colors hover:bg-dark-border hover:text-[#ffd08a]"
          :title="t('header.login')"
          @click="goLogin"
        >
          <CircleUserRound class="h-5 w-5" />
        </button>

        <Menu
          v-else
          as="div"
          class="relative"
        >
          <MenuButton
            type="button"
            class="w-8 h-8 rounded-full bg-primary/20 text-primary flex items-center justify-center text-sm font-medium hover:bg-primary/30 transition-colors"
            :title="userInfo?.email"
          >
            {{ userInitial }}
          </MenuButton>
          <MenuItems class="absolute right-0 mt-2 w-56 origin-top-right bg-dark-surface border border-dark-border rounded-lg shadow-lg focus:outline-none z-50">
            <div class="px-4 py-3 border-b border-dark-border">
              <p class="text-xs text-gray-500">
                {{ t('auth.loggedInAs') }}
              </p>
              <p class="text-sm text-gray-200 truncate">
                {{ userInfo?.email }}
              </p>
            </div>
            <MenuItem v-slot="{ active }">
              <button
                type="button"
                :class="[
                  'w-full flex items-center gap-2 px-4 py-2 text-sm transition-colors',
                  active ? 'bg-dark-border text-white' : 'text-gray-300'
                ]"
                @click="handleLogout"
              >
                <LogOut class="w-4 h-4" />
                {{ t('auth.logout') }}
              </button>
            </MenuItem>
          </MenuItems>
        </Menu>

        <button
          type="button"
          class="p-2 rounded-lg hover:bg-dark-border text-gray-400 hover:text-white transition-colors"
          :title="locale === 'zh-CN' ? 'Switch to English' : '切换到中文'"
          @click="toggleLocale"
        >
          <Globe class="w-5 h-5" />
        </button>

        <button
          v-if="projectStore.currentProject"
          :disabled="isProcessing"
          :class="[
            'p-2 rounded-lg transition-colors',
            isProcessing
              ? 'text-gray-600 cursor-not-allowed'
              : 'hover:bg-dark-border text-gray-400 hover:text-white'
          ]"
          :title="isProcessing ? t('common.processing') : t('header.openFolder')"
          @click="openProjectFolder"
        >
          <FolderOpen class="w-5 h-5" />
        </button>

        <button
          :disabled="isProcessing"
          :class="[
            'p-2 rounded-lg transition-colors',
            isProcessing
              ? 'text-gray-600 cursor-not-allowed'
              : 'hover:bg-dark-border text-gray-400 hover:text-white'
          ]"
          :title="isProcessing ? t('common.processing') : t('header.settings')"
          @click="openSettings"
        >
          <Settings class="w-5 h-5" />
        </button>

        <button
          :disabled="isProcessing"
          :class="[
            'p-2 rounded-lg transition-colors',
            isProcessing
              ? 'text-gray-600 cursor-not-allowed'
              : 'hover:bg-dark-border text-gray-400 hover:text-white'
          ]"
          :title="isProcessing ? t('common.processing') : t('header.backToProjects')"
          @click="goHome"
        >
          <Home class="w-5 h-5" />
        </button>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router';
import { storeToRefs } from 'pinia';
import { useI18n } from 'vue-i18n';
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { Menu, MenuButton, MenuItems, MenuItem } from '@headlessui/vue';
import { CircleUserRound, FolderOpen, Settings, Home, Globe, LogOut } from 'lucide-vue-next';
import { useProjectStore } from '@/stores/project';
import { useProcessStore } from '@/stores/process';
import { useAuthStore } from '@/stores/auth';
import { useBillingStore } from '@/stores/billing';
import { api } from '@/api';
import { toggleLocale } from '@/locales';
import { openSubscriptionPage } from '@/composables/useSubscriptionPage';
import { decideActivationRefresh } from '@/window-activation';
import CreditDetailPopover from './CreditDetailPopover.vue';

defineProps<{
  minimal?: boolean;
  fullWidth?: boolean;
  pageAligned?: boolean;
  /** 创作页变体：吸顶 + 更高栏 */
  sticky?: boolean;
}>();

const router = useRouter();
const projectStore = useProjectStore();
const processStore = useProcessStore();
const authStore = useAuthStore();
const billingStore = useBillingStore();
const { locale, t } = useI18n();

const { currentProject } = storeToRefs(projectStore);
const { isProcessing } = storeToRefs(processStore);
const { isLoggedIn, userInfo, sessionExpired } = storeToRefs(authStore);
const logoUrl = new URL('../../assets/logo-2.png', import.meta.url).href;

const userInitial = computed(() => (userInfo.value?.email?.[0] || '?').toUpperCase());

// ---------- 订阅入口状态化 ----------
/** 到期时间：统一 yyyy-MM-dd（同年也不省略年份，避免续费场景下与跨年混淆） */
function fmtDate(s?: string | null): string {
  if (!s) return '';
  const d = new Date(String(s).replace(' ', 'T'));
  if (isNaN(d.getTime())) return '';
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

const subscribeLabel = computed(() =>
  billingStore.subscriptionStatus?.hasSubscription ? t('header.renew') : t('header.subscribe')
);

/** 到期文本取队列末端（续费锚点），无则当前段到期 */
const expiryText = computed(() => {
  const st = billingStore.subscriptionStatus;
  if (!st?.hasSubscription) return '';
  const date = fmtDate(st.queueEnd ?? st.currentPeriodEnd);
  return date ? t('header.expiresAt', { date }) : '';
});

const subscribeTitle = computed(() =>
  expiryText.value ? `${t('header.subscribe')} · ${expiryText.value}` : t('header.subscribe')
);

// ---------- 账户数据（billing store：登录拉取 / 登出清零） ----------
watch(isLoggedIn, (val) => {
  if (val) {
    billingStore.refreshAll();
  } else {
    billingStore.reset();
  }
}, { immediate: true });

// 窗口重新激活即刷新账户数据：桌面端"用户切走又切回"是最可靠的"可能需要新数据"信号。
// focus 与 visibilitychange 都监听 —— pywebview 在 Windows 上关闭了 devtools
// （backend/main.py 注释：debug=True 会卡死 WebView2），无法直接观察"最小化→恢复"
// 到底触发哪个，两个都听最稳；重复由 store 的节流挡掉，不会产生多余请求。
const subOpenedAt = ref(0);

function handleWindowActivated(source: 'focus' | 'visibilitychange') {
  const decision = decideActivationRefresh({
    isLoggedIn: isLoggedIn.value,
    visibilityState: document.visibilityState,
    subOpenedAt: subOpenedAt.value,
    now: Date.now(),
  });
  if (!decision.refresh) return;

  if (decision.force) subOpenedAt.value = 0;
  billingStore.refreshOnActivation({ force: decision.force, source });
}

const onFocus = () => handleWindowActivated('focus');
const onVisibilityChange = () => handleWindowActivated('visibilitychange');

onMounted(() => {
  window.addEventListener('focus', onFocus);
  document.addEventListener('visibilitychange', onVisibilityChange);
});
onUnmounted(() => {
  window.removeEventListener('focus', onFocus);
  document.removeEventListener('visibilitychange', onVisibilityChange);
});

const subscribeError = ref('');
let subscribeErrorTimer: ReturnType<typeof setTimeout> | null = null;

function showSubscribeError(msg: string) {
  subscribeError.value = msg;
  if (subscribeErrorTimer) clearTimeout(subscribeErrorTimer);
  subscribeErrorTimer = setTimeout(() => { subscribeError.value = ''; }, 5000);
}

async function goSubscribe() {
  try {
    await openSubscriptionPage();
    subscribeError.value = '';
    // 记录开窗时间；用户付完款关窗回来后 focus 刷新余额与订阅状态
    subOpenedAt.value = Date.now();
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    showSubscribeError(msg === 'NETWORK_ERROR' ? t('common.networkError') : msg);
  }
}

function goLogin() {
  router.push({ path: '/login', query: { redirect: router.currentRoute.value.fullPath } });
}

async function handleLogout() {
  await authStore.logout();
  if (['/login', '/register'].includes(router.currentRoute.value.path)) {
    router.push('/');
  }
}

function openSettings() {
  if (isProcessing.value) return;
  router.push('/video-generation/settings');
}

async function openProjectFolder() {
  if (isProcessing.value) {
    return; // Prevent opening folder during processing
  }
  if (currentProject.value) {
    await api.system.openProjectFolder(currentProject.value.path);
  }
}

async function goHome() {
  if (isProcessing.value) {
    return; // Prevent navigation during processing
  }
  const failure = await router.push('/');
  if (!failure) projectStore.setCurrentProject(null);
}
</script>
