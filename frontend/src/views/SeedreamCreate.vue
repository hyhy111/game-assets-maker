<template>
  <component :is="embedded ? 'div' : SeedreamShell">
    <form
      class="w-full"
      @submit.prevent="submit"
    >
      <section
        class="seedream-prompt-surface rounded-[24px] border border-[#3b3b3b] bg-[#1f1f1f] p-4 sm:p-5"
        :class="referenceDragActive ? 'ring-2 ring-primary' : ''"
        data-test="seedream-composer"
        @dragover="onReferenceDragOver"
        @dragleave="referenceDragActive = false"
        @drop.prevent="onReferenceDrop"
      >
        <div class="relative flex min-h-[282px] items-center gap-4 px-1 py-1">
          <div
            class="shrink-0"
            data-test="seedream-reference-card"
          >
            <SeedanceImagePicker
              class="rotate-[3deg] transition-transform duration-200 hover:-translate-y-0.5 hover:rotate-[1.5deg]"
              :model-value="form.reference_image || null"
              :preview-url="workspace.imagePreviewUrls.reference"
              :label="t('seedream.create.referenceImage')"
              :card-label="t('seedream.create.referenceImageShort')"
              :optional-label="t('seedream.create.optionalShort')"
              :help="t('seedream.create.referenceImageHelp')"
              help-id="seedream-reference-help"
              :select-label="t('seedream.create.selectReferenceImage')"
              :change-label="t('seedream.create.changeReferenceImage')"
              :remove-label="t('seedream.create.removeReferenceImage')"
              :selected-label="t('seedream.create.referenceSelected')"
              :drop-label="t('seedream.create.dropAsReference')"
              compact
              @select="selectReferenceImage"
              @clear="clearReferenceImage"
              @drop-image="dropCandidateReference"
              @drop-file="dropReferenceFile"
              @drop-error="referenceError = t($event)"
            />
          </div>
          <div class="relative min-w-0 flex-1 self-stretch">
            <textarea
              v-model="form.prompt"
              rows="3"
              class="h-full min-h-[82px] w-full resize-none bg-transparent px-1 py-1 pb-7 pr-10 text-base leading-7 text-[#e7e7e7] outline-none placeholder:text-[#747474]"
              :placeholder="t('seedream.create.promptPlaceholder')"
              data-test="seedream-prompt"
            />
            <button
              type="button"
              class="absolute right-0 top-0 rounded-lg p-2 text-[#777] transition-colors hover:bg-[#303030] hover:text-[#d8d8d8]"
              :title="copyTitle"
              @click="copyPrompt"
            >
              <Check
                v-if="copied"
                :size="16"
                aria-hidden="true"
              />
              <Copy
                v-else
                :size="16"
                aria-hidden="true"
              />
            </button>
            <div class="absolute bottom-0 right-0 flex items-center justify-end text-xs">
              <p
                class="group relative shrink-0 cursor-help tabular-nums"
                :class="promptOverLimit ? 'text-warning' : 'text-gray-500'"
                data-test="seedream-prompt-count"
              >
                {{ promptInfo.count }}/{{ promptInfo.limit }}
                {{ promptInfo.chinese ? t('seedream.ui.characters') : t('seedream.ui.words') }}
                <span
                  class="pointer-events-none absolute right-0 top-full z-50 mt-2 hidden w-64 rounded-xl border border-white/10 bg-[#222329] px-3 py-2 text-left text-xs font-normal leading-5 text-gray-300 shadow-2xl shadow-black/40 group-hover:block"
                  data-test="seedream-prompt-suggestion"
                >
                  {{ t('seedream.create.promptSuggestion') }}
                </span>
              </p>
            </div>
          </div>
        </div>

        <div
          v-if="capabilitiesBlocked"
          class="mt-3 flex flex-wrap items-center gap-3 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-warning"
          data-test="seedream-capabilities-blocked"
          role="alert"
        >
          <span>{{ workspace.capabilitiesError ? t('aiCreation.capabilitiesFailed', { message: workspace.capabilitiesError }) : t('aiCreation.capabilitiesLoading') }}</span>
          <button
            type="button"
            class="rounded-md border border-warning/40 px-2 py-0.5 text-xs transition-colors hover:bg-warning/20"
            data-test="seedream-capabilities-retry"
            @click="reloadCapabilities()"
          >
            {{ t('aiCreation.capabilitiesRetry') }}
          </button>
        </div>

        <div class="mt-4 flex flex-wrap items-center gap-2 border-t border-[#343434] pt-4">
          <div class="inline-flex h-10 items-center rounded-xl border border-[#414141] bg-[#2d2d2d] p-1">
            <button
              type="button"
              class="h-8 rounded-lg px-3 text-sm transition-colors"
              :class="creationMode === 'image' ? 'bg-primary text-dark-bg' : 'text-gray-400 hover:text-white'"
              data-test="creation-mode-image"
              @click="emit('change-mode', 'image')"
            >
              {{ t('aiCreation.imageMode') }}
            </button>
            <button
              type="button"
              class="h-8 rounded-lg px-3 text-sm transition-colors"
              :class="creationMode === 'video' ? 'bg-primary text-dark-bg' : 'text-gray-400 hover:text-white'"
              data-test="creation-mode-video"
              @click="emit('change-mode', 'video')"
            >
              {{ t('aiCreation.videoMode') }}
            </button>
          </div>

          <CreationModelSelect
            :model-value="form.model"
            :options="modelOptions"
            :label="t('seedream.create.model')"
            test-id="seedream-model"
            @update:model-value="selectModel"
          />

          <div class="relative">
            <button
              type="button"
              class="inline-flex h-10 items-center gap-2 rounded-xl border border-[#414141] bg-[#2d2d2d] px-3 text-sm text-gray-200 transition-colors hover:border-[#555] hover:bg-[#353535]"
              :class="parametersOpen ? 'border-primary/50 bg-white/[0.06]' : ''"
              :aria-expanded="parametersOpen"
              data-test="seedream-parameter-summary"
              @click="parametersOpen = !parametersOpen"
              @keydown.escape.stop="parametersOpen = false"
            >
              <Settings2
                :size="15"
                class="text-gray-400"
                aria-hidden="true"
              />
              <span>{{ form.ratio }}</span>
              <span class="text-gray-600">·</span>
              <span>{{ form.resolution }}</span>
              <span class="text-gray-600">·</span>
              <span>× {{ form.count }}</span>
              <ChevronDown
                :size="14"
                class="text-gray-500 transition-transform"
                :class="parametersOpen ? 'rotate-180' : ''"
                aria-hidden="true"
              />
            </button>

            <div
              v-show="parametersOpen"
              class="absolute right-0 top-full z-30 mt-3 w-[min(420px,calc(100vw-2rem))] rounded-2xl border border-[#3b3b3b] bg-[#1f1f1f] p-4 shadow-2xl shadow-black/50"
              data-test="seedream-parameter-panel"
              @keydown.escape.stop="parametersOpen = false"
            >
              <fieldset data-test="seedream-ratio">
                <legend class="mb-2 text-xs text-gray-500">
                  {{ t('seedream.create.ratio') }}
                </legend>
                <div class="grid grid-cols-5 gap-1 rounded-xl bg-black/15 p-1">
                  <button
                    v-for="ratio in allowedRatios"
                    :key="ratio"
                    type="button"
                    class="rounded-lg px-2 py-2 text-xs transition-colors"
                    :class="form.ratio === ratio ? 'bg-primary/20 text-primary-200 shadow-sm' : 'text-gray-400 hover:bg-white/[0.05] hover:text-gray-200'"
                    :aria-pressed="form.ratio === ratio"
                    :data-value="ratio"
                    @click="form.ratio = ratio"
                  >
                    {{ ratio }}
                  </button>
                </div>
              </fieldset>

              <fieldset class="mt-4" data-test="seedream-resolution">
                <legend class="mb-2 text-xs text-gray-500">
                  {{ t('seedream.create.resolution') }}
                </legend>
                <div class="grid grid-cols-3 gap-1 rounded-xl bg-black/15 p-1">
                  <button
                    v-for="resolution in allResolutions"
                    :key="resolution"
                    type="button"
                    class="rounded-lg px-3 py-2 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-30"
                    :class="form.resolution === resolution ? 'bg-primary/20 text-primary-200 shadow-sm' : 'text-gray-400 hover:bg-white/[0.05] hover:text-gray-200'"
                    :disabled="!supportedResolutions.includes(resolution) || (platformGenerationSelected && !creditUsage.canPay('image', form.model, resolution, undefined, form.count))"
                    :aria-pressed="form.resolution === resolution"
                    :data-value="resolution"
                    @click="form.resolution = resolution"
                  >
                    {{ resolution }}
                  </button>
                </div>
              </fieldset>

              <fieldset class="mt-4" data-test="seedream-count">
                <legend class="mb-2 text-xs text-gray-500">
                  {{ t('seedream.create.count') }}
                </legend>
                <div class="grid grid-cols-4 gap-1 rounded-xl bg-black/15 p-1">
                  <button
                    v-for="count in allowedCounts"
                    :key="count"
                    type="button"
                    class="rounded-lg px-3 py-2 text-sm transition-colors"
                    :class="form.count === count ? 'bg-primary/20 text-primary-200 shadow-sm' : 'text-gray-400 hover:bg-white/[0.05] hover:text-gray-200'"
                    :aria-pressed="form.count === count"
                    :data-value="count"
                    @click="form.count = count"
                  >
                    {{ count }}
                  </button>
                </div>
              </fieldset>
            </div>
          </div>

          <button
            type="button"
            class="h-10 rounded-xl px-3 text-sm text-gray-400 transition-colors hover:bg-white/[0.05] hover:text-white"
            data-test="clear-image-draft"
            @click="clearDraft"
          >
            {{ t('aiCreation.clear') }}
          </button>

          <div class="ml-auto flex min-w-0 items-center gap-3 pl-2">
            <div v-if="showCreditEstimate" class="text-right" data-test="generation-credits" aria-live="polite">
              <p v-if="quoteLoading" class="text-sm text-gray-500">{{ t('aiCreation.platformQuoteLoading') }}</p>
              <p v-else-if="platformQuoteTotal !== null" class="text-sm text-gray-300">{{ t('aiCreation.estimatedCredits', { credits: platformQuoteTotal }) }}<span v-if="bonusPayment" class="ml-1 text-xs text-primary">({{ t(bonusPayment.general > 0 ? 'creditUsage.payment' : 'creditUsage.bonusOnly', bonusPayment) }})</span></p>
              <p v-else-if="creditUsage.error" class="max-w-[16rem] text-xs leading-5 text-warning">{{ t('creditUsage.unavailable') }} <button type="button" class="underline" @click="creditUsage.refresh()">{{ t('creditUsage.refresh') }}</button></p>
              <p v-else-if="quoteError" class="max-w-[16rem] text-xs leading-5 text-warning">{{ t('aiCreation.platformQuoteFailed', { message: quoteError }) }}</p>
              <p v-else class="text-sm text-gray-500">{{ t('aiCreation.creditsUnavailable') }}</p>
            </div>
            <CreationModelSelect
              v-if="showGenerationSourceSelector"
              :model-value="workspace.generationSource"
              :options="generationSourceOptions"
              :label="t('aiCreation.generationSource')"
              test-id="seedream-generation-source"
              @update:model-value="selectGenerationSource"
            />
            <button
              type="submit"
              class="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-[#ffbd5c] text-[#242424] transition hover:bg-[#ffc975] disabled:cursor-not-allowed disabled:bg-[#4a4a4a] disabled:text-[#777]"
              :disabled="submitting || platformConfirmBlocked || capabilitiesBlocked || !form.prompt.trim()"
              :aria-label="t('seedream.create.createBatch')"
              :title="t('seedream.create.createBatch')"
              data-test="seedream-submit"
            >
              <span
                v-if="submitting"
                class="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white"
                aria-hidden="true"
              />
              <ArrowUp
                v-else
                :size="20"
                aria-hidden="true"
              />
            </button>
          </div>
        </div>
      </section>
      <p v-if="referenceError" class="mt-2 text-sm text-danger" role="alert">{{ referenceError }}</p>
    </form>

    <div v-if="showBatchList" class="mt-8">
      <SeedreamBatchList />
    </div>

    <div
      v-if="confirmModal"
      ref="confirmModalRoot"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="seedream-confirm-title"
      aria-describedby="seedream-confirm-description"
      @keydown="onConfirmKeydown"
      @click.self="closeConfirmModal"
    >
      <div class="max-w-md rounded-xl border border-dark-border bg-dark-surface p-6">
        <h2
          id="seedream-confirm-title"
          class="text-lg font-semibold text-white"
        >
          {{ t('seedream.confirm.title') }}
        </h2>
        <ol
          id="seedream-confirm-description"
          class="mt-3 list-decimal space-y-2 pl-5 text-sm leading-6 text-gray-300"
        >
          <li>
            <template v-if="platformGenerationSelected">{{ t('aiCreation.platformBilledOnSubmit') }}</template>
            <template v-else>{{ t('seedream.confirm.cost') }}</template>
            <span class="text-warning" data-test="seedream-paid-confirm-irrevocable">{{ t('seedream.confirm.irrevocable') }}</span>
          </li>
          <li v-if="form.reference_image" data-test="seedream-confirm-reference">
            {{ t('seedream.confirm.reference') }}
          </li>
          <li>{{ t('seedream.confirm.download') }}</li>
          <li>{{ t('seedream.confirm.expiry') }}</li>
        </ol>
        <div class="mt-5 flex justify-end gap-3">
          <Button
            variant="secondary"
            :disabled="submitting"
            @click="closeConfirmModal"
          >
            {{ t('common.cancel') }}
          </Button>
          <Button
            :loading="submitting"
            :disabled="submitting || platformConfirmBlocked"
            data-test="seedream-confirm-submit"
            @click="confirmSubmit"
          >
            {{ t('seedream.confirm.confirm') }}
          </Button>
        </div>
      </div>
    </div>

    <DraftClearConfirmation
      :open="clearConfirmOpen"
      @cancel="clearConfirmOpen = false"
      @confirm="confirmClearDraft"
    />
    <GenerationAccessDialog
      :open="accessDialogOpen"
      :logged-in="authStore.isLoggedIn"
      @cancel="accessDialogOpen = false"
      @login="goToLogin"
      @configure-key="goToSettings"
    />
  </component>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { ArrowUp, Check, ChevronDown, Copy, Settings2 } from 'lucide-vue-next';
