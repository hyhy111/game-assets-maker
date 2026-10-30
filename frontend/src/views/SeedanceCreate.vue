<template>
  <component :is="embedded ? 'div' : SeedanceShell">
    <form
      class="w-full"
      @submit.prevent="submit"
      @drop.prevent
      @dragover.prevent
    >
      <section
        class="seedance-prompt-surface rounded-[24px] border border-[#3b3b3b] bg-[#1f1f1f] p-4 sm:p-5"
        data-test="seedance-composer"
      >
        <div class="relative flex min-h-[282px] items-center gap-5 px-1 py-1">
          <div class="relative flex shrink-0 items-center gap-3 sm:gap-4" data-test="seedance-frame-strip">
            <SeedanceImagePicker
              class="-rotate-[7deg] transition-transform duration-200 hover:-translate-y-0.5 hover:-rotate-[4deg]"
              :model-value="form.first_frame"
              :preview-url="previewUrls.first_frame"
              :label="t('seedance.create.firstFrame')"
              :card-label="t('seedance.create.firstFrameShort')"
              required
              :help="`${t('seedance.create.firstFrameHelp')}${t('seedance.create.supportedFormats')}`"
              help-id="seedance-first-frame-help"
              :error="errorMessage(errors.first_frame)"
              error-id="seedance-first-frame-error"
              :select-label="t('seedance.create.selectImage')"
              :change-label="t('seedance.create.changeImage')"
              :edit-label="t('seedance.create.editImage')"
              :remove-label="t('seedance.create.removeImage')"
              :selected-label="t('seedance.create.imageSelected')"
              :drop-label="t('seedance.create.dropAsFirstFrame')"
              compact
              @select="selectFrame('first_frame')"
              @edit="openImageEditor('first_frame')"
              @clear="clearFrame('first_frame')"
              @drop-image="dropCandidateFrame('first_frame', $event)"
              @drop-file="dropLocalFrame('first_frame', $event)"
              @drop-error="dropError = t($event)"
            />
            <ArrowRight :size="14" class="shrink-0 text-gray-600" stroke-width="1.8" aria-hidden="true" />
            <SeedanceImagePicker
              class="rotate-[4deg] transition-transform duration-200 hover:-translate-y-0.5 hover:rotate-[2deg]"
              :model-value="form.last_frame"
              :preview-url="previewUrls.last_frame"
              :label="t('seedance.create.lastFrame')"
              :card-label="t('seedance.create.lastFrameShort')"
              :optional-label="t('seedance.create.optionalShort')"
              :help="`${t('seedance.create.lastFrameHelp')}${t('seedance.create.supportedFormats')}`"
              help-id="seedance-last-frame-help"
              :error="errorMessage(errors.last_frame)"
              error-id="seedance-last-frame-error"
              :select-label="t('seedance.create.selectImage')"
              :change-label="t('seedance.create.changeImage')"
              :edit-label="t('seedance.create.editImage')"
              :remove-label="t('seedance.create.removeImage')"
              :selected-label="t('seedance.create.imageSelected')"
              :drop-label="t('seedance.create.dropAsLastFrame')"
              compact
              @select="selectFrame('last_frame')"
              @edit="openImageEditor('last_frame')"
              @clear="clearFrame('last_frame')"
              @drop-image="dropCandidateFrame('last_frame', $event)"
              @drop-file="dropLocalFrame('last_frame', $event)"
              @drop-error="dropError = t($event)"
            />
          </div>

          <div class="relative min-w-0 flex-1 self-stretch">
            <label for="seedance-prompt" class="sr-only">{{ t('seedance.create.promptTitle') }}</label>
            <textarea
              id="seedance-prompt"
              v-model="form.prompt"
              rows="3"
              class="h-full min-h-[82px] w-full resize-none bg-transparent px-0 py-0 pb-7 pr-9 text-[15px] leading-7 text-[#e7e7e7] outline-none placeholder:text-[#747474]"
              :placeholder="promptPlaceholder"
              :aria-invalid="!!errors.prompt"
              data-test="seedance-prompt"
            />
            <button
              type="button"
              class="absolute -right-1 -top-1 rounded-lg p-2 text-[#777] transition-colors hover:bg-[#303030] hover:text-[#d8d8d8]"
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
                :class="promptInfo.count > promptInfo.limit ? 'text-yellow-400' : errors.prompt ? 'text-danger' : 'text-gray-500'"
                data-test="seedance-prompt-count"
              >
                {{ promptInfo.count }}/{{ promptInfo.limit }}
                {{ promptInfo.chinese ? t('seedance.ui.characters') : t('seedance.ui.words') }}
                <span
                  class="pointer-events-none absolute right-0 top-full z-50 mt-2 hidden w-64 rounded-xl border border-white/10 bg-[#222329] px-3 py-2 text-left text-xs font-normal leading-5 text-gray-300 shadow-2xl shadow-black/40 group-hover:block"
                  data-test="seedance-prompt-suggestion"
                >
                  {{ t('seedance.create.promptSuggestion') }}
                </span>
              </p>
            </div>
          </div>
        </div>

        <p v-if="imageEditorLaunchError" class="mt-2 text-sm text-danger" role="alert">
          {{ imageEditorLaunchError }}
        </p>
        <p v-if="errors.first_frame" class="mt-2 text-sm text-danger">{{ errorMessage(errors.first_frame) }}</p>
        <p v-if="errors.last_frame" class="mt-2 text-sm text-danger">{{ errorMessage(errors.last_frame) }}</p>
        <p v-if="errors.prompt" class="mt-2 text-sm text-danger">{{ errorMessage(errors.prompt) }}</p>

        <p v-if="draftLoadFailed" class="mt-3 text-sm text-danger">
          {{ handoffLoadFailed ? t('seedance.create.handoffLoadFailed') : t('seedance.create.continuationLoadFailed') }}
        </p>
        <p v-if="errors.body" class="mt-3 text-sm text-danger">{{ errorMessage(errors.body) }}</p>
        <div
          v-if="capabilitiesBlocked"
          class="mt-3 flex flex-wrap items-center gap-3 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-warning"
          data-test="seedance-capabilities-blocked"
          role="alert"
        >
          <span>{{ workspace.capabilitiesError ? t('aiCreation.capabilitiesFailed', { message: workspace.capabilitiesError }) : t('aiCreation.capabilitiesLoading') }}</span>
          <button
            type="button"
            class="rounded-md border border-warning/40 px-2 py-0.5 text-xs transition-colors hover:bg-warning/20"
            data-test="seedance-capabilities-retry"
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
            :label="t('seedance.create.model')"
            test-id="seedance-model"
            @update:model-value="selectModel"
          />

          <div class="relative">
            <button
              type="button"
              class="inline-flex h-10 items-center gap-2 rounded-xl border border-[#414141] bg-[#2d2d2d] px-3 text-sm text-gray-200 transition-colors hover:border-[#555] hover:bg-[#353535]"
              :class="parametersOpen ? 'border-primary/50 bg-white/[0.06]' : ''"
              :aria-expanded="parametersOpen"
              :aria-label="t('seedance.create.summaryTitle')"
              data-test="seedance-parameter-summary"
              @click="parametersOpen = !parametersOpen"
              @keydown.escape.stop="parametersOpen = false"
            >
              <Settings2 :size="15" class="text-gray-400" aria-hidden="true" />
              <span>{{ form.ratio === 'adaptive' ? t('seedance.create.adaptive') : form.ratio }}</span>
              <span class="text-gray-600">·</span>
              <span>{{ form.resolution }}</span>
              <span class="text-gray-600">·</span>
              <span>{{ form.duration === -1 ? t('seedance.ui.smart') : `${form.duration}s` }}</span>
              <ChevronDown :size="14" class="text-gray-500 transition-transform" :class="parametersOpen ? 'rotate-180' : ''" aria-hidden="true" />
            </button>

            <div
              v-show="parametersOpen"
              class="absolute right-0 top-full z-30 mt-3 w-[min(520px,calc(100vw-2rem))] rounded-2xl border border-[#3b3b3b] bg-[#1f1f1f] p-4 shadow-2xl shadow-black/50"
              data-test="seedance-parameter-panel"
              @keydown.escape.stop="parametersOpen = false"
            >
              <fieldset>
                <legend class="mb-2 text-xs text-gray-500">{{ t('seedance.create.ratio') }}</legend>
                <SeedanceRatioPicker v-model="form.ratio" :adaptive-label="t('seedance.create.adaptive')" />
                <p class="mt-2 text-xs text-gray-500">{{ t('seedance.create.adaptiveHelp') }}</p>
              </fieldset>

              <div class="mt-4 grid gap-4 sm:grid-cols-2">
                <fieldset>
                  <legend class="mb-2 text-xs text-gray-500">{{ t('seedance.create.resolution') }}</legend>
                  <div class="grid w-3/4 grid-cols-3 gap-1 rounded-xl bg-black/15 p-1" data-test="seedance-resolution">
                    <button
                      v-for="resolution in allResolutions"
                      :key="resolution"
                      type="button"
                      class="rounded-lg px-2 py-2 text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-30"
                      :class="form.resolution === resolution ? 'bg-primary/20 text-primary-200 shadow-sm' : 'text-gray-400 hover:bg-white/[0.05] hover:text-gray-200'"
                      :disabled="!supportedResolutions.includes(resolution) || (platformGenerationSelected && !creditUsage.canPay('video', form.model, resolution))"
                      :aria-pressed="form.resolution === resolution"
                      :data-value="resolution"
                      @click="form.resolution = resolution"
                    >
                      {{ resolution }}
                    </button>
                  </div>
                  <p v-if="errors.resolution" class="error">{{ errorMessage(errors.resolution) }}</p>
                </fieldset>

                <div class="text-xs text-gray-500">
                  {{ t('seedance.create.duration') }}
                  <Listbox v-slot="{ open }" v-model="form.duration">
                    <div class="relative mt-2">
                      <ListboxButton
                        class="flex h-10 w-full items-center justify-between gap-2 rounded-xl border border-[#414141] bg-[#2d2d2d] px-3 text-sm text-gray-200 transition-colors hover:border-[#555] hover:bg-[#353535] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                        :aria-invalid="!!errors.duration"
                        aria-describedby="seedance-duration-error"
                        data-test="seedance-duration"
                      >
                        <span>{{ form.duration }}s</span>
                        <ChevronDown
                          :size="14"
                          class="text-[#777] transition-transform"
                          :class="open ? 'rotate-180' : ''"
                          aria-hidden="true"
                        />
                      </ListboxButton>

                      <Transition
                        enter-active-class="transition duration-100 ease-out"
                        enter-from-class="scale-95 opacity-0"
                        enter-to-class="scale-100 opacity-100"
                        leave-active-class="transition duration-75 ease-in"
                        leave-from-class="scale-100 opacity-100"
                        leave-to-class="scale-95 opacity-0"
                      >
                        <ListboxOptions
                          class="absolute left-0 top-full z-40 mt-2 w-full overflow-hidden rounded-xl border border-[#3b3b3b] bg-[#1f1f1f] p-1 shadow-2xl shadow-black/50 focus:outline-none"
                        >
                          <ListboxOption
                            v-for="duration in durationOptions"
                            :key="duration"
                            v-slot="{ active, selected }"
                            as="template"
                            :value="duration"
                            :disabled="platformGenerationSelected && !creditUsage.canPay('video', form.model, form.resolution, duration)"
                          >
                            <li
                              class="flex cursor-pointer items-center justify-between gap-4 rounded-lg px-3 py-2 text-sm whitespace-nowrap"
                              :class="selected
                                ? 'bg-primary/20 text-primary-200'
                                : active
                                  ? 'bg-[#303030] text-white'
                                  : 'text-gray-400'"
                            >
                              <span>{{ duration }}s <small v-if="platformGenerationSelected && !creditUsage.canPay('video', form.model, form.resolution, duration)" class="text-gray-500">{{ t('creditUsage.optionUnavailable') }}</small></span>
                              <Check
                                v-if="selected"
                                :size="14"
                                class="text-primary-200"
                                aria-hidden="true"
                              />
                            </li>
                          </ListboxOption>
                        </ListboxOptions>
                      </Transition>
                    </div>
                  </Listbox>
                  <p v-if="errors.duration" id="seedance-duration-error" class="error">{{ errorMessage(errors.duration) }}</p>
                </div>
              </div>

              <div class="mt-4 flex flex-wrap gap-x-8 gap-y-4 border-t border-white/[0.06] pt-4">
                <Switch v-model="form.generate_audio" :label="t('seedance.create.generateAudio')" />
                <div>
                  <Switch v-model="form.return_last_frame" :disabled="platformGenerationSelected" :label="t('seedance.create.returnLastFrame')" />
                  <p v-if="platformGenerationSelected" class="mt-1 text-xs text-gray-500">{{ t('aiCreation.platformLimited') }}</p>
                </div>
              </div>

            </div>
          </div>

          <button
            type="button"
            class="h-10 rounded-xl px-3 text-sm text-gray-400 transition-colors hover:bg-white/[0.05] hover:text-white"
            data-test="clear-video-draft"
            @click="clearDraft"
          >
            {{ t('aiCreation.clear') }}
          </button>

          <div class="ml-auto flex min-w-0 items-center gap-3 pl-2">
            <div v-if="showCreditEstimate" class="text-right" data-test="generation-credits" aria-live="polite">
              <p v-if="quoteLoading" class="text-sm text-gray-500">{{ t('aiCreation.platformQuoteLoading') }}</p>
              <p v-else-if="quoteValue !== null" class="text-sm text-gray-300">{{ t('aiCreation.estimatedCredits', { credits: quoteValue }) }}<span v-if="bonusPayment" class="ml-1 text-xs text-primary">({{ t(bonusPayment.general > 0 ? 'creditUsage.payment' : 'creditUsage.bonusOnly', bonusPayment) }})</span></p>
              <p v-else-if="creditUsage.error" class="max-w-[16rem] text-xs leading-5 text-warning">{{ t('creditUsage.unavailable') }} <button type="button" class="underline" @click="creditUsage.refresh()">{{ t('creditUsage.refresh') }}</button></p>
              <p v-else-if="quoteError" class="max-w-[16rem] text-xs leading-5 text-warning">{{ t('aiCreation.platformQuoteFailed', { message: quoteError }) }}</p>
              <p v-else class="text-sm text-gray-500">{{ t('aiCreation.creditsUnavailable') }}</p>
            </div>
            <CreationModelSelect
              v-if="showGenerationSourceSelector"
              :model-value="workspace.generationSource"
              :options="generationSourceOptions"
              :label="t('aiCreation.generationSource')"
              test-id="seedance-generation-source"
              @update:model-value="selectGenerationSource"
            />
            <button
              type="submit"
              class="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-[#ffbd5c] text-[#242424] transition hover:bg-[#ffc975] disabled:cursor-not-allowed disabled:bg-[#4a4a4a] disabled:text-[#777]"
              :disabled="submitting || platformConfirmBlocked || capabilitiesBlocked || draftLoadFailed || !form.first_frame || !form.prompt.trim()"
              :aria-label="t('seedance.create.createTask')"
              :title="t('seedance.create.createTask')"
              data-test="seedance-submit"
            >
              <span v-if="submitting" class="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" aria-hidden="true" />
              <ArrowUp v-else :size="20" aria-hidden="true" />
            </button>
          </div>
        </div>
      </section>
      <p v-if="dropError" class="mt-2 text-sm text-danger" role="alert">{{ dropError }}</p>
    </form>

    <section v-if="showTaskList" class="mt-10" data-test="seedance-create-task-list">
      <SeedanceTaskList />
    </section>

    <SeedreamImageEraser
      v-if="editingField && editorImageUrl"
      :image-url="editorImageUrl"
      :edit-source-url="editorEditSourceUrl"
      :title="t('seedance.create.imageEditorTitle')"
      :saving="editorSaving"
      :error="editorError"
      :generation-layout="editorGenerationLayout"
      resize-enabled
      @cancel="closeImageEditor"
      @apply="saveEditedImage"
    />

    <div
      v-if="validationModal"
      ref="validationModalRoot"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="validation-title"
      aria-describedby="validation-description"
      @keydown="onValidationKeydown"
      @click.self="closeValidationModal"
    >
      <div class="max-w-md rounded-xl border border-dark-border bg-dark-surface p-6">
        <h2 id="validation-title" class="text-lg font-semibold text-white">{{ t('seedance.ui.checkInput') }}</h2>
        <p id="validation-description" class="mt-3 text-gray-300">{{ modalMessage }}</p>
        <Button class="mt-5" @click="closeValidationModal">{{ t('common.confirm') }}</Button>
      </div>
    </div>

    <div
      v-if="paidConfirmModal"
      ref="paidConfirmModalRoot"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="paid-confirm-title"
      aria-describedby="paid-confirm-description"
      @keydown="onPaidConfirmKeydown"
      @click.self="cancelPaidAction"
    >
      <div class="max-w-md rounded-xl border border-dark-border bg-dark-surface p-6">
        <h2 id="paid-confirm-title" class="text-lg font-semibold text-white">{{ t('seedance.create.paidConfirmTitle') }}</h2>
        <ol id="paid-confirm-description" class="mt-3 list-decimal space-y-2 pl-5 text-sm leading-6 text-gray-300">
          <li>
            {{ t('seedance.create.paidConfirmCost') }}<span class="text-warning" data-test="seedance-paid-confirm-irrevocable">{{ t('seedance.create.paidConfirmIrrevocable') }}</span>
          </li>
          <li>{{ t('seedance.create.paidConfirmDownload') }}</li>
          <li>{{ t('seedance.create.paidConfirmExpiry') }}</li>
        </ol>
        <div v-if="platformGenerationSelected" class="mt-4 rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm" data-test="seedance-platform-quote" aria-live="polite">
          <p v-if="quoteLoading" class="text-gray-400">{{ t('aiCreation.platformQuoteLoading') }}</p>
          <p v-else-if="quoteError" class="text-danger">{{ t('aiCreation.platformQuoteFailed', { message: quoteError }) }}</p>
          <p v-else-if="quoteValue !== null" class="text-gray-200">{{ t('aiCreation.platformQuote', { credits: quoteValue }) }}</p>
        </div>
        <div class="mt-5 flex justify-end gap-3">
          <Button variant="secondary" :disabled="submitting" @click="cancelPaidAction">{{ t('seedance.create.paidConfirmCancel') }}</Button>
          <Button :loading="submitting" :disabled="submitting || platformConfirmBlocked" @click="confirmPaidAction">{{ t('seedance.create.paidConfirmConfirm') }}</Button>
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
import { Listbox, ListboxButton, ListboxOption, ListboxOptions } from '@headlessui/vue';
import { ArrowRight, ArrowUp, Check, ChevronDown, Copy, Settings2 } from 'lucide-vue-next';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';
import DraftClearConfirmation from '@/components/ai-creation/DraftClearConfirmation.vue';
import GenerationAccessDialog from '@/components/ai-creation/GenerationAccessDialog.vue';
import CreationModelSelect from '@/components/ai-creation/CreationModelSelect.vue';
import { useCreditUsageStore } from '@/stores/creditUsage';
import Button from '@/components/common/Button.vue';
import { api } from '@/api';
import Switch from '@/components/common/Switch.vue';
import SeedanceImagePicker from '@/components/seedance/SeedanceImagePicker.vue';
import SeedreamImageEraser from '@/components/seedream/SeedreamImageEraser.vue';
import SeedanceRatioPicker from '@/components/seedance/SeedanceRatioPicker.vue';
import SeedanceShell from '@/components/seedance/SeedanceShell.vue';
import SeedanceTaskList from '@/components/seedance/SeedanceTaskList.vue';
import { trapModalTab } from '@/modal-focus';
import type { SeedreamImageDragPayload } from '@/seedream-image-drag';
import {
  correctResolution,
  correctDuration,
  createRequest,
  DURATION_OPTIONS,
  localModelResolutions,
  promptCount,
  validateCreateForm,
  validationIssueForApiError,
  type CreateForm,
  type SeedanceValidationIssue,
} from '@/seedance-ui';
import { useSeedanceStore } from '@/stores/seedance';
import { useConfigStore } from '@/stores/config';
import { useAuthStore } from '@/stores/auth';
import { defaultVideoDraft, useAICreationStore, type CreationMode, type GenerationSource } from '@/stores/aiCreation';
import { usePlatformCapabilities } from '@/composables/usePlatformCapabilities';
import { platformModelOptions, type ModelOption } from '@/platform-models';
import type { GenerationLayout, SeedanceModel, SeedanceResolution } from '@/types';

