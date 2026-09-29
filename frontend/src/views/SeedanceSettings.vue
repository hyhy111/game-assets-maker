<template>
  <div class="seedance-workspace">
    <Header
      sticky
      page-aligned
    />
    <SeedancePageBar
      :title="t('aiCreation.settingsTitle')"
      :subtitle="t('seedance.settings.subtitle')"
    >
      <template #actions>
        <div class="ml-auto flex items-center gap-2">
          <p v-if="saveFeedback" class="text-sm text-success">{{ saveFeedback }}</p>
          <Button
            type="submit"
            form="seedance-settings-form"
            :loading="saving"
            :disabled="!settingsReady"
          >
            {{ t('common.save') }}
          </Button>
        </div>
      </template>
    </SeedancePageBar>

    <main class="seedance-container">
      <p v-if="settingsError" class="mb-5 rounded-lg border border-danger/30 bg-danger/10 p-3 text-sm text-danger">
      {{ settingsError }}
      </p>
      <SeedancePanel v-if="!settingsReady">
        <div class="flex min-h-64 items-center justify-center text-[var(--seedance-muted)]" role="status">
          {{ initialLoadComplete ? t('aiCreation.settingsLoadFailed') : t('common.loading') }}
        </div>
      </SeedancePanel>

      <form
        v-else-if="settings"
        id="seedance-settings-form"
        class="seedance-settings-grid grid gap-5 xl:grid-cols-2"
        @submit.prevent="save"
      >
      <SeedancePanel
        :title="t('seedance.settings.apiKey')"
        :description="t('seedance.settings.apiKeyDescription')"
      >
        <div class="flex items-center gap-2 text-sm">
          <span
            class="h-2 w-2 rounded-full"
            :class="settings.api_key_configured ? 'bg-success' : 'bg-gray-500'"
          />
          <span :class="settings.api_key_configured ? 'text-success' : 'text-gray-400'">
            {{ settings.api_key_configured ? t('seedance.settings.apiKeyConfigured') : t('seedance.ui.keyNotConfigured') }}
          </span>
        </div>
        <input
          v-model="apiKey"
          type="password"
          autocomplete="new-password"
          class="seedance-control mt-4"
          :placeholder="t('seedance.settings.apiKeyHint')"
        >
        <p class="mt-2 text-xs leading-5 text-[var(--seedance-muted)]">{{ t('seedance.settings.apiKeySafeHint') }}</p>
        <div class="mt-4 flex flex-wrap gap-2">
          <Button type="button" variant="secondary" :loading="connectionLoading" @click="testConnection">
            {{ t('seedance.settings.testConnection') }}
          </Button>
          <Button type="button" variant="danger" @click="openClearConfirmation">
            {{ t('seedance.ui.clearKey') }}
          </Button>
        </div>
        <p v-if="connectionResult" class="mt-3 text-sm text-gray-300">{{ connectionResult }}</p>
      </SeedancePanel>

      <SeedancePanel
        :title="t('seedance.settings.appSettings')"
        :description="t('seedance.settings.appSettingsDescription')"
      >
        <div class="space-y-4">
          <div>
            <Switch v-model="appDraft.logger_enabled" :label="t('settings.enableLogging')" />
          </div>
          <div class="[&_span]:!text-danger">
            <Switch
              v-model="appDraft.paid_generation_confirmation_enabled"
              :label="t('settings.paidGenerationConfirmation')"
            />
          </div>
        </div>
      </SeedancePanel>

      <SeedancePanel
        class="xl:col-span-2"
        :title="t('storage.title')"
        :description="t('storage.description')"
      >
        <div class="grid gap-4 sm:grid-cols-2">
          <label class="text-sm text-gray-300">
            {{ t('storage.projectDir') }}
            <span class="mt-2 flex flex-col gap-2 sm:flex-row">
              <input :value="projectDisplayPath" class="seedance-control min-w-0 flex-1" readonly data-test="storage-project-dir">
              <Button type="button" class="h-[42px] shrink-0" @click="selectStorageDirectory('project_dir')">
                {{ t('seedance.ui.chooseFolder') }}
              </Button>
            </span>
          </label>
          <label class="text-sm text-gray-300">
            {{ t('storage.aiCacheDir') }}
            <span class="mt-2 flex flex-col gap-2 sm:flex-row">
              <input :value="cacheDisplayPath" class="seedance-control min-w-0 flex-1" readonly data-test="storage-cache-dir">
              <Button type="button" class="h-[42px] shrink-0" @click="selectStorageDirectory('cache_dir')">
                {{ t('seedance.ui.chooseFolder') }}
              </Button>
            </span>
          </label>
        </div>
        <p v-if="migrationError" class="mt-3 text-sm text-danger" data-test="storage-migration-error">
          {{ t('storage.migrationFailed') }}: {{ migrationError }}
        </p>
      </SeedancePanel>

      <SeedancePanel
        class="xl:col-span-2"
        :title="t('seedance.settings.defaults')"
        :description="t('seedance.settings.defaultsDescription')"
      >
        <div class="grid gap-4 sm:grid-cols-2">
          <label class="text-sm text-gray-300">
            {{ t('seedance.settings.model') }}
            <select v-model="draft.default_model" class="seedance-control mt-2" @change="correctDefault">
              <option value="standard">{{ t('seedance.models.standard') }}</option>
              <option value="fast">{{ t('seedance.models.fast') }}</option>
              <option value="mini">{{ t('seedance.models.mini') }}</option>
            </select>
          </label>
          <label class="text-sm text-gray-300">
            {{ t('seedance.settings.resolution') }}
            <select v-model="draft.default_resolution" class="seedance-control mt-2">
              <option v-for="option in supported" :key="option" :value="option">{{ option }}</option>
            </select>
          </label>
          <label class="text-sm text-gray-300">
            {{ t('seedance.create.ratio') }}
            <select v-model="draft.default_ratio" class="seedance-control mt-2">
              <option value="adaptive">{{ t('seedance.create.adaptive') }}</option>
              <option value="16:9">16:9</option>
              <option value="1:1">1:1</option>
              <option value="4:3">4:3</option>
            </select>
          </label>
          <label class="text-sm text-gray-300">
            {{ t('seedance.create.duration') }}
            <select v-model.number="draft.default_duration" class="seedance-control mt-2">
              <option v-for="duration in DURATION_OPTIONS" :key="duration" :value="duration">
                {{ t('seedance.ui.seconds', { value: duration }) }}
              </option>
            </select>
          </label>
        </div>
        <div class="mt-5 flex flex-wrap gap-6">
          <Switch v-model="draft.default_generate_audio" :label="t('seedance.create.generateAudio')" />
          <Switch v-model="draft.default_return_last_frame" :label="t('seedance.create.returnLastFrame')" />
        </div>
      </SeedancePanel>

      <SeedancePanel
        class="xl:col-span-2"
        :title="t('seedream.settings.defaults')"
        :description="t('seedream.settings.defaultsDescription')"
      >
        <div class="grid gap-4 sm:grid-cols-2">
          <label class="text-sm text-gray-300">
            {{ t('seedream.create.model') }}
            <select v-model="seedreamDraft.default_model" class="seedance-control mt-2" data-test="seedream-settings-model" @change="fixSeedreamDefault">
              <option value="pro">{{ t('seedream.models.pro') }}</option>
              <option value="flash">{{ t('seedream.models.flash') }}</option>
              <option value="lite">{{ t('seedream.models.lite') }}</option>
            </select>
          </label>
          <label class="text-sm text-gray-300">
            {{ t('seedream.create.resolution') }}
            <select v-model="seedreamDraft.default_resolution" class="seedance-control mt-2" data-test="seedream-settings-resolution">
              <option v-for="option in seedreamSupportedResolutions" :key="option" :value="option">{{ option }}</option>
            </select>
          </label>
          <label class="text-sm text-gray-300">
            {{ t('seedream.create.ratio') }}
            <select v-model="seedreamDraft.default_ratio" class="seedance-control mt-2" data-test="seedream-settings-ratio">
              <option v-for="ratio in seedreamAllowedRatios" :key="ratio" :value="ratio">{{ ratio }}</option>
            </select>
          </label>
          <label class="text-sm text-gray-300">
            {{ t('seedream.settings.defaultCount') }}
            <select
              v-model.number="seedreamDraft.default_count"
              class="seedance-control mt-2"
              data-test="seedream-settings-count"
            >
              <option v-for="count in allowedCounts" :key="count" :value="count">{{ count }}</option>
            </select>
          </label>
        </div>
        <p class="mt-3 text-xs leading-5 text-[var(--seedance-muted)]">{{ t('seedream.settings.defaultCountHint') }}</p>
      </SeedancePanel>

      <SeedancePanel
        class="xl:col-span-2"
        :title="t('seedance.settings.cacheManagement')"
        :description="t('seedance.settings.cacheDescription')"
      >
        <div class="grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_minmax(360px,.8fr)]">
          <div>
            <label class="block text-sm text-gray-300">
              {{ t('seedance.settings.retention') }}
              <select v-model.number="draft.retention_days" class="seedance-control mt-2">
                <option :value="0">{{ t('seedance.ui.never') }}</option>
                <option v-for="day in [7, 30, 90, 180]" :key="day" :value="day">
                  {{ t('seedance.ui.days', { value: day }) }}
                </option>
              </select>
            </label>
            <p v-if="retentionDisabled" class="mt-2 text-sm text-[var(--seedance-muted)]">
              {{ t('seedance.ui.retentionDisabled') }}
            </p>
          </div>

          <div class="rounded-xl border border-[var(--seedance-border)] bg-black/15 p-4">
            <dl class="grid grid-cols-2 gap-4 text-sm">
              <div>
                <dt class="text-[var(--seedance-muted)]">{{ t('seedance.settings.totalBytes') }}</dt>
                <dd class="mt-1 text-lg font-semibold text-white">{{ formatBytes(cache?.total_bytes) }}</dd>
              </div>
              <div>
                <dt class="text-[var(--seedance-muted)]">{{ t('seedance.settings.clearableBytes') }}</dt>
                <dd class="mt-1 text-lg font-semibold text-white">{{ formatBytes(cache?.clearable_bytes) }}</dd>
              </div>
              <div>
                <dt class="text-[var(--seedance-muted)]">{{ t('seedance.settings.taskCount') }}</dt>
                <dd class="mt-1 text-gray-200">{{ cache?.task_count ?? 0 }}</dd>
              </div>
              <div>
                <dt class="text-[var(--seedance-muted)]">{{ t('seedance.settings.protectedTaskCount') }}</dt>
                <dd class="mt-1 text-gray-200">{{ cache?.protected_task_count ?? 0 }}</dd>
              </div>
            </dl>
            <Button
              class="mt-5"
              block
              type="button"
              variant="danger"
              :disabled="retentionDisabled"
              :loading="cleaning"
              @click="openCacheCleanConfirmation"
            >
              {{ t('seedance.settings.clearCache') }}
            </Button>
            <p v-if="cleaned" class="mt-3 text-sm text-gray-300">
              {{ t('seedance.ui.released') }} {{ formatBytes(cleaned.bytes_released) }};
              {{ cleaned.protected_tasks_skipped }} {{ t('seedance.ui.protectedSkipped') }}
            </p>
          </div>
        </div>
      </SeedancePanel>

      </form>
    </main>

    <div
      v-if="confirmCacheClean"
      ref="cacheCleanModalRoot"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="clean-cache-title"
      aria-describedby="clean-cache-description"
      @keydown="onCacheCleanKeydown"
      @click.self="closeCacheCleanConfirmation"
    >
      <div class="max-w-md rounded-xl border border-dark-border bg-dark-surface p-6">
        <h2 id="clean-cache-title" class="text-lg font-semibold text-white">{{ t('seedance.settings.clearCache') }}</h2>
        <p id="clean-cache-description" class="mt-3 text-gray-300">{{ t('seedance.settings.clearCacheConfirmation') }}</p>
        <div class="mt-5 flex justify-end gap-2">
          <Button type="button" variant="secondary" @click="closeCacheCleanConfirmation">{{ t('common.cancel') }}</Button>
          <Button type="button" variant="danger" :loading="cleaning" :disabled="cleaning" @click="clean">
            {{ t('seedance.settings.clearCache') }}
          </Button>
        </div>
      </div>
    </div>

    <div
      v-if="confirmClear"
      ref="clearModalRoot"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="clear-key-title"
      aria-describedby="clear-key-description"
      @keydown="onClearKeydown"
      @click.self="closeClearConfirmation"
    >
      <div class="max-w-md rounded-xl border border-dark-border bg-dark-surface p-6">
        <h2 id="clear-key-title" class="text-lg font-semibold text-white">{{ t('seedance.settings.clearKeyTitle') }}</h2>
        <p id="clear-key-description" class="mt-3 text-gray-300">{{ t('seedance.settings.clearKeyConfirmation') }}</p>
        <div class="mt-5 flex justify-end gap-2">
          <Button type="button" variant="secondary" @click="closeClearConfirmation">{{ t('common.cancel') }}</Button>
          <Button type="button" variant="danger" :loading="clearingKey" @click="clearKey">{{ t('seedance.ui.clearKey') }}</Button>
        </div>
      </div>
    </div>

    <div
      v-if="migrationSummary"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="storage-migration-title"
      aria-describedby="storage-migration-description"
      data-test="storage-migration-confirm"
    >
      <div class="max-w-lg rounded-xl border border-dark-border bg-dark-surface p-6">
        <h2 id="storage-migration-title" class="text-lg font-semibold text-white">{{ t('storage.migrationTitle') }}</h2>
        <p id="storage-migration-description" class="mt-3 text-gray-300">{{ t('storage.migrationDescription') }}</p>
        <ul class="mt-4 space-y-3">
          <li
            v-for="entry in migrationSummary.entries"
            :key="entry.kind"
            class="rounded-lg border border-[var(--seedance-border)] bg-black/15 p-3 text-sm"
          >
            <p class="font-medium text-gray-200">
              {{ entry.kind === 'project' ? t('storage.scopeProject') : t('storage.scopeAiCache') }}
            </p>
            <p class="mt-1 break-all text-gray-400">{{ entry.source }} → {{ entry.target }}</p>
            <p class="mt-1 text-xs text-[var(--seedance-muted)]">
              {{ entry.file_count }} · {{ formatBytes(entry.total_bytes) }}
            </p>
          </li>
        </ul>
        <p class="mt-4 text-sm text-gray-300">{{ t('storage.keepOldNotice') }}</p>
        <p class="mt-2 text-sm text-amber-300">{{ t('storage.restartNotice') }}</p>
        <p v-if="migrationProgress" class="mt-3 text-sm text-gray-300">
          {{ t('storage.migrationProgress', { copied: migrationProgress.copied, total: migrationProgress.total }) }}
        </p>
        <div class="mt-5 flex justify-end gap-2">
          <Button type="button" variant="secondary" :disabled="executingMigration" @click="closeMigrationConfirmation">
            {{ t('common.cancel') }}
          </Button>
          <Button type="button" variant="danger" :loading="executingMigration" @click="executeMigration">
            {{ t('storage.migrationConfirm') }}
          </Button>
        </div>
      </div>
    </div>

    <div
      v-if="restartRequired"
      class="fixed inset-0 z-[60] flex items-center justify-center bg-black/80 p-4"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="storage-restart-title"
      aria-describedby="storage-restart-description"
      data-test="storage-restart-required"
    >
      <div class="max-w-md rounded-xl border border-dark-border bg-dark-surface p-6">
        <h2 id="storage-restart-title" class="text-lg font-semibold text-white">{{ t('storage.restartRequiredTitle') }}</h2>
        <p id="storage-restart-description" class="mt-3 text-gray-300">{{ t('storage.restartRequiredDescription') }}</p>
        <div class="mt-5 flex justify-end gap-2">
          <Button type="button" variant="secondary" @click="closeApp">{{ t('storage.closeApp') }}</Button>
          <Button type="button" data-test="storage-restart-now" @click="restartNow">{{ t('storage.restartNow') }}</Button>
        </div>
      </div>
    </div>

    <div
      v-if="confirmLeave"
      ref="leaveModalRoot"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="unsaved-settings-title"
      aria-describedby="unsaved-settings-description"
      @keydown="onLeaveKeydown"
      @click.self="continueEditing"
    >
      <div class="max-w-md rounded-xl border border-dark-border bg-dark-surface p-6">
        <h2 id="unsaved-settings-title" class="text-lg font-semibold text-white">
          {{ t('seedance.settings.unsavedTitle') }}
        </h2>
        <p id="unsaved-settings-description" class="mt-3 text-gray-300">
          {{ t('seedance.settings.unsavedDescription') }}
        </p>
        <div class="mt-5 flex justify-end gap-2">
          <Button type="button" variant="secondary" @click="continueEditing">
            {{ t('seedance.settings.continueEditing') }}
          </Button>
          <Button type="button" variant="danger" @click="discardAndLeave">
            {{ t('seedance.settings.discardAndLeave') }}
          </Button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { onBeforeRouteLeave, useRouter } from 'vue-router';
