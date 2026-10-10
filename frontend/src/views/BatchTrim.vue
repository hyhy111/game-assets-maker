<template>
  <div class="batch-trim-page min-h-screen bg-dark-bg">
    <Header />

    <main class="mx-auto w-full max-w-[1480px] px-4 pb-10 pt-6 sm:px-6 sm:pt-8">
      <div class="mb-5 flex justify-end">
        <button
          class="flex items-center gap-1.5 text-sm text-gray-400 transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          @click="goBack"
        >
          <ArrowLeft class="h-4 w-4" />
          {{ t('common.back') }}
        </button>
      </div>

      <div
        v-if="projects.length > 0"
        class="batch-trim-toolbar"
      >
        <label class="batch-trim-search">
          <Search class="h-4 w-4 flex-none" />
          <input
            v-model="searchQuery"
            type="search"
            :placeholder="t('projectManager.searchPlaceholder')"
          >
        </label>

        <div class="batch-trim-control-bar">
          <div
            class="batch-trim-mode-toggle"
            :aria-label="t('batchTrim.trimMode')"
          >
            <button
              type="button"
              :class="{ active: trimMode === 'global' }"
              :aria-pressed="trimMode === 'global'"
              :title="t('batchTrim.uniformSizeDesc')"
              @click="trimMode = 'global'"
            >
              {{ t('batchTrim.uniformSize') }}
            </button>
            <button
              type="button"
              :class="{ active: trimMode === 'individual' }"
              :aria-pressed="trimMode === 'individual'"
              :title="t('batchTrim.tightCropDesc')"
              @click="trimMode = 'individual'"
            >
              {{ t('batchTrim.tightCrop') }}
            </button>
          </div>

          <div class="batch-trim-output-path">
            <span>{{ t('batchTrim.outputDir') }}</span>
            <code>project/&lt;role&gt;/batch-trim[-n]/&lt;animation&gt;/</code>
          </div>

          <Button
            class="batch-trim-run-button"
            size="sm"
            :disabled="!canExecute"
            :loading="processing"
            @click="executeTrim"
          >
            <Scissors
              v-if="!processing"
              class="h-4 w-4"
            />
            {{ processing ? t('batchTrim.processing') : t('batchTrim.startTrim') }}
          </Button>
        </div>
      </div>

      <div
        v-if="loading"
        class="batch-trim-empty"
      >
        <div class="h-8 w-8 animate-spin rounded-full border-2 border-primary/20 border-b-primary" />
        <p>{{ t('batchTrim.loadingProjects') }}</p>
      </div>

      <div
        v-else-if="projects.length === 0"
        class="batch-trim-empty"
      >
        <Folder class="h-12 w-12 opacity-40" />
        <p>{{ t('batchTrim.noProjects') }}</p>
      </div>

      <div
        v-else-if="filteredGroupedProjects.length === 0"
        class="batch-trim-empty border-dashed"
      >
        <Search class="h-10 w-10 opacity-35" />
        <p>{{ t('projectManager.noSearchResults') }}</p>
      </div>

      <div
        v-else
        class="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3"
      >
        <article
          v-for="group in filteredGroupedProjects"
          :key="group.role"
          class="batch-trim-role-card"
        >
          <div class="mb-4 flex items-start justify-between gap-3">
            <div class="min-w-0">
              <h2 class="truncate font-semibold text-white">
                {{ group.role }}
              </h2>
              <p class="mt-1 text-xs text-gray-500">
                {{ t('batchTrim.roleSelection', {
                  total: group.projects.length,
                  selected: selectedInRole(group)
                }) }}
              </p>
            </div>
            <button
              type="button"
              class="batch-trim-select-role"
              @click="toggleRole(group)"
            >
              {{ isRoleSelected(group)
                ? t('batchTrim.clearRole')
                : t('batchTrim.selectRole')
              }}
            </button>
          </div>

          <div class="flex flex-wrap gap-2">
            <button
              v-for="project in group.projects"
              :key="project.id"
              type="button"
              class="batch-trim-action-chip"
              :class="{
                selected: selectedProjects.includes(project.id),
                unavailable: projectTrimStatus(project) === 'unavailable'
              }"
              :aria-pressed="selectedProjects.includes(project.id)"
              :title="statusText(projectTrimStatus(project))"
              @click="toggleProject(project.id)"
            >
              <Check
                v-if="selectedProjects.includes(project.id)"
                class="h-3.5 w-3.5"
              />
              <span>{{ project.action || project.name }}</span>
              <span
                aria-hidden="true"
                class="batch-trim-status-dot"
                :class="projectTrimStatus(project)"
              />
              <span class="sr-only">{{ statusText(projectTrimStatus(project)) }}</span>
            </button>
          </div>
        </article>
      </div>

      <!-- Execution results and logs -->
      <Card
        v-if="trimResults.length > 0"
        class="mt-8"
      >
        <template #header>
          <div class="flex items-center justify-between gap-3">
            <h2 class="text-lg font-semibold text-white">
              {{ t('batchTrim.results') }}
            </h2>
            <Button
              v-if="batchTrimRootPaths.length > 0"
              size="sm"
              :title="t('batchTrim.openResultDirTitle')"
              @click="openBatchTrimRoots"
            >
              <FolderOpen class="w-4 h-4" />
              {{ t('batchTrim.openResultDir') }}
            </Button>
          </div>
        </template>
        <div class="space-y-4">
          <!-- Project results list -->
          <div
            v-for="result in trimResults"
            :key="result.projectId"
            class="border-b border-dark-border pb-3 last:border-0"
          >
            <div class="flex items-center gap-2 text-sm mb-2 min-w-0">
              <component
                :is="resultStatusIcon(result.status)"
                :class="['w-4 h-4 flex-shrink-0', resultStatusClass(result.status)]"
              />
              <span class="text-white font-medium truncate">{{ result.projectName }}</span>
              <span :class="['truncate', resultStatusClass(result.status)]">{{ result.message }}</span>
            </div>

            <!-- Failed frame details -->
            <div
              v-if="result.failedFrames && result.failedFrames.length > 0"
              class="mt-2 ml-6"
            >
              <div class="text-xs text-warning mb-1">
                {{ t('batchTrim.failedFrames', { count: result.failedCount }) }}
              </div>
              <div class="max-h-32 overflow-y-auto bg-dark-surface rounded p-2 text-xs">
                <div
                  v-for="(frame, idx) in result.failedFrames.slice(0, 5)"
                  :key="idx"
                  class="text-gray-400 mb-1"
                >
                  • {{ frame.filename }}: {{ frame.reason }}
                </div>
                <div
                  v-if="result.failedFrames.length > 5"
                  class="text-gray-500 italic"
                >
                  {{ t('batchTrim.moreFailed', { count: result.failedFrames.length - 5 }) }}
                </div>
              </div>
            </div>
          </div>

          <!-- Overall failure notice -->
          <div
            v-if="hasFailedFrames"
            class="mt-4 p-3 bg-warning/10 border border-warning/30 rounded-lg"
          >
            <div class="flex items-start gap-2">
              <AlertTriangle class="w-5 h-5 text-warning flex-shrink-0 mt-0.5" />
              <div>
                <div class="text-warning font-medium text-sm">
                  {{ t('batchTrim.partialFailure') }}
                </div>
                <div class="text-gray-400 text-xs mt-1">
                  {{ t('batchTrim.partialFailureDesc', { count: totalFailedCount }) }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </Card>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { storeToRefs } from 'pinia';
import { useI18n } from 'vue-i18n';
import {
  ArrowLeft,
  Check,
  Folder,
  FolderOpen,
  Scissors,
  Search,
  CheckCircle,
  AlertTriangle,
  XCircle,
  HelpCircle
} from 'lucide-vue-next';
import { useAgentBatchTrimStore } from '@/stores/agentBatchTrim';
import { useProjectStore } from '@/stores/project';
import { api } from '@/api';
import type { Project, BatchTrimResult } from '@/types';
import Card from '@/components/common/Card.vue';
import Button from '@/components/common/Button.vue';
import Header from '@/components/layout/Header.vue';

const router = useRouter();
const route = useRoute();
const projectStore = useProjectStore();
const { t } = useI18n();
const { projects } = storeToRefs(projectStore);

const loading = ref(true);
const selectedProjects = ref<string[]>([]);
const searchQuery = ref('');
const trimMode = ref<'global' | 'individual'>('global');
const processing = ref(false);
const trimResults = ref<BatchTrimResult[]>([]);
const agentTrim = useAgentBatchTrimStore();
function applyAgentResult() {
  if (!agentTrim.result) return;
  selectedProjects.value = [...agentTrim.result.project_ids];
  trimMode.value = agentTrim.result.mode;
  trimResults.value = [...agentTrim.result.raw_results];
}
watch(() => agentTrim.result, applyAgentResult, { immediate: true });

onMounted(async () => {
  await loadProjects();
  const requestedProjectIds = Array.isArray(route.query.projects)
    ? route.query.projects
    : [route.query.projects];
  const availableProjectIds = new Set(projects.value.map(project => project.id));
  selectedProjects.value = requestedProjectIds
    .filter((projectId): projectId is string => typeof projectId === 'string')
    .filter(projectId => availableProjectIds.has(projectId));
  applyAgentResult();
});

type ProjectGroup = { role: string; projects: Project[] };

const groupedProjects = computed<ProjectGroup[]>(() => {
  const groups = new Map<string, Project[]>();
  for (const project of projects.value) {
    const role = project.role || 'Unknown';
    if (!groups.has(role)) {
      groups.set(role, []);
    }
    groups.get(role)?.push(project);
  }

  return Array.from(groups.entries()).map(([role, roleProjects]) => ({
    role,
    projects: roleProjects
  }));
});

const filteredGroupedProjects = computed(() => {
  const query = searchQuery.value.trim().toLocaleLowerCase();
  if (!query) return groupedProjects.value;

  return groupedProjects.value
    .map(group => {
      if (group.role.toLocaleLowerCase().includes(query)) return group;
      return {
        ...group,
        projects: group.projects.filter(project =>
          (project.action || project.name).toLocaleLowerCase().includes(query)
        ),
      };
    })
    .filter(group => group.projects.length > 0);
});

async function loadProjects() {
  loading.value = true;
  try {
    await projectStore.loadProjects();
  } finally {
    loading.value = false;
  }
}

function isRoleSelected(group: ProjectGroup) {
  return group.projects.length > 0 && group.projects.every(project => selectedProjects.value.includes(project.id));
}

function toggleRole(group: ProjectGroup) {
  const ids = group.projects.map(project => project.id);
  if (ids.every(id => selectedProjects.value.includes(id))) {
    selectedProjects.value = selectedProjects.value.filter(id => !ids.includes(id));
  } else {
    selectedProjects.value = Array.from(new Set([...selectedProjects.value, ...ids]));
  }
}

function selectedInRole(group: ProjectGroup) {
  return group.projects.filter(project => selectedProjects.value.includes(project.id)).length;
}

function toggleProject(projectId: string) {
  selectedProjects.value = selectedProjects.value.includes(projectId)
    ? selectedProjects.value.filter(id => id !== projectId)
    : [...selectedProjects.value, projectId];
}

type TrimStatus = 'available' | 'fallback' | 'unavailable';

function projectTrimStatus(project: Project): TrimStatus {
  if ((project.steps?.['3']?.count ?? 0) > 0) return 'available';
  if ((project.steps?.['2']?.count ?? 0) > 0) return 'fallback';
  return 'unavailable';
}

function statusText(status: TrimStatus) {
  switch (status) {
    case 'available': return t('batchTrim.status.available');
    case 'fallback': return t('batchTrim.status.fallback');
    case 'unavailable': return t('batchTrim.status.unavailable');
  }
}

const canExecute = computed(() => {
  return selectedProjects.value.length > 0 && !processing.value;
});

async function executeTrim() {
  if (selectedProjects.value.length === 0) return;

  processing.value = true;
  trimResults.value = [];

  try {
    const results = await api.batchTrim.executeTrim({
      projectIds: selectedProjects.value,
      mode: trimMode.value,
      outputDir: ''
    });
    trimResults.value = results;
  } catch (error) {
    console.error('执行裁切失败:', error);
  } finally {
    processing.value = false;
  }
}

function goBack() {
  router.push('/');
}

function getParentDirectory(path: string) {
  return path.replace(/[\\/]+$/, '').replace(/[\\/][^\\/]+$/, '');
}

const batchTrimRootPaths = computed(() => {
  const paths = new Set<string>();
  for (const result of trimResults.value) {
    if (result.outputPath) {
      paths.add(getParentDirectory(result.outputPath));
    }
  }
  return Array.from(paths);
});

async function openBatchTrimRoots() {
  try {
    await Promise.all(batchTrimRootPaths.value.map(path => api.system.openProjectFolder(path)));
  } catch (error) {
    console.error('打开裁剪结果目录失败:', error);
  }
}

// Result status display.
function resultStatusIcon(status: string) {
  switch (status) {
    case 'success': return CheckCircle;
    case 'partial': return AlertTriangle;
    case 'error': return XCircle;
    default: return HelpCircle;
  }
}

function resultStatusClass(status: string) {
  switch (status) {
    case 'success': return 'text-success';
    case 'partial': return 'text-warning';
    case 'error': return 'text-danger';
    default: return 'text-gray-400';
  }
}

const hasFailedFrames = computed(() => {
  return trimResults.value.some(r => r.failedCount && r.failedCount > 0);
});

const totalFailedCount = computed(() => {
  return trimResults.value.reduce((sum, r) => sum + (r.failedCount || 0), 0);
});
</script>

<style scoped>
.batch-trim-page {
  background: #1a1a1a;
}

.batch-trim-toolbar {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1rem;
  align-items: center;
}

.batch-trim-search {
  display: flex;
  width: 100%;
  height: 2.75rem;
  align-items: center;
  gap: 0.5rem;
  border: 1px solid #333333;
  border-radius: 0.625rem;
  background: #242424;
  padding: 0 0.75rem;
  color: #9ca3af;
}

.batch-trim-search:focus-within {
  border-color: #ffbd5c;
  box-shadow: 0 0 0 3px rgb(255 189 92 / 12%);
}

.batch-trim-search input {
  min-width: 0;
  flex: 1;
  background: transparent;
  color: white;
  font-size: 0.875rem;
  outline: none;
}

.batch-trim-search input::placeholder {
  color: #6b7280;
}

.batch-trim-empty {
  display: grid;
  min-height: 18rem;
  place-items: center;
  align-content: center;
  gap: 0.875rem;
  border: 1px solid #333333;
  border-radius: 1rem;
  background: #242424;
  color: #9ca3af;
  font-size: 0.875rem;
}

.batch-trim-role-card {
  min-height: 11.25rem;
  border: 1px solid #333333;
  border-radius: 1rem;
  background: #242424;
  padding: 1rem;
  box-shadow: 0 12px 32px rgb(0 0 0 / 16%);
}

.batch-trim-select-role {
  flex: none;
  color: #ffbd5c;
  font-size: 0.6875rem;
  transition: color 160ms ease;
}

.batch-trim-select-role:hover {
  color: #ffc15f;
}

.batch-trim-select-role:focus-visible,
.batch-trim-action-chip:focus-visible,
.batch-trim-mode-toggle button:focus-visible {
  border-radius: 0.5rem;
  outline: 2px solid #ffbd5c;
  outline-offset: 2px;
}

.batch-trim-action-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  border: 1px solid #333333;
  border-radius: 0.5625rem;
  background: #1a1a1a;
  padding: 0.5rem 0.625rem;
  color: #d1d5db;
  font-size: 0.75rem;
  transition: border-color 160ms ease, background 160ms ease, color 160ms ease;
}

