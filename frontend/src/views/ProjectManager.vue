<template>
  <div class="min-h-screen bg-dark-bg">
    <Header
      page-aligned
      class="sticky top-0 z-30 bg-dark-bg/95 backdrop-blur-xl"
    />

    <main>
      <ProjectManagerHero @start-ai-creation="goToAICreation" />

      <section class="mx-auto w-full max-w-[1320px] space-y-4 px-4 pb-20 pt-10 sm:px-6">
        <div
          v-if="importMessage"
          class="flex items-start justify-between gap-3 rounded-lg border border-dark-border bg-dark-surface p-3 text-sm text-gray-300"
          role="status"
          aria-live="polite"
          data-test="import-legacy-result"
        >
          <p class="min-w-0 flex-1 break-all">
            {{ importMessage }}
          </p>
          <button
            type="button"
            class="flex-none rounded-md p-1 text-gray-500 transition-colors hover:bg-white/5 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            :aria-label="t('projectManager.close')"
            @click="importMessage = ''"
          >
            <X class="h-4 w-4" />
          </button>
        </div>

        <div
          v-if="loading"
          class="text-center py-12"
        >
          <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
          <p class="mt-4 text-gray-400">
            {{ t('common.loading') }}
          </p>
        </div>

        <div
          v-if="!loading && legacyProjects.length > 0 && legacyMigrationVisible"
          class="p-4 border border-warning/30 bg-warning/10 rounded-lg space-y-4"
        >
          <div class="flex items-start gap-3">
            <AlertTriangle class="w-5 h-5 text-warning mt-0.5" />
            <div class="flex-1">
              <p class="text-warning font-medium">
                {{ t('projectManager.legacyProjects', { count: legacyProjects.length }) }}
              </p>
              <p class="text-sm text-gray-400 mt-1">
                {{ t('projectManager.legacyHint') }}
              </p>
            </div>
            <button
              type="button"
              class="rounded-md p-1 text-gray-500 transition-colors hover:bg-white/5 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              :aria-label="t('projectManager.close')"
              @click="legacyMigrationVisible = false"
            >
              <X class="h-4 w-4" />
            </button>
          </div>

          <div class="flex flex-col sm:flex-row gap-2 sm:items-center">
            <input
              v-model="newMigrationRole"
              type="text"
              class="flex-1 sm:max-w-xs px-3 py-2 bg-dark-surface border border-dark-border rounded-lg text-white text-sm"
              :placeholder="t('projectManager.newRolePlaceholder')"
              @keydown.enter.prevent="createMigrationRole"
            >
            <Button
              variant="secondary"
              size="sm"
              :disabled="!newMigrationRole.trim()"
              @click="createMigrationRole"
            >
              <Plus class="w-4 h-4 mr-1" />
              {{ t('projectManager.createNewRole') }}
            </Button>
            <div
              v-if="migrationRoleMessage"
              class="text-sm text-gray-400"
            >
              {{ migrationRoleMessage }}
            </div>
          </div>

          <div class="overflow-x-auto">
            <table class="w-full min-w-[640px] text-sm">
              <thead>
                <tr class="text-left text-gray-500 border-b border-warning/20">
                  <th class="py-2 pr-3 font-medium">
                    {{ t('projectManager.oldProject') }}
                  </th>
                  <th class="py-2 px-3 font-medium">
                    {{ t('projectManager.targetRole') }}
                  </th>
                  <th class="py-2 px-3 font-medium">
                    {{ t('projectManager.targetAction') }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="project in legacyProjects"
                  :key="project.id"
                  class="border-b border-warning/10 last:border-0"
                >
                  <td class="py-2 pr-3 text-gray-300">
                    {{ project.action || project.name || project.id }}
                  </td>
                  <td class="py-2 px-3">
                    <Select
                      v-if="migrationDrafts[project.id]"
                      v-model="migrationDrafts[project.id].targetRole"
                      :options="migrationRoleSelectOptions"
                      :placeholder="t('projectManager.selectRole')"
                      :aria-label="t('projectManager.targetRole')"
                    />
                  </td>
                  <td class="py-2 px-3">
                    <input
                      v-if="migrationDrafts[project.id]"
                      v-model="migrationDrafts[project.id].targetAction"
                      type="text"
                      class="w-full px-3 py-2 bg-dark-surface border border-dark-border rounded-lg text-white text-sm"
                      :placeholder="t('projectManager.actionName')"
                    >
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="flex justify-end">
            <Button
              variant="secondary"
              :loading="migrating"
              :disabled="!canMigrateLegacy"
              @click="migrateLegacy"
            >
              {{ t('projectManager.batchMigrate') }}
            </Button>
          </div>
        </div>

        <div
          v-if="migrationMessage"
          class="p-3 bg-dark-surface border border-dark-border rounded-lg text-sm text-gray-300"
        >
          {{ migrationMessage }}
        </div>

        <div
          v-if="!loading && projects.length === 0"
          class="empty-library"
        >
          <div class="preview-stage mb-5 grid aspect-square w-48 place-items-center rounded-2xl border border-dark-border">
            <ImagePlus class="h-16 w-16 text-primary/70" />
          </div>
          <h3 class="text-lg font-semibold text-white">
            {{ t('projectManager.noProjects') }}
          </h3>
          <Button
            class="mt-5"
            @click="goToAICreation"
          >
            <ImagePlus class="mr-2 h-4 w-4" />
            {{ t('projectManager.startWithAICreation') }}
          </Button>
          <button
            type="button"
            class="mt-3 text-sm text-gray-500 underline-offset-4 transition-colors hover:text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:cursor-not-allowed disabled:opacity-50"
            data-test="import-legacy-projects-empty"
            :disabled="importingLegacyDirectory"
            @click="importLegacyProjectDirectory"
          >
            {{ t('projectManager.importLegacyProjectsLink') }}
          </button>
        </div>

        <div
          v-else-if="!loading"
          class="library-workbench"
          data-test="project-manager-library-workbench"
        >
          <aside
            class="role-dock"
            data-test="project-manager-role-dock"
          >
            <div class="flex items-end justify-between gap-3">
              <div>
                <p class="font-mono text-[10px] tracking-[0.16em] text-primary uppercase whitespace-nowrap">
                  Game Assets
                </p>
                <h2 class="mt-1 text-xl font-semibold text-white">
                  {{ t('projectManager.animationLibrary') }}
                </h2>
              </div>
              <div class="flex items-center gap-1">
                <button
                  type="button"
                  class="rounded-lg p-2 text-gray-500 transition-colors hover:bg-white/5 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                  :title="t('common.refresh')"
                  :aria-label="t('common.refresh')"
                  @click="loadProjects"
                >
                  <RefreshCw class="h-4 w-4" />
                </button>
                <Menu
                  as="div"
                  class="relative"
                >
                  <MenuButton
                    type="button"
                    class="rounded-lg p-2 text-gray-500 transition-colors hover:bg-white/5 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                    :title="t('projectManager.moreActions')"
                    :aria-label="t('projectManager.moreActions')"
                  >
                    <MoreVertical class="h-4 w-4" />
                  </MenuButton>
                  <MenuItems class="absolute right-0 z-50 mt-2 w-48 origin-top-right rounded-lg border border-dark-border bg-dark-surface shadow-lg focus:outline-none">
                    <MenuItem v-slot="{ active }">
                      <button
                        type="button"
                        data-test="import-legacy-projects"
                        :disabled="importingLegacyDirectory"
                        :class="[
                          'flex w-full items-center gap-2 px-4 py-2 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50',
                          active ? 'bg-dark-border text-white' : 'text-gray-300'
                        ]"
                        @click="importLegacyProjectDirectory"
                      >
                        <FolderOpen class="h-4 w-4" />
                        {{ t('projectManager.importLegacyProjects') }}
                      </button>
                    </MenuItem>
                  </MenuItems>
                </Menu>
              </div>
            </div>

            <button
              type="button"
              class="mt-5 flex w-full items-center justify-center gap-2 rounded-lg border border-primary/25 bg-primary/10 px-3 py-2.5 text-sm font-medium text-primary-300 transition-colors hover:border-primary/45 hover:bg-primary/15 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              data-test="create-frame-animation"
              @click="goToCreate()"
            >
              <Plus class="h-4 w-4" />
              {{ t('projectManager.createNewRole') }}
            </button>

            <label class="mt-2.5 flex min-w-0 items-center gap-2 rounded-lg border border-dark-border bg-dark-bg/70 px-3 py-2.5">
              <Search class="h-4 w-4 flex-none text-gray-500" />
              <input
                v-model="searchQuery"
                type="search"
                class="min-w-0 flex-1 bg-transparent text-sm text-white outline-none placeholder:text-gray-600"
                :placeholder="t('projectManager.searchPlaceholder')"
              >
            </label>

            <nav
              ref="roleNav"
              class="role-nav"
              :aria-label="t('projectManager.roleListLabel')"
            >
              <div
                v-for="group in filteredGroupedProjects"
                :key="group.role"
                class="role-nav-item"
                :class="{ active: group.role === selectedGroup?.role }"
              >
                <button
                  type="button"
                  class="flex min-w-0 flex-1 items-center gap-2.5 rounded text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                  :aria-current="group.role === selectedGroup?.role ? 'true' : undefined"
                  @click="selectRole(group.role)"
                >
                  <span class="role-nav-dot" />
                  <span class="min-w-0 flex-1 truncate">{{ group.role }}</span>
                </button>
                <LibraryItemMenu
                  v-if="group.role !== '未迁移'"
                  :menu-key="`role:${group.role}`"
                  :label="t('projectManager.roleMenu', { name: group.role })"
                  @rename="beginRoleRename(group.role, $event)"
                />
              </div>
            </nav>
          </aside>

          <section
            v-if="selectedGroup"
            class="min-w-0"
            data-test="project-manager-role-detail"
          >
            <header class="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p class="font-mono text-[10px] uppercase tracking-[0.16em] text-gray-500">
                  Selected Role
                </p>
                <h2 class="mt-1 text-2xl font-semibold tracking-tight text-white sm:text-3xl">
                  {{ selectedGroup.role }}
                </h2>
                <p class="mt-2 text-sm text-gray-500">
                  {{ t('projectManager.roleSummary', {
                    actions: selectedGroup.projects.length,
                    frames: roleFrameCount(selectedGroup),
                  }) }}
                </p>
              </div>

              <div class="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  @click="goToCreate(selectedGroup.role)"
                >
                  <Plus class="mr-1 h-4 w-4" />
                  {{ t('projectManager.addAction') }}
                </Button>
                <button
                  type="button"
                  class="rounded-lg p-2 text-gray-500 transition-colors hover:bg-danger/15 hover:text-danger focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger"
                  :title="t('projectManager.deleteRole')"
                  @click="confirmDeleteRole(selectedGroup.role, roleProjectCount(selectedGroup.role))"
                >
                  <Trash2 class="h-5 w-5" />
                </button>
              </div>
            </header>

            <div class="role-command-bar">
              <span class="text-xs text-gray-500">
                {{ t('projectManager.selectedAnimations', { count: selectedInRole(selectedGroup) }) }}
              </span>

              <div class="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  class="rounded-lg px-3 py-1.5 text-xs font-medium text-gray-400 transition-colors hover:bg-white/5 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:cursor-not-allowed disabled:opacity-50"
                  :disabled="trimmingRole !== null"
                  @click="toggleRoleSelection(selectedGroup)"
                >
                  {{ isRoleFullySelected(selectedGroup) ? t('batchTrim.deselectAll') : t('batchTrim.selectAll') }}
                </button>

                <div
                  role="radiogroup"
                  class="inline-flex h-[34px] items-center rounded-lg border border-dark-border bg-dark-bg/70 p-0.5"
                  :aria-label="t('projectManager.trimMode')"
                >
                  <button
                    type="button"
                    role="radio"
                    class="h-full rounded-md px-3 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:cursor-not-allowed disabled:opacity-50"
                    :class="trimMode === 'global' ? 'bg-primary/20 text-primary-200 shadow-sm' : 'text-gray-500 hover:text-gray-200'"
                    :aria-checked="trimMode === 'global'"
                    :disabled="trimmingRole !== null"
                    @click="trimMode = 'global'"
                  >
                    {{ t('batchTrim.uniformSize') }}
                  </button>
                  <button
                    type="button"
                    role="radio"
                    class="h-full rounded-md px-3 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:cursor-not-allowed disabled:opacity-50"
                    :class="trimMode === 'individual' ? 'bg-primary/20 text-primary-200 shadow-sm' : 'text-gray-500 hover:text-gray-200'"
                    :aria-checked="trimMode === 'individual'"
                    :disabled="trimmingRole !== null"
                    @click="trimMode = 'individual'"
                  >
                    {{ t('batchTrim.tightCrop') }}
                  </button>
                </div>

                <Button
                  :variant="selectedInRole(selectedGroup) > 0 ? 'primary' : 'ghost'"
                  size="sm"
                  :disabled="selectedInRole(selectedGroup) === 0 || trimmingRole !== null"
                  :loading="trimmingRole === selectedGroup.role"
                  @click="executeSelectedTrim(selectedGroup)"
                >
                  <Scissors
                    v-if="trimmingRole !== selectedGroup.role"
                    class="mr-1 h-4 w-4"
                  />
                  {{ t('projectManager.trimExport') }}
                </Button>
              </div>
            </div>

            <div class="mt-4 grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              <article
                v-for="project in paginatedProjects"
                :key="project.id"
                tabindex="0"
                class="group relative cursor-pointer overflow-hidden rounded-xl border border-dark-border bg-dark-surface transition-all hover:-translate-y-0.5 hover:border-primary hover:shadow-[0_12px_30px_-18px_rgba(255,189,92,0.5)] focus:outline-none focus:ring-2 focus:ring-primary"
                :class="{
                  'border-primary shadow-[0_0_0_1px_rgba(255,189,92,0.45)]': isProjectSelected(project.id),
                  'pointer-events-none opacity-60': openingProjectId === project.id,
                }"
                @mouseenter="startProjectPreview(project)"
                @mouseleave="stopProjectPreview(project.id)"
                @focus="startProjectPreview(project)"
                @blur="stopProjectPreview(project.id)"
                @click="openProject(project)"
                @keydown.enter.prevent="openProject(project)"
              >
                <div class="preview-stage relative grid aspect-[16/11] place-items-center overflow-hidden">
                  <input
                    type="checkbox"
                    class="absolute left-2.5 top-2.5 z-10 h-5 w-5 cursor-pointer rounded border-dark-border bg-dark-bg accent-primary shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-dark-bg"
                    :checked="isProjectSelected(project.id)"
                    :aria-label="t('projectManager.selectAnimation', { name: project.action || project.name })"
                    @click.stop
                    @keydown.stop
                    @change="toggleProjectSelection(project.id)"
                  >
                  <img
                    v-if="currentPreviewFrame(project.id)?.url"
                    :src="currentPreviewFrame(project.id)?.url"
                    alt=""
                    class="h-[78%] w-[58%] object-contain [image-rendering:auto] drop-shadow-[0_6px_10px_rgba(0,0,0,0.45)]"
                  >
                  <Loader2
                    v-else-if="previewLoading.has(project.id)"
                    class="h-7 w-7 animate-spin text-primary"
                  />
                  <Play
                    v-else-if="canPreview(project)"
                    class="h-8 w-8 text-gray-600 transition-colors group-hover:text-primary"
                  />
                  <ImageOff
                    v-else
                    class="h-8 w-8 text-gray-700"
                  />

                  <span
                    v-if="canPreview(project)"
                    data-test="project-preview-status"
                    class="absolute right-2 top-2 rounded-full border border-white/5 bg-black/40 px-2 py-1 font-mono text-[10px] text-gray-500"
                  >
                    {{ activePreviewId === project.id ? t('projectManager.previewPlaying') : t('projectManager.hoverPreview') }}
                  </span>
                  <span class="absolute bottom-2 left-2 rounded bg-black/40 px-1.5 py-0.5 font-mono text-[10px] text-gray-500">
                    {{ previewFrameLabel(project) }}
                  </span>
                </div>

                <div class="px-3.5 pb-3.5 pt-3">
                  <div class="flex items-center justify-between gap-2">
                    <h3 class="min-w-0 truncate font-semibold text-white transition-colors group-hover:text-primary">
                      {{ project.action || project.name }}
                    </h3>

                    <div
                      class="flex flex-none items-center gap-0.5"
                      @click.stop
                    >
                      <LibraryItemMenu
                        :menu-key="`project:${project.id}`"
                        :label="t('projectManager.animationMenu', { name: project.action || project.name })"
                        @rename="beginProjectRename(project, $event)"
                      />
                      <button
                        type="button"
                        class="rounded-md p-1.5 text-gray-500 hover:bg-danger/15 hover:text-danger"
                        :title="t('projectManager.deleteProject')"
                        @click="confirmDelete(project)"
                        @keydown.stop
                      >
                        <Trash2 class="h-4 w-4" />
                      </button>
                    </div>
                  </div>

                  <div class="mt-2 flex items-center gap-2.5 text-[11px] text-gray-500">
                    <span
                      class="flex items-center gap-1"
                      :title="t('projectManager.pipelineProgress')"
                    >
                      <span
                        v-for="step in 3"
                        :key="step"
                        class="h-2 w-2 rounded-sm"
                        :class="stepDotClass(project, step)"
                      />
                    </span>
                    <span class="font-mono">{{ t('projectManager.frames', { count: projectFrameCount(project) }) }}</span>
                    <span class="ml-auto font-mono">{{ formatDate(project.modified_at) }}</span>
                  </div>
                </div>

                <div
                  v-if="openingProjectId === project.id"
                  class="absolute inset-0 flex items-center justify-center rounded-lg bg-dark-bg/60"
                >
                  <Loader2 class="h-6 w-6 animate-spin text-primary" />
                </div>
              </article>
            </div>

            <nav
              v-if="animationPageCount > 1"
              class="mt-6 flex items-center justify-center gap-3"
              :aria-label="t('projectManager.animationPagination')"
            >
              <button
                type="button"
                class="pagination-button"
                :disabled="animationPage === 1"
                :aria-label="t('projectManager.previousPage')"
                @click="animationPage -= 1"
              >
                <ChevronLeft class="h-4 w-4" />
              </button>
              <span class="min-w-20 text-center font-mono text-xs text-gray-500">
                {{ t('projectManager.pageStatus', { current: animationPage, total: animationPageCount }) }}
              </span>
              <button
                type="button"
                class="pagination-button"
                :disabled="animationPage === animationPageCount"
                :aria-label="t('projectManager.nextPage')"
                @click="animationPage += 1"
              >
                <ChevronRight class="h-4 w-4" />
              </button>
            </nav>
          </section>
          <div
            v-else
            class="rounded-xl border border-dashed border-dark-border py-12 text-center text-gray-500"
            role="status"
          >
            {{ t('projectManager.noSearchResults') }}
          </div>
        </div>
      </section>
    </main>

    <!-- Delete confirmation modal -->
    <TransitionRoot
      as="template"
      :show="showDeleteModal"
    >
      <Dialog
        as="div"
        class="relative z-50"
        @close="showDeleteModal = false"
      >
        <TransitionChild
          as="template"
          enter="ease-out duration-300"
          enter-from="opacity-0"
          enter-to="opacity-100"
          leave="ease-in duration-200"
          leave-from="opacity-100"
          leave-to="opacity-0"
        >
          <div class="fixed inset-0 bg-black/50 backdrop-blur-sm" />
        </TransitionChild>

        <div class="fixed inset-0 z-10 overflow-y-auto">
          <div class="flex min-h-full items-center justify-center p-4">
            <TransitionChild
              as="template"
              enter="ease-out duration-300"
              enter-from="opacity-0 scale-95"
              enter-to="opacity-100 scale-100"
              leave="ease-in duration-200"
              leave-from="opacity-100 scale-100"
              leave-to="opacity-0 scale-95"
            >
              <DialogPanel class="w-full max-w-sm bg-dark-surface border border-dark-border rounded-xl p-6">
                <DialogTitle class="text-lg font-semibold text-white mb-2">
                  {{ t('projectManager.deleteProject') }}
                </DialogTitle>
                <p class="text-gray-400 mb-6">
                  {{ t('projectManager.deleteProjectConfirm', { name: projectToDelete?.name }) }}
                </p>

                <div class="flex gap-3">
                  <Button
                    variant="secondary"
                    class="flex-1"
                    @click="showDeleteModal = false"
                  >
                    {{ t('common.cancel') }}
                  </Button>
                  <Button
                    variant="danger"
                    class="flex-1"
                    :loading="deleting"
                    @click="deleteProject"
                  >
                    {{ t('common.delete') }}
                  </Button>
                </div>
              </DialogPanel>
            </TransitionChild>
          </div>
        </div>
      </Dialog>
    </TransitionRoot>

    <!-- Trim success modal -->
    <TransitionRoot
      as="template"
      :show="showTrimSuccessModal"
    >
      <Dialog
        as="div"
        class="relative z-50"
        @close="showTrimSuccessModal = false"
      >
        <TransitionChild
          as="template"
          enter="ease-out duration-300"
          enter-from="opacity-0"
          enter-to="opacity-100"
          leave="ease-in duration-200"
          leave-from="opacity-100"
          leave-to="opacity-0"
        >
          <div class="fixed inset-0 bg-black/50 backdrop-blur-sm" />
        </TransitionChild>

        <div class="fixed inset-0 z-10 overflow-y-auto">
          <div class="flex min-h-full items-center justify-center p-4">
            <TransitionChild
              as="template"
              enter="ease-out duration-300"
              enter-from="opacity-0 scale-95"
              enter-to="opacity-100 scale-100"
              leave="ease-in duration-200"
              leave-from="opacity-100 scale-100"
              leave-to="opacity-0 scale-95"
            >
              <DialogPanel class="w-full max-w-lg rounded-xl border border-dark-border bg-dark-surface p-6 shadow-2xl">
                <div class="flex items-start gap-3">
                  <span class="grid h-10 w-10 flex-none place-items-center rounded-full bg-success/15 text-success">
                    <CheckCircle class="h-5 w-5" />
                  </span>
                  <div class="min-w-0 flex-1">
                    <DialogTitle class="text-lg font-semibold text-white">
                      {{ t('projectManager.trimSuccessTitle') }}
                    </DialogTitle>
                    <p class="mt-1 text-sm text-gray-400">
                      {{ t('projectManager.outputDirectory') }}
                    </p>
                  </div>
                </div>

                <div class="mt-5 space-y-2">
                  <div
                    v-for="path in trimOutputDirectories"
                    :key="path"
                    class="relative rounded-lg border border-dark-border bg-dark-bg"
                  >
                    <code class="block break-all px-3 py-2.5 pr-24 text-xs text-gray-300">{{ path }}</code>
                    <button
                      type="button"
                      class="absolute right-2 top-2 flex items-center gap-1 rounded-md px-2 py-1 text-xs text-gray-400 transition-colors hover:bg-dark-border hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                      :aria-label="copiedOutputPath === path ? t('common.copied') : t('common.copy')"
                      :title="copiedOutputPath === path ? t('common.copied') : t('common.copy')"
                      @click="copyOutputPath(path)"
                    >
                      <Check
                        v-if="copiedOutputPath === path"
                        class="h-3.5 w-3.5 text-success"
                      />
                      <Copy
                        v-else
                        class="h-3.5 w-3.5"
                      />
                      {{ copiedOutputPath === path ? t('common.copied') : t('common.copy') }}
                    </button>
                  </div>
                </div>

                <div class="mt-6 flex justify-end gap-3">
                  <Button
                    variant="secondary"
                    @click="showTrimSuccessModal = false"
                  >
                    {{ t('projectManager.close') }}
                  </Button>
                  <Button @click="openTrimOutputDirectories">
                    <FolderOpen class="mr-2 h-4 w-4" />
                    {{ t('projectManager.openOutputDirectory') }}
                  </Button>
                </div>
              </DialogPanel>
            </TransitionChild>
          </div>
        </div>
      </Dialog>
    </TransitionRoot>

    <Dialog
      v-if="renameTarget"
      :open="true"
      :initial-focus="renameInput"
      class="relative z-50"
      @close="closeRename"
    >
      <div
        class="fixed inset-0 bg-black/60"
        aria-hidden="true"
      />
      <div class="fixed inset-0 overflow-y-auto">
        <div class="flex min-h-full items-center justify-center p-4">
          <DialogPanel class="w-full max-w-sm rounded-xl border border-dark-border bg-dark-surface p-6 shadow-2xl">
            <DialogTitle class="mb-4 text-lg font-semibold text-white">
              {{ t(renameTarget.kind === 'role' ? 'projectManager.renameRole' : 'projectManager.renameAnimation') }}
            </DialogTitle>
            <form @submit.prevent="submitRename">
              <label
                for="library-rename-name"
                class="mb-2 block text-sm text-gray-300"
              >
                {{ t(renameTarget.kind === 'role' ? 'projectManager.roleName' : 'projectManager.actionName') }}
              </label>
              <input
                id="library-rename-name"
                ref="renameInput"
                v-model="renameName"
                type="text"
                autocomplete="off"
                class="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2.5 text-sm text-white outline-none focus:border-primary"
                :disabled="renaming"
                :aria-invalid="Boolean(renameError)"
                :aria-describedby="renameError ? 'library-rename-error' : undefined"
                @focus="renameInput?.select()"
              >
              <p
                v-if="renameError"
                id="library-rename-error"
                role="alert"
                class="mt-2 break-words text-sm text-danger"
              >
                {{ renameError }}
              </p>
              <div class="mt-5 flex justify-end gap-3">
                <Button
                  variant="secondary"
                  :disabled="renaming"
                  @click="closeRename"
                >
                  {{ t('common.cancel') }}
                </Button>
                <Button
                  type="submit"
                  :loading="renaming"
                  :disabled="!renameName.trim() || renaming"
                >
                  {{ t('common.save') }}
                </Button>
              </div>
            </form>
          </DialogPanel>
        </div>
      </div>
    </Dialog>

    <!-- Delete role confirmation modal -->
    <TransitionRoot
      as="template"
      :show="showDeleteRoleModal"
    >
      <Dialog
        as="div"
        class="relative z-50"
        @close="showDeleteRoleModal = false"
      >
        <TransitionChild
          as="template"
          enter="ease-out duration-300"
          enter-from="opacity-0"
          enter-to="opacity-100"
          leave="ease-in duration-200"
          leave-from="opacity-100"
          leave-to="opacity-0"
        >
          <div class="fixed inset-0 bg-black/50 backdrop-blur-sm" />
        </TransitionChild>

        <div class="fixed inset-0 z-10 overflow-y-auto">
          <div class="flex min-h-full items-center justify-center p-4">
            <TransitionChild
              as="template"
              enter="ease-out duration-300"
              enter-from="opacity-0 scale-95"
              enter-to="opacity-100 scale-100"
              leave="ease-in duration-200"
              leave-from="opacity-100 scale-100"
              leave-to="opacity-0 scale-95"
            >
              <DialogPanel class="w-full max-w-md bg-dark-surface border border-dark-border rounded-xl p-6">
                <DialogTitle class="text-lg font-semibold text-white mb-2">
                  {{ t('projectManager.deleteRole') }}
                </DialogTitle>
                <p class="text-gray-400 mb-6">
                  {{ t('projectManager.deleteRoleConfirm', { role: roleToDelete?.role, count: roleToDelete?.count }) }}
                </p>

                <div class="flex gap-3">
                  <Button
                    variant="secondary"
                    class="flex-1"
                    @click="showDeleteRoleModal = false"
                  >
                    {{ t('common.cancel') }}
                  </Button>
                  <Button
                    variant="danger"
                    class="flex-1"
                    :loading="deletingRole"
                    @click="deleteRole"
                  >
                    {{ t('projectManager.deleteRole') }}
                  </Button>
                </div>
              </DialogPanel>
            </TransitionChild>
          </div>
        </div>
      </Dialog>
    </TransitionRoot>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { onBeforeRouteLeave, useRouter } from 'vue-router';