import { api } from '@/api';
import Button from '@/components/common/Button.vue';
import Switch from '@/components/common/Switch.vue';
import Header from '@/components/layout/Header.vue';
import SeedancePageBar from '@/components/seedance/SeedancePageBar.vue';
import SeedancePanel from '@/components/seedance/SeedancePanel.vue';
import { trapModalTab } from '@/modal-focus';
import { correctDuration, correctResolution, DURATION_OPTIONS, formatBytes, MODEL_RESOLUTIONS, validationIssueForApiError } from '@/seedance-ui';
import {
  ALLOWED_COUNTS,
  ALLOWED_RATIOS,
  correctResolution as correctSeedreamResolution,
  DEFAULT_COUNT,
  MODEL_RESOLUTIONS as SEEDREAM_MODEL_RESOLUTIONS,
} from '@/seedream-ui';
import { useConfigStore } from '@/stores/config';
import { useSeedanceStore } from '@/stores/seedance';
import { useSeedreamStore } from '@/stores/seedream';
import type {
  SeedanceCacheCleanResult,
  SeedanceSettings,
  SeedreamSettings,
  StorageMigrationProgress,
  StorageMigrationSummary,
  StorageSettings,
  StorageSettingsDraft,
} from '@/types';

const { t } = useI18n();
const router = useRouter();
const store = useSeedanceStore();
const seedreamStore = useSeedreamStore();
const configStore = useConfigStore();
const apiKey = ref('');
const connectionResult = ref('');
const cleaned = ref<SeedanceCacheCleanResult | null>(null);
const confirmClear = ref(false);
const clearModalRoot = ref<HTMLElement | null>(null);
const confirmCacheClean = ref(false);
const cacheCleanModalRoot = ref<HTMLElement | null>(null);
const confirmLeave = ref(false);
const leaveModalRoot = ref<HTMLElement | null>(null);
const savedSnapshot = ref('');
const pendingRoute = ref('');
const connectionLoading = ref(false);
const saving = ref(false);
const initialLoadComplete = ref(false);
const seedanceSettingsLoaded = ref(Boolean(store.settings));
const cleaning = ref(false);
const clearingKey = ref(false);
const saveFeedback = ref('');
const allowedCounts = ALLOWED_COUNTS;
let clearTrigger: HTMLElement | null = null;
let cacheCleanTrigger: HTMLElement | null = null;
let leaveTrigger: HTMLElement | null = null;
let allowPendingNavigation = false;
const appDraft = reactive({
  logger_enabled: false,
  paid_generation_confirmation_enabled: true,
});
const seedreamDraft = reactive<SeedreamSettings>({
  default_count: DEFAULT_COUNT,
  default_model: 'pro',
  default_resolution: '1K',
  default_ratio: '16:9',
});
const draft = reactive<Omit<SeedanceSettings, 'api_key_configured' | 'last_cleanup_at' | 'default_priority' | 'default_expires_after'>>({
  cache_dir: '',
  default_model: 'standard',
  default_resolution: '720p',
  default_ratio: 'adaptive',
  default_duration: 4,
  default_generate_audio: false,
  default_return_last_frame: false,
  retention_days: 0,
});
// Storage-location drafts hold the *configured* values; the inputs display
// the resolved absolute paths. Edits stay draft-only until Save is clicked.
const storageSettings = ref<StorageSettings | null>(null);
const storageDraft = reactive({ project_dir: '', cache_dir: '' });
const migrationSummary = ref<StorageMigrationSummary | null>(null);
const migrationError = ref('');
const migrationProgress = ref<StorageMigrationProgress | null>(null);
const executingMigration = ref(false);
const restartRequired = ref(false);
const settings = computed(() => store.settings);
const settingsReady = computed(() => Boolean(
  store.settings
  && seedanceSettingsLoaded.value
  && seedreamStore.settings
  && configStore.config
  && !seedreamStore.error
  && !configStore.error
));
const cache = computed(() => store.cacheStatus);
const supported = computed(() => MODEL_RESOLUTIONS[draft.default_model]);
const retentionDisabled = computed(() => draft.retention_days === 0);
const seedreamAllowedRatios = ALLOWED_RATIOS;
const seedreamSupportedResolutions = computed(() => SEEDREAM_MODEL_RESOLUTIONS[seedreamDraft.default_model]);
const currentSnapshot = computed(() => JSON.stringify({
  app: { ...appDraft },
  seedance: { ...draft },
  seedream: { ...seedreamDraft },
  storage: { ...storageDraft },
  apiKeyChanged: apiKey.value.length > 0,
}));
// Relative configured values display as the backend-resolved absolute roots;
// a chosen (absolute) directory displays as itself.
const isAbsoluteStoragePath = (value: string) => /^(~|[a-zA-Z]:[\\/]|\\\\|\/)/.test(value.trim());
const storageDisplayPath = (draft: string, resolvedRoot: string | undefined) => (
  isAbsoluteStoragePath(draft) ? draft : resolvedRoot ?? draft
);
const projectDisplayPath = computed(() => storageDisplayPath(storageDraft.project_dir, storageSettings.value?.projects_root));
const cacheDisplayPath = computed(() => storageDisplayPath(storageDraft.cache_dir, storageSettings.value?.ai_cache_root));
// Textual comparison is only an immediate hint for routing the save; the
// backend re-resolves and stays the authority on physical path equality.
const storagePathsChanged = computed(() => Boolean(
  storageSettings.value
  && (storageDraft.project_dir !== storageSettings.value.project_dir
    || storageDraft.cache_dir !== storageSettings.value.cache_dir)
));
const hasUnsavedChanges = computed(() => (
  savedSnapshot.value.length > 0 && currentSnapshot.value !== savedSnapshot.value
));
const settingsError = computed(() => {
  if (store.error) {
    const issue = validationIssueForApiError(store.error);
    const code = /^[A-Z0-9_]{1,64}$/.test(issue.code) ? issue.code : 'UNKNOWN';
    return issue.key === 'seedance.validation.generic' ? `${t(issue.key)} (${code})` : t(issue.key);
  }
  if (seedreamStore.error?.message) return seedreamStore.error.message;
  return configStore.error ?? '';
});

