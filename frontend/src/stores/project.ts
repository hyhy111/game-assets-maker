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
      console.error('Failed to load projects:', e);
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
      console.error('Failed to load project:', e);
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
      console.error('Failed to create project:', e);
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
      console.error('Failed to migrate legacy projects:', e);
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
      console.error('Failed to import legacy projects:', e);
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
      console.error('Failed to delete project:', e);
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
      console.error('Failed to delete role:', e);
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
      console.error('Failed to update project:', e);
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