withDefaults(defineProps<{
  embedded?: boolean;
  creationMode?: CreationMode;
  showTaskList?: boolean;
}>(), {
  embedded: false,
  creationMode: 'video',
  showTaskList: true,
});

const emit = defineEmits<{
  'change-mode': [mode: CreationMode];
}>();

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const store = useSeedanceStore();
const configStore = useConfigStore();
const authStore = useAuthStore();
const workspace = useAICreationStore();
const creditUsage = useCreditUsageStore();
// 平台能力清单的加载时机：登录后 / 切到平台源 / 登出清空。
const { reload: reloadCapabilities } = usePlatformCapabilities();
const errors = ref<Record<string, SeedanceValidationIssue>>({});
const validationModal = ref(false);
const modalMessage = ref('');
const validationModalRoot = ref<HTMLElement | null>(null);
const paidConfirmModal = ref(false);
const clearConfirmOpen = ref(false);
const accessDialogOpen = ref(false);
const paidConfirmModalRoot = ref<HTMLElement | null>(null);
let pendingRequest: ReturnType<typeof createRequest> | null = null;
let paidConfirmTrigger: HTMLElement | null = null;
const parametersOpen = ref(false);
const submitting = ref(false);
const draftLoadFailed = ref(false);
const handoffLoadFailed = ref(false);
const dropError = ref('');
const editingField = ref<'first_frame' | 'last_frame' | null>(null);
const editorImageUrl = ref('');
const editorEditSourceUrl = ref('');
const editorSaving = ref(false);
const editorError = ref('');
const editorGenerationLayout = ref<GenerationLayout | null>(null);
const imageEditorLaunchError = ref('');
let validationTrigger: HTMLElement | null = null;
const allResolutions: SeedanceResolution[] = ['480p', '720p', '1080p'];
// 平台源下模型与参数由能力清单决定（每个模型只暴露自己有定价的分辨率/时长）；
// 直连源仍用客户端预设表。见 openspec: gen-capabilities。
const platformVideoModels = computed(() => workspace.capabilities?.video.models ?? []);
const localVideoModelOptions = (): ModelOption[] => [
  { value: 'standard', label: t('seedance.models.standard') },
  { value: 'fast', label: t('seedance.models.fast') },
  { value: 'mini', label: t('seedance.models.mini') },
];
const modelOptions = computed<ModelOption[]>(() => (
  platformGenerationSelected.value
    ? platformModelOptions(platformVideoModels.value).map(option => ({ ...option, disabled: !creditUsage.canPay('video', option.value), reason: creditUsage.canPay('video', option.value) ? '' : t(creditUsage.ready ? 'creditUsage.optionUnavailable' : 'creditUsage.loading') }))
    : localVideoModelOptions()
));
const form: CreateForm = workspace.videoDraft;
const modelDefaultsReady = ref(false);
// 平台源只需要登录；api-key 源还需要已配置 Ark Key。
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
// 平台源报价（quote-preview）：编辑页参数一变就刷新，弹窗确认前必须有值。
const quoteLoading = ref(false);
const quoteValue = ref<number | null>(null);
const bonusPayment = computed(() => {
  if (!creditUsage.ready || quoteValue.value === null) return null;
  const row = creditUsage.matching('video', form.model, form.resolution, form.duration)[0];
  const bonus = Math.min(row?.bonusAvailable ?? 0, quoteValue.value);
  return bonus > 0 ? { bonus, general: quoteValue.value - bonus } : null;
});
const quoteError = ref('');
const platformConfirmBlocked = computed(() => (
  platformGenerationSelected.value && (quoteLoading.value || quoteError.value !== '' || quoteValue.value === null)
));
const QUOTE_DEBOUNCE_MS = 350;
let quoteTimer: ReturnType<typeof setTimeout> | null = null;
let quoteRequestId = 0;
/** 当前报价对应的参数签名；与表单不一致时说明报价已过期。 */
const quoteSignatureOf = ref('');

