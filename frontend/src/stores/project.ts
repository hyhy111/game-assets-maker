/**
 * Project Store - Manages project state
 */
import { defineStore } from 'pinia';
import { ref, computed, reactive } from 'vue';
import { api } from '@/api';
import type {
  Project,
  CreateProjectData,
  RoleSummary,
  ProjectRenameResult,
  LegacyMigrationRequest,
  LegacyMigrationResult,
  LegacyProjectImportResult,
} from '@/types';
import { logEvent } from '@/debug/request-log';

export const useProjectStore = defineStore('project', () => {
  // State
  const projects = ref<Project[]>([]);
  const roles = ref<RoleSummary[]>([]);
  const currentProject = ref<Project | null>(null);
  const activeLibraryRole = ref('');
  const libraryViewState = reactive({
    searchQuery: '',
    animationPage: 1,
    scrollY: 0,
    roleScrollTop: 0,
  });
  const loading = ref(false);
  const error = ref<string | null>(null);

  // Getters
  const hasProject = computed(() => currentProject.value !== null);
  const projectPath = computed(() => currentProject.value?.path);
  const projectId = computed(() => currentProject.value?.id);
  const legacyProjects = computed(() => projects.value.filter(project => project.legacy));
  const isStepCompleted = (step: number) => {
    return currentProject.value?.steps?.[step.toString()]?.completed ?? false;
  };

  // Actions
  async function loadProjects() {
    loading.value = true;
    error.value = null;
    try {
      const data = await api.project.getProjects();
      // Sort by modification time descending.
      projects.value = data.sort((a, b) => {
        return new Date(b.modified_at).getTime() - new Date(a.modified_at).getTime();
      });
      roles.value = await api.project.getRoles();
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load projects';
      logEvent(['Failed to load projects:', e].join(' '), 'error');
    } finally {
      loading.value = false;
    }
  }

  async function loadProject(projectId: string) {
    loading.value = true;
    error.value = null;
    try {
      const project = await api.project.getProject(projectId);
      currentProject.value = project;
      return project;
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load project';
      logEvent(['Failed to load project:', e].join(' '), 'error');
      return null;
    } finally {
      loading.value = false;
    }
  }

  async function createProject(data: CreateProjectData) {
    loading.value = true;
    error.value = null;
    try {
      const project = await api.project.createProject(data);
      projects.value.unshift(project);
      currentProject.value = project;
      return project;
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to create project';
      logEvent(['Failed to create project:', e].join(' '), 'error');
      throw e;
    } finally {
      loading.value = false;
    }
  }

  async function migrateLegacyProjects(migrations: LegacyMigrationRequest[] | string = 'Unknown'): Promise<LegacyMigrationResult> {
    loading.value = true;
    error.value = null;
    try {
      const result = await api.project.migrateLegacyProjects(migrations);
      await loadProjects();
      return result;
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to migrate projects';
      logEvent(['Failed to migrate legacy projects:', e].join(' '), 'error');
      throw e;
    } finally {
      loading.value = false;
    }
  }

  async function importLegacyProjectDirectory(sourceDirectory: string): Promise<LegacyProjectImportResult> {
    loading.value = true;
    error.value = null;
    try {
      const result = await api.project.importLegacyProjectDirectory(sourceDirectory);
      await loadProjects();
      return result;
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to import legacy projects';
      logEvent(['Failed to import legacy projects:', e].join(' '), 'error');
      throw e;
    } finally {
      loading.value = false;
    }
  }

  async function deleteProject(projectId: string) {
    loading.value = true;
    error.value = null;
    try {
      const success = await api.project.deleteProject(projectId);
      if (success) {
        projects.value = projects.value.filter(p => p.id !== projectId);
        if (currentProject.value?.id === projectId) {
          currentProject.value = null;
        }
      }
      return success;
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to delete project';
      logEvent(['Failed to delete project:', e].join(' '), 'error');
      return false;
    } finally {
      loading.value = false;
    }
  }

  async function deleteRole(role: string) {
    loading.value = true;
    error.value = null;
    try {
      const success = await api.project.deleteRole(role);
      if (success) {
        projects.value = projects.value.filter(project => project.role !== role);
        roles.value = roles.value.filter(item => item.name !== role);
        if (currentProject.value?.role === role) {
          currentProject.value = null;
        }
      }
      return success;
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to delete role';
      logEvent(['Failed to delete role:', e].join(' '), 'error');
      return false;
    } finally {
      loading.value = false;
    }
  }

  async function updateProject(projectId: string, data: Partial<Project>) {
    try {
      const project = await api.project.updateProject(projectId, data);
      const index = projects.value.findIndex(p => p.id === projectId);
      if (index !== -1) {
        projects.value[index] = project;
      }
      if (currentProject.value?.id === projectId) {
        currentProject.value = project;
      }
      return project;
    } catch (e) {
      logEvent(['Failed to update project:', e].join(' '), 'error');
      throw e;
    }
  }

  function applyRename(result: ProjectRenameResult) {
    const replacements = new Map(result.projects.map(project => [project.id, project]));
    const selected = projects.value.find(project => (
      project.role === activeLibraryRole.value && result.idMap[project.id]
    ));
    if (selected) {
      activeLibraryRole.value = replacements.get(result.idMap[selected.id])?.role ?? activeLibraryRole.value;
    }
    if (currentProject.value && result.idMap[currentProject.value.id]) {
      currentProject.value = replacements.get(result.idMap[currentProject.value.id]) ?? null;
    }
    projects.value = projects.value.map(project => replacements.get(result.idMap[project.id]) ?? project);
    roles.value = result.roles;
  }

  function setCurrentProject(project: Project | null) {
    currentProject.value = project;
  }

  function clearError() {
    error.value = null;
  }

  return {
    // State
    projects,
    roles,
    currentProject,
    activeLibraryRole,
    libraryViewState,
    loading,
    error,
    // Getters
    hasProject,
    projectPath,
    projectId,
    legacyProjects,
    isStepCompleted,
    // Actions
    loadProjects,
    loadProject,
    createProject,
    migrateLegacyProjects,
    importLegacyProjectDirectory,
    deleteProject,
    deleteRole,
    updateProject,
    applyRename,
    setCurrentProject,
    clearError
  };
});
