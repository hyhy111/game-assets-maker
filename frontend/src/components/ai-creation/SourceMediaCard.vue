<template>
  <article class="relative flex h-full min-w-0 flex-col overflow-hidden rounded-xl border border-dark-border bg-dark-surface transition hover:border-primary/50">
    <button
      type="button"
      class="group/preview relative block aspect-video w-full shrink-0 overflow-hidden bg-black focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary"
      :class="{ 'cursor-grab active:cursor-grabbing': item.kind === 'image' }"
      :data-test="`source-media-${item.id}`"
      :draggable="item.kind === 'image'"
      :aria-description="item.kind === 'image' ? t('aiCreation.recent.dragImageToVideoFrame') : undefined"
      @click="openDetail"
      @dragstart="dragImage"
    >
      <img
        :src="item.thumbnail_url"
        alt=""
        loading="lazy"
        draggable="false"
        class="h-full w-full object-contain"
      >
      <MediaPreviewDragHint v-if="item.kind === 'image'" />
      <span class="media-overlay-badge absolute left-2 top-2">{{ t('aiCreation.sourceMedia.local') }}</span>
    </button>
    <RouterLink
      :to="detailRoute"
      class="mt-auto block focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary"
    >
      <div class="p-4">
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
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
import MediaPreviewDragHint from './MediaPreviewDragHint.vue';
import RecentMediaFavoriteButton from './RecentMediaFavoriteButton.vue';
import { useRecentMediaFavorites } from '@/recent-media-favorites';
import type { SourceMedia } from '@/types';
import { writeSourceImageDrag } from '@/seedream-image-drag';

const props = defineProps<{ item: SourceMedia }>();
const { t, d } = useI18n();
const router = useRouter();
const { sourceMediaKey, isFavorite, toggleFavorite } = useRecentMediaFavorites();
const detailRoute = computed(() => `/ai-creation/source-media/${props.item.id}`);

function openDetail() {
  router.push(detailRoute.value);
}

function dragImage(event: DragEvent) {
  if (props.item.kind === 'image') {
    writeSourceImageDrag(
      event.dataTransfer,
      props.item.id,
      event.currentTarget as HTMLElement,
      props.item.absolute_path,
    );
  }
}
</script>