import { useI18n } from 'vue-i18n';
import { hasImageDrop, readImageDrop, type SeedreamImageDragPayload } from '@/seedream-image-drag';
import { useRoute, useRouter } from 'vue-router';
import DraftClearConfirmation from '@/components/ai-creation/DraftClearConfirmation.vue';
import GenerationAccessDialog from '@/components/ai-creation/GenerationAccessDialog.vue';
import CreationModelSelect from '@/components/ai-creation/CreationModelSelect.vue';
import { useCreditUsageStore } from '@/stores/creditUsage';
import Button from '@/components/common/Button.vue';
import SeedreamBatchList from '@/components/seedream/SeedreamBatchList.vue';
import SeedreamShell from '@/components/seedream/SeedreamShell.vue';
import { trapModalTab } from '@/modal-focus';
import SeedanceImagePicker from '@/components/seedance/SeedanceImagePicker.vue';
import {
  ALLOWED_COUNTS,
  ALLOWED_RATIOS,
  DEFAULT_COUNT,
  correctResolution,
  correctPlatformImageParameters,
  localModelResolutions,
  createRequest,
  defaultForm,
  promptCount,
  type CreateForm,
} from '@/seedream-ui';
import { useSeedreamStore } from '@/stores/seedream';
import { useSeedanceStore } from '@/stores/seedance';
import { useConfigStore } from '@/stores/config';
import { useAuthStore } from '@/stores/auth';
import { useAICreationStore, type CreationMode, type GenerationSource } from '@/stores/aiCreation';
import { usePlatformCapabilities } from '@/composables/usePlatformCapabilities';
import { platformModelOptions, type ModelOption } from '@/platform-models';
import type { SeedreamModel, SeedreamRatio, SeedreamResolution } from '@/types';