.batch-trim-action-chip:hover {
  border-color: #ffbd5c;
  color: white;
}

.batch-trim-action-chip.selected {
  border-color: #ffbd5c;
  background: rgb(255 189 92 / 16%);
  color: white;
}

.batch-trim-action-chip.unavailable {
  opacity: 0.48;
}

.batch-trim-status-dot {
  height: 0.3125rem;
  width: 0.3125rem;
  border-radius: 999px;
}

.batch-trim-status-dot.available {
  background: #2cc985;
}

.batch-trim-status-dot.fallback {
  background: #f39c12;
}

.batch-trim-status-dot.unavailable {
  background: #6b7280;
}

.batch-trim-control-bar {
  display: flex;
  grid-column: span 2 / span 2;
  height: 2.75rem;
  min-width: 0;
  align-items: center;
  gap: 1rem;
  border: 1px solid #333333;
  border-radius: 0.625rem;
  background: #242424;
  padding: 0.125rem 0.5rem;
  box-shadow: 0 8px 20px rgb(0 0 0 / 18%);
}

.batch-trim-output-path {
  display: flex;
  min-width: 0;
  flex: 1;
  align-items: center;
  gap: 0.625rem;
  border-left: 1px solid #333333;
  padding-left: 1rem;
}

.batch-trim-output-path span {
  flex: none;
  color: #6b7280;
  font-size: 0.625rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.batch-trim-output-path code {
  min-width: 0;
  overflow: hidden;
  color: #9ca3af;
  font-size: 0.6875rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.batch-trim-mode-toggle {
  display: flex;
  flex: none;
  border-radius: 0.5625rem;
  background: #1a1a1a;
  padding: 0.1875rem;
}

.batch-trim-mode-toggle button {
  border-radius: 0.4375rem;
  padding: 0.4375rem 0.625rem;
  color: #9ca3af;
  font-size: 0.6875rem;
  transition: background 160ms ease, color 160ms ease;
}

.batch-trim-mode-toggle button.active {
  background: rgb(255 189 92 / 20%);
  color: #ffda9a;
}

.batch-trim-run-button {
  flex: none;
  gap: 0.5rem;
}

@media (max-width: 640px) {
  .batch-trim-mode-toggle {
    width: 100%;
  }

  .batch-trim-mode-toggle button {
    flex: 1;
  }

  .batch-trim-run-button {
    width: 100%;
  }
}

@media (max-width: 1024px) {
  .batch-trim-toolbar {
    grid-template-columns: 1fr;
    gap: 0.75rem;
  }

  .batch-trim-control-bar {
    grid-column: auto;
    flex-wrap: wrap;
  }
}

@media (max-width: 640px) {
  .batch-trim-control-bar {
    height: auto;
    align-items: stretch;
    flex-direction: column;
    padding: 0.75rem;
  }

  .batch-trim-output-path {
    align-items: flex-start;
    flex-direction: column;
    gap: 0.25rem;
    width: 100%;
    border-left: 0;
    border-top: 1px solid #333333;
    padding-left: 0;
    padding-top: 0.75rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .batch-trim-select-role,
  .batch-trim-action-chip,
  .batch-trim-mode-toggle button {
    transition-duration: 0.01ms;
  }
}
</style>
