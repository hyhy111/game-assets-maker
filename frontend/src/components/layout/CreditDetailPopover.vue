/**
 * 积分明细弹层 - 顶栏积分按钮的点击展开
 *
 * headlessui Popover：外击/再次点击关闭；打开时刷新 billing store。
 * 空态引导去订阅（emit subscribe，由 Header 打开落地页）。
 */
<script setup lang="ts">
import { computed } from 'vue';
import { Popover, PopoverButton, PopoverPanel } from '@headlessui/vue';
import { useI18n } from 'vue-i18n';
import { Coins } from 'lucide-vue-next';
import { useBillingStore } from '@/stores/billing';
import CreditBucketRow from './CreditBucketRow.vue';
import { useCreditUsageStore } from '@/stores/creditUsage';

const emit = defineEmits<{
  (e: 'subscribe'): void;
}>();

const { t } = useI18n();
const billingStore = useBillingStore();
const creditUsage = useCreditUsageStore();

const buckets = computed(() => billingStore.buckets);
const isEmpty = computed(() => buckets.value.length === 0);
const hasBonus = computed(() => creditUsage.ready && (creditUsage.data?.account.bonusAvailable ?? 0) > 0);
function bonusDetail(bucketId: string) {
  return creditUsage.ready ? creditUsage.data?.account.buckets.find(row => row.bucket.bucketId === bucketId && row.bucket.creditClass === 'BONUS' && row.bucket.remainAmount > 0) : undefined;
}

function onOpen() {
  // 打开即拉最新（支付回来/消耗后同步）
  billingStore.refreshAccount();
  void creditUsage.refresh();
}

function onSubscribe() {
  emit('subscribe');
}
</script>

<template>
  <Popover class="relative">
    <PopoverButton
      type="button"
      class="flex items-center gap-1 px-2 py-1 rounded-lg text-sm text-gray-300 hover:bg-dark-border transition-colors"
      :title="t('header.creditBalance')"
      data-test="credit-balance-button"
    >
      <Coins class="w-4 h-4 text-primary" />
      <span class="tabular-nums">{{ billingStore.totalAvailable === null ? '-' : billingStore.totalAvailable }}</span>
    </PopoverButton>

    <transition
      enter-active-class="transition duration-150 ease-out"
      enter-from-class="opacity-0 translate-y-1"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition duration-100 ease-in"
      leave-from-class="opacity-100 translate-y-0"
      leave-to-class="opacity-0 translate-y-1"
    >
      <PopoverPanel
        v-slot="{ close }"
        class="absolute right-0 mt-2 w-80 origin-top-right rounded-xl border border-dark-border bg-dark-surface shadow-lg shadow-black/50 focus:outline-none z-50"
        @vue:mounted="onOpen"
      >
        <div class="px-4 py-3 border-b border-dark-border">
          <p class="text-sm font-semibold text-white">{{ t('billing.title') }}</p>
          <p v-if="hasBonus" class="mt-1 text-xs text-gray-300">{{ t('creditUsage.balance', { general: creditUsage.data?.account.generalAvailable, bonus: creditUsage.data?.account.bonusAvailable }) }}</p>
        </div>

        <div
          v-if="isEmpty"
          class="px-4 py-8 text-center"
        >
          <p class="text-sm text-gray-500">{{ t('billing.empty') }}</p>
          <button
            type="button"
            class="mt-3 rounded-lg border border-primary/40 px-4 py-1.5 text-xs text-primary transition-colors hover:bg-primary/10"
            data-test="credit-empty-subscribe"
            @click="
              close();
              onSubscribe();
            "
          >
            {{ t('billing.emptyAction') }}
          </button>
        </div>

        <div
          v-else
          class="max-h-72 overflow-y-auto px-3 py-3 flex flex-col gap-2.5"
        >
          <div v-for="b in buckets" :key="b.bucketId">
            <CreditBucketRow :bucket="b" />
            <p v-if="bonusDetail(b.bucketId)" class="mt-1 px-2 text-xs text-gray-400">{{ t('creditUsage.bonusScope', { scope: bonusDetail(b.bucketId)?.usageSummary }) }}</p>
            <p v-if="bonusDetail(b.bucketId)?.message" class="px-2 text-xs text-warning">{{ bonusDetail(b.bucketId)?.message }}</p>
          </div>
        </div>
      </PopoverPanel>
    </transition>
  </Popover>
</template>