/** 报价只依赖 model/resolution/duration/ratio/generate_audio（与图片无关）。 */
function quoteSignature() {
  return [form.model, form.resolution, form.duration, form.ratio, form.generate_audio].join('|');
}

async function refreshPlatformQuote() {
  const requestId = ++quoteRequestId;
  if (!quoteReady.value) {
    quoteValue.value = null;
    quoteError.value = '';
    quoteLoading.value = false;
    quoteSignatureOf.value = '';
    return;
  }
  const signature = quoteSignature();
  quoteLoading.value = true;
  quoteError.value = '';
  let data: { quote: number } | null = null;
  let paymentError = '';
  try {
    const result = await creditUsage.quote('video', { model: form.model, resolution: form.resolution, duration: form.duration, ratio: form.ratio, generate_audio: form.generate_audio, content: [{ type: 'text', text: 'quote' }] });
    if (result.canSubmit) data = result; else paymentError = result.message;
  } catch (error) { paymentError = error instanceof Error ? error.message : t('creditUsage.unavailable'); }
  // 只接受最后一次请求的结果，避免快速切参数时旧响应覆盖新报价。
  if (requestId !== quoteRequestId) return;
  quoteLoading.value = false;
  quoteSignatureOf.value = signature;
  if (data && typeof data.quote === 'number') {
    quoteValue.value = data.quote;
    return;
  }
  quoteValue.value = null;
  quoteError.value = paymentError || t('aiCreation.creditsUnavailable');
}

