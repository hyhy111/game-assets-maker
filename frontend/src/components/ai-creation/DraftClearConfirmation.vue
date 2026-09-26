<template>
  <Teleport to="body" :disabled="teleportDisabled">
    <div
      v-if="open"
      ref="modalRoot"
      class="fixed inset-0 z-[70] flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="draft-clear-title"
      aria-describedby="draft-clear-description"
      data-test="draft-clear-confirmation"
      @keydown="onKeydown"
      @click.self="emit('cancel')"
    >
      <div class="w-full max-w-md rounded-xl border border-dark-border bg-dark-surface p-6 shadow-2xl shadow-black/50">
        <h2 id="draft-clear-title" class="text-lg font-semibold text-white">
          {{ t('aiCreation.clearTitle') }}
        </h2>
        <p id="draft-clear-description" class="mt-3 text-gray-300">
          {{ t('aiCreation.clearConfirm') }}
        </p>
        <div class="mt-5 flex justify-end gap-3">
          <Button variant="secondary" data-test="draft-clear-cancel" @click="emit('cancel')">
            {{ t('common.cancel') }}
          </Button>
          <Button data-test="draft-clear-submit" @click="emit('confirm')">
            {{ t('aiCreation.clear') }}
          </Button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import Button from '@/components/common/Button.vue';
import { trapModalTab } from '@/modal-focus';

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{
  cancel: [];
  confirm: [];
}>();

const { t } = useI18n();
const modalRoot = ref<HTMLElement | null>(null);
const teleportDisabled = typeof window === 'undefined';
let returnFocus: HTMLElement | null = null;

watch(() => props.open, async (open) => {
  if (typeof document === 'undefined') return;
  if (open) {
    returnFocus = document.activeElement as HTMLElement | null;
    await nextTick();
    modalRoot.value?.querySelector<HTMLElement>('button')?.focus();
    return;
  }
  restoreFocus();
});

onBeforeUnmount(restoreFocus);

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault();
    emit('cancel');
    return;
  }
  if (modalRoot.value) trapModalTab(event, modalRoot.value);
}

function restoreFocus() {
  returnFocus?.focus();
  returnFocus = null;
}
</script>
