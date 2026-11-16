<template>
  <article class="relative min-w-0 overflow-hidden rounded-xl border border-dark-border bg-dark-surface transition hover:border-primary/50">
    <RouterLink
      :to="`/ai-creation/source-media/${item.id}`"
      class="group/source flex h-full flex-col focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary"
      :class="{ 'cursor-grab active:cursor-grabbing': item.kind === 'image' }"
      :data-test="`source-media-${item.id}`"
      :draggable="item.kind === 'image'"
      :aria-description="item.kind === 'image' ? t('aiCreation.recent.dragImageToVideoFrame') : undefined"
      @dragstart="dragImage"
    >
      <div class="group/preview relative aspect-video w-full shrink-0 overflow-hidden bg-black">
        <img
          :src="item.thumbnail_url"
          alt=""
          loading="lazy"
          draggable="false"
          class="h-full w-full object-contain"
        >
        <MediaPreviewDragHint
          v-if="item.kind === 'image'"
          class="group-hover/preview:opacity-100 group-focus-visible/source:opacity-100"
        />
        <span class="media-overlay-badge absolute left-2 top-2">{{ t('aiCreation.sourceMedia.local') }}</span>
      </div>
      <div class="mt-auto p-4">
        <p class="truncate text-sm font-medium leading-6 text-gray-100">
          {{ item.name }}
        </p>
        <dl class="mt-4 grid grid-cols-2 gap-3 border-t border-dark-border pt-4 text-xs">
          <div>
            <dt class="text-gray-500">
              {{ t('aiCreation.sourceMedia.importedAt') }}
            </dt>
            <dd class="mt-1 text-gray-300">
              {{ d(new Date(item.imported_at)) }}
            </dd>
          </div>
          <div class="text-right">
            <dt class="text-gray-500">
              {{ t('seedream.detail.dimensions') }}
            </dt>
            <dd class="mt-1 text-gray-300">
              {{ item.width }} × {{ item.height }}
            </dd>
          </div>
        </dl>
      </div>
    </RouterLink>
    <RecentMediaFavoriteButton
      class="absolute right-2 top-2 z-[2]"
      :favorite="isFavorite(sourceMediaKey(item.id))"
      :data-test="`source-media-favorite-${item.id}`"
      @toggle="toggleFavorite(sourceMediaKey(item.id))"
    />
  </article>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import MediaPreviewDragHint from './MediaPreviewDragHint.vue';
import RecentMediaFavoriteButton from './RecentMediaFavoriteButton.vue';
import { useRecentMediaFavorites } from '@/recent-media-favorites';
import type { SourceMedia } from '@/types';
import { writeSourceImageDrag } from '@/seedream-image-drag';

const props = defineProps<{ item: SourceMedia }>();
const { t, d } = useI18n();
const { sourceMediaKey, isFavorite, toggleFavorite } = useRecentMediaFavorites();

function dragImage(event: DragEvent) {
  if (props.item.kind === 'image') {
    writeSourceImageDrag(event.dataTransfer, props.item.id, event.currentTarget as HTMLElement);
  }
}
</script>
