/**
 * 积分桶行 - 单个积分来源的明细展示
 *
 * Shows source name, acquisition date, remaining balance and expiry.
 * 已用完（remain=0）整行置灰；剩余有效期 ≤7 天到期时间醒目展示。
 * Ordering is supplied by the V2 account endpoint.
 */
<script setup lang="ts">
import { computed, ref, onBeforeUnmount } from 'vue';
import { HelpCircle } from 'lucide-vue-next';
import { useI18n } from 'vue-i18n';
import type { CreditBucket } from '@/api/billing';
import { EXPIRING_DAYS } from '@/stores/billing';

const props = defineProps<{
  bucket: CreditBucket;
  scope?: string;
  scopeMessage?: string;
}>();

const { t } = useI18n();
const scopeOpen = ref(false);
let closeTimer: ReturnType<typeof setTimeout> | null = null;
function keepScope() { if (closeTimer) clearTimeout(closeTimer); }
function closeScope() { keepScope(); closeTimer = setTimeout(() => { scopeOpen.value = false; }, 120); }
onBeforeUnmount(keepScope);
const scopePosition = ref({ left: '0px', top: '0px' });
const scopeLines = computed(() => {
  const models = new Map<string, string[]>();
  for (const item of (props.scope ?? '').split('；').filter(Boolean)) {
    const [model, ...spec] = item.split(' · ');
    models.set(model, [...(models.get(model) ?? []), ...spec]);
  }
  return [...models].map(([model, specs]) => ({ model, specs: specs.join('；') }));
});
function showScope(event: Event) {
  keepScope();
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
  const height = Math.min(360, 50 + scopeLines.value.length * 48);
  scopePosition.value = {
    left: `${Math.max(12, Math.min(rect.right - 304, window.innerWidth - 316))}px`,
    top: `${Math.max(12, Math.min(rect.bottom + 8, window.innerHeight - height - 12))}px`,
  };
  scopeOpen.value = true;
}

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

/** 待生效 = 续费排队中的桶（生效日在未来） */
const isPending = computed(() => {
  const eff = parseDate(props.bucket.effectiveFrom);
  return !!eff && eff.getTime() > Date.now();
});

const remainingPercent = computed(() =>
  isPending.value || total.value <= 0
    ? 0
    : Math.min(100, Math.round((remain.value / total.value) * 100))
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
const amountLabel = computed(() =>
  isPending.value
    ? t('billing.pendingOfTotal', { total: total.value.toLocaleString() })
    : t('billing.remainingOfTotal', { remain: remain.value.toLocaleString(), total: total.value.toLocaleString() })
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
    : t('billing.expiresAt', { date: fmtDate(props.bucket.expireTime) });
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
        :style="{ width: remainingPercent + '%' }"
      />
    </div>

    <div class="mt-1.5 flex items-baseline justify-between gap-3 text-[11.5px] tabular-nums">
      <span class="text-gray-500">{{ amountLabel }}</span>
      <span
        :class="isPending ? 'text-amber-600' : isUsedUp ? 'text-gray-500' : isExpiring ? 'font-bold text-primary' : 'text-gray-500'"
        data-test="bucket-expire"
      >
        {{ remainLabel }}
      </span>
    </div>
    <div v-if="scope" class="mt-2 flex min-w-0 items-center gap-1.5 border-t border-dark-border/60 pt-2 text-[11px] text-gray-400" data-test="bucket-model-scope">
      <span class="min-w-0 flex-1 truncate">{{ t('creditUsage.availableModels') }}{{ scope }}</span>
      <button
        type="button"
        class="shrink-0 rounded text-gray-500 hover:text-gray-300 focus-visible:outline focus-visible:outline-1 focus-visible:outline-primary"
        :aria-label="t('creditUsage.viewModels')"
        :aria-describedby="scopeOpen ? `bucket-scope-${bucket.bucketId}` : undefined"
        @mouseenter="showScope" @mouseleave="closeScope"
        @focus="showScope" @blur="closeScope" @keydown.esc="scopeOpen = false"
      ><HelpCircle class="h-3.5 w-3.5" /></button>
    </div>
    <p v-if="scopeMessage" class="mt-1 text-[11px] text-warning">{{ scopeMessage }}</p>
    <Teleport to="body">
      <div v-if="scopeOpen" :id="`bucket-scope-${bucket.bucketId}`" role="tooltip"
        class="fixed z-[100] w-[304px] max-w-[calc(100vw-24px)] rounded-lg border border-dark-border bg-dark-surface p-3 text-xs text-gray-200 shadow-xl"
        @mouseenter="keepScope" @mouseleave="closeScope"
        :style="scopePosition">
        <p class="mb-2 font-semibold">{{ t('creditUsage.availableModels') }}</p>
        <ul class="max-h-72 space-y-2 overflow-y-auto">
          <li v-for="line in scopeLines" :key="line.model" class="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-3 border-b border-dark-border/50 pb-2 last:border-0 last:pb-0">
            <span class="break-words font-medium">{{ line.model }}</span>
            <span class="break-words text-gray-400">{{ line.specs }}</span>
          </li>
        </ul>
      </div>
    </Teleport>
  </div>
</template>