onMounted(async () => {
  seedanceSettingsLoaded.value = false;
  const [settingsLoaded, , , , storageResult] = await Promise.all([
    store.loadSettings(),
    store.loadCacheStatus(),
    configStore.loadConfig(),
    seedreamStore.loadSettings(),
    api.storage.getSettings(),
  ]);
  seedanceSettingsLoaded.value = settingsLoaded;
  initialLoadComplete.value = true;
  if (storageResult.success) {
    storageSettings.value = storageResult.settings;
    storageDraft.project_dir = storageResult.settings.project_dir;
    storageDraft.cache_dir = storageResult.settings.cache_dir;
  }
  if (store.settings) {
    Object.assign(draft, store.settings);
    draft.default_duration = correctDuration(draft.default_duration);
  }
  if (configStore.config) syncAppDraft(configStore.config);
  if (seedreamStore.settings) Object.assign(seedreamDraft, seedreamStore.settings);
  markSettingsSaved();
});

watch(settings, (value) => {
  if (value) {
    Object.assign(draft, value);
    draft.default_duration = correctDuration(draft.default_duration);
    // Fallback while the storage endpoint is unavailable: keep the cache
    // directory draft aligned with the Seedance settings.
    if (!storageSettings.value) storageDraft.cache_dir = value.cache_dir;
  }
}, { immediate: true });