function scheduleQuoteRefresh() {
  if (quoteTimer) clearTimeout(quoteTimer);
  quoteTimer = null;
  quoteRequestId += 1;
  quoteValue.value = null;
  quoteError.value = '';
  quoteLoading.value = quoteReady.value;
  quoteSignatureOf.value = '';
  if (!quoteReady.value) return;
  quoteTimer = setTimeout(() => {
    quoteTimer = null;
    void refreshPlatformQuote();
  }, QUOTE_DEBOUNCE_MS);
}
const previewUrls = workspace.videoPreviewUrls;
const promptInfo = computed(() => promptCount(form.prompt));
const promptPlaceholder = computed(() => t(
  form.first_frame ? 'seedance.create.imagePromptPlaceholder' : 'seedance.create.textPromptPlaceholder',
));
const platformModelEntry = computed(() => (
  platformVideoModels.value.find((entry) => entry.model === form.model) ?? null
));
const supportedResolutions = computed<SeedanceResolution[]>(() => (
  platformGenerationSelected.value
    ? (platformModelEntry.value?.resolutions ?? []) as SeedanceResolution[]
    : localModelResolutions(form.model)
));
// 平台源的时长由清单决定，且**按当前分辨率取**——不同分辨率可售的时长可以不同
// （如 480p 有 4s/5s，720p 只有 4s）。直连源沿用本地选项。
const platformDurations = computed<number[]>(() => (
  platformModelEntry.value?.durationsByResolution?.[form.resolution] ?? []
));
const durationOptions = computed<number[]>(() => (
  platformGenerationSelected.value ? platformDurations.value : [...DURATION_OPTIONS]
));
const paidConfirmationEnabled = computed(() => configStore.config?.paid_generation_confirmation_enabled !== false);
const copied = ref(false);
const copyTitle = computed(() => copied.value ? t('common.copied') : t('common.copy'));

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

