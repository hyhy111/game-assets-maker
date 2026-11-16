<template>
  <section
    class="mt-10"
    data-test="recent-generations"
  >
    <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
      <div class="flex items-center gap-3">
        <h2 class="text-lg font-semibold text-white">
          {{ t('aiCreation.recent.title') }}
        </h2>
        <div class="flex rounded-lg border border-dark-border bg-dark-surface p-1">
          <button
            v-for="filter in filters"
            :key="filter"
            type="button"
            class="rounded-md px-3 py-1.5 text-sm transition"
            :class="workspace.recentFilter === filter ? 'bg-primary text-dark-bg' : 'text-gray-400 hover:text-white'"
            :aria-pressed="workspace.recentFilter === filter"
            :data-test="`recent-filter-${filter}`"
            @click="workspace.setRecentFilter(filter)"
          >
            {{ t(filter === 'image' ? 'aiCreation.recent.images' : 'aiCreation.recent.videos') }}
          </button>
        </div>
      </div>
      <div class="flex flex-wrap items-center gap-4">
        <Button
          variant="secondary"
          size="sm"
          :loading="importing"
          data-test="source-media-import"
          @click="importLocalMedia"
        >
          <Upload
            v-if="!importing"
            class="mr-2 h-4 w-4"
            aria-hidden="true"
          />
          {{ t('aiCreation.sourceMedia.import') }}
        </Button>
        <Switch
          v-model="stackSamePrompts"
          :label="t('aiCreation.recent.stackSamePrompts')"
          data-test="recent-stack-same-prompts"
        />
        <button
          type="button"
          class="flex items-center gap-1.5 rounded-lg border border-dark-border bg-dark-surface px-3 py-2 text-sm text-gray-400 transition-colors hover:border-gray-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-50 icon-button control-tooltip"
          :disabled="loading"
          data-test="recent-refresh"
          :aria-label="t('aiCreation.sourceMedia.refresh')"
          :data-tooltip="t('aiCreation.sourceMedia.refresh')"
          @click="refreshCurrent"
        >
          <RefreshCw
            class="h-5 w-5"
            aria-hidden="true"
          />
        </button>
      </div>
    </div>

    <p
      v-if="error"
      class="mb-4 rounded-lg border border-danger/30 bg-danger/10 p-3 text-sm text-danger"
    >
      {{ error.message }}
    </p>
    <p
      v-if="importError || localMediaError"
      class="mb-4 rounded-lg border border-danger/30 bg-danger/10 p-3 text-sm text-danger"
      role="alert"
    >
      {{ importError || localMediaError }}
    </p>
    <div
      v-if="loading && !visibleItems.length"
      class="grid min-h-56 place-items-center rounded-xl border border-dark-border bg-dark-surface text-sm text-gray-400"
      role="status"
    >
      {{ t('common.loading') }}
    </div>
    <div
      v-else-if="!visibleItems.length"
      class="grid min-h-56 place-items-center rounded-xl border border-dark-border bg-dark-surface text-sm text-gray-400"
    >
      {{ t(workspace.recentFilter === 'image' ? 'aiCreation.recent.emptyImages' : 'aiCreation.recent.emptyVideos') }}
    </div>
    <div
      v-else
      class="grid auto-rows-fr grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4"
      data-test="recent-generations-grid"
    >
      <template
        v-for="entry in visibleItems"
        :key="entry.key"
      >
        <SourceMediaCard
          v-if="entry.kind === 'local'"
          :item="entry.item"
        />
        <RecentPromptGroup
          v-else-if="entry.kind === 'image'"
          :group-id="promptGroupId('image', entry.group.key)"
          :prompt="entry.group.prompt"
          :count="entry.group.items.length"
          :expanded="isExpanded('image', entry.group.key)"
          @toggle-expanded="toggleExpanded('image', entry.group.key)"
        >
          <RecentImageGenerationCard
            :batch="entry.group.items[0]"
            @open="openImageDetail"
          >
            <template
              v-if="entry.group.items.length === 1"
              #top-right="{ attempt }"
            >
              <RecentMediaFavoriteButton
                v-if="attempt"
                :favorite="isFavorite(imageMediaKey(entry.group.items[0].local_id, attempt.local_id))"
                :data-test="`recent-media-favorite-${imageMediaKey(entry.group.items[0].local_id, attempt.local_id)}`"
                @toggle="toggleFavorite(imageMediaKey(entry.group.items[0].local_id, attempt.local_id))"
              />
            </template>
          </RecentImageGenerationCard>
          <template #expanded>
            <RecentImageGenerationCard
              v-for="batch in entry.group.items"
              :key="batch.local_id"
              :batch="batch"
              @open="openImageDetail"
            >
              <template #top-right="{ attempt }">
                <RecentMediaFavoriteButton
                  v-if="attempt"
                  :favorite="isFavorite(imageMediaKey(batch.local_id, attempt.local_id))"
                  :data-test="`recent-media-favorite-${imageMediaKey(batch.local_id, attempt.local_id)}`"
                  @toggle="toggleFavorite(imageMediaKey(batch.local_id, attempt.local_id))"
                />
              </template>
            </RecentImageGenerationCard>
          </template>
        </RecentPromptGroup>
        <RecentPromptGroup
          v-else
          :group-id="promptGroupId('video', entry.group.key)"
          :prompt="entry.group.prompt"
          :count="entry.group.items.length"
          :expanded="isExpanded('video', entry.group.key)"
          @toggle-expanded="toggleExpanded('video', entry.group.key)"
        >
          <RecentVideoGenerationCard
            :task="entry.group.items[0]"
            @open="openVideoDetail"
          >
            <template
              v-if="entry.group.items.length === 1"
              #top-right
            >
              <RecentMediaFavoriteButton
                :favorite="isFavorite(videoMediaKey(entry.group.items[0].local_id))"
                :data-test="`recent-media-favorite-${videoMediaKey(entry.group.items[0].local_id)}`"
                @toggle="toggleFavorite(videoMediaKey(entry.group.items[0].local_id))"
              />
            </template>
          </RecentVideoGenerationCard>
          <template #expanded>
            <RecentVideoGenerationCard
              v-for="task in entry.group.items"
              :key="task.local_id"
              :task="task"
              @open="openVideoDetail"
            >
              <template #top-right>
                <RecentMediaFavoriteButton
                  :favorite="isFavorite(videoMediaKey(task.local_id))"
                  :data-test="`recent-media-favorite-${videoMediaKey(task.local_id)}`"
                  @toggle="toggleFavorite(videoMediaKey(task.local_id))"
                />
              </template>
            </RecentVideoGenerationCard>
          </template>
        </RecentPromptGroup>
      </template>
    </div>

    <div
      v-if="hasMore"
      class="mt-5 flex justify-center"
    >
      <button
        type="button"
        class="rounded-lg border border-dark-border bg-dark-surface px-5 py-2 text-sm text-gray-300 transition hover:border-gray-500 hover:text-white"
        data-test="recent-load-more"
        @click="workspace.loadMoreRecent(workspace.recentFilter)"
      >
        {{ t('aiCreation.recent.loadMore') }}
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { RefreshCw, Upload } from 'lucide-vue-next';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
import { useRecentMediaFavorites } from '@/recent-media-favorites';
import { groupRecentByPrompt, listRecentIndividually } from '@/recent-prompt-groups';
import { useAICreationStore, type RecentGenerationFilter } from '@/stores/aiCreation';
import { useSeedanceStore } from '@/stores/seedance';
import { useSeedreamStore } from '@/stores/seedream';
import { api } from '@/api';
import type { SourceMedia } from '@/types';
import Button from '@/components/common/Button.vue';
import SourceMediaCard from './SourceMediaCard.vue';
import Switch from '@/components/common/Switch.vue';
import RecentImageGenerationCard from './RecentImageGenerationCard.vue';
import RecentMediaFavoriteButton from './RecentMediaFavoriteButton.vue';
import RecentPromptGroup from './RecentPromptGroup.vue';
import RecentVideoGenerationCard from './RecentVideoGenerationCard.vue';

