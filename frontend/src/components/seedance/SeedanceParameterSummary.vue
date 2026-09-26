<template>
  <SeedancePanel :title="t('seedance.create.summaryTitle')" :description="t('seedance.create.summaryDescription')">
    <dl class="divide-y divide-[var(--seedance-border)] text-sm">
      <div v-for="item in items" :key="item.label" class="flex items-center justify-between gap-4 py-3">
        <dt class="text-[var(--seedance-muted)]">{{ item.label }}</dt>
        <dd class="text-right font-medium text-gray-200">{{ item.value }}</dd>
      </div>
    </dl>
    <div class="mt-5">
      <slot />
    </div>
  </SeedancePanel>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type { CreateForm } from '@/seedance-ui';
import SeedancePanel from './SeedancePanel.vue';

const props = defineProps<{ form: CreateForm }>();
const { t } = useI18n();

const durationLabel = computed(() => (
  props.form.duration === -1 ? t('seedance.ui.smart') : `${props.form.duration}s`
));
const audioLabel = computed(() => (
  props.form.generate_audio ? t('seedance.create.generateAudio') : t('seedance.ui.audioOff')
));
const items = computed(() => [
  { label: t('seedance.create.model'), value: t(`seedance.models.${props.form.model}`) },
  { label: t('seedance.create.resolution'), value: props.form.resolution },
  { label: t('seedance.create.ratio'), value: props.form.ratio === 'adaptive' ? t('seedance.create.adaptive') : props.form.ratio },
  { label: t('seedance.create.duration'), value: durationLabel.value },
  { label: t('seedance.create.audio'), value: audioLabel.value },
]);
</script>
