<template>
  <section
    ref="panel"
    class="flex shrink-0 flex-wrap items-center justify-between gap-x-4 gap-y-2 border-t border-dark-border bg-dark-surface px-4 py-2.5 focus:outline-none"
    aria-labelledby="frame-picker-title"
    aria-describedby="frame-picker-range"
    tabindex="-1"
    data-test="frame-picker"
  >
    <div>
      <h2
        id="frame-picker-title"
        class="text-sm font-medium text-gray-100"
      >
        {{ t('step1.framePickerTitle', { frame: currentFrame }) }}
      </h2>
      <p
        id="frame-picker-range"
        class="text-xs text-gray-400"
      >
        {{ t('step1.framePickerRange', { min: minFrame, max: maxFrame }) }}
      </p>
    </div>

    <div class="flex flex-wrap items-center gap-2">
      <div class="flex items-center rounded-lg border border-dark-border bg-dark-bg">
        <Button
          icon-only
          variant="ghost"
          :disabled="candidate <= minFrame"
          :tooltip="`${t('step1.previousCandidate')} (←)`"
          @click="emit('step', -1)"
        >
          <ChevronLeft class="h-4 w-4" />
        </Button>
        <span
          class="min-w-[5rem] px-1 text-center text-sm tabular-nums"
          :class="showCurrent ? 'text-gray-300' : 'text-primary'"
          aria-live="polite"
        >{{ t('step1.frameNumber', { frame: showCurrent ? currentFrame : candidate }) }}</span>
        <Button
          icon-only
          variant="ghost"
          :disabled="candidate >= maxFrame"
          :tooltip="`${t('step1.nextCandidate')} (→)`"
          @click="emit('step', 1)"
        >
          <ChevronRight class="h-4 w-4" />
        </Button>
      </div>
      <Button
        size="sm"
        :variant="showCurrent ? 'secondary' : 'ghost'"
        :aria-pressed="showCurrent"
        :disabled="candidate === currentFrame"
        @click="emit('compare')"
      >
        {{ t('step1.compareFrame') }}
      </Button>
      <Button
        v-if="baseFrame !== currentFrame && baseFrame >= minFrame && baseFrame <= maxFrame"
        size="sm"
        variant="ghost"
        :disabled="candidate === baseFrame && !showCurrent"
        @click="emit('restore')"
      >
        {{ t('step1.restoreTick') }}
      </Button>
    </div>

    <div class="flex items-center gap-1.5">
      <Button
        size="sm"
        variant="ghost"
        @click="emit('close')"
      >
        {{ t('common.cancel') }}
      </Button>
      <Button
        size="sm"
        :disabled="!canReplace"
        @click="emit('replace')"
      >
        {{ t('step1.useFrame', { frame: candidate }) }}
      </Button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { ChevronLeft, ChevronRight } from 'lucide-vue-next';
import Button from '@/components/common/Button.vue';

defineProps<{
  baseFrame: number;
  currentFrame: number;
  minFrame: number;
  maxFrame: number;
  candidate: number;
  showCurrent: boolean;
  canReplace: boolean;
}>();
const emit = defineEmits<{ step: [delta: number]; compare: []; restore: []; close: []; replace: [] }>();
const { t } = useI18n();
const panel = ref<HTMLElement | null>(null);

onMounted(() => panel.value?.focus({ preventScroll: true }));
</script>
