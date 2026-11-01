<template>
  <span
    v-if="isPlatform"
    :class="badgeClass"
    data-test="platform-source-badge"
  >
    <span :class="{ 'platform-brand-glass-label': glass || overlay }">{{ t('aiCreation.forfunerAI') }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

const props = defineProps<{ source?: string; overlay?: boolean; glass?: boolean }>();
const { t } = useI18n();
const badgeClass = computed(() => {
  if (props.overlay) return 'platform-brand-glass platform-brand-glass-overlay';
  if (props.glass) return 'platform-brand-glass';
  return 'inline-flex items-center rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary-200';
});
// Only platform tasks display the brand; custom-key tasks keep their original presentation.
const isPlatform = computed(() => props.source === 'forfuner-ai');
</script>

<style scoped>
.platform-brand-glass {
  position: relative;
  isolation: isolate;
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  overflow: hidden;
  padding: 6px 14px;
  border: 1px solid rgb(255 255 255 / 8%);
  border-radius: 999px;
  background: #292a28;
  color: #ffbd5c;
  font-size: 12px;
  font-weight: 500;
  line-height: 18px;
  letter-spacing: 0.025em;
  white-space: nowrap;
  box-shadow:
    inset 0 1px 2px rgb(255 255 255 / 5%),
    inset 0 -1px 2px rgb(255 255 255 / 2%),
    0 2px 6px rgb(0 0 0 / 12%);
}

/* Broad, soft reflections keep the center transparent and the label sharp. */
.platform-brand-glass::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background:
    radial-gradient(ellipse at 15% 0%, rgb(255 255 255 / 8%), transparent 65%),
    radial-gradient(ellipse at 85% 100%, rgb(255 189 92 / 8%), transparent 65%);
  pointer-events: none;
}

/* A masked rim varies the light around the lens without filling its center. */
.platform-brand-glass::after {
  content: '';
  position: absolute;
  inset: 0;
  padding: 1px;
  border-radius: inherit;
  background: linear-gradient(
    145deg,
    rgb(255 255 255 / 22%),
    rgb(255 255 255 / 5%) 38%,
    rgb(255 255 255 / 3%) 58%,
    rgb(255 237 211 / 16%) 85%,
    rgb(255 255 255 / 8%)
  );
  -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
  mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  pointer-events: none;
}

.platform-brand-glass-label {
  position: relative;
  text-shadow:
    0 1px 1px rgb(0 0 0 / 65%),
    0 2px 4px rgb(0 0 0 / 35%),
    0 0 6px rgb(255 189 92 / 18%);
}

@supports ((backdrop-filter: blur(12px)) or (-webkit-backdrop-filter: blur(12px))) {
  .platform-brand-glass {
    background: rgb(255 255 255 / 3%);
    -webkit-backdrop-filter: blur(12px) saturate(140%);
    backdrop-filter: blur(12px) saturate(140%);
  }
}
/* Preview media needs a darker glass tint to keep the brand readable on bright frames. */
.platform-brand-glass-overlay {
  max-width: 100%;
  padding: 2px 8px;
  background: #20252b;
  font-size: 11px;
  line-height: 16px;
  letter-spacing: 0;
}

.platform-brand-glass-overlay::before {
  background:
    radial-gradient(ellipse at 15% 0%, rgb(255 255 255 / 6%), transparent 65%),
    radial-gradient(ellipse at 85% 100%, rgb(255 189 92 / 3%), transparent 65%);
}

@supports ((backdrop-filter: blur(12px)) or (-webkit-backdrop-filter: blur(12px))) {
  .platform-brand-glass-overlay {
    background: rgb(12 16 20 / 76%);
  }
}
</style>