import { storeToRefs } from 'pinia';
import { useI18n } from 'vue-i18n';
import {
  AlertTriangle,
  Check,
  CheckCircle,
  ChevronLeft,
  ChevronRight,
  Copy,
  FolderOpen,
  ImageOff,
  ImagePlus,
  Loader2,
  MoreVertical,
  Play,
  Plus,
  RefreshCw,
  Scissors,
  Search,
  Trash2,
  X,
} from 'lucide-vue-next';
import { Dialog, DialogPanel, DialogTitle, Menu, MenuButton, MenuItem, MenuItems, TransitionChild, TransitionRoot } from '@headlessui/vue';
import { useProjectStore } from '@/stores/project';
import { usePlayerStore } from '@/stores/player';
import { api } from '@/api';
import type { BatchTrimResult, Frame, Project, ProjectRenameResult } from '@/types';
import Button from '@/components/common/Button.vue';
import Select from '@/components/common/Select.vue';
import Header from '@/components/layout/Header.vue';
import ProjectManagerHero from '@/components/project-manager/ProjectManagerHero.vue';
import LibraryItemMenu from '@/components/project-manager/LibraryItemMenu.vue';

const router = useRouter();
const projectStore = useProjectStore();
const playerStore = usePlayerStore();
const { locale, t } = useI18n();
const { projects, loading, legacyProjects, activeLibraryRole: activeRole } = storeToRefs(projectStore);