withDefaults(defineProps<{
  embedded?: boolean;
  creationMode?: CreationMode;
  showBatchList?: boolean;
}>(), {
  embedded: false,
  creationMode: 'image',
  showBatchList: true,
});

const emit = defineEmits<{
  'change-mode': [mode: CreationMode];
}>();

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const store = useSeedreamStore();
const keySettingsStore = useSeedanceStore();
const configStore = useConfigStore();
const authStore = useAuthStore();
const workspace = useAICreationStore();
const creditUsage = useCreditUsageStore();
// 平台能力清单的加载时机：登录后 / 切到平台源 / 登出清空。
const { reload: reloadCapabilities } = usePlatformCapabilities();

const allResolutions: SeedreamResolution[] = ['1K', '1.5K', '2K'];
const allowedRatios: SeedreamRatio[] = ALLOWED_RATIOS;
const allowedCounts = ALLOWED_COUNTS;
// 平台源下模型与尺寸档由能力清单决定（每个模型只暴露自己有定价的档位，
// 未定价的模型如 Flash 根本不会出现）；直连源仍用客户端预设表。
const platformImageModels = computed(() => workspace.capabilities?.image.models ?? []);
const localImageModelOptions = (): ModelOption[] => [
  { value: 'pro', label: t('seedream.models.pro') },
  { value: 'flash', label: t('seedream.models.flash') },
];
const modelOptions = computed<ModelOption[]>(() => (
  platformGenerationSelected.value
    ? platformModelOptions(platformImageModels.value).map(option => ({ ...option, disabled: !creditUsage.canPay('image', option.value), reason: creditUsage.canPay('image', option.value) ? '' : t(creditUsage.ready ? 'creditUsage.optionUnavailable' : 'creditUsage.loading') }))
    : localImageModelOptions()
));

