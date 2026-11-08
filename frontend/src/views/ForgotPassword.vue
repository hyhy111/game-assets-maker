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
            {{ t('auth.forgotTitle') }}
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

          <!-- Success banner -->
          <div
            v-if="successMessage"
            class="p-3 bg-primary/10 border border-primary/30 rounded-lg text-primary"
          >
            {{ successMessage }}
          </div>

          <!-- Neutral hint (例如：二次发码前需要重新输入图形验证码) -->
          <div
            v-if="hintMessage"
            class="p-3 bg-dark-surface border border-dark-border rounded-lg text-gray-300 text-sm"
          >
            {{ hintMessage }}
          </div>

          <Input
            v-model="form.email"
            type="email"
            :label="t('auth.email')"
            :placeholder="t('auth.emailPlaceholder')"
            :error="errors.email"
            autocomplete="email"
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

          <Input
            v-model="form.password"
            type="password"
            :label="t('auth.newPassword')"
            :placeholder="t('auth.newPasswordPlaceholder')"
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

          <Button
            type="submit"
            variant="primary"
            block
            :loading="authStore.loading"
          >
            {{ t('auth.resetPassword') }}
          </Button>

          <div class="text-center">
            <router-link
              :to="{ path: '/login', query: { email: form.email || undefined } }"
              class="text-sm text-primary hover:underline"
            >
              {{ t('auth.backToLogin') }}
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
  code: '',
  emailCode: '',
  password: '',
  confirmPassword: ''
});
const errors = reactive({ email: '', code: '', emailCode: '', password: '', confirmPassword: '' });
const submitError = ref('');
const successMessage = ref('');
const hintMessage = ref('');

const captchaEnabled = ref(false);
const captchaUuid = ref('');
const captchaImg = ref('');
// 服务端在发码时一次性消费图形验证码：成功后旧图已失效，但不能立刻清空输入框吓用户一跳。
// 标记下来，等用户真的需要再次发码时再换图、再要求重新输入。
const captchaConsumed = ref(false);

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
  successMessage.value = '';
  hintMessage.value = '';
  errors.code = '';
  if (!validateEmail()) return;

  // 兜底：倒计时期间按钮是禁用的，正常走不到这里；万一走到，先换图再说
  if (captchaEnabled.value && captchaConsumed.value) {
    resetConsumedCaptcha();
    return;
  }

  if (captchaEnabled.value && !form.code) {
    errors.code = t('auth.captchaRequired');
    return;
  }
  sendingCode.value = true;
  try {
    await authStore.sendResetEmailCode(form.email, form.code, captchaUuid.value);
    // 文案与服务端一致：不区分邮箱是否注册
    successMessage.value = t('auth.resetCodeSent');
    // 服务端已消费这张图形码，但**不在这里换图/清输入**：用户当前的目标是提交新密码，
    // 图形码不再参与提交。等倒计时结束、需要再次发码时再换成新图（见 resetConsumedCaptcha）。
    captchaConsumed.value = true;
    startCountdown();
  } catch (e) {
    submitError.value = e instanceof Error ? e.message : String(e);
    refreshCaptcha();
  } finally {
    sendingCode.value = false;
  }
}

/**
 * 倒计时结束：若上一张图形码已被服务端消费，换新图并提示重新输入。
 * 此时清空图形码输入框是合理的——旧答案确实已经失效，且用户正准备再次发码。
 */
async function resetConsumedCaptcha() {
  if (!captchaEnabled.value || !captchaConsumed.value) return;
  captchaConsumed.value = false;
  successMessage.value = '';
  await refreshCaptcha();
  hintMessage.value = t('auth.captchaRenewed');
}

function startCountdown() {
  countdown.value = 60;
  countdownTimer = window.setInterval(() => {
    countdown.value -= 1;
    if (countdown.value <= 0 && countdownTimer !== undefined) {
      window.clearInterval(countdownTimer);
      countdownTimer = undefined;
      void resetConsumedCaptcha();
    }
  }, 1000);
}

function validate(): boolean {
  const emailOk = validateEmail();
  errors.emailCode = form.emailCode ? '' : t('auth.emailCodeRequired');
  errors.password = form.password
    ? (form.password.length >= 6 ? '' : t('auth.passwordTooShort'))
    : t('auth.passwordRequired');
  errors.confirmPassword = form.confirmPassword === form.password ? '' : t('auth.passwordMismatch');
  return emailOk && !errors.emailCode && !errors.password && !errors.confirmPassword;
}

async function onSubmit() {
  submitError.value = '';
  successMessage.value = '';
  hintMessage.value = '';
  if (!validate()) return;
  try {
    await authStore.resetPassword(form.email, form.emailCode, form.password, form.confirmPassword);
    authStore.afterPasswordReset();
    router.push({ path: '/login', query: { email: form.email, reset: '1' } });
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
