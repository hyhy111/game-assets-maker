<template>
  <article
    class="relative isolate min-w-0"
    :data-test="`recent-prompt-group-${groupId}`"
  >
    <template v-if="count > 1">
      <span class="pointer-events-none absolute inset-0 translate-x-1.5 translate-y-1.5 rounded-xl border border-dark-border bg-[#151820]" />
      <span class="pointer-events-none absolute inset-0 translate-x-[3px] translate-y-[3px] rounded-xl border border-dark-border bg-[#242424]" />
    </template>
    <div class="relative z-[1] h-full">
      <slot />
    </div>
    <button
      v-if="count > 1"
      type="button"
      class="media-overlay-action control-tooltip absolute right-[9px] top-[9px] z-[2]"
      :aria-expanded="expanded"
      :data-test="`recent-prompt-expand-${groupId}`"
      :aria-label="t(expanded ? 'aiCreation.recent.collapseTasks' : 'aiCreation.recent.expandTasks')"
      :data-tooltip="t(expanded ? 'aiCreation.recent.collapseTasks' : 'aiCreation.recent.expandTasks')"
      @click="emit('toggle-expanded')"
    >
      <ChevronDown
        class="h-3.5 w-3.5"
        aria-hidden="true"
      />
    </button>
  </article>

  <Teleport
    to="body"
    :disabled="teleportDisabled"
  >
    <div
      v-if="expanded && count > 1"
      ref="modalRoot"
      class="fixed inset-0 z-[80] flex items-center justify-center bg-black/75 p-4 backdrop-blur-[2px] sm:p-6"
      role="presentation"
      :data-test="`recent-prompt-expanded-${groupId}`"
      @click.self="requestClose"
      @keydown="onModalKeydown"
    >
      <section
        class="flex max-h-[calc(100vh-3rem)] w-full max-w-[1400px] flex-col overflow-hidden rounded-2xl border border-white/15 bg-[#151820] shadow-2xl shadow-black/70"
        role="dialog"
        aria-modal="true"
        :aria-label="t('aiCreation.recent.promptTasksDialog')"
      >
        <header class="flex items-start justify-between gap-4 border-b border-dark-border bg-primary/5 px-5 py-4">
          <p class="line-clamp-2 min-w-0 text-xs leading-5 text-gray-400">
            {{ prompt }}
          </p>
          <button
            ref="closeButton"
            type="button"
            class="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-white/[0.06] text-gray-400 transition hover:bg-white/[0.1] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
            :aria-label="t('aiCreation.recent.collapseTasks')"
            @click="requestClose"
          >
            <X
              class="h-4 w-4"
              aria-hidden="true"
            />
          </button>
        </header>
        <div class="grid min-h-0 flex-1 auto-rows-fr grid-cols-1 gap-4 overflow-y-auto p-4 sm:p-5 md:grid-cols-2 xl:grid-cols-4">
          <slot name="expanded" />
        </div>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { ChevronDown, X } from 'lucide-vue-next';
import { useI18n } from 'vue-i18n';
import { trapModalTab } from '@/modal-focus';

const props = defineProps<{
  groupId: string;
  prompt: string;
  count: number;
  expanded: boolean;
}>();

const emit = defineEmits<{
  'toggle-expanded': [];
}>();

const { t } = useI18n();
const modalRoot = ref<HTMLElement | null>(null);
const closeButton = ref<HTMLButtonElement | null>(null);
const teleportDisabled = typeof window === 'undefined';
let returnFocus: HTMLElement | null = null;
let previousBodyOverflow = '';
let pageLocked = false;

watch(() => props.expanded, async (expanded) => {
  if (typeof document === 'undefined') return;
  if (expanded) {
    returnFocus = document.activeElement as HTMLElement | null;
    previousBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    pageLocked = true;
    await nextTick();
    closeButton.value?.focus();
    return;
  }
  restorePage();
});

onBeforeUnmount(restorePage);

function requestClose() {
  emit('toggle-expanded');
}

function onModalKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault();
    requestClose();
    return;
  }
  if (modalRoot.value) trapModalTab(event, modalRoot.value);
}

function restorePage() {
  if (typeof document === 'undefined' || !pageLocked) return;
  document.body.style.overflow = previousBodyOverflow;
  pageLocked = false;
  returnFocus?.focus();
  returnFocus = null;
}
</script>