watch(() => seedreamStore.settings, (value) => {
  if (value) Object.assign(seedreamDraft, value);
}, { immediate: true });

watch(() => configStore.config, (value) => {
  if (value) {
    syncAppDraft(value);
    if (!storageSettings.value && value.project_dir) storageDraft.project_dir = value.project_dir;
  }
}, { immediate: true });

onBeforeUnmount(() => {
  closeClearConfirmation();
  closeCacheCleanConfirmation();
});

onBeforeRouteLeave((to) => {
  // A committed migration makes this runtime stale: the only allowed exits
  // are the one-click restart or closing the app from the blocking overlay.
  if (restartRequired.value) return false;
  if (!hasUnsavedChanges.value || allowPendingNavigation) {
    allowPendingNavigation = false;
    return true;
  }
  pendingRoute.value = to.fullPath;
  openLeaveConfirmation();
  return false;
});

function correctDefault() {
  draft.default_resolution = correctResolution(draft.default_model, draft.default_resolution);
}

function fixSeedreamDefault() {
  seedreamDraft.default_resolution = correctSeedreamResolution(
    seedreamDraft.default_model,
    seedreamDraft.default_resolution
  );
}

function syncAppDraft(config: { logger_enabled: boolean; paid_generation_confirmation_enabled: boolean }) {
  appDraft.logger_enabled = config.logger_enabled;
  appDraft.paid_generation_confirmation_enabled = config.paid_generation_confirmation_enabled !== false;
}

