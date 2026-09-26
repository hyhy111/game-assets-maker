<template>
  <button
    type="button"
    class="grid h-9 w-9 place-items-center rounded-lg border border-white/15 bg-black/70 text-gray-300 shadow-lg backdrop-blur transition hover:border-warning/50 hover:text-warning focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-warning/70"
    :class="favorite ? 'border-warning/40 bg-[#241d11]/90 text-warning' : ''"
    :aria-label="t(favorite ? 'aiCreation.recent.unfavoriteMedia' : 'aiCreation.recent.favoriteMedia')"
    :aria-pressed="favorite"
    :title="t(favorite ? 'aiCreation.recent.unfavoriteMedia' : 'aiCreation.recent.favoriteMedia')"
    :data-test="dataTest"
    @click.stop="emit('toggle')"
    @keydown.stop
  >
    <Star class="h-[18px] w-[18px]" :fill="favorite ? 'currentColor' : 'none'" aria-hidden="true" />
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
