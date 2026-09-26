<template>
  <div class="border-t border-dark-border bg-dark-surface">
    <div class="px-4 py-2 text-xs text-gray-500 font-medium uppercase tracking-wider">
      {{ t('player.frames') }}
    </div>
    <div class="overflow-y-auto max-h-64 px-2 pb-2">
      <div class="grid grid-cols-3 gap-2">
        <button
          v-for="frame in frames"
          :key="frame.index"
          :class="[
            'relative aspect-square rounded-lg overflow-hidden border-2 transition-all',
            currentIndex === frame.index
              ? 'border-primary ring-2 ring-primary/30'
              : 'border-dark-border hover:border-gray-500'
          ]"
          @click="$emit('select', frame.index)"
        >
          <img
            v-if="thumbnails[frame.index]"
            :src="`data:image/png;base64,${thumbnails[frame.index]}`"
            class="w-full h-full object-cover"
            :class="useNearest ? 'pixelated' : ''"
          >
          <div
            v-else
            class="w-full h-full bg-dark-border flex items-center justify-center text-gray-600 text-xs"
          >
            {{ frame.index + 1 }}
          </div>
          <div class="absolute bottom-0 left-0 right-0 px-1 py-0.5 bg-black/60 text-[10px] text-white text-center">
            {{ frame.index + 1 }}
          </div>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import type { Frame } from '@/types';
import { api } from '@/api';

const { t } = useI18n();

const props = defineProps<{
  frames: Frame[];
  currentIndex: number;
  useNearest?: boolean;
}>();

defineEmits<{
  select: [index: number];
}>();

// Thumbnail cache
const thumbnails = ref<Record<number, string>>({});

// Load thumbnails
watch(() => props.frames, async (newFrames) => {
  // Load first page of thumbnails
  const framesToLoad = newFrames.slice(0, 30);

  for (const frame of framesToLoad) {
    if (!thumbnails.value[frame.index]) {
      try {
        const thumb = await api.frame.getFrameThumbnail(frame.path, 64);
        thumbnails.value[frame.index] = thumb;
      } catch (e) {
        console.error('Failed to load thumbnail:', e);
      }
    }
  }
}, { immediate: true });
</script>

<style scoped>
.pixelated {
  image-rendering: pixelated;
}
</style>