const savedLibraryView = { ...projectStore.libraryViewState, role: activeRole.value };
const searchQuery = ref(savedLibraryView.searchQuery);
const roleNav = ref<HTMLElement | null>(null);
let leavingLibrary = false;
const renameTarget = ref<{ kind: 'role' | 'project'; id: string; name: string } | null>(null);
const renameName = ref('');
const renameError = ref('');
const renaming = ref(false);
const renameInput = ref<HTMLInputElement | null>(null);
let renameTrigger: HTMLElement | undefined;
let preservingRenamePage = false;
const previewVersions = new Map<string, number>();
const showDeleteModal = ref(false);
const projectToDelete = ref<Project | null>(null);
const deleting = ref(false);
const showDeleteRoleModal = ref(false);
const roleToDelete = ref<{ role: string; count: number } | null>(null);
const deletingRole = ref(false);
const openingProjectId = ref<string | null>(null);
const migrating = ref(false);
const migrationMessage = ref('');
const migrationDrafts = ref<Record<string, { targetRole: string; targetAction: string }>>({});
const legacyMigrationVisible = ref(true);
const newMigrationRole = ref('');
const customMigrationRoles = ref<string[]>([]);
const migrationRoleMessage = ref('');
const importingLegacyDirectory = ref(false);
const importMessage = ref('');
const animationPage = ref(savedLibraryView.animationPage);
const cardsPerPage = ref(16);
const selectedProjectIds = ref<Set<string>>(new Set());
const trimMode = ref<'global' | 'individual'>('global');
const trimmingRole = ref<string | null>(null);
const showTrimSuccessModal = ref(false);
const trimOutputDirectories = ref<string[]>([]);
const copiedOutputPath = ref('');
const previewFrames = ref<Record<string, Frame[]>>({});
const previewIndexes = ref<Record<string, number>>({});
const previewLoading = ref<Set<string>>(new Set());
const activePreviewId = ref<string | null>(null);
const previewTimers = new Map<string, ReturnType<typeof setInterval>>();

