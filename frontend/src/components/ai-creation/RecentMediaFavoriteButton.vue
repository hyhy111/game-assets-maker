<template>
  <button
    type="button"
    class="media-overlay-action"
    draggable="false"
    :class="favorite ? 'border-warning/40 bg-[#241d11]/90 text-warning' : ''"
    :aria-label="t(favorite ? 'aiCreation.recent.unfavoriteMedia' : 'aiCreation.recent.favoriteMedia')"
    :aria-pressed="favorite"
    :title="t(favorite ? 'aiCreation.recent.unfavoriteMedia' : 'aiCreation.recent.favoriteMedia')"
    :data-test="dataTest"
    @click.stop="emit('toggle')"
    @keydown.stop
  >
    <Star
      class="h-3.5 w-3.5"
      :fill="favorite ? 'currentColor' : 'none'"
      aria-hidden="true"
    />
  </button>
</template>

<script setup lang="ts">
import { Star } from 'lucide-vue-next';
import { useI18n } from 'vue-i18n';

defineProps<{
  favorite: boolean;
  dataTest: string;
}>();

const emit = defineEmits<{
  toggle: [];
}>();

const { t } = useI18n();
</script>
