<template>
  <SeedreamShell>
    <template #page-bar>
      <SeedreamPageBar
        :title="t('seedream.settings.title')"
        :subtitle="t('seedream.settings.subtitle')"
      >
        <template #actions>
          <div class="flex items-center gap-3">
            <p v-if="saveFeedback" class="text-sm text-success">{{ saveFeedback }}</p>
            <Button
              type="submit"
              form="seedream-settings-form"
              :loading="saving"
            >
              {{ t('common.save') }}
            </Button>
          </div>
        </template>
      </SeedreamPageBar>
    </template>

    <p v-if="settingsError" class="mb-5 rounded-lg border border-danger/30 bg-danger/10 p-3 text-sm text-danger">
      {{ settingsError }}
    </p>

    <SeedreamPanel v-if="!settings">
      <div class="flex min-h-32 items-center justify-center text-gray-400" role="status">
        {{ t('common.loading') }}
      </div>
    </SeedreamPanel>

    <form
      v-else
      id="seedream-settings-form"
      class="space-y-5"
      @submit.prevent="save"
    >
      <SeedreamPanel
        :title="t('seedream.settings.defaults')"
        :description="t('seedream.settings.defaultsDescription')"
      >
        <label class="text-sm text-gray-300">
          {{ t('seedream.settings.defaultCount') }}
          <select
            v-model.number="draft.default_count"
            class="mt-2 w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-gray-100 sm:max-w-xs"
            data-test="seedream-settings-count"
          >
            <option v-for="count in allowedCounts" :key="count" :value="count">{{ count }}</option>
          </select>
        </label>
        <p class="mt-3 text-xs leading-5 text-gray-400">{{ t('seedream.settings.defaultCountHint') }}</p>
      </SeedreamPanel>

      <SeedreamPanel
        :title="t('seedream.settings.apiKey')"
        :description="t('seedream.settings.apiKeyDescription')"
      >
        <p class="text-sm text-gray-300">{{ t('seedream.settings.apiKeySharedHint') }}</p>
      </SeedreamPanel>
    </form>
  </SeedreamShell>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import Button from '@/components/common/Button.vue';
import SeedreamPageBar from '@/components/seedream/SeedreamPageBar.vue';
import SeedreamPanel from '@/components/seedream/SeedreamPanel.vue';
import SeedreamShell from '@/components/seedream/SeedreamShell.vue';
import { ALLOWED_COUNTS, DEFAULT_COUNT } from '@/seedream-ui';
import { useSeedreamStore } from '@/stores/seedream';
import type { SeedreamSettings } from '@/types';

const { t } = useI18n();
const store = useSeedreamStore();

const allowedCounts = ALLOWED_COUNTS;
const saving = ref(false);
const saveFeedback = ref('');

const draft = reactive<SeedreamSettings>({
  default_count: DEFAULT_COUNT,
  default_model: 'pro',
  default_resolution: '2K',
  default_ratio: '16:9',
});

const settings = computed(() => store.settings);
const settingsError = computed(() => store.error?.message ?? '');

watch(settings, (value) => {
  if (value) Object.assign(draft, value);
}, { immediate: true });

onMounted(() => {
  if (!store.settings) {
    void store.loadSettings();
  }
});

async function save() {
  saving.value = true;
  saveFeedback.value = '';
  const saved = await store.saveSettings({ ...draft });
  saving.value = false;
  if (saved) {
    saveFeedback.value = t('seedream.settings.saved');
  }
}
</script>