const groupedProjects = computed(() => {
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
  const query = searchQuery.value.trim().toLocaleLowerCase(locale.value);
  if (!query) return groupedProjects.value;

  return groupedProjects.value
    .map(group => {
      if (group.role.toLocaleLowerCase(locale.value).includes(query)) return group;
      return {
        ...group,
        projects: group.projects.filter(project => (
          (project.action || project.name).toLocaleLowerCase(locale.value).includes(query)
        )),
      };
    })
    .filter(group => group.projects.length > 0);
});

const selectedGroup = computed(() => (
  filteredGroupedProjects.value.find(group => group.role === activeRole.value)
  ?? filteredGroupedProjects.value[0]
  ?? null
));

const animationPageCount = computed(() => Math.max(
  1,
  Math.ceil((selectedGroup.value?.projects.length ?? 0) / cardsPerPage.value)
));

const paginatedProjects = computed(() => {
  if (!selectedGroup.value) return [];
  const start = (animationPage.value - 1) * cardsPerPage.value;
  return selectedGroup.value.projects.slice(start, start + cardsPerPage.value);
});

watch(
  () => filteredGroupedProjects.value.map(group => group.role),
  (roles) => {
    if (!roles.includes(activeRole.value)) activeRole.value = roles[0] ?? '';
  },
  { immediate: true }
);

