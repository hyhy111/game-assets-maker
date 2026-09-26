/**
 * 积分桶行 - 单个积分来源的明细展示
 *
 * 展示：积分名字（skuName 快照）、获得时间、已用/共 N 进度条、剩余与单桶到期。
 * 已用完（remain=0）整行置灰；剩余有效期 ≤7 天到期时间醒目展示。
 * 排序由 store 保证（最先到期在前）。
 */
<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type { CreditBucket } from '@/api/billing';
import { EXPIRING_DAYS } from '@/stores/billing';

const props = defineProps<{
  bucket: CreditBucket;
}>();

const { t } = useI18n();

/** "yyyy-MM-dd HH:mm:ss"（GMT+8 序列化）→ Date，按本地时区解析 */
function parseDate(s?: string | null): Date | null {
  if (!s) return null;
  const d = new Date(String(s).replace(' ', 'T'));
  return isNaN(d.getTime()) ? null : d;
}

/** 短日期：当年 MM-dd，跨年 yyyy-MM-dd */
function fmtDate(s?: string | null): string {
  const d = parseDate(s);
  if (!d) return '-';
  const p = (n: number) => String(n).padStart(2, '0');
  const ymd = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
  return d.getFullYear() === new Date().getFullYear() ? ymd.slice(5) : ymd;
}

const total = computed(() => Number(props.bucket.totalAmount || 0));
const remain = computed(() => Number(props.bucket.remainAmount || 0));
const used = computed(() => Math.max(0, total.value - remain.value));

/** 待生效 = 续费排队中的桶（生效日在未来） */
const isPending = computed(() => {
  const eff = parseDate(props.bucket.effectiveFrom);
  return !!eff && eff.getTime() > Date.now();
});

const usedPercent = computed(() =>
  isPending.value || total.value <= 0
    ? 0
    : Math.min(100, Math.round((used.value / total.value) * 100))
);
const isUsedUp = computed(() => !isPending.value && remain.value === 0);

const isExpiring = computed(() => {
  if (isPending.value || isUsedUp.value) return false;
  const d = parseDate(props.bucket.expireTime);
  if (!d) return false;
  return (d.getTime() - Date.now()) / 86400000 <= EXPIRING_DAYS;
});

const acquiredLabel = computed(() =>
  isPending.value
    ? t('billing.pendingTag')
    : t('billing.acquired', { date: fmtDate((props.bucket as { createTime?: string }).createTime ?? props.bucket.effectiveFrom) })
);
const usedLabel = computed(() =>
  isPending.value
    ? t('billing.pendingOfTotal', { total: total.value.toLocaleString() })
    : t('billing.usedOfTotal', { used: used.value.toLocaleString(), total: total.value.toLocaleString() })
);
const remainLabel = computed(() => {
  if (isPending.value) {
    return t('billing.pendingWindow', {
      from: fmtDate(props.bucket.effectiveFrom),
      to: fmtDate(props.bucket.expireTime),
    });
  }
  return isUsedUp.value
    ? t('billing.usedUp')
    : t('billing.remainingExpires', { remain: remain.value.toLocaleString(), date: fmtDate(props.bucket.expireTime) });
});
</script>

<template>
  <div
    class="rounded-lg border border-dark-border bg-dark-bg/60 px-3 py-2.5"
    :class="isUsedUp ? 'opacity-50' : isPending ? 'opacity-70' : ''"
    data-test="credit-bucket-row"
  >
    <div class="flex items-baseline justify-between gap-3">
      <span
        class="truncate text-[13px] font-semibold"
        :class="isPending ? 'text-gray-400' : 'text-gray-200'"
      >
        {{ bucket.skuName || t('billing.fallbackName') }}
      </span>
      <span
        v-if="isPending"
        class="shrink-0 rounded-full border border-dashed border-primary/50 px-2 py-0.5 text-[10.5px] font-bold text-primary"
        data-test="bucket-pending-tag"
      >{{ acquiredLabel }}</span>
      <span
        v-else
        class="shrink-0 text-[11px] text-gray-500"
      >{{ acquiredLabel }}</span>
    </div>

    <div class="mt-2 h-1.5 overflow-hidden rounded-full bg-dark-border/60">
      <div
        class="h-full rounded-full transition-[width] duration-700"
        :class="isUsedUp || isPending ? 'bg-dark-border' : 'bg-gradient-to-r from-amber-600 to-primary'"
        :style="{ width: usedPercent + '%' }"
      />
    </div>

    <div class="mt-1.5 flex items-baseline justify-between gap-3 text-[11.5px] tabular-nums">
      <span class="text-gray-500">{{ usedLabel }}</span>
      <span
        :class="isPending ? 'text-amber-600' : isUsedUp ? 'text-gray-500' : isExpiring ? 'font-bold text-primary' : 'text-gray-500'"
        data-test="bucket-expire"
      >
        {{ remainLabel }}
      </span>
    </div>
  </div>
</template>