// Only an untouched initial draft may receive an automatic payable default.
const initialSelectionPending = ref(!workspace.videoDraftChanged() && !route.query.regenerate && !route.query.continue && !route.query.handoff);
let initialDraftSignature = '';
watch(
  () => [modelDefaultsReady.value, creditUsage.ready, creditUsage.data?.asOf, platformGenerationSelected.value, platformVideoModels.value],
  () => {
    if (!initialSelectionPending.value || !initialDraftSignature || !modelDefaultsReady.value || !platformGenerationSelected.value || !creditUsage.ready || !platformVideoModels.value.length) return;
    initialSelectionPending.value = false;
    if (JSON.stringify(form) !== initialDraftSignature) return;
    const current = creditUsage.canPay('video', form.model, form.resolution, form.duration);
    if (current) return;
    const next = creditUsage.data?.combinations.find(row => row.context.mediaType === 'video'
      && platformVideoModels.value.some(model => model.model === row.context.model)
      && creditUsage.canPay('video', row.context.model, row.context.resolution ?? undefined, row.context.durationSec ?? undefined));
    if (!next) return;
    form.model = next.context.model as typeof form.model;
    form.resolution = next.context.resolution as typeof form.resolution;
    form.duration = next.context.durationSec as typeof form.duration;
  },
  { flush: 'post' },
);