watch(
  [() => selectedGroup.value?.role, searchQuery, cardsPerPage],
  () => {
    if (!preservingRenamePage) animationPage.value = 1;
  }
);

watch(animationPageCount, (pageCount) => {
  animationPage.value = Math.min(animationPage.value, pageCount);
});

const canMigrateLegacy = computed(() => {
  return legacyProjects.value.length > 0 && legacyProjects.value.every(project => {
    const draft = migrationDrafts.value[project.id];
    return draft?.targetRole.trim() && draft?.targetAction.trim();
  });
});

const migrationRoleOptions = computed(() => {
  const roles = new Set<string>();
  for (const role of projectStore.roles) {
    if (role.name) {
      roles.add(role.name);
    }
  }
  for (const role of customMigrationRoles.value) {
    if (role) {
      roles.add(role);
    }
  }
  return Array.from(roles).sort((a, b) => a.localeCompare(b, 'zh-CN'));
});
const migrationRoleSelectOptions = computed(() => migrationRoleOptions.value.map(role => ({
  value: role,
  label: role,
})));

watch(
  legacyProjects,
  (items) => {
    const next: Record<string, { targetRole: string; targetAction: string }> = {};
    for (const project of items) {
      const existing = migrationDrafts.value[project.id];
      next[project.id] = {
        targetRole: existing?.targetRole ?? '',
        targetAction: existing?.targetAction ?? project.action ?? project.name ?? project.id,
      };
    }
    migrationDrafts.value = next;
  },
  { immediate: true }
);