const form: CreateForm = workspace.imageDraft;
const modelDefaultsReady = ref(false);
const showGenerationSourceSelector = computed(() => authStore.isLoggedIn);
const generationSourceOptions = computed(() => [
  { value: 'api-key', label: t('aiCreation.customApiKey') },
  { value: 'forfuner-ai', label: t('aiCreation.forfunerAI') },
]);
const platformGenerationSelected = computed(() => workspace.generationSource === 'forfuner-ai');
// 降级（design D3）：平台源下拉取失败/未就绪时**阻断提交**并提示重试，
// 绝不回退到客户端预设模型表——那会把"选中后必然失败"的组合重新放出来。
const capabilitiesBlocked = computed(() => (
  platformGenerationSelected.value
  && (authStore.isLoggedIn && (!workspace.capabilities || !!workspace.capabilitiesError))
));
const showCreditEstimate = computed(() => (
  authStore.isLoggedIn && platformGenerationSelected.value
));
const quoteReady = computed(() => (
  platformGenerationSelected.value && authStore.isLoggedIn && modelDefaultsReady.value
  && !capabilitiesBlocked.value && !workspace.capabilitiesLoading && creditUsage.ready
));
// 平台源报价：单价来自服务端（model + size），总数 = 单价 × 生成数量（N 张 = N 个平台任务）。
const quoteLoading = ref(false);
const quoteUnit = ref<number | null>(null);
const quoteError = ref('');
const platformQuoteTotal = computed(() => (
  quoteUnit.value === null ? null : quoteUnit.value * form.count
));
const bonusPayment = computed(() => {
  if (!creditUsage.ready || platformQuoteTotal.value === null) return null;
  const row = creditUsage.matching('image', form.model, form.resolution)[0];
  const bonus = Math.min(row?.bonusAvailable ?? 0, platformQuoteTotal.value);
  return bonus > 0 ? { bonus, general: platformQuoteTotal.value - bonus } : null;
});
const platformConfirmBlocked = computed(() => platformGenerationSelected.value && (!creditUsage.canPay('image', form.model, form.resolution, undefined, form.count) || quoteLoading.value || !!quoteError.value || quoteUnit.value === null));
const QUOTE_DEBOUNCE_MS = 350;
let quoteTimer: ReturnType<typeof setTimeout> | null = null;
let quoteRequestId = 0;

