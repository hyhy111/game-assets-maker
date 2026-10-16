import { computed, ref } from 'vue';
import { defineStore } from 'pinia';
import { api } from '@/api';
import type { AppUpdateInfo } from '@/types';

export const useUpdateStore = defineStore('updates', () => {
  const currentVersion = ref('');
  const state = ref<AppUpdateInfo | null>(null);
  const checking = ref(false);
  const actionPending = ref(false);
  const actionError = ref('');
  const hasUpdate = computed(() => state.value?.status === 'available');
  const canUpdate = computed(() => hasUpdate.value || state.value?.status === 'ignored');
  let initialized = false;

  async function initialize() {
    if (initialized) return;
    initialized = true;
    checking.value = true;
    const version = api.system.getAppVersion().then(value => {
      currentVersion.value = value;
    }).catch(() => {});
    try {
      state.value = await api.system.checkAppUpdate();
      currentVersion.value = state.value.current_version;
    } catch {
      state.value = {
        current_version: currentVersion.value,
        latest_version: '',
        release_notes: '',
        release_url: '',
        status: 'error',
        error: 'NETWORK_ERROR',
      };
    } finally {
      await version;
      checking.value = false;
    }
  }

  async function ignoreCurrentVersion() {
    if (!hasUpdate.value || !state.value || actionPending.value) return;
    actionPending.value = true;
    actionError.value = '';
    try {
      if (!await api.system.ignoreAppUpdate(state.value.latest_version)) throw new Error('save failed');
      state.value = { ...state.value, status: 'ignored' };
    } catch {
      actionError.value = 'ignoreFailed';
    } finally {
      actionPending.value = false;
    }
  }

  async function openUpdate() {
    if (!canUpdate.value || actionPending.value) return;
    actionPending.value = true;
    actionError.value = '';
    try {
      if (!await api.system.openAppUpdate()) throw new Error('open failed');
    } catch {
      actionError.value = 'openFailed';
    } finally {
      actionPending.value = false;
    }
  }

  return { currentVersion, state, checking, actionPending, actionError, hasUpdate, canUpdate, initialize, ignoreCurrentVersion, openUpdate };
});