function markSettingsSaved() {
  savedSnapshot.value = currentSnapshot.value;
}

function openLeaveConfirmation() {
  leaveTrigger = document.activeElement as HTMLElement;
  confirmLeave.value = true;
  void nextTick(() => leaveModalRoot.value?.querySelector<HTMLElement>('button:not([disabled])')?.focus());
}

function continueEditing() {
  confirmLeave.value = false;
  pendingRoute.value = '';
  leaveTrigger?.focus();
  leaveTrigger = null;
}

async function discardAndLeave() {
  const destination = pendingRoute.value;
  confirmLeave.value = false;
  pendingRoute.value = '';
  allowPendingNavigation = true;
  await router.push(destination);
}

function onLeaveKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    continueEditing();
    return;
  }
  if (leaveModalRoot.value) trapModalTab(event, leaveModalRoot.value);
}

async function selectStorageDirectory(field: 'project_dir' | 'cache_dir') {
  const path = await api.system.selectDirectory();
  if (path) storageDraft[field] = path;
}

async function testConnection() {
  connectionLoading.value = true;
  connectionResult.value = await store.testConnection(apiKey.value)
    ? t('seedance.ui.connectionOk')
    : t('seedance.ui.connectionFailed');
  connectionLoading.value = false;
}

async function openClearConfirmation() {
  clearTrigger = document.activeElement as HTMLElement;
  confirmClear.value = true;
  await nextTick();
  clearModalRoot.value?.querySelector<HTMLElement>('button:not([disabled])')?.focus();
}