const { t } = useI18n();
const router = useRouter();
const workspace = useAICreationStore();
const seedream = useSeedreamStore();
const seedance = useSeedanceStore();
const filters: RecentGenerationFilter[] = ['image', 'video'];
const STACK_STORAGE_KEY = 'gam:stack-same-prompts';
const { imageMediaKey, videoMediaKey, isFavorite, toggleFavorite } = useRecentMediaFavorites();
const stackSamePrompts = ref(loadStackSamePrompts());
const expandedPromptKeys = ref(new Set<string>());

const imageGroups = computed(() => stackSamePrompts.value
  ? groupRecentByPrompt(seedream.batches)
  : listRecentIndividually(seedream.batches));
const videoGroups = computed(() => stackSamePrompts.value
  ? groupRecentByPrompt(seedance.tasks)
  : listRecentIndividually(seedance.tasks));
const localMedia = ref<SourceMedia[]>([]);
const loadingLocalMedia = ref(false);
const localMediaError = ref('');
const importError = ref('');
const importing = ref(false);
let localMediaLoadId = 0;

const mediaEntries = computed(() => {
  const filter = workspace.recentFilter;
  const localEntries = localMedia.value.filter(item => item.kind === filter).map(item => ({
    kind: 'local' as const, key: `local:${item.id}`, createdAt: item.imported_at, item,
  }));
  const generatedEntries = filter === 'image'
    ? imageGroups.value.map(group => ({
      kind: 'image' as const, key: `image:${group.key}`, createdAt: group.items[0].created_at, group,
    }))
    : videoGroups.value.map(group => ({
      kind: 'video' as const, key: `video:${group.key}`, createdAt: group.items[0].created_at, group,
    }));
  return [...localEntries, ...generatedEntries]
    .sort((left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt));
});
const visibleItems = computed(() => mediaEntries.value.slice(0, workspace.recentLoaded[workspace.recentFilter]));
const hasMore = computed(() => visibleItems.value.length < mediaEntries.value.length);
const loading = computed(() => loadingLocalMedia.value || (workspace.recentFilter === 'image' ? seedream.loading : seedance.loading));
const error = computed(() => workspace.recentFilter === 'image' ? seedream.error : seedance.error);

