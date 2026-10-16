<template>
  <div class="mt-5 border-t border-dark-border pt-4">
    <label
      v-if="ready"
      class="block text-sm text-gray-300"
    >
      {{ label }}
      <Select
        :model-value="modelValue"
        :options="options"
        :aria-label="label"
        :data-test="`platform-default-${kind}`"
        class="mt-2"
        @update:model-value="$emit('update:modelValue', String($event))"
      />
    </label>
    <div v-else>
      <p class="text-sm text-gray-300">
        {{ label }}
      </p>
      <p class="mt-2 text-sm text-gray-400">
        {{ modelValue || t('settings.platformDefaultAuto') }}
      </p>
    </div>
    <p class="mt-2 text-xs text-[var(--seedance-muted)]">
      {{ t('settings.platformDefaultHint') }}
    </p>
    <p
      v-if="!auth.isLoggedIn"
      class="mt-2 text-sm text-gray-400"
    >
      {{ t('settings.platformDefaultsLogin') }}
    </p>
    <p
      v-else-if="workspace.capabilitiesLoading"
      class="mt-2 text-sm text-gray-400"
      role="status"
    >
      {{ t('common.loading') }}
    </p>
    <div
      v-else-if="workspace.capabilitiesError"
      class="mt-2 flex items-center gap-2"
      role="status"
    >
      <p class="text-sm text-gray-400">
        {{ t('settings.platformDefaultsUnavailable') }}
      </p>
      <Button
        type="button"
        size="sm"
        variant="secondary"
        @click="workspace.ensureCapabilities(true)"
      >
        {{ t('settings.platformDefaultsRetry') }}
      </Button>
    </div>
    <p
      v-else-if="workspace.capabilities && models.length === 0"
      class="mt-2 text-sm text-gray-400"
    >
      {{ t('settings.platformDefaultsEmpty') }}
    </p>
    <p
      v-if="ready && missingModel"
      class="mt-2 text-sm text-warning"
    >
      {{ t('settings.platformDefaultMissing', { model: modelValue }) }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import Button from '@/components/common/Button.vue';
import Select from '@/components/common/Select.vue';
import { useAuthStore } from '@/stores/auth';
import { useAICreationStore } from '@/stores/aiCreation';
import { platformModelOptions } from '@/platform-models';

const props = defineProps<{ modelValue: string; kind: 'image' | 'video' }>();
defineEmits<{ 'update:modelValue': [value: string] }>();
const { t } = useI18n();
const auth = useAuthStore();
const workspace = useAICreationStore();
const models = computed(() => workspace.capabilities?.[props.kind].models ?? []);
const ready = computed(() => auth.isLoggedIn && workspace.capabilities !== null
  && !workspace.capabilitiesLoading && !workspace.capabilitiesError && models.value.length > 0);
const label = computed(() => t(props.kind === 'image' ? 'settings.platformImageDefault' : 'settings.platformVideoDefault'));
const missingModel = computed(() => props.modelValue !== '' && !models.value.some(model => model.model === props.modelValue));
const options = computed(() => [
  { value: '', label: t('settings.platformDefaultAuto') },
  ...platformModelOptions(models.value),
  ...(missingModel.value ? [{ value: props.modelValue, label: t('settings.platformDefaultMissingOption', { model: props.modelValue }) }] : []),
]);

watch(() => auth.isLoggedIn, loggedIn => {
  if (loggedIn) void workspace.ensureCapabilities(true);
  else workspace.clearCapabilities();
}, { immediate: true });
</script>