function closeClearConfirmation() {
  confirmClear.value = false;
  clearTrigger?.focus();
  clearTrigger = null;
}

function onClearKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    closeClearConfirmation();
    return;
  }
  if (clearModalRoot.value) trapModalTab(event, clearModalRoot.value);
}

async function clearKey() {
  clearingKey.value = true;
  const saved = await store.saveSettings({ api_key: null });
  clearingKey.value = false;
  if (saved) {
    apiKey.value = '';
    closeClearConfirmation();
    saveFeedback.value = t('seedance.settings.saved');
  }
}

async function openCacheCleanConfirmation() {
  if (retentionDisabled.value) return;
  cacheCleanTrigger = document.activeElement as HTMLElement;
  confirmCacheClean.value = true;
  await nextTick();
  cacheCleanModalRoot.value?.querySelector<HTMLElement>('button:not([disabled])')?.focus();
}

function closeCacheCleanConfirmation() {
  confirmCacheClean.value = false;
  cacheCleanTrigger?.focus();
  cacheCleanTrigger = null;
}

function onCacheCleanKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    closeCacheCleanConfirmation();
    return;
  }
  if (cacheCleanModalRoot.value) trapModalTab(event, cacheCleanModalRoot.value);
}

async function save() {
  if (!settingsReady.value) return;
  saving.value = true;
  saveFeedback.value = '';
  migrationError.value = '';
  if (storagePathsChanged.value) {
    await saveWithMigrationCheck();
  } else {
    await savePlain();
  }
  saving.value = false;
}