onMounted(async () => {
  await store.loadSettings();
  const settings = store.settings;
  if (settings) {
    workspace.initializeVideoDraft({
      ...defaultVideoDraft(),
      model: settings.default_model,
      resolution: correctResolution(settings.default_model, settings.default_resolution),
      ratio: settings.default_ratio,
      duration: correctDuration(settings.default_duration),
      generate_audio: settings.default_generate_audio,
      return_last_frame: settings.default_return_last_frame,
    }, settings.default_model_id);
  } else {
    workspace.initializeVideoDraft(defaultVideoDraft());
  }
  modelDefaultsReady.value = true;
  if (platformGenerationSelected.value) {
    form.return_last_frame = false;
  }
  initialDraftSignature = JSON.stringify(form);

  const regenerateId = typeof route.query.regenerate === 'string' ? route.query.regenerate : '';
  const continuationId = typeof route.query.continue === 'string' ? route.query.continue : '';

  const handoffId = typeof route.query.handoff === 'string' ? route.query.handoff : '';
  if (handoffId) {
    const attemptIndex = Number.parseInt(String(route.query.attempt ?? '0'), 10) || 0;
    if (!await workspace.handoffCandidateToVideo(handoffId, attemptIndex)) {
      draftLoadFailed.value = true;
      handoffLoadFailed.value = true;
    }
    return;
  }

  if (!regenerateId && !continuationId) return;
  const source = regenerateId
    ? await store.loadRegenerationDraft(regenerateId)
    : await store.loadContinuationDraft(continuationId);
  if (!source) {
    draftLoadFailed.value = true;
    return;
  }
  const request = source.request;
  form.first_frame = request.first_frame;
  form.last_frame = request.last_frame ?? null;
  form.prompt = request.prompt ?? '';
  form.model = request.model ?? form.model;
  form.resolution = platformGenerationSelected.value ? (request.resolution ?? form.resolution) : correctResolution(form.model, request.resolution ?? form.resolution);
  form.ratio = request.ratio ?? form.ratio;
  form.duration = correctDuration(request.duration ?? form.duration);
  form.generate_audio = request.generate_audio ?? form.generate_audio;
  form.return_last_frame = request.return_last_frame ?? form.return_last_frame;
  previewUrls.first_frame = source.preview_urls.first_frame ?? '';
  previewUrls.last_frame = source.preview_urls.last_frame ?? '';
});

function clearDraft() {
  if (workspace.videoDraftChanged()) {
    clearConfirmOpen.value = true;
    return;
  }
  resetDraft();
}

function confirmClearDraft() {
  clearConfirmOpen.value = false;
  resetDraft();
}

async function dropCandidateFrame(
  field: 'first_frame' | 'last_frame',
  candidate: SeedreamImageDragPayload,
) {
  dropError.value = '';
  if (await workspace.handoffCandidateToVideo(candidate.localId, candidate.attemptIndex, field)) {
    delete errors.value[field];
  } else dropError.value = workspace.candidateHandoffError || t('aiCreation.imageUnavailable');
}

