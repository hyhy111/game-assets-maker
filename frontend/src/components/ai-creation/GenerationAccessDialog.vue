<template>
  <Teleport to="body" :disabled="teleportDisabled">
    <div
      v-if="open"
      ref="modalRoot"
      class="fixed inset-0 z-[70] flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="generation-access-title"
      aria-describedby="generation-access-description"
      data-test="generation-access-dialog"
      @click.self="emit('cancel')"
      @keydown="onKeydown"
    >
      <div class="w-full max-w-md rounded-xl border border-dark-border bg-dark-surface p-6 shadow-2xl shadow-black/50">
        <h2 id="generation-access-title" class="text-lg font-semibold text-white">
          {{ t(loggedIn ? 'aiCreation.apiKeyRequiredTitle' : 'aiCreation.generationAccessTitle') }}
        </h2>
        <p id="generation-access-description" class="mt-3 text-sm leading-6 text-gray-300">
          {{ t(loggedIn ? 'aiCreation.apiKeyRequiredDescription' : 'aiCreation.generationAccessDescription') }}
        </p>
        <div class="mt-5 flex flex-col gap-3 sm:flex-row sm:justify-end">
          <Button v-if="!loggedIn" variant="secondary" @click="emit('login')">
            {{ t('aiCreation.loginToGenerate') }}
          </Button>
          <Button @click="emit('configure-key')">
            {{ t('aiCreation.configureApiKey') }}
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

const props = defineProps<{ open: boolean; loggedIn: boolean }>();
const emit = defineEmits<{
  cancel: [];
  login: [];
  'configure-key': [];
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
    modalRoot.value?.querySelector<HTMLElement>('button:not([disabled])')?.focus();
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
