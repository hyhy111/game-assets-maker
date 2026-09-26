<template>
  <section class="mt-10" data-test="recent-generations">
    <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
      <div class="flex items-center gap-3">
        <h2 class="text-lg font-semibold text-white">{{ t('aiCreation.recent.title') }}</h2>
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
      <div class="flex items-center gap-4">
        <Switch
          v-model="stackSamePrompts"
          :label="t('aiCreation.recent.stackSamePrompts')"
          data-test="recent-stack-same-prompts"
        />
        <button
          type="button"
          class="flex items-center gap-1.5 rounded-lg border border-dark-border bg-dark-surface px-3 py-2 text-sm text-gray-400 transition-colors hover:border-gray-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="loading"
          data-test="recent-refresh"
          @click="refreshCurrent"
        >
          <RefreshCw class="h-4 w-4" />
          {{ t('common.refresh') }}
        </button>
      </div>
    </div>

    <p v-if="error" class="mb-4 rounded-lg border border-danger/30 bg-danger/10 p-3 text-sm text-danger">{{ error.message }}</p>
    <div v-if="loading && !visibleItems.length" class="grid min-h-56 place-items-center rounded-xl border border-dark-border bg-dark-surface text-sm text-gray-400" role="status">
      {{ t('common.loading') }}
    </div>
    <div v-else-if="!visibleItems.length" class="grid min-h-56 place-items-center rounded-xl border border-dark-border bg-dark-surface text-sm text-gray-400">
      {{ t(workspace.recentFilter === 'image' ? 'aiCreation.recent.emptyImages' : 'aiCreation.recent.emptyVideos') }}
    </div>
    <div v-else class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4" data-test="recent-generations-grid">
      <template v-if="workspace.recentFilter === 'image'">
        <RecentPromptGroup
          v-for="group in visibleImageGroups"
          :key="group.key"
          :group-id="promptGroupId('image', group.key)"
          :prompt="group.prompt"
          :count="group.items.length"
          :expanded="isExpanded('image', group.key)"
          @toggle-expanded="toggleExpanded('image', group.key)"
        >
          <RecentImageGenerationCard :batch="group.items[0]" @open="openImageDetail">
            <template v-if="group.items.length === 1" #top-right="{ attempt }">
              <RecentMediaFavoriteButton
                v-if="attempt"
                :favorite="isFavorite(imageMediaKey(group.items[0].local_id, attempt.local_id))"
                :data-test="`recent-media-favorite-${imageMediaKey(group.items[0].local_id, attempt.local_id)}`"
                @toggle="toggleFavorite(imageMediaKey(group.items[0].local_id, attempt.local_id))"
              />
            </template>
            <template v-if="group.items.length > 1" #bottom-right>
              <button
                type="button"
                class="inline-flex items-center gap-1 text-xs font-medium text-primary transition hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
                :aria-expanded="isExpanded('image', group.key)"
                :data-test="`recent-prompt-expand-${promptGroupId('image', group.key)}`"
                @click.stop="toggleExpanded('image', group.key)"
                @keydown.stop
              >
                {{ t(isExpanded('image', group.key) ? 'aiCreation.recent.collapseTasks' : 'aiCreation.recent.expandTasks') }}
                <ChevronDown class="h-3.5 w-3.5 transition-transform" :class="isExpanded('image', group.key) ? 'rotate-180' : ''" aria-hidden="true" />
              </button>
            </template>
          </RecentImageGenerationCard>
          <template #expanded>
            <RecentImageGenerationCard
              v-for="batch in group.items"
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
      </template>
      <template v-else>
        <RecentPromptGroup
          v-for="group in visibleVideoGroups"
          :key="group.key"
          :group-id="promptGroupId('video', group.key)"
          :prompt="group.prompt"
          :count="group.items.length"
          :expanded="isExpanded('video', group.key)"
          @toggle-expanded="toggleExpanded('video', group.key)"
        >
          <RecentVideoGenerationCard :task="group.items[0]" @open="openVideoDetail">
            <template v-if="group.items.length === 1" #top-right>
              <RecentMediaFavoriteButton
                :favorite="isFavorite(videoMediaKey(group.items[0].local_id))"
                :data-test="`recent-media-favorite-${videoMediaKey(group.items[0].local_id)}`"
                @toggle="toggleFavorite(videoMediaKey(group.items[0].local_id))"
              />
            </template>
            <template v-if="group.items.length > 1" #bottom-right>
              <button
                type="button"
                class="inline-flex items-center gap-1 text-xs font-medium text-primary transition hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
                :aria-expanded="isExpanded('video', group.key)"
                :data-test="`recent-prompt-expand-${promptGroupId('video', group.key)}`"
                @click.stop="toggleExpanded('video', group.key)"
                @keydown.stop
              >
                {{ t(isExpanded('video', group.key) ? 'aiCreation.recent.collapseTasks' : 'aiCreation.recent.expandTasks') }}
                <ChevronDown class="h-3.5 w-3.5 transition-transform" :class="isExpanded('video', group.key) ? 'rotate-180' : ''" aria-hidden="true" />
              </button>
            </template>
          </RecentVideoGenerationCard>
          <template #expanded>
            <RecentVideoGenerationCard
              v-for="task in group.items"
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

    <div v-if="hasMore" class="mt-5 flex justify-center">
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
import { ChevronDown, RefreshCw } from 'lucide-vue-next';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
import { useRecentMediaFavorites } from '@/recent-media-favorites';
import { groupRecentByPrompt, listRecentIndividually } from '@/recent-prompt-groups';
import { useAICreationStore, type RecentGenerationFilter } from '@/stores/aiCreation';
import { useSeedanceStore } from '@/stores/seedance';
import { useSeedreamStore } from '@/stores/seedream';
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
const visibleImageGroups = computed(() => workspace.recentFilter === 'image'
  ? imageGroups.value.slice(0, workspace.recentLoaded.image)
  : []);
const visibleVideoGroups = computed(() => workspace.recentFilter === 'video'
  ? videoGroups.value.slice(0, workspace.recentLoaded.video)
  : []);
const visibleItems = computed(() => workspace.recentFilter === 'image' ? visibleImageGroups.value : visibleVideoGroups.value);
const totalItems = computed(() => workspace.recentFilter === 'image' ? imageGroups.value.length : videoGroups.value.length);
const hasMore = computed(() => visibleItems.value.length < totalItems.value);
const loading = computed(() => workspace.recentFilter === 'image' ? seedream.loading : seedance.loading);
const error = computed(() => workspace.recentFilter === 'image' ? seedream.error : seedance.error);

onMounted(() => loadCurrent());
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
  await loadCurrent();
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
