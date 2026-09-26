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
            {{ t('auth.registerTitle') }}
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
            autocomplete="new-password"
          />

          <Input
            v-model="form.confirmPassword"
            type="password"
            :label="t('auth.confirmPassword')"
            :placeholder="t('auth.confirmPasswordPlaceholder')"
            :error="errors.confirmPassword"
            autocomplete="new-password"
          />

          <div v-if="captchaEnabled">
            <Input
              v-model="form.code"
              type="text"
              :label="t('auth.captcha')"
              :placeholder="t('auth.captchaPlaceholder')"
              :error="errors.code"
              autocomplete="off"
            />
            <img
              v-if="captchaImg"
              :src="captchaImg"
              :title="t('auth.refreshCaptcha')"
              alt=""
              class="mt-2 h-10 rounded border border-dark-border cursor-pointer"
              @click="refreshCaptcha"
            >
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-300 mb-2">
              {{ t('auth.emailCode') }}
            </label>
            <div class="flex gap-2">
              <div class="flex-1">
                <Input
                  v-model="form.emailCode"
                  type="text"
                  :placeholder="t('auth.emailCodePlaceholder')"
                  :error="errors.emailCode"
                  autocomplete="off"
                />
              </div>
              <Button
                variant="secondary"
                :disabled="countdown > 0"
                :loading="sendingCode"
                @click="onSendEmailCode"
              >
                {{ countdown > 0 ? t('auth.resendAfter', { s: countdown }) : t('auth.sendEmailCode') }}
              </Button>
            </div>
          </div>

          <Button
            type="submit"
            variant="primary"
            block
            :loading="authStore.loading"
          >
            {{ t('auth.register') }}
          </Button>

          <div class="text-center">
            <router-link
              :to="{ path: '/login', query: route.query }"
              class="text-sm text-primary hover:underline"
            >
              {{ t('auth.hasAccount') }}
            </router-link>
          </div>
        </form>
      </Card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { AlertCircle } from 'lucide-vue-next';
import Header from '@/components/layout/Header.vue';
import Card from '@/components/common/Card.vue';
import Input from '@/components/common/Input.vue';
import Button from '@/components/common/Button.vue';
import { useAuthStore } from '@/stores/auth';
import { NETWORK_ERROR } from '@/api/http';

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

const form = reactive({
  email: (route.query.email as string) || '',
  password: '',
  confirmPassword: '',
  code: '',
  emailCode: ''
});
const errors = reactive({ email: '', password: '', confirmPassword: '', code: '', emailCode: '' });
const submitError = ref('');

const captchaEnabled = ref(false);
const captchaUuid = ref('');
const captchaImg = ref('');

const sendingCode = ref(false);
const countdown = ref(0);
let countdownTimer: number | undefined;

const errorMessage = computed(() =>
  submitError.value === NETWORK_ERROR ? t('auth.networkError') : submitError.value
);

async function refreshCaptcha() {
  try {
    const res = await authStore.fetchCaptcha();
    captchaEnabled.value = res.captchaEnabled;
    captchaUuid.value = res.uuid || '';
    captchaImg.value = res.img ? `data:image/jpeg;base64,${res.img}` : '';
    form.code = '';
  } catch (e) {
    submitError.value = e instanceof Error ? e.message : String(e);
  }
}

function validateEmail(): boolean {
  errors.email = form.email
    ? (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email) ? '' : t('auth.emailInvalid'))
    : t('auth.emailRequired');
  return !errors.email;
}

async function onSendEmailCode() {
  submitError.value = '';
  errors.code = '';
  if (!validateEmail()) return;
  if (captchaEnabled.value && !form.code) {
    errors.code = t('auth.captchaRequired');
    return;
  }
  sendingCode.value = true;
  try {
    await authStore.sendEmailCode(form.email, form.code, captchaUuid.value);
    startCountdown();
  } catch (e) {
    submitError.value = e instanceof Error ? e.message : String(e);
    refreshCaptcha();
  } finally {
    sendingCode.value = false;
  }
}

function startCountdown() {
  countdown.value = 60;
  countdownTimer = window.setInterval(() => {
    countdown.value -= 1;
    if (countdown.value <= 0 && countdownTimer !== undefined) {
      window.clearInterval(countdownTimer);
      countdownTimer = undefined;
    }
  }, 1000);
}

function validate(): boolean {
  const emailOk = validateEmail();
  errors.password = form.password
    ? (form.password.length >= 6 ? '' : t('auth.passwordTooShort'))
    : t('auth.passwordRequired');
  errors.confirmPassword = form.confirmPassword === form.password ? '' : t('auth.passwordMismatch');
  errors.code = captchaEnabled.value && !form.code ? t('auth.captchaRequired') : '';
  errors.emailCode = form.emailCode ? '' : t('auth.emailCodeRequired');
  return emailOk && !errors.password && !errors.confirmPassword && !errors.code && !errors.emailCode;
}

async function onSubmit() {
  submitError.value = '';
  if (!validate()) return;
  try {
    await authStore.register(form.email, form.password, form.emailCode, form.code, captchaUuid.value);
    router.push({ path: '/login', query: { email: form.email } });
  } catch (e) {
    submitError.value = e instanceof Error ? e.message : String(e);
    refreshCaptcha();
  }
}

onMounted(refreshCaptcha);

onUnmounted(() => {
  if (countdownTimer !== undefined) {
    window.clearInterval(countdownTimer);
  }
});
</script>
