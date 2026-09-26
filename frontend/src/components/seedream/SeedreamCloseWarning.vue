<template>
  <div
    v-if="open"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
    role="dialog"
    aria-modal="true"
    aria-labelledby="seedream-close-warning-title"
    aria-describedby="seedream-close-warning-body"
    @click.self="$emit('continue')"
  >
    <div class="max-w-md rounded-xl border border-dark-border bg-dark-surface p-6">
      <h2 id="seedream-close-warning-title" class="text-lg font-semibold text-white">
        {{ t('seedream.close.title') }}
      </h2>
      <p id="seedream-close-warning-body" class="mt-3 text-gray-300">
        {{ t('seedream.close.body', { count }) }}
      </p>
      <div class="mt-5 flex justify-end gap-3">
        <Button
          variant="primary"
          data-test="seedream-close-continue"
          @click="$emit('continue')"
        >
          {{ t('seedream.close.continue') }}
        </Button>
        <Button
          variant="danger"
          data-test="seedream-close-exit"
          @click="$emit('exit')"
        >
          {{ t('seedream.close.exit') }}
        </Button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import Button from '@/components/common/Button.vue';

defineProps<{ open: boolean; count: number }>();
defineEmits<{ continue: []; exit: [] }>();

const { t } = useI18n();
</script>