async function savePlain() {
  const appSaved = await configStore.saveConfig({ ...appDraft });
  const update = { ...draft, ...(apiKey.value ? { api_key: apiKey.value } : {}) };
  const seedanceSaved = appSaved ? await store.saveSettings(update) : null;
  const seedreamSaved = seedanceSaved ? await seedreamStore.saveSettings({ ...seedreamDraft }) : null;
  if (seedreamSaved) {
    apiKey.value = '';
    markSettingsSaved();
    saveFeedback.value = t('seedance.settings.saved');
  }
}

async function saveWithMigrationCheck() {
  // A newly entered API key travels inside the transactional draft: it is
  // committed together with every other setting on execute, and nothing is
  // persisted when the migration fails. After a successful migration the app
  // restarts anyway, so the Seedance manager picks the key up on next launch.
  const combined: StorageSettingsDraft = {
    logger_enabled: appDraft.logger_enabled,
    paid_generation_confirmation_enabled: appDraft.paid_generation_confirmation_enabled,
    project_dir: storageDraft.project_dir,
    seedance: {
      ...draft,
      cache_dir: storageDraft.cache_dir,
      ...(apiKey.value ? { api_key: apiKey.value } : {}),
    },
    seedream: { ...seedreamDraft },
  };
  const result = await api.storage.saveSettings(combined);
  if (!result.success) {
    migrationError.value = result.error.message;
    return;
  }
  if (!result.migration_required) {
    // Plain save (equivalent path spellings): no migration to fail, so rebuild
    // the Seedance manager for a newly entered key like the normal flow does.
    if (apiKey.value) {
      const keySaved = await store.saveSettings({ api_key: apiKey.value });
      if (!keySaved) return;
    }
    apiKey.value = '';
    if (storageSettings.value) {
      storageSettings.value = {
        ...storageSettings.value,
        project_dir: storageDraft.project_dir,
        cache_dir: storageDraft.cache_dir,
      };
    }
    markSettingsSaved();
    saveFeedback.value = t('seedance.settings.saved');
    return;
  }
  migrationSummary.value = result.migration;
}

