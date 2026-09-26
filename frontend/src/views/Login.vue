<template>
  <div class="min-h-screen bg-dark-bg">
    <Header
      minimal
      page-aligned
    />

    <div class="max-w-md mx-auto mt-16 px-4">
      <Card padding="lg">
        <template #header>
          <h2 class="text-lg font-semibold text-white">
            {{ t('auth.loginTitle') }}
          </h2>
        </template>

        <form
          class="space-y-4"
          @submit.prevent="onSubmit"
        >
          <!-- Error banner -->
          <div
            v-if="errorMessage"
            class="p-3 bg-danger/10 border border-danger/30 rounded-lg"
          >
            <div class="flex items-center gap-2 text-danger">
              <AlertCircle class="w-5 h-5 shrink-0" />
              <span class="font-medium">{{ errorMessage }}</span>
            </div>
          </div>

          <Input
            v-model="form.email"
            type="email"
            :label="t('auth.email')"
            :placeholder="t('auth.emailPlaceholder')"
            :error="errors.email"
            autocomplete="email"
          />

          <Input
            v-model="form.password"
            type="password"
            :label="t('auth.password')"
            :placeholder="t('auth.passwordPlaceholder')"
            :error="errors.password"
            autocomplete="current-password"
          />

          <label class="flex items-center gap-2 text-sm text-gray-300 cursor-pointer select-none">
            <input
              v-model="remember"
              type="checkbox"
              class="w-4 h-4 rounded border-dark-border bg-dark-bg accent-primary"
              data-test="remember-checkbox"
            >
            {{ t('auth.rememberMe') }}
          </label>

          <Button
            type="submit"
            variant="primary"
            block
            :loading="authStore.loading"
          >
            {{ t('auth.login') }}
          </Button>

          <div class="text-center">
            <router-link
              :to="{ path: '/register', query: route.query }"
              class="text-sm text-primary hover:underline"
            >
              {{ t('auth.noAccount') }}
            </router-link>
          </div>
        </form>
      </Card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { AlertCircle } from 'lucide-vue-next';
import Header from '@/components/layout/Header.vue';
import Card from '@/components/common/Card.vue';
import Input from '@/components/common/Input.vue';
import Button from '@/components/common/Button.vue';
import { useAuthStore } from '@/stores/auth';
import { NETWORK_ERROR } from '@/api/http';
import { loadCredentials } from '@/api/credentialVault';
import { applyPrefill, hasPrefillableFields } from '@/login-prefill';
import { logEvent } from '@/debug/request-log';

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

const form = reactive({
  email: (route.query.email as string) || '',
  password: ''
});
const errors = reactive({ email: '', password: '' });
const submitError = ref('');
// 默认勾选：把"记住账号密码"由主动选择加入改为主动选择退出。
// 与登出保留凭证、登录页回填合起来才构成完整体验——不主动取消，登出后回来就是填好的。
// 代价（同一 Windows 账号下的其他人点一下即可登录）见 design.md D5。
const remember = ref(true);

const errorMessage = computed(() =>
  submitError.value === NETWORK_ERROR ? t('auth.networkError') : submitError.value
);

function validate(): boolean {
  errors.email = form.email
    ? (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email) ? '' : t('auth.emailInvalid'))
    : t('auth.emailRequired');
  errors.password = form.password ? '' : t('auth.passwordRequired');
  return !errors.email && !errors.password;
}

async function onSubmit() {
  submitError.value = '';
  if (!validate()) return;
  try {
    await authStore.login(form.email, form.password, remember.value);
    router.push((route.query.redirect as string) || '/');
  } catch (e) {
    submitError.value = e instanceof Error ? e.message : String(e);
  }
}

// ---------- 回填「记住账号密码」 ----------
// loadCredentials 需要经 pywebview 桥解密，最长等 5 秒，所以是异步的：
// 页面先渲染空表单，解密回来再填。绝不阻塞渲染、也绝不自动提交。
onMounted(async () => {
  const creds = await loadCredentials();
  if (!creds) {
    logEvent('登录页：无可回填的凭证');
    return;
  }
  // 只填空字段：桥慢时用户可能已经在输入，覆盖会把他刚敲的内容冲掉
  const next = applyPrefill({ email: form.email, password: form.password }, creds);
  const changed = hasPrefillableFields({ email: form.email, password: form.password }, creds);
  form.email = next.email;
  form.password = next.password;
  logEvent(
    changed ? '登录页：已回填记住的账号密码' : '登录页：表单已有内容，未覆盖',
    changed ? 'ok' : 'info',
  );
});
</script>
