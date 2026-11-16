<template>
  <section class="mt-3 shrink-0 rounded-xl border border-dark-border bg-dark-surface">
    <div class="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3">
      <div>
        <p
          class="text-sm font-medium text-gray-200"
          aria-live="polite"
        >
          {{ t('frameVisibility.hiddenCount', { count: filenames.length }) }}
        </p>
        <p class="text-xs text-gray-400">
          {{ t('frameVisibility.hint') }}
        </p>
      </div>

      <div class="ml-auto flex flex-wrap items-center justify-end gap-2">
        <Button
          variant="danger"
          size="sm"
          :disabled="!canHide || busy"
          icon-only
          :tooltip="t('buttonHints.hideFrame')"
          @click="$emit('hide')"
        >
          <EyeOff
            class="h-5 w-5"
            aria-hidden="true"
          />
        </Button>
        <Button
          variant="secondary"
          size="sm"
          class="h-10"
          :disabled="!filenames.length || busy"
          @click="$emit('restoreAll')"
        >
          {{ t('frameVisibility.restoreAll') }}
        </Button>
        <Button
          ref="toggle"
          variant="secondary"
          size="sm"
          class="h-10 gap-1.5"
          :aria-expanded="expanded"
          aria-controls="hidden-frame-list"
          @click="expanded = !expanded"
        >
          {{ t(expanded ? 'frameVisibility.collapse' : 'frameVisibility.expand') }}
          <ChevronDown
            class="h-4 w-4 text-gray-400"
            :class="{ 'rotate-180': expanded }"
            aria-hidden="true"
          />
        </Button>
      </div>
    </div>

    <div
      v-show="expanded"
      id="hidden-frame-list"
      class="border-t border-dark-border"
      @keydown.up.stop
      @keydown.down.stop
    >
      <ul
        v-if="expanded && cards.length"
        ref="list"
        class="grid max-h-[min(12rem,28vh)] auto-rows-max grid-cols-[repeat(auto-fill,minmax(min(100%,8rem),1fr))] gap-2 overflow-y-auto px-4 py-3"
      >
        <li
          v-for="card in cards"
          :key="card.filename"
          class="relative min-w-0 overflow-hidden rounded-lg border border-dark-border bg-dark-bg"
        >
          <button
            v-if="card.preview"
            type="button"
            class="block h-16 w-full cursor-zoom-in after:absolute after:inset-0 hover:after:bg-white/5 focus-visible:outline-none focus-visible:after:ring-2 focus-visible:after:ring-inset focus-visible:after:ring-primary"
            :aria-label="t('frameVisibility.previewFrame', { frame: card.label })"
            aria-haspopup="dialog"
            :title="card.filename"
            @click="openPreview(card.filename, $event)"
          >
            <span class="hidden-frame-preview relative grid h-full place-items-center">
              <ImageOff
                class="h-5 w-5 text-gray-400"
                aria-hidden="true"
              />
              <img
                :key="card.preview.url"
                :src="card.preview.url"
                class="hidden-frame-preview absolute inset-0 h-full w-full object-contain p-1"
                loading="lazy"
                decoding="async"
                alt=""
                @error="($event.target as HTMLImageElement).classList.add('hidden')"
              >
              <span class="absolute right-1.5 top-1.5 grid h-6 w-6 place-items-center rounded bg-black/70 text-white">
                <ZoomIn
                  class="h-4 w-4"
                  aria-hidden="true"
                />
              </span>
            </span>
          </button>
          <div
            v-else
            class="hidden-frame-preview grid h-16 place-items-center"
          >
            <ImageOff
              class="h-5 w-5 text-gray-400"
              aria-hidden="true"
            />
          </div>
          <div class="flex items-center justify-between gap-1 px-2 py-1">
            <span
              class="truncate text-xs tabular-nums text-gray-300"
              :title="card.filename"
            >{{ card.label }}</span>
            <Button
              variant="ghost"
              size="sm"
              class="relative z-10 shrink-0 !px-1.5 text-xs text-primary hover:bg-dark-border hover:text-primary aria-disabled:opacity-50"
              :aria-label="t('frameVisibility.restoreFrame', { frame: card.label })"
              :aria-disabled="busy || undefined"
              :data-restore-frame="card.filename"
              @click="!busy && $emit('restore', card.filename)"
            >
              {{ t('frameVisibility.restore') }}
            </Button>
          </div>
        </li>
      </ul>
      <p
        v-else-if="expanded"
        class="px-4 py-3 text-sm text-gray-400"
      >
        {{ t('frameVisibility.empty') }}
      </p>
    </div>

    <p
      v-if="error"
      class="border-t border-dark-border px-4 py-2 text-sm text-danger"
      role="alert"
    >
      {{ error }}
    </p>
  </section>

  <Dialog
    v-if="previewCard?.preview"
    :open="true"
    class="fixed inset-0 z-50"
    @close="closePreview"
  >
    <div
      class="absolute inset-0 bg-black/75"
      aria-hidden="true"
    />
    <div class="relative grid h-full place-items-center overflow-y-auto p-4">
      <DialogPanel
        class="w-full max-w-4xl overflow-hidden rounded-xl border border-dark-border bg-dark-surface shadow-2xl"
        @keydown="onPreviewKeydown"
      >
        <div class="flex items-center justify-between gap-3 px-4 py-2">
          <DialogTitle class="truncate text-sm font-medium text-gray-200">
            {{ previewCard.label }}
          </DialogTitle>
          <Button
            variant="ghost"
            icon-only
            :tooltip="t('frameVisibility.closePreview')"
            @click="closePreview"
          >
            <X aria-hidden="true" />
          </Button>
        </div>
        <div class="hidden-frame-preview grid h-[min(68vh,42rem)] place-items-center border-t border-dark-border">
          <img
            v-if="!previewFailed"
            :src="previewCard.preview.url"
            class="h-full min-h-0 w-full object-contain p-4"
            alt=""
            @error="previewFailed = true"
          >
          <p
            v-else
            class="rounded bg-dark-surface px-3 py-2 text-sm text-gray-300"
            role="status"
          >
            {{ t('frameVisibility.previewUnavailable') }}
          </p>
        </div>
      </DialogPanel>
    </div>
  </Dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/vue';