async function dropLocalFrame(field: 'first_frame' | 'last_frame', file: File) {
  dropError.value = '';
  if (await workspace.importDroppedImage(file, field)) delete errors.value[field];
  else dropError.value = workspace.candidateHandoffError || t('aiCreation.imageUnavailable');
}

function resetDraft() {
  workspace.resetVideoDraft();
  if (platformGenerationSelected.value) clampToPlatformModel();
  previewUrls.first_frame = '';
  previewUrls.last_frame = '';
  errors.value = {};
  draftLoadFailed.value = false;
  handoffLoadFailed.value = false;
}

function fixResolution() {
  form.resolution = correctResolution(form.model as SeedanceModel, form.resolution);
}

/**
 * 平台源：把模型/分辨率/时长收敛到清单给的合法域。
 * 清单变化、切源、切模型后都要调用——否则会留下"当前模型没有这个档位"的悬空值，
 * 用户点提交才被后端拒掉。
 */
function clampToPlatformModel() {
  if (!modelDefaultsReady.value) return;
  const models = platformVideoModels.value;
  if (!models.length) return;
  let entry = models.find((candidate) => candidate.model === form.model);
  if (!entry) {
    entry = models.find(candidate => candidate.model === store.settings?.default_model_id) ?? models[0];
    form.model = entry.model;
  }
  const resolutions = (entry.resolutions ?? []) as SeedanceResolution[];
  if (resolutions.length && !resolutions.includes(form.resolution)) {
    form.resolution = resolutions[0];
  }
  // 时长按**当前分辨率**收敛：换分辨率后原时长可能在该分辨率下没有定价
  const durations = entry.durationsByResolution?.[form.resolution] ?? [];
  if (durations.length && !durations.includes(form.duration)) {
    form.duration = durations[0] as CreateForm['duration'];
  }
}

function selectModel(model: string) {
  form.model = model as SeedanceModel;
  if (platformGenerationSelected.value) clampToPlatformModel();
  else fixResolution();
}

// 切模型/分辨率/时长/比例/音频都刷新平台报价（仅平台源）。
watch(
  () => [quoteReady.value, creditUsage.data?.asOf, quoteSignature()].join('#'),
  () => scheduleQuoteRefresh(),
  { immediate: true },
);

// Capability refreshes preserve the draft. Invalid combinations are explained by the quote and scope notice.

async function selectFrame(field: 'first_frame' | 'last_frame') {
  const selection = await store.selectImageFile();
  if (selection) {
    form[field] = selection.path;
    previewUrls[field] = selection.previewUrl;
    delete errors.value[field];
  }
}

function clearFrame(field: 'first_frame' | 'last_frame') {
  if (field === 'first_frame') form.first_frame = '';
  else form.last_frame = null;
  previewUrls[field] = '';
  delete errors.value[field];
}

async function openImageEditor(field: 'first_frame' | 'last_frame') {
  const sourcePath = form[field];
  if (!sourcePath) return;
  imageEditorLaunchError.value = '';
  try {
    const result = await api.seedance.getEditableImage(sourcePath);
    if (!result.success) {
      imageEditorLaunchError.value = result.error.message;
      return;
    }
    editorImageUrl.value = result.data.image_data_url;
    editorEditSourceUrl.value = result.data.edit_source_data_url;
    editorGenerationLayout.value = result.data.generation_layout;
    editorError.value = '';
    editingField.value = field;
  } catch (error) {
    imageEditorLaunchError.value = error instanceof Error
      ? error.message
      : t('seedance.create.imageEditorLoadFailed');
  }
}

function closeImageEditor() {
  if (editorSaving.value) return;
  editingField.value = null;
  editorImageUrl.value = '';
  editorEditSourceUrl.value = '';
  editorGenerationLayout.value = null;
  editorError.value = '';
}

async function saveEditedImage(
  imageDataUrl: string,
  editSourceDataUrl: string,
  generationLayout: GenerationLayout | null
) {
  const field = editingField.value;
  const sourcePath = field ? form[field] : null;
  if (!field || !sourcePath || editorSaving.value) return;
  editorSaving.value = true;
  editorError.value = '';
  try {
    const result = await api.seedance.saveEditedImage(
      sourcePath, imageDataUrl, editSourceDataUrl, generationLayout
    );
    if (!result.success) {
      editorError.value = result.error.message;
      return;
    }
    form[field] = result.data.path;
    const thumbnail = await api.frame.getFrameThumbnail(result.data.path, 320);
    previewUrls[field] = `data:image/png;base64,${thumbnail}`;
    delete errors.value[field];
    editorSaving.value = false;
    closeImageEditor();
  } catch (error) {
    editorError.value = error instanceof Error ? error.message : t('seedance.create.imageEditorSaveFailed');
  } finally {
    editorSaving.value = false;
  }
}

async function openValidationModal(message: string) {
  validationTrigger = document.activeElement as HTMLElement;
  modalMessage.value = message;
  validationModal.value = true;
  await nextTick();
  validationModalRoot.value?.querySelector<HTMLElement>('button:not([disabled])')?.focus();
}

function closeValidationModal() {
  validationModal.value = false;
  validationTrigger?.focus();
  validationTrigger = null;
}

function onValidationKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    closeValidationModal();
    return;
  }
  if (validationModalRoot.value) trapModalTab(event, validationModalRoot.value);
}