function quoteSignature() {
  return [form.model, form.resolution].join('|');
}

async function refreshPlatformQuote() {
  const requestId = ++quoteRequestId;
  if (!quoteReady.value) {
    quoteUnit.value = null;
    quoteError.value = '';
    quoteLoading.value = false;
    return;
  }
  quoteLoading.value = true;
  quoteError.value = '';
  let data: { quote: number } | null = null;
  let paymentError = '';
  try {
    const result = await creditUsage.quote('image', { model: form.model, size: form.resolution });
    if (result.canSubmit) data = result; else paymentError = result.message;
  } catch (error) { paymentError = error instanceof Error ? error.message : t('creditUsage.unavailable'); }
  // 只接受最后一次请求的结果，避免快速切模型时旧响应覆盖新报价。
  if (requestId !== quoteRequestId) return;
  quoteLoading.value = false;
  if (data && typeof data.quote === 'number') {
    quoteUnit.value = data.quote;
    return;
  }
  quoteUnit.value = null;
  quoteError.value = paymentError || t('aiCreation.creditsUnavailable');
}

function scheduleQuoteRefresh() {
  if (quoteTimer) clearTimeout(quoteTimer);
  quoteTimer = null;
  quoteRequestId += 1;
  quoteUnit.value = null;
  quoteError.value = '';
  quoteLoading.value = quoteReady.value;
  if (!quoteReady.value) return;
  quoteTimer = setTimeout(() => {
    quoteTimer = null;
    void refreshPlatformQuote();
  }, QUOTE_DEBOUNCE_MS);
}
const submitting = ref(false);
const parametersOpen = ref(false);
const confirmModal = ref(false);
const confirmModalRoot = ref<HTMLElement | null>(null);
let confirmTrigger: HTMLElement | null = null;
const copied = ref(false);
const referenceError = ref('');
const referenceDragActive = ref(false);

