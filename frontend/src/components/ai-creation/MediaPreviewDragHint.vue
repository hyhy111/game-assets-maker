<template>
  <span
    ref="overlay"
    class="media-preview-drag-hint"
    aria-hidden="true"
  >
    <span
      ref="label"
      :class="{ absolute: position }"
      :style="position"
    >{{ t('aiCreation.recent.dragImageToVideoFrame') }}</span>
  </span>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();
const overlay = ref<HTMLElement | null>(null);
const label = ref<HTMLElement | null>(null);
const position = ref<{ left: string; top: string }>();
let preview: HTMLElement | null = null;

function labelOffset(pointer: number, size: number, available: number) {
  const gap = 12;
  const travel = Math.max(0, available - size);
  const padding = Math.min(8, travel / 2);
  const afterPointer = pointer + gap;
  const offset = afterPointer <= travel - padding ? afterPointer : pointer - gap - size;
  return Math.max(padding, Math.min(offset, travel - padding));
}

function followPointer(event: PointerEvent) {
  if (!overlay.value || !label.value || event.pointerType === 'touch') return;
  const { left, top, width, height } = overlay.value.getBoundingClientRect();
  position.value = {
    left: `${labelOffset(event.clientX - left, label.value.offsetWidth, width)}px`,
    top: `${labelOffset(event.clientY - top, label.value.offsetHeight, height)}px`,
  };
}

function resetPosition() {
  position.value = undefined;
}

onMounted(() => {
  // Listen on the preview so the overlay does not intercept clicks or drags.
  preview = overlay.value?.parentElement ?? null;
  preview?.addEventListener('pointerenter', followPointer);
  preview?.addEventListener('pointermove', followPointer);
  preview?.addEventListener('pointerleave', resetPosition);
});

onBeforeUnmount(() => {
  preview?.removeEventListener('pointerenter', followPointer);
  preview?.removeEventListener('pointermove', followPointer);
  preview?.removeEventListener('pointerleave', resetPosition);
});
</script>