function closeMigrationConfirmation() {
  migrationSummary.value = null;
  migrationProgress.value = null;
}

async function executeMigration() {
  if (!migrationSummary.value) return;
  executingMigration.value = true;
  migrationError.value = '';
  migrationProgress.value = null;
  window.addEventListener('storage-migration-progress', onMigrationProgress);
  try {
    const result = await api.storage.executeMigration(migrationSummary.value.token);
    if (!result.success) {
      // Nothing was committed: keep the draft dirty so the user can retry.
      migrationError.value = result.error.message;
      migrationSummary.value = null;
      return;
    }
    migrationSummary.value = null;
    markSettingsSaved();
    restartRequired.value = true;
  } finally {
    executingMigration.value = false;
    window.removeEventListener('storage-migration-progress', onMigrationProgress);
  }
}

function onMigrationProgress(event: Event) {
  migrationProgress.value = (event as CustomEvent<StorageMigrationProgress>).detail;
}

async function restartNow() {
  // Enter the application close flow immediately: the bridge records the
  // restart intent and destroys the window, so there is no plain-save
  // success message to wait for.
  await api.lifecycle.requestAppRestart();
}

function closeApp() {
  // Route through the backend so the closed event runs the regular cleanup;
  // PyWebView does not reliably route a plain JS window close to the native
  // window.
  api.lifecycle.closeApp();
}

async function clean() {
  if (retentionDisabled.value) return;
  cleaning.value = true;
  cleaned.value = await store.cleanCache(draft.retention_days);
  cleaning.value = false;
  if (cleaned.value) closeCacheCleanConfirmation();
}
</script>
