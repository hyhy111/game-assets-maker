<template>
  <Teleport to="body">
    <div
      v-if="trigger && text"
      id="gam-control-tooltip"
      ref="tooltip"
      role="tooltip"
      class="control-tooltip-popup"
      :style="{ left: `${position.x}px`, top: `${position.y}px` }"
    >
      {{ text }}
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue';

const trigger = shallowRef<HTMLElement | null>(null);
const tooltip = ref<HTMLElement | null>(null);
const text = ref('');
const position = ref({ x: 0, y: 0 });
let originalTitle: string | null = null;
let addedLabel = false;
let observer: MutationObserver | undefined;
let hoverTarget: HTMLElement | null = null;
let hoverTimer: number | undefined;

function hide() {
  window.clearTimeout(hoverTimer);
  hoverTarget = null;
  hoverTimer = undefined;
  const element = trigger.value;
  if (element) {
    const descriptions = (element.getAttribute('aria-describedby') || '').split(/\s+/)
      .filter(id => id && id !== 'gam-control-tooltip');
    if (descriptions.length) element.setAttribute('aria-describedby', descriptions.join(' '));
    else element.removeAttribute('aria-describedby');
    if (originalTitle !== null) element.setAttribute('title', originalTitle);
    if (addedLabel) element.removeAttribute('aria-label');
  }
  trigger.value = null;
  originalTitle = null;
  addedLabel = false;
  observer?.disconnect();
}

function show(event: Event) {
  const element = event.target instanceof Element
    ? event.target.closest<HTMLElement>('.control-tooltip, button[title]') : null;
  if (!element || element.getAttribute('aria-expanded') === 'true') return;
  const hovering = event.type === 'pointerover';
  if (trigger.value === element || (hovering && hoverTarget === element)) return;
  hide();
  const delay = hovering ? Number(element.dataset.tooltipDelay) : 0;
  if (Number.isFinite(delay) && delay > 0) {
    hoverTarget = element;
    hoverTimer = window.setTimeout(() => {
      hoverTarget = null;
      hoverTimer = undefined;
      if (element.matches(':hover')) void reveal(element);
    }, delay);
    return;
  }
  void reveal(element);
}

async function reveal(element: HTMLElement) {
  if (!element.isConnected || element.getAttribute('aria-expanded') === 'true') return;
  const label = element.getAttribute('data-tooltip') || element.getAttribute('aria-label') || element.getAttribute('title');
  if (!label) return;
  originalTitle = element.getAttribute('title');
  if (originalTitle !== null) {
    if (!element.hasAttribute('aria-label')) {
      element.setAttribute('aria-label', originalTitle);
      addedLabel = true;
    }
    element.removeAttribute('title');
  }
  const descriptions = element.getAttribute('aria-describedby');
  element.setAttribute('aria-describedby', [descriptions, 'gam-control-tooltip'].filter(Boolean).join(' '));
  trigger.value = element;
  text.value = label;
  await nextTick();
  if (trigger.value !== element || !tooltip.value) return;
  const bounds = element.getBoundingClientRect();
  const hint = tooltip.value.getBoundingClientRect();
  let x = bounds.left + (bounds.width - hint.width) / 2;
  let y = bounds.top - hint.height - 8;
  if (element.classList.contains('control-tooltip--below')) y = bounds.bottom + 8;
  if (element.classList.contains('control-tooltip--end')) x = bounds.right - hint.width;
  if (element.classList.contains('control-tooltip--left')) {
    x = bounds.left - hint.width - 8;
    y = bounds.top + (bounds.height - hint.height) / 2;
  }
  if (y < 8) y = bounds.bottom + 8;
  position.value = {
    x: Math.max(8, Math.min(x, document.documentElement.clientWidth - hint.width - 8)),
    y: Math.max(8, Math.min(y, window.innerHeight - hint.height - 8)),
  };
  observer?.observe(document.body, { childList: true, subtree: true });
}

function leave(event: Event) {
  const next = (event as MouseEvent | FocusEvent).relatedTarget;
  if (next instanceof Node && (trigger.value ?? hoverTarget)?.contains(next)) return;
  hide();
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') hide();
}

onMounted(() => {
  observer = new MutationObserver(() => {
    if (trigger.value && !trigger.value.isConnected) hide();
  });
  document.addEventListener('pointerover', show);
  document.addEventListener('pointerout', leave);
  document.addEventListener('focusin', show);
  document.addEventListener('focusout', leave);
  document.addEventListener('keydown', onKeydown);
  document.addEventListener('click', hide);
  document.addEventListener('dragstart', hide);
  document.addEventListener('scroll', hide, true);
  window.addEventListener('resize', hide);
});

onBeforeUnmount(() => {
  hide();
  document.removeEventListener('pointerover', show);
  document.removeEventListener('pointerout', leave);
  document.removeEventListener('focusin', show);
  document.removeEventListener('focusout', leave);
  document.removeEventListener('keydown', onKeydown);
  document.removeEventListener('click', hide);
  document.removeEventListener('dragstart', hide);
  document.removeEventListener('scroll', hide, true);
  window.removeEventListener('resize', hide);
});
</script>
