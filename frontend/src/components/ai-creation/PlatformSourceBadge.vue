<template>
  <span
    v-if="isPlatform"
    class="inline-flex items-center rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary-200"
    data-test="platform-source-badge"
  >
    {{ t('aiCreation.forfunerAI') }}
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

const props = defineProps<{ source?: string }>();
const { t } = useI18n();
// 只标平台源任务；直连（api-key / 缺省）不标，保持卡片简洁。
const isPlatform = computed(() => props.source === 'forfuner-ai');
</script>