async function dropCandidateReference(candidate: SeedreamImageDragPayload) {
  referenceError.value = '';
  if (!await workspace.handoffCandidateToImage(candidate.localId, candidate.attemptIndex)) {
    referenceError.value = workspace.candidateHandoffError || t('aiCreation.imageUnavailable');
  }
}

async function dropReferenceFile(file: File) {
  referenceError.value = '';
  if (!await workspace.importDroppedImage(file, 'reference')) {
    referenceError.value = workspace.candidateHandoffError || t('aiCreation.imageUnavailable');
  }
}

function onReferenceDragOver(event: DragEvent) {
  event.preventDefault();
  if (!hasImageDrop(event.dataTransfer)) return;
  referenceDragActive.value = true;
}

function onReferenceDrop(event: DragEvent) {
  referenceDragActive.value = false;
  const result = readImageDrop(event.dataTransfer);
  if (result.kind === 'candidate') void dropCandidateReference(result.candidate);
  else if (result.kind === 'file') void dropReferenceFile(result.file);
  else referenceError.value = t(result.key);
}
const copyTitle = computed(() => copied.value ? t('common.copied') : t('common.copy'));

const promptInfo = computed(() => promptCount(form.prompt));
const clearConfirmOpen = ref(false);
const accessDialogOpen = ref(false);
const promptOverLimit = computed(() => promptInfo.value.count > promptInfo.value.limit);
const platformModelEntry = computed(() => (
  platformImageModels.value.find((entry) => entry.model === form.model) ?? null
));
const supportedResolutions = computed<SeedreamResolution[]>(() => {
  if (platformGenerationSelected.value) {
    return (platformModelEntry.value?.sizes ?? []) as SeedreamResolution[];
  }
  return localModelResolutions(form.model);
});
/**
 * 平台源：把模型/尺寸收敛到清单给的合法域（切源、切模型、清单到达后都要调）。
 * lite 只有 2K 这类单档情形就靠这里回退。
 */