onMounted(initializeLibrary);
onBeforeRouteLeave(rememberLibraryView);

onBeforeUnmount(() => {
  leavingLibrary = true;
  window.removeEventListener('resize', updateCardsPerPage);
  stopProjectPreview();
});

function rememberLibraryView() {
  leavingLibrary = true;
  Object.assign(projectStore.libraryViewState, {
    searchQuery: searchQuery.value,
    animationPage: animationPage.value,
    scrollY: window.scrollY,
    roleScrollTop: roleNav.value?.scrollTop ?? 0,
  });
}

async function initializeLibrary() {
  updateCardsPerPage();
  window.addEventListener('resize', updateCardsPerPage);
  await loadProjects();
  await nextTick();
  if (leavingLibrary) return;

  // Loading and responsive page sizes may reset the page before the list is ready.
  animationPage.value = activeRole.value === savedLibraryView.role
    ? Math.min(savedLibraryView.animationPage, animationPageCount.value)
    : 1;
  await nextTick();
  if (leavingLibrary) return;

  if (roleNav.value) roleNav.value.scrollTop = savedLibraryView.roleScrollTop;
  window.scrollTo({ top: savedLibraryView.scrollY, behavior: 'auto' });
}

function updateCardsPerPage() {
  const width = window.innerWidth;
  let next = 4;
  if (width >= 1280) next = 16;
  else if (width >= 1024) next = 12;
  else if (width >= 640) next = 8;
  cardsPerPage.value = next;
}

function loadProjects() {
  stopProjectPreview();
  previewFrames.value = {};
  previewIndexes.value = {};
  return projectStore.loadProjects();
}

async function importLegacyProjectDirectory() {
  const directory = await api.system.selectDirectory();
  if (!directory) return;

  importingLegacyDirectory.value = true;
  importMessage.value = '';
  try {
    const result = await projectStore.importLegacyProjectDirectory(directory);
    if (!result.success && result.imported.length === 0 && result.skipped.length === 0) {
      importMessage.value = result.failed[0]?.reason || t('projectManager.importLegacyProjectsFailed');
    } else {
      importMessage.value = t('projectManager.importLegacyProjectsResult', {
        source: result.source,
        imported: result.imported.length,
        skipped: result.skipped.length,
        failed: result.failed.length,
      });
    }
  } catch (error) {
    importMessage.value = error instanceof Error ? error.message : t('projectManager.importLegacyProjectsFailed');
  } finally {
    importingLegacyDirectory.value = false;
  }
}

function goToCreate(role?: string) {
  if (typeof role === 'string' && role) {
    router.push({ path: '/create', query: { role } });
  } else {
    router.push('/create');
  }
}

function isProjectSelected(projectId: string) {
  return selectedProjectIds.value.has(projectId);
}

function toggleProjectSelection(projectId: string) {
  const next = new Set(selectedProjectIds.value);
  if (next.has(projectId)) {
    next.delete(projectId);
  } else {
    next.add(projectId);
  }
  selectedProjectIds.value = next;
}

function selectedInRole(group: { projects: Project[] }) {
  return group.projects.filter(project => selectedProjectIds.value.has(project.id)).length;
}

function isRoleFullySelected(group: { projects: Project[] }) {
  return group.projects.length > 0
    && group.projects.every(project => selectedProjectIds.value.has(project.id));
}

function toggleRoleSelection(group: { projects: Project[] }) {
  const next = new Set(selectedProjectIds.value);
  if (isRoleFullySelected(group)) {
    for (const project of group.projects) next.delete(project.id);
  } else {
    for (const project of group.projects) next.add(project.id);
  }
  selectedProjectIds.value = next;
}

function selectRole(role: string) {
  stopProjectPreview();
  activeRole.value = role;
}

function roleFrameCount(group: { projects: Project[] }) {
  return group.projects.reduce((total, project) => total + projectFrameCount(project), 0);
}

function roleProjectCount(role: string) {
  return groupedProjects.value.find(group => group.role === role)?.projects.length ?? 0;
}

async function executeSelectedTrim(group: { role: string; projects: Project[] }) {
  const projectIds = group.projects
    .map(project => project.id)
    .filter(projectId => selectedProjectIds.value.has(projectId));
  if (projectIds.length === 0 || trimmingRole.value !== null) return;

  trimmingRole.value = group.role;
  try {
    const results: BatchTrimResult[] = await api.batchTrim.executeTrim({
      projectIds,
      mode: trimMode.value,
      outputDir: '',
    });
    trimOutputDirectories.value = Array.from(new Set(
      results
        .filter(result => result.status === 'success' && result.outputPath)
        .map(result => getParentDirectory(result.outputPath as string))
    ));
    showTrimSuccessModal.value = results.length > 0
      && results.every(result => result.status === 'success')
      && trimOutputDirectories.value.length > 0;
  } catch (error) {
    console.error('执行裁剪导出失败:', error);
  } finally {
    trimmingRole.value = null;
  }
}

function getParentDirectory(path: string) {
  return path.replace(/[\\/]+$/, '').replace(/[\\/][^\\/]+$/, '');
}

async function openTrimOutputDirectories() {
  await Promise.all(trimOutputDirectories.value.map(path => api.system.openProjectFolder(path)));
}

async function copyOutputPath(path: string) {
  let copied = false;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(path);
      copied = true;
    }
  } catch {
    // Fall through to the WebView-compatible textarea copy below.
  }

  if (!copied) {
    const textarea = document.createElement('textarea');
    textarea.value = path;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.append(textarea);
    textarea.select();
    try {
      copied = document.execCommand('copy');
    } catch {
      copied = false;
    } finally {
      textarea.remove();
    }
  }

  if (!copied) return;
  copiedOutputPath.value = path;
  window.setTimeout(() => {
    if (copiedOutputPath.value === path) copiedOutputPath.value = '';
  }, 1600);
}

function goToAICreation() {
  router.push('/ai-creation');
}

function canPreview(project: Project) {
  const step = project.steps?.['1'];
  return Boolean(step && step.count > 0 && (step.data_ready || step.completed));
}

function previewSourceStep(project: Project) {
  if ((project.steps?.['3']?.count ?? 0) > 0) return 3;
  if ((project.steps?.['2']?.count ?? 0) > 0) return 2;
  return 1;
}