onBeforeUnmount(() => {
  if (quoteTimer) {
    clearTimeout(quoteTimer);
    quoteTimer = null;
  }
  closeValidationModal();
  editingField.value = null;
  editorImageUrl.value = '';
  editorEditSourceUrl.value = '';
  paidConfirmModal.value = false;
  pendingRequest = null;
});

function errorMessage(issue?: SeedanceValidationIssue) {
  if (!issue) return '';
  // 平台业务异常原文优先透传（余额不足/未定价/素材无效等）。
  if (issue.message) return issue.message;
  return issue.key === 'seedance.validation.generic'
    ? `${t(issue.key)} (${safeCode(issue.code)})`
    : t(issue.key);
}

function safeCode(code: string) {
  return /^[A-Z0-9_]{1,64}$/.test(code) ? code : 'UNKNOWN';
}

async function submit() {
  if (submitting.value) return;
  if (paidConfirmModal.value) return;
  if (capabilitiesBlocked.value) return;
  submitting.value = true;
  try {
  errors.value = validateCreateForm(form);
  if (Object.keys(errors.value).length) {
    const blocking = errors.value.prompt || errors.value.body;
    if (blocking) await openValidationModal(errorMessage(blocking));
    return;
  }
  if (!ensureGenerationAccess()) return;
  const request = platformGenerationSelected.value
    ? { ...createRequest(form), return_last_frame: false }
    : createRequest(form);
  const preflight = await store.validateRequest(request, workspace.generationSource);
  if (!preflight) {
    const error = store.error;
    if (error) {
      const issue = validationIssueForApiError(error);
      errors.value[issue.field] = issue;
      if (issue.field === 'prompt' || issue.code === 'PAYLOAD_TOO_LARGE') {
        await openValidationModal(errorMessage(issue));
      }
    }
    return;
  }
  pendingRequest = request;
  if (!paidConfirmationEnabled.value) {
    await createPendingTask();
    return;
  }
  paidConfirmTrigger = document.activeElement as HTMLElement;
  paidConfirmModal.value = true;
  if (platformGenerationSelected.value) void ensureQuoteForConfirm();
  await nextTick();
  paidConfirmModalRoot.value?.querySelector<HTMLElement>('button:not([disabled])')?.focus();
  } finally {
    submitting.value = false;
  }
}

/** 弹窗确认前确保报价对应当前参数：签名一致就复用，否则立即重拉（不走防抖）。 */
async function ensureQuoteForConfirm() {
  if (quoteSignatureOf.value === quoteSignature() && (quoteValue.value !== null || quoteError.value)) return;
  if (quoteTimer) {
    clearTimeout(quoteTimer);
    quoteTimer = null;
  }
  await refreshPlatformQuote();
}

function ensureGenerationAccess(): boolean {
  if (platformGenerationSelected.value) {
    if (authStore.isLoggedIn) return true;
    accessDialogOpen.value = true;
    return false;
  }
  if (store.settings?.api_key_configured) return true;
  accessDialogOpen.value = true;
  return false;
}

function selectGenerationSource(source: string) {
  const next = source as GenerationSource;
  workspace.setGenerationSource(next);
  if (next === 'forfuner-ai') {
    // 参数收敛：平台源强制重置越界值（后端同样校验，双保险）。
    form.return_last_frame = false;
    clampToPlatformModel();
  } else {
    // Restore the saved API-key default when the current ID belongs to the platform.
    if (!localModelResolutions(form.model).length) form.model = store.settings?.default_model ?? 'mini';
    fixResolution();
    form.duration = correctDuration(form.duration);
  }
  scheduleQuoteRefresh();
}

function goToLogin() {
  accessDialogOpen.value = false;
  void router.push({ path: '/login', query: { redirect: router.currentRoute.value.fullPath } });
}

function goToSettings() {
  accessDialogOpen.value = false;
  void router.push('/ai-creation/settings');
}

async function confirmPaidAction() {
  if (submitting.value || !pendingRequest || platformConfirmBlocked.value) return;
  paidConfirmModal.value = false;
  submitting.value = true;
  try {
    await createPendingTask();
  } finally {
    submitting.value = false;
  }
}

async function createPendingTask() {
  if (!pendingRequest) return;
  const request = pendingRequest;
  pendingRequest = null;
  const source = workspace.generationSource;
  let task = await store.createTask(request, source);
  // 平台 401：token 过期——先静默重登（token watcher 会自动把新 token 推进 Python），重试一次。
  if (!task && source === 'forfuner-ai' && store.error?.code === 'UNAUTHORIZED') {
    const recovered = await authStore.silentRelogin();
    if (recovered) task = await store.createTask(request, source);
  }
  if (task) {
    workspace.setCurrentGeneration({ kind: 'video', localId: task.local_id });
    return;
  }
  const error = store.error;
  if (error) {
    const issue = validationIssueForApiError(error);
    errors.value[issue.field] = issue;
  }
}

function cancelPaidAction() {
  paidConfirmModal.value = false;
  pendingRequest = null;
  paidConfirmTrigger?.focus();
  paidConfirmTrigger = null;
}

function onPaidConfirmKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    cancelPaidAction();
    return;
  }
  if (paidConfirmModalRoot.value) trapModalTab(event, paidConfirmModalRoot.value);
}
</script>

<style scoped>
.seedance-prompt-surface {
  box-shadow:
    0 1px 0 rgb(255 255 255 / 3%) inset,
    0 18px 44px rgb(0 0 0 / 18%);
}

.error {
  @apply mt-1 text-sm text-danger;
}
</style>
