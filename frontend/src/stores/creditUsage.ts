import { defineStore } from 'pinia';
import { computed, ref, watch } from 'vue';
import { httpGet, httpPost } from '@/api/http';
import { useAuthStore } from '@/stores/auth';
import { useBillingStore } from '@/stores/billing';

export interface CreditCombination {
  context: { platform: string; mediaType: string; model: string; resolution: string | null; durationSec: number | null; sizeLabel: string | null };
  quote: number;
  generalAvailable: number;
  bonusAvailable: number;
  message: string;
  canSubmit: boolean;
}
export interface CreditUsageAccount {
  generalAvailable: number;
  bonusAvailable: number;
  totalAvailable: number;
  buckets: { bucket: { bucketId: string; remainAmount: number; creditClass?: string }; usageSummary: string; message?: string }[];
}
interface Availability {
  combinations: CreditCombination[];
  account: CreditUsageAccount;
  asOf: string;
  refreshAt: string;
}

/** Server-calculated eligibility, isolated by account and bounded by expiry. */
export const useCreditUsageStore = defineStore('credit-usage', () => {
  const auth = useAuthStore();
  const billing = useBillingStore();
  const data = ref<Availability | null>(null);
  const loading = ref(false);
  const error = ref('');
  const expired = ref(true);
  let revision = 0;
  let pending: Promise<void> | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  const ready = computed(() => !!data.value && !expired.value && !error.value);
  function reset() {
    revision += 1;
    pending = null;
    data.value = null;
    expired.value = true;
    error.value = '';
    loading.value = false;
    if (timer) clearTimeout(timer);
    timer = null;
  }
  async function refresh(): Promise<void> {
    if (!auth.isLoggedIn) { reset(); return; }
    if (pending) return pending;
    const id = ++revision;
    const token = auth.token;
    loading.value = true;
    expired.value = true;
    error.value = '';
    pending = (async () => {
      try {
        const result = await httpGet<{ data: Availability }>('/app/credit/v2/availability');
        if (id !== revision || token !== auth.token) return;
        data.value = result.data;
        expired.value = false;
        if (timer) clearTimeout(timer);
        const asOf = new Date(result.data.asOf).getTime();
        const next = new Date(result.data.refreshAt).getTime();
        const delay = Math.min(60_000, Math.max(250, Number.isFinite(next - asOf) ? next - asOf : 30_000));
        timer = setTimeout(() => { expired.value = true; void refresh(); }, delay);
      } catch (e) {
        if (id !== revision) return;
        expired.value = true;
        error.value = e instanceof Error ? e.message : '积分可用范围加载失败';
      } finally {
        if (id === revision) { loading.value = false; pending = null; }
      }
    })();
    return pending;
  }
  async function quote(media: 'image' | 'video', request: Record<string, unknown>) {
    const token = auth.token;
    const result = await httpPost<{ data: { quote: number; canSubmit: boolean; message: string; bonusPayment: number; generalPayment: number } }>(`/app/credit/v2/quote/${media}`, request);
    if (token !== auth.token) throw new Error('登录状态已变化，请重新获取报价');
    return result.data;
  }
  function matching(media: string, model: string, resolution?: string, duration?: number) {
    return (data.value?.combinations ?? []).filter(row => {
      const c = row.context;
      return c.mediaType === media && c.model === model
        && (!resolution || (media === 'image' ? c.sizeLabel : c.resolution) === resolution)
        && (duration === undefined || c.durationSec === duration);
    });
  }
  function canPay(media: string, model: string, resolution?: string, duration?: number, count = 1) {
    return ready.value && matching(media, model, resolution, duration).some(row => row.generalAvailable + row.bonusAvailable >= row.quote * count);
  }
  watch(() => auth.token, () => { reset(); if (auth.isLoggedIn) void refresh(); });
  watch(() => auth.isLoggedIn, loggedIn => { if (loggedIn) void refresh(); else reset(); }, { immediate: true });
  watch(() => billing.account, () => { expired.value = true; if (auth.isLoggedIn) void refresh(); });
  if (typeof window !== 'undefined') {
    window.addEventListener('focus', () => { if (auth.isLoggedIn) void refresh(); });
    document.addEventListener('visibilitychange', () => { if (!document.hidden && auth.isLoggedIn) void refresh(); });
    const states = new Map<string, string>();
    const generationChanged = (event: Event) => {
      const item = (event as CustomEvent<{ source?: string; request?: { source?: string }; local_id?: string; status?: string; remote_status?: string; updated_at?: string }>).detail;
      if (!item || (item.source ?? item.request?.source) !== 'forfuner-ai' || !item.local_id) return;
      const status = item.status ?? item.remote_status;
      const fingerprint = `${status}:${item.updated_at}`;
      if (states.get(item.local_id) === fingerprint) return;
      states.set(item.local_id, fingerprint);
      if (states.size > 500) states.delete(states.keys().next().value!);
      expired.value = true;
      void billing.refreshAccount();
      void refresh();
      // Video refunds can follow the terminal status in the money projector.
      if (['completed', 'succeeded', 'failed', 'cancelled', 'expired'].includes(String(status).toLowerCase())) {
        setTimeout(() => { if (auth.isLoggedIn) { void billing.refreshAccount(); void refresh(); } }, 6000);
      }
    };
    window.addEventListener('seedance-task-updated', generationChanged);
    window.addEventListener('seedream-batch-updated', generationChanged);
  }
  return { data, loading, error, ready, refresh, reset, quote, matching, canPay };
});
