import { computed, ref } from 'vue';
import { defineStore } from 'pinia';
import { api } from '@/api';
import type { GamSkillsStatus } from '@/types';

export const useGamSkillsUpdatesStore = defineStore('gam-skills-updates', () => {
  const states = ref<Record<string, GamSkillsStatus | null>>({});
  const checking = ref(false);
  const updateAgent = computed(() => Object.keys(states.value).find(agent => {
    const state = states.value[agent];
    return state?.source === 'npx' && state.can_check
      && state.status === 'update_available' && state.outdated.length > 0;
  }) ?? '');
  const hasUpdate = computed(() => updateAgent.value !== '');
  let initialized = false;
  let requestId = 0;
  const revisions: Record<string, number> = {};

  function record(agent: string, state: GamSkillsStatus | null) {
    revisions[agent] = (revisions[agent] ?? 0) + 1;
    states.value[agent] = state;
  }

  async function refresh() {
    const id = ++requestId;
    const previous = { ...revisions };
    checking.value = true;
    try {
      const result = await api.system.getGamSkillsUpdates();
      if (id !== requestId) return;
      for (const agent of new Set([...Object.keys(states.value), ...Object.keys(result)])) {
        // A settings check or installation may have completed after this scan began.
        if ((previous[agent] ?? 0) === (revisions[agent] ?? 0)) states.value[agent] = result[agent] ?? null;
      }
    } catch {
      if (id !== requestId) return;
      for (const agent of Object.keys(states.value)) {
        if ((previous[agent] ?? 0) === (revisions[agent] ?? 0)) states.value[agent] = null;
      }
    } finally {
      if (id === requestId) checking.value = false;
    }
  }

  async function initialize() {
    if (initialized) return;
    initialized = true;
    await refresh();
  }

  return { states, checking, updateAgent, hasUpdate, record, refresh, initialize };
});