function clampToPlatformModel() {
  if (!modelDefaultsReady.value) return;
  Object.assign(form, correctPlatformImageParameters(
    form.model, form.resolution, platformImageModels.value, store.settings?.default_model_id,
  ));
}
const paidConfirmationEnabled = computed(() => configStore.config?.paid_generation_confirmation_enabled !== false);

// Only an untouched initial draft may receive an automatic payable default.
const initialSelectionPending = ref(!workspace.imageDraftChanged() && !route.query.regenerate && !route.query.continue && !route.query.handoff);
let initialDraftSignature = '';
watch(
  () => [modelDefaultsReady.value, creditUsage.ready, creditUsage.data?.asOf, platformGenerationSelected.value, platformImageModels.value],
  () => {
    if (!initialSelectionPending.value || !initialDraftSignature || !modelDefaultsReady.value || !platformGenerationSelected.value || !creditUsage.ready || !platformImageModels.value.length) return;
    initialSelectionPending.value = false;
    if (JSON.stringify(form) !== initialDraftSignature) return;
    const current = creditUsage.canPay('image', form.model, form.resolution, undefined, form.count);
    if (current) return;
    const next = creditUsage.data?.combinations.find(row => row.context.mediaType === 'image'
      && platformImageModels.value.some(model => model.model === row.context.model)
      && creditUsage.canPay('image', row.context.model, row.context.sizeLabel ?? undefined, undefined, form.count));
    if (!next) return;
    form.model = next.context.model as typeof form.model;
    form.resolution = next.context.sizeLabel as typeof form.resolution;
  },
  { flush: 'post' },
);

onMounted(async () => {
  if (!store.settings) {
    await store.loadSettings();
  }
  if (!keySettingsStore.settings) {
    await keySettingsStore.loadSettings();
  }
  const settings = store.settings;
  workspace.initializeImageDraft({
    ...defaultForm(settings?.default_count ?? DEFAULT_COUNT),
    model: settings?.default_model ?? 'pro',
    resolution: correctResolution(settings?.default_model ?? 'pro', settings?.default_resolution ?? '2K'),
    ratio: settings?.default_ratio ?? '16:9',
  }, settings?.default_model_id);
  initialDraftSignature = JSON.stringify(form);
  modelDefaultsReady.value = true;
  if (!platformGenerationSelected.value) fixResolution();
  const regenerateId = typeof route.query.regenerate === 'string' ? route.query.regenerate : '';
  if (regenerateId) {
    // Restore an editable draft from a previous batch. This does NOT call
    // ImageGenerations or create a new batch - the user must confirm again.
    const draft = await store.loadRegenerationDraft(regenerateId);
    if (draft) {
      const request = draft.request;
      form.prompt = request.prompt ?? '';
      form.model = (request.model as SeedreamModel) ?? form.model;
      form.resolution = platformGenerationSelected.value ? ((request.resolution as SeedreamResolution) ?? form.resolution) : correctResolution(form.model, (request.resolution as SeedreamResolution) ?? form.resolution);
      form.ratio = (request.ratio as SeedreamRatio) ?? form.ratio;
      form.count = request.count ?? form.count;
      form.reference_image = request.reference_image ?? '';
      workspace.imagePreviewUrls.reference = draft.reference_image_url ?? '';
    }
    return;
  }
});

function clearDraft() {
  if (workspace.imageDraftChanged()) {
    clearConfirmOpen.value = true;
    return;
  }
  workspace.resetImageDraft();
  if (platformGenerationSelected.value) clampToPlatformModel();
}

function confirmClearDraft() {
  clearConfirmOpen.value = false;
  workspace.resetImageDraft();
  if (platformGenerationSelected.value) clampToPlatformModel();
}

function fixResolution() {
  form.resolution = correctResolution(form.model as SeedreamModel, form.resolution);
}

async function selectReferenceImage() {
  const selection = await store.selectReferenceImage();
  if (selection) {
    form.reference_image = selection.path;
    workspace.imagePreviewUrls.reference = selection.previewUrl;
  }
}