onMounted(() => Promise.all([loadCurrent(), loadLocalMedia()]));
watch(() => workspace.recentFilter, () => {
  expandedPromptKeys.value = new Set();
  return loadCurrent();
});
watch(stackSamePrompts, (enabled) => {
  expandedPromptKeys.value = new Set();
  saveStackSamePrompts(enabled);
});

function loadCurrent() {
  return workspace.recentFilter === 'image' ? seedream.loadBatches() : seedance.loadTasks();
}

async function refreshCurrent() {
  workspace.resetRecentLoaded(workspace.recentFilter);
  await Promise.all([loadCurrent(), loadLocalMedia()]);
}

async function loadLocalMedia() {
  const requestId = ++localMediaLoadId;
  loadingLocalMedia.value = true;
  localMediaError.value = '';
  try {
    const items = await api.sourceMedia.list();
    if (requestId === localMediaLoadId) localMedia.value = items;
  } catch {
    if (requestId === localMediaLoadId) localMediaError.value = t('aiCreation.sourceMedia.loadFailed');
  } finally {
    if (requestId === localMediaLoadId) loadingLocalMedia.value = false;
  }
}

async function importLocalMedia() {
  if (importing.value) return;
  importing.value = true;
  importError.value = '';
  try {
    const { items, failed } = await api.sourceMedia.import();
    if (items.length) {
      localMedia.value = [...items, ...localMedia.value.filter(item => !items.some(imported => imported.id === item.id))];
      if (!items.some(item => item.kind === workspace.recentFilter)) workspace.setRecentFilter(items[0].kind);
      await loadLocalMedia();
    }
    if (failed.length) importError.value = t('aiCreation.sourceMedia.importFailedFiles', { files: failed.join(', ') });
  } catch {
    importError.value = t('aiCreation.sourceMedia.importFailed');
  } finally {
    importing.value = false;
  }
}

function openImageDetail(localId: string) {
  return router.push(`/image-generation/batches/${encodeURIComponent(localId)}`);
}

function openVideoDetail(localId: string) {
  return router.push(`/video-generation/tasks/${encodeURIComponent(localId)}`);
}

function storedPromptKey(filter: RecentGenerationFilter, groupKey: string): string {
  return `${filter}:${groupKey}`;
}

function promptGroupId(filter: RecentGenerationFilter, groupKey: string): string {
  return `${filter}-${encodeURIComponent(groupKey)}`;
}

function isExpanded(filter: RecentGenerationFilter, groupKey: string): boolean {
  return expandedPromptKeys.value.has(storedPromptKey(filter, groupKey));
}

function toggleExpanded(filter: RecentGenerationFilter, groupKey: string) {
  const next = new Set(expandedPromptKeys.value);
  const key = storedPromptKey(filter, groupKey);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  expandedPromptKeys.value = next;
}

function loadStackSamePrompts(): boolean {
  try {
    return localStorage.getItem(STACK_STORAGE_KEY) !== 'false';
  } catch {
    return true;
  }
}

function saveStackSamePrompts(enabled: boolean) {
  try {
    localStorage.setItem(STACK_STORAGE_KEY, String(enabled));
  } catch {
    // The setting remains available for this window when storage is unavailable.
  }
}
</script>