async function loadPreviewFrames(project: Project) {
  const cached = previewFrames.value[project.id];
  if (cached) return cached;
  if (previewLoading.value.has(project.id)) return [];

  previewLoading.value = new Set(previewLoading.value).add(project.id);
  const version = previewVersions.get(project.id) ?? 0;
  try {
    const response = await api.frame.getFrames(project.id, previewSourceStep(project), 1, 12, true);
    if ((previewVersions.get(project.id) ?? 0) !== version || leavingLibrary) return [];
    const frames = response.success ? response.frames : [];
    previewFrames.value = { ...previewFrames.value, [project.id]: frames };
    previewIndexes.value = { ...previewIndexes.value, [project.id]: 0 };
    return frames;
  } catch (error) {
    console.error('Failed to load project preview:', error);
    return [];
  } finally {
    if ((previewVersions.get(project.id) ?? 0) === version) {
      const nextLoading = new Set(previewLoading.value);
      nextLoading.delete(project.id);
      previewLoading.value = nextLoading;
    }
  }
}

async function startProjectPreview(project: Project) {
  if (!canPreview(project)) return;

  stopProjectPreview();
  activePreviewId.value = project.id;
  const frames = await loadPreviewFrames(project);
  if (activePreviewId.value !== project.id || frames.length < 2) return;

  previewTimers.set(project.id, setInterval(() => {
    const current = previewIndexes.value[project.id] ?? 0;
    previewIndexes.value = {
      ...previewIndexes.value,
      [project.id]: (current + 1) % frames.length,
    };
  }, 100));
}

function stopProjectPreview(projectId?: string) {
  if (projectId && activePreviewId.value !== projectId) return;

  for (const timer of previewTimers.values()) clearInterval(timer);
  previewTimers.clear();

  const activeId = activePreviewId.value;
  if (activeId) previewIndexes.value = { ...previewIndexes.value, [activeId]: 0 };
  activePreviewId.value = null;
}

function currentPreviewFrame(projectId: string) {
  const frames = previewFrames.value[projectId];
  if (!frames?.length) return undefined;
  return frames[previewIndexes.value[projectId] ?? 0];
}

function projectFrameCount(project: Project) {
  return Math.max(
    project.steps?.['1']?.count ?? 0,
    project.steps?.['2']?.count ?? 0,
    project.steps?.['3']?.count ?? 0,
  );
}

function previewFrameLabel(project: Project) {
  const frames = previewFrames.value[project.id];
  const current = frames?.length ? (previewIndexes.value[project.id] ?? 0) + 1 : 0;
  return `${String(current).padStart(2, '0')}/${String(projectFrameCount(project)).padStart(2, '0')}`;
}

function stepDotClass(project: Project, step: number) {
  if (project.steps?.[String(step)]?.completed) return 'bg-success';

  const currentStep = [1, 2, 3].find(item => !project.steps?.[String(item)]?.completed) ?? 3;
  return step === currentStep
    ? 'bg-primary shadow-[0_0_0_2px_rgba(255,189,92,0.25)]'
    : 'bg-dark-border';
}

async function openProject(project: Project) {
  if (openingProjectId.value) return;
  openingProjectId.value = project.id;

  try {
    projectStore.setCurrentProject(project);

    // Preload step 1 frames so the editor opens with images ready
    const response = await api.frame.getFrames(project.id, 1, 1, 500, true);
    if (response.success && response.frames.length > 0) {
      playerStore.loadFrames(response.frames);
      // Urgent preload first 6 frames before switching UI
      const urgent = response.frames.slice(0, 6);
      await playerStore.preloadFrames(urgent, 3);
    }

    router.push('/editor');
  } catch (e) {
    console.error('Failed to preload project frames:', e);
    // Still navigate so user isn't stuck
    router.push('/editor');
  } finally {
    openingProjectId.value = null;
  }
}

function beginRoleRename(role: string, trigger?: HTMLButtonElement) {
  if (role === '未迁移') return;
  beginRename({ kind: 'role', id: role, name: role }, trigger);
}

function beginProjectRename(project: Project, trigger?: HTMLButtonElement) {
  beginRename({ kind: 'project', id: project.id, name: project.action || project.name }, trigger);
}

function beginRename(target: NonNullable<typeof renameTarget.value>, trigger?: HTMLButtonElement) {
  if (renaming.value || openingProjectId.value) return;
  renameTrigger = trigger;
  renameTarget.value = target;
  renameName.value = target.name;
  renameError.value = '';
  void nextTick(() => renameInput.value?.select());
}

async function restoreRenameFocus(key?: string) {
  await nextTick();
  if (typeof document === 'undefined') return;
  const menu = key ? Array.from(document.querySelectorAll<HTMLElement>('[data-item-menu]'))
    .find(item => item.dataset.itemMenu === key) : undefined;
  const target = menu?.querySelector('button')
    ?? (renameTrigger?.isConnected ? renameTrigger : undefined)
    ?? document.querySelector<HTMLInputElement>('input[type="search"]');
  target?.focus();
}

function closeRename() {
  if (renaming.value) return;
  renameTarget.value = null;
  void restoreRenameFocus();
}

function applyRenameResult(result: ProjectRenameResult) {
  const affected = new Set(Object.keys(result.idMap));
  if (activePreviewId.value && affected.has(activePreviewId.value)) stopProjectPreview();
  for (const id of affected) {
    previewVersions.set(id, (previewVersions.get(id) ?? 0) + 1);
    const timer = previewTimers.get(id);
    if (timer) clearInterval(timer);
    previewTimers.delete(id);
    delete previewFrames.value[id];
    delete previewIndexes.value[id];
  }
  previewLoading.value = new Set([...previewLoading.value].filter(id => !affected.has(id)));
  selectedProjectIds.value = new Set([...selectedProjectIds.value].map(id => result.idMap[id] ?? id));
  const drafts = { ...migrationDrafts.value };
  for (const [oldId, newId] of Object.entries(result.idMap)) {
    if (oldId !== newId && drafts[oldId]) {
      drafts[newId] = drafts[oldId];
      delete drafts[oldId];
    }
  }
  migrationDrafts.value = drafts;
  if (projectStore.currentProject && affected.has(projectStore.currentProject.id)) {
    playerStore.stop();
    playerStore.loadFrames([]);
  }
  preservingRenamePage = true;
  projectStore.applyRename(result);
  void nextTick(() => { preservingRenamePage = false; });
}

async function submitRename() {
  const target = renameTarget.value;
  if (!target || renaming.value || !renameName.value.trim()) return;
  renaming.value = true;
  renameError.value = '';
  try {
    const result = target.kind === 'role'
      ? await api.project.renameRole(target.id, renameName.value)
      : await api.project.renameProject(target.id, renameName.value);
    applyRenameResult(result);
    const newId = target.kind === 'role'
      ? result.projects[0]?.role ?? target.id
      : result.idMap[target.id] ?? target.id;
    renameTarget.value = null;
    await restoreRenameFocus(`${target.kind}:${newId}`);
  } catch (error) {
    const message = error instanceof Error ? error.message
      : String((error as { message?: string })?.message ?? error);
    const code = message.match(/RENAME_(?:INVALID|NOT_FOUND|CONFLICT|BUSY|RESTART|FAILED|RECOVERY)\b/)?.[0];
    renaming.value = false;
    renameError.value = t(`projectManager.renameErrors.${code ?? 'RENAME_UNKNOWN'}`);
    if (code === 'RENAME_RECOVERY') renameError.value += ` ${message}`;
    await nextTick();
    renameInput.value?.focus();
  } finally {
    renaming.value = false;
  }
}