function clearReferenceImage() {
  form.reference_image = '';
  workspace.imagePreviewUrls.reference = '';
}

function selectModel(model: string) {
  form.model = model as SeedreamModel;
  if (platformGenerationSelected.value) clampToPlatformModel();
  else fixResolution();
}

// 切模型/分辨率刷新平台报价；数量是本地倍率，改数量无需重查。
watch(
  () => [quoteReady.value, creditUsage.data?.asOf, quoteSignature()].join('#'),
  () => scheduleQuoteRefresh(),
  { immediate: true },
);

// Capability refreshes preserve the draft; the user must explicitly choose a replacement.

function selectGenerationSource(source: string) {
  const next = source as GenerationSource;
  workspace.setGenerationSource(next);
  if (next === 'forfuner-ai') {
    clampToPlatformModel();
  } else {
    // Restore the saved API-key default when the current ID belongs to the platform.
    if (!localModelResolutions(form.model).length) form.model = store.settings?.default_model ?? 'pro';
    fixResolution();
  }
  scheduleQuoteRefresh();
}

async function copyPrompt() {
  const text = form.prompt.trim();
  if (!text || copied.value) return;
  try {
    await navigator.clipboard.writeText(text);
    copied.value = true;
    setTimeout(() => {
      copied.value = false;
    }, 1500);
  } catch {
    // Ignore clipboard errors in restricted environments.
  }
}

async function submit() {
  if (submitting.value || confirmModal.value) return;
  if (capabilitiesBlocked.value) return;
  if (!form.prompt.trim()) return;
  if (!ensureGenerationAccess()) return;
  if (!paidConfirmationEnabled.value) {
    await confirmSubmit();
    return;
  }
  confirmTrigger = document.activeElement as HTMLElement;
  confirmModal.value = true;
  await nextTick();
  confirmModalRoot.value?.querySelector<HTMLElement>('button:not([disabled])')?.focus();
}

function ensureGenerationAccess(): boolean {
  if (platformGenerationSelected.value) {
    if (authStore.isLoggedIn) return true;
    accessDialogOpen.value = true;
    return false;
  }
  if (keySettingsStore.settings?.api_key_configured) return true;
  accessDialogOpen.value = true;
  return false;
}

function goToLogin() {
  accessDialogOpen.value = false;
  void router.push({ path: '/login', query: { redirect: router.currentRoute.value.fullPath } });
}

function goToSettings() {
  accessDialogOpen.value = false;
  void router.push('/ai-creation/settings');
}

function closeConfirmModal() {
  if (submitting.value) return;
  confirmModal.value = false;
  confirmTrigger?.focus();
  confirmTrigger = null;
}

function onConfirmKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    closeConfirmModal();
    return;
  }
  if (confirmModalRoot.value) trapModalTab(event, confirmModalRoot.value);
}

onBeforeUnmount(() => {
  if (quoteTimer) {
    clearTimeout(quoteTimer);
    quoteTimer = null;
  }
  confirmModal.value = false;
});

async function confirmSubmit() {
  if (submitting.value || platformConfirmBlocked.value) return;
  submitting.value = true;
  try {
    const request = createRequest(form);
    const source = workspace.generationSource;
    let batch = await store.createBatch(request, source);
    // 平台 401：token 过期——先静默重登（token watcher 会自动把新 token 推进 Python），重试一次。
    if (!batch && source === 'forfuner-ai' && store.error?.code === 'UNAUTHORIZED') {
      const recovered = await authStore.silentRelogin();
      if (recovered) batch = await store.createBatch(request, source);
    }
    if (batch) {
      confirmModal.value = false;
      workspace.setCurrentGeneration({ kind: 'image', localId: batch.local_id });
    }
  } finally {
    submitting.value = false;
  }
}
</script>

<style>
.seedream-prompt-surface {
  box-shadow:
    0 1px 0 rgb(255 255 255 / 3%) inset,
    0 18px 44px rgb(0 0 0 / 18%);
}
</style>
