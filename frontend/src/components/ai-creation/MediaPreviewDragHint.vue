<template>
  <span
    ref="overlay"
    class="media-preview-drag-hint"
    :data-follow-pointer="position ? '' : undefined"
    :data-dragging="dragging ? '' : undefined"
    aria-hidden="true"
  >
    <span
      :class="{ fixed: position }"
      :style="position"
    >{{ t('aiCreation.recent.dragImageToVideoFrame') }}</span>
  </span>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();
const overlay = ref<HTMLElement | null>(null);
const position = ref<{ left: string; top: string }>();
const dragging = ref(false);
let preview: HTMLElement | null = null;

function setPosition({ clientX, clientY }: MouseEvent) {
  position.value = { left: `${clientX + 12}px`, top: `${clientY + 12}px` };
}

function followPointer(event: PointerEvent) {
  if (!dragging.value && event.pointerType !== 'touch') setPosition(event);
}

function resetPosition() {
  if (!dragging.value) position.value = undefined;
}

function isInsidePreview({ clientX, clientY }: DragEvent) {
  if (!preview) return false;
  const { left, top, right, bottom } = preview.getBoundingClientRect();
  return clientX >= left && clientX < right && clientY >= top && clientY < bottom;
}

function followDrag(event: DragEvent) {
  if (isInsidePreview(event)) setPosition(event);
  else position.value = undefined;
}

function leaveDuringDrag(event: DragEvent) {
  if (!isInsidePreview(event)) position.value = undefined;
}

function startDrag() {
  dragging.value = true;
  const document = preview?.ownerDocument;
  // Native dragging suspends pointer events, so track the drag across the document.
  document?.addEventListener('dragenter', followDrag, true);
  document?.addEventListener('dragover', followDrag, true);
  document?.addEventListener('dragleave', leaveDuringDrag, true);
  document?.addEventListener('drop', finishDrag, true);
  document?.addEventListener('dragend', finishDrag, true);
}

function finishDrag() {
  if (!dragging.value) return;
  dragging.value = false;
  position.value = undefined;
  const document = preview?.ownerDocument;
  document?.removeEventListener('dragenter', followDrag, true);
  document?.removeEventListener('dragover', followDrag, true);
  document?.removeEventListener('dragleave', leaveDuringDrag, true);
  document?.removeEventListener('drop', finishDrag, true);
  document?.removeEventListener('dragend', finishDrag, true);
}

onMounted(() => {
  // Listen on the preview so the overlay does not intercept clicks or drags.
  preview = overlay.value?.parentElement ?? null;
  preview?.addEventListener('pointerenter', followPointer);
  preview?.addEventListener('pointermove', followPointer);
  preview?.addEventListener('pointerleave', resetPosition);
  preview?.addEventListener('dragstart', startDrag);
});

onBeforeUnmount(() => {
  preview?.removeEventListener('pointerenter', followPointer);
  preview?.removeEventListener('pointermove', followPointer);
  preview?.removeEventListener('pointerleave', resetPosition);
  preview?.removeEventListener('dragstart', startDrag);
  finishDrag();
});
</script>