function confirmDelete(project: Project) {
  projectToDelete.value = project;
  showDeleteModal.value = true;
}

function confirmDeleteRole(role: string, count: number) {
  roleToDelete.value = { role, count };
  showDeleteRoleModal.value = true;
}

async function deleteProject() {
  if (!projectToDelete.value) return;

  deleting.value = true;
  try {
    await projectStore.deleteProject(projectToDelete.value.id);
    showDeleteModal.value = false;
    projectToDelete.value = null;
  } finally {
    deleting.value = false;
  }
}

async function deleteRole() {
  if (!roleToDelete.value) return;

  deletingRole.value = true;
  try {
    await projectStore.deleteRole(roleToDelete.value.role);
    showDeleteRoleModal.value = false;
    roleToDelete.value = null;
  } finally {
    deletingRole.value = false;
  }
}

async function migrateLegacy() {
  if (!canMigrateLegacy.value) return;

  migrating.value = true;
  migrationMessage.value = '';
  try {
    const migrations = legacyProjects.value.map(project => ({
      projectId: project.id,
      targetRole: migrationDrafts.value[project.id].targetRole.trim(),
      targetAction: migrationDrafts.value[project.id].targetAction.trim(),
    }));
    const result = await projectStore.migrateLegacyProjects(migrations);
    migrationMessage.value = result.success
      ? `Migrated ${result.migrated.length} legacy project(s).`
      : `Migration aborted: ${result.conflicts.length} target directory(s) already exist. Please resolve conflicts first.`;
  } finally {
    migrating.value = false;
  }
}

function createMigrationRole() {
  const role = newMigrationRole.value.trim();
  if (!role) return;

  const exists = migrationRoleOptions.value.some(item => item.toLowerCase() === role.toLowerCase());
  if (!exists) {
    customMigrationRoles.value = [...customMigrationRoles.value, role];
  }

  for (const project of legacyProjects.value) {
    const draft = migrationDrafts.value[project.id];
    if (draft && !draft.targetRole.trim()) {
      draft.targetRole = role;
    }
  }

  migrationRoleMessage.value = exists
    ? `Role "${role}" already exists.`
    : `Created role "${role}". You can now select it from the target role dropdown.`;
  newMigrationRole.value = '';
}

function formatDate(dateStr: string): string {
  if (!dateStr) return 'Unknown';
  const date = new Date(dateStr);
  return date.toLocaleDateString(locale.value, {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    ...(locale.value.startsWith('en') ? { hourCycle: 'h23' as const } : {}),
  });
}
</script>

<style scoped>
.library-workbench {
  display: grid;
  grid-template-columns: minmax(210px, 240px) minmax(0, 1fr);
  align-items: start;
  gap: 1.75rem;
}

.role-dock {
  position: sticky;
  top: 5.5rem;
  min-width: 0;
  border-radius: 1rem;
  background: linear-gradient(155deg, rgb(36 36 36 / 72%), rgb(26 26 26 / 36%));
  box-shadow: inset 0 1px rgb(255 255 255 / 3%);
  padding: 1rem;
}

.role-nav {
  display: grid;
  gap: 0.3rem;
  margin-top: 0.8rem;
  max-height: 28.95rem;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-width: thin;
  scrollbar-color: #3a3a3a transparent;
}

.role-nav-item {
  display: flex;
  width: 100%;
  min-width: 0;
  min-height: 2.625rem;
  align-items: center;
  gap: 0.6rem;
  border-radius: 0.6rem;
  padding: 0.65rem;
  color: #737b87;
  text-align: left;
  transition: color 160ms ease, background 160ms ease;
}

.role-nav-item:hover {
  color: #d1d5db;
  background: rgb(255 255 255 / 3%);
}

.role-nav-item.active {
  color: white;
  background: rgb(255 189 92 / 14%);
}

.role-nav-item:focus-visible {
  outline: 2px solid #ffbd5c;
  outline-offset: 2px;
}

.role-nav-dot {
  width: 0.45rem;
  height: 0.45rem;
  flex: none;
  border-radius: 0.15rem;
  background: currentColor;
}

.role-command-bar {
  display: flex;
  min-height: 3.25rem;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-top: 1.5rem;
  border-radius: 0.8rem;
  background: rgb(36 36 36 / 55%);
  padding: 0.55rem 0.65rem 0.55rem 1rem;
}

.pagination-button {
  display: grid;
  width: 2rem;
  height: 2rem;
  place-items: center;
  border-radius: 0.55rem;
  color: #9ca3af;
  background: rgb(36 36 36 / 72%);
  transition: color 160ms ease, background 160ms ease;
}

.pagination-button:hover:not(:disabled) {
  color: white;
  background: #333;
}

.pagination-button:focus-visible {
  outline: 2px solid #ffbd5c;
  outline-offset: 2px;
}

.pagination-button:disabled {
  cursor: not-allowed;
  opacity: 0.35;
}

.preview-stage {
  background-color: #1c1c1c;
  background-image:
    linear-gradient(45deg, #242424 25%, transparent 25%),
    linear-gradient(-45deg, #242424 25%, transparent 25%),
    linear-gradient(45deg, transparent 75%, #242424 75%),
    linear-gradient(-45deg, transparent 75%, #242424 75%);
  background-position: 0 0, 0 9px, 9px -9px, -9px 0;
  background-size: 18px 18px;
}

.empty-library {
  display: flex;
  flex-direction: column;
  align-items: center;
  border: 1px dashed #333;
  border-radius: 1rem;
  background:
    radial-gradient(500px 240px at 50% -10%, rgb(255 189 92 / 10%), transparent 60%),
    #141414;
  padding: 4rem 1.25rem;
  text-align: center;
}

@media (max-width: 1023px) {
  .library-workbench {
    grid-template-columns: minmax(0, 1fr);
  }

  .role-dock {
    position: static;
  }

  .role-nav {
    display: flex;
    max-height: none;
    overflow-x: auto;
    overflow-y: hidden;
    padding-bottom: 0.15rem;
  }

  .role-nav-item {
    width: auto;
    min-width: 9rem;
    flex: none;
  }
}

@media (max-width: 639px) {
  .role-command-bar {
    align-items: flex-start;
    flex-direction: column;
    padding: 0.75rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  article {
    transition: none;
  }

  article:hover {
    transform: none;
  }
}
</style>