import { ChevronDown, EyeOff, ImageOff, X, ZoomIn } from 'lucide-vue-next';
import Button from '@/components/common/Button.vue';
import type { HiddenFramePreview } from '@/types';

const props = defineProps<{
  filenames: string[];
  previews: HiddenFramePreview[];
  canHide: boolean;
  busy: boolean;
  error: string;
}>();

defineEmits<{
  hide: [];
  restoreAll: [];
  restore: [filename: string];
}>();

const { t } = useI18n();
const expanded = ref(false);
const toggle = ref<InstanceType<typeof Button>>();
const list = ref<HTMLUListElement>();
const previewFilename = ref<string>();
const previewFailed = ref(false);
let previewTrigger: HTMLButtonElement | undefined;

const cards = computed(() => {
  const previews = new Map(props.previews.map(preview => [preview.filename, preview]));
  return props.filenames.map(filename => {
    const preview = previews.get(filename);
    const label = preview ? t('frameVisibility.frameNumber', { number: preview.timeline_index }) : filename;
    return { filename, label, preview };
  }).sort((a, b) => (a.preview?.timeline_index ?? Infinity) - (b.preview?.timeline_index ?? Infinity));
});

const previewCard = computed(() => cards.value.find(card => card.filename === previewFilename.value));

function openPreview(filename: string, event: MouseEvent) {
  previewTrigger = event.currentTarget as HTMLButtonElement;
  previewFailed.value = false;
  previewFilename.value = filename;
}

async function closePreview() {
  const trigger = previewTrigger;
  previewTrigger = undefined;
  previewFilename.value = undefined;
  await nextTick();
  trigger?.focus({ preventScroll: true });
}

function onPreviewKeydown(event: KeyboardEvent) {
  // Leave Tab handling to Dialog and keep editor shortcuts out of the preview.
  if (event.key === 'Tab') return;
  event.stopPropagation();
  if (event.key === 'Escape') {
    event.preventDefault();
    void closePreview();
  }
}

watch(cards, async (nextCards, previousCards) => {
  const active = document.activeElement as HTMLElement | null;
  const filename = active?.dataset.restoreFrame;
  if (!list.value?.contains(active) || !filename || nextCards.some(card => card.filename === filename)) return;
  const index = previousCards.findIndex(card => card.filename === filename);
  await nextTick();
  if (document.activeElement !== document.body) return;
  const buttons = list.value?.querySelectorAll<HTMLButtonElement>('[data-restore-frame]');
  const nextButton = buttons?.[Math.min(index, buttons.length - 1)];
  const fallback: HTMLElement | undefined = toggle.value?.$el;
  (nextButton ?? fallback)?.focus({ preventScroll: true });
});
</script>

<style scoped>
.hidden-frame-preview {
  background-color: #292d32;
  background-image: conic-gradient(#34383d 25%, #292d32 0 50%, #34383d 0 75%, #292d32 0);
  background-size: 12px 12px;
}
</style>
