import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { BatchTrimResult } from '@/types';

export interface AgentTrimResult {
  raw_results: BatchTrimResult[];
  project_ids: string[];
  mode: 'global' | 'individual';
}
export const useAgentBatchTrimStore = defineStore('agent-batch-trim', () => {
  const result = ref<AgentTrimResult | null>(null);
  return { result };
});
