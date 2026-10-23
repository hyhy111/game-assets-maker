<template>
  <div class="min-h-screen bg-dark-bg">
    <Header
      sticky
      page-aligned
    />
    <main class="mx-auto w-full max-w-[1320px] px-4 py-6 sm:px-6">
      <div
        class="w-full"
        data-test="ai-creation-work-area"
      >
        <div>
          <KeepAlive>
            <SeedreamCreate
              v-if="workspace.activeMode === 'image'"
              embedded
              :show-batch-list="false"
              :creation-mode="workspace.activeMode"
              @change-mode="workspace.activeMode = $event"
            />
            <SeedanceCreate
              v-else
              embedded
              :show-task-list="false"
              :creation-mode="workspace.activeMode"
              @change-mode="workspace.activeMode = $event"
            />
          </KeepAlive>
        </div>
      </div>

      <RecentGenerations />
    </main>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, watch } from 'vue';
import { onBeforeRouteLeave, useRoute } from 'vue-router';
import Header from '@/components/layout/Header.vue';
import RecentGenerations from '@/components/ai-creation/RecentGenerations.vue';
import { useAICreationStore } from '@/stores/aiCreation';
import { useAuthStore } from '@/stores/auth';
import SeedanceCreate from './SeedanceCreate.vue';
import SeedreamCreate from './SeedreamCreate.vue';

const route = useRoute();
const workspace = useAICreationStore();
const auth = useAuthStore();
if (route.query.mode === 'video') workspace.activeMode = 'video';
if (route.query.mode === 'image') workspace.activeMode = 'image';

watch(() => auth.isLoggedIn, (loggedIn) => {
  if (loggedIn) workspace.setGenerationSource('forfuner-ai');
}, { immediate: true });

onMounted(async () => {
  await nextTick();
  window.scrollTo({ top: workspace.workspaceScrollY, behavior: 'auto' });
});

onBeforeRouteLeave(() => {
  workspace.rememberWorkspaceScroll(window.scrollY);
});
</script>
