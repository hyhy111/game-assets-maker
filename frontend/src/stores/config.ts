/**
 * Config Store - Manages application configuration
 */
import { defineStore } from 'pinia';
import { ref } from 'vue';
import { api } from '@/api';
import type { AppConfig } from '@/types';

export const useConfigStore = defineStore('config', () => {
  // State
  const config = ref<AppConfig | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);

  // Actions
  async function loadConfig() {
    loading.value = true;
    error.value = null;
    try {
      config.value = await api.config.getConfig();
    } catch (e) {
      console.error('Failed to load config:', e);
      error.value = e instanceof Error ? e.message : 'Failed to load config';
      // Set defaults
      config.value = {
        language: 'zh',
        theme: 'dark',
        logger_enabled: false,
        paid_generation_confirmation_enabled: true,
        logger_config: {
          log_dir: './logs',
          max_log_size_mb: 10,
          max_log_files: 5,
          auto_cleanup_days: 30,
          cleanup_interval_hours: 24,
        },
        seedance: {
          api_key_configured: false,
          cache_dir: '',
          default_model: 'standard',
          default_resolution: '720p',
          default_ratio: 'adaptive',
          default_duration: 5,
          default_generate_audio: false,
          default_return_last_frame: false,
          default_priority: 0,
          default_expires_after: 172800,
          retention_days: 90,
          last_cleanup_at: null,
        },
      };
    } finally {
      loading.value = false;
    }
  }

  async function saveConfig(update: Partial<AppConfig>) {
    try {
      const success = await api.config.saveConfig(update);
      if (success && config.value) {
        config.value = { ...config.value, ...update };
      }
      return success;
    } catch (e) {
      console.error('Failed to save config:', e);
      return false;
    }
  }

  return {
    // State
    config,
    loading,
    error,
    // Actions
    loadConfig,
    saveConfig
  };
});
