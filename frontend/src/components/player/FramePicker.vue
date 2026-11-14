<template>
  <Teleport
    to="body"
    :disabled="teleportDisabled"
  >
    <div
      ref="dialogRef"
      class="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="frame-picker-title"
      tabindex="-1"
      data-test="frame-picker"
      @click.self="emit('close')"
      @keydown.stop="onKeydown"
    >
      <div class="w-full max-w-xl max-h-[90vh] overflow-y-auto rounded-xl border border-dark-border bg-dark-surface p-4 shadow-2xl">
        <div class="mb-3 flex items-start justify-between gap-3">
          <div>
            <h2
              id="frame-picker-title"
              class="text-sm font-medium text-white"
            >
              {{ t('step1.framePickerTitle', { frame: baseFrame }) }}
            </h2>
            <p class="mt-1 text-xs text-gray-400">
              {{ t('step1.framePickerRange', { min: minFrame, max: maxFrame }) }}
            </p>
          </div>
          <button
            type="button"
            class="rounded p-1 text-gray-400 hover:text-white focus-visible:outline focus-visible:outline-primary"
            :aria-label="t('step1.closeFramePicker')"
            @click="emit('close')"
          >
            <X class="h-4 w-4" />
          </button>
        </div>

        <div class="flex items-center gap-2">
          <button
            type="button"
            class="rounded p-1 text-gray-300 hover:bg-dark-border disabled:opacity-30"
            :disabled="candidate <= minFrame"
            :aria-label="t('player.previousFrame')"
            @click="moveCandidate(-1)"
          >
            <ChevronLeft class="h-5 w-5" />
          </button>
          <div class="flex h-56 min-w-0 flex-1 items-center justify-center rounded-lg bg-dark-bg">
            <img
              :key="candidate"
              :src="frames[candidate]?.url"
              :alt="t('step1.frameNumber', { frame: candidate })"
              class="max-h-full max-w-full object-contain"
              draggable="false"
            >
          </div>
          <button
            type="button"
            class="rounded p-1 text-gray-300 hover:bg-dark-border disabled:opacity-30"
            :disabled="candidate >= maxFrame"
            :aria-label="t('player.nextFrame')"
            @click="moveCandidate(1)"
          >
            <ChevronRight class="h-5 w-5" />
          </button>
        </div>

        <div class="my-3 grid grid-cols-5 gap-2">
          <button
            v-for="frame in nearbyFrames"
            :key="frame"
            type="button"
            class="overflow-hidden rounded-md border bg-dark-bg p-1 focus-visible:outline focus-visible:outline-primary"
            :class="candidate === frame ? 'border-primary text-primary' : 'border-dark-border text-gray-400 hover:border-gray-500'"
            :aria-label="t('step1.frameNumber', { frame })"
            :aria-pressed="candidate === frame"
            :data-candidate="frame"
            @click="candidate = frame"
          >
            <img
              :src="frames[frame]?.url"
              alt=""
              class="h-16 w-full object-contain"
              draggable="false"
            >
            <span class="mt-1 block text-xs">{{ frame }}</span>
          </button>
        </div>

        <div class="flex items-center justify-between gap-3">
          <button
            type="button"
            class="text-xs text-gray-400 hover:text-white disabled:opacity-30"
            :disabled="baseFrame < minFrame || baseFrame > maxFrame || candidate === baseFrame"
            @click="candidate = baseFrame"
          >
            {{ t('step1.restoreTick') }}
          </button>
          <Button @click="emit('select', candidate)">
            {{ t('step1.useFrame', { frame: candidate }) }}
          </Button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onBeforeUnmount, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { ChevronLeft, ChevronRight, X } from 'lucide-vue-next';
import Button from '@/components/common/Button.vue';
import { trapModalTab } from '@/modal-focus';
import type { Frame } from '@/types';

const props = defineProps<{
  frames: Frame[];
  baseFrame: number;
  currentFrame: number;
  minFrame: number;
  maxFrame: number;
}>();
const emit = defineEmits<{ select: [frame: number]; close: [] }>();
const { t } = useI18n();
const dialogRef = ref<HTMLElement | null>(null);
const candidate = ref(props.currentFrame);
const teleportDisabled = typeof window === 'undefined';
let returnFocus: HTMLElement | null = null;
const nearbyFrames = computed(() => {
  const count = Math.min(5, props.maxFrame - props.minFrame + 1);
  const start = Math.max(props.minFrame, Math.min(candidate.value - 2, props.maxFrame - count + 1));
  return Array.from({ length: count }, (_, index) => start + index);
});

onMounted(async () => {
  returnFocus = document.activeElement as HTMLElement | null;
  await nextTick();
  dialogRef.value?.focus();
});
onBeforeUnmount(() => returnFocus?.focus());

function moveCandidate(delta: number) {
  candidate.value = Math.max(props.minFrame, Math.min(props.maxFrame, candidate.value + delta));
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') { event.preventDefault(); emit('close'); }
  else if (event.key === 'ArrowLeft') { event.preventDefault(); moveCandidate(-1); }
  else if (event.key === 'ArrowRight') { event.preventDefault(); moveCandidate(1); }
  if (dialogRef.value) trapModalTab(event, dialogRef.value);
}
</script>
