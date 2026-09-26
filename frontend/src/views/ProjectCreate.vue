<template>
  <div class="min-h-screen bg-dark-bg">
    <Header page-aligned />

    <TransitionRoot
      as="template"
      :show="showResolutionWarningModal"
    >
      <Dialog
        as="div"
        class="relative z-50"
        @close="showResolutionWarningModal = false"
      >
        <TransitionChild
          as="template"
          enter="ease-out duration-200"
          enter-from="opacity-0"
          enter-to="opacity-100"
          leave="ease-in duration-150"
          leave-from="opacity-100"
          leave-to="opacity-0"
        >
          <div class="fixed inset-0 bg-black/60" />
        </TransitionChild>

        <div class="fixed inset-0 z-50 overflow-y-auto">
          <div class="flex min-h-full items-center justify-center p-4">
            <TransitionChild
              as="template"
              enter="ease-out duration-200"
              enter-from="opacity-0 translate-y-2 scale-95"
              enter-to="opacity-100 translate-y-0 scale-100"
              leave="ease-in duration-150"
              leave-from="opacity-100 translate-y-0 scale-100"
              leave-to="opacity-0 translate-y-2 scale-95"
            >
              <DialogPanel class="w-full max-w-md bg-dark-surface border border-dark-border rounded-xl p-6">
                <div class="flex items-start gap-3">
                  <AlertTriangle class="w-5 h-5 text-warning mt-0.5 flex-shrink-0" />
                  <div>
                    <DialogTitle class="text-lg font-semibold text-white mb-2">
                      {{ t('projectCreate.resolutionWarning') }}
                    </DialogTitle>
                    <p class="text-sm text-gray-300">
                      {{ t('projectCreate.resolutionWarningDesc') }}
                    </p>
                  </div>
                </div>

                <div class="mt-6 flex justify-end">
                  <Button @click="showResolutionWarningModal = false">
                    {{ t('projectCreate.gotIt') }}
                  </Button>
                </div>
              </DialogPanel>
            </TransitionChild>
          </div>
        </div>
      </Dialog>
    </TransitionRoot>

    <main class="container mx-auto px-4 py-8 max-w-2xl">
      <!-- Page title -->
      <div class="mb-8">
        <button
          class="mb-4 ml-auto flex w-fit items-center gap-1 text-gray-400 transition-colors hover:text-white"
          @click="goBack"
        >
          <ArrowLeft class="w-4 h-4" />
          {{ t('common.back') }}
        </button>
        <h1 class="text-3xl font-bold text-white mb-2">
          {{ t('projectCreate.title') }}
        </h1>
      </div>

      <Card class="space-y-6">
        <!-- Video file selection -->
        <div class="space-y-2">
          <label class="block text-sm font-medium text-gray-300">{{ t('projectCreate.videoFile') }}</label>
          <div class="flex gap-2">
            <Input
              v-model="form.videoPath"
              readonly
              :placeholder="t('projectCreate.videoPlaceholder')"
              class="flex-1"
            />
            <Button @click="selectVideo">
              <FolderOpen class="w-4 h-4 mr-2" />
              {{ t('projectCreate.browse') }}
            </Button>
          </div>

          <!-- Video info -->
          <div
            v-if="videoInfo.success"
            class="mt-4 p-4 bg-dark-bg rounded-lg space-y-2"
          >
            <div class="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span class="text-gray-500">{{ t('projectCreate.resolution') }}:</span>
                <span class="text-gray-300 ml-2">{{ videoInfo.width }}x{{ videoInfo.height }}</span>
              </div>
              <div>
                <span class="text-gray-500">{{ t('projectCreate.fps') }}:</span>
                <span class="text-gray-300 ml-2">{{ Math.round(videoInfo.fps || 0) }}</span>
              </div>
              <div>
                <span class="text-gray-500">{{ t('projectCreate.totalFrames') }}:</span>
                <span class="text-gray-300 ml-2">{{ videoInfo.frame_count }}</span>
              </div>
              <div>
                <span class="text-gray-500">{{ t('projectCreate.duration') }}:</span>
                <span class="text-gray-300 ml-2">{{ videoInfo.duration_formatted }}</span>
              </div>
            </div>

            <!-- Validation errors -->
            <div
              v-if="validation.errors?.length"
              class="mt-4 p-3 bg-danger/10 border border-danger/30 rounded-lg"
            >
              <div class="flex items-center gap-2 text-danger mb-2">
                <AlertCircle class="w-5 h-5" />
                <span class="font-medium">{{ t('projectCreate.validationFailed') }}</span>
              </div>
              <ul class="text-sm text-danger/80 list-disc list-inside">
                <li
                  v-for="error in validation.errors"
                  :key="error"
                >
                  {{ error }}
                </li>
              </ul>
            </div>

            <!-- Validation warnings -->
            <div
              v-if="validation.warnings?.length"
              class="mt-4 p-3 bg-warning/10 border border-warning/30 rounded-lg"
            >
              <div class="flex items-center gap-2 text-warning mb-2">
                <AlertTriangle class="w-5 h-5" />
                <span class="font-medium">{{ t('projectCreate.warning') }}</span>
              </div>
              <ul class="text-sm text-warning/80 list-disc list-inside">
                <li
                  v-for="warning in validation.warnings"
                  :key="warning"
                >
                  {{ warning }}
                </li>
              </ul>
            </div>
          </div>
        </div>

        <!-- Error message -->
        <div
          v-if="projectStore.error"
          class="p-3 bg-danger/10 border border-danger/30 rounded-lg"
        >
          <div class="flex items-center gap-2 text-danger">
            <AlertCircle class="w-5 h-5" />
            <span class="font-medium">{{ projectStore.error }}</span>
          </div>
        </div>

        <!-- Role name -->
        <div class="space-y-2 mt-6">
          <label class="block text-sm font-medium text-gray-300">{{ t('projectCreate.roleName') }}</label>
          <div class="relative">
            <input
              v-model="form.role"
              type="text"
              :placeholder="t('projectCreate.roleNamePlaceholder')"
              class="w-full px-3 py-2 pr-10 bg-dark-surface border border-dark-border rounded-lg text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              @input="projectStore.clearError()"
              @focus="roleMenuOpen = true"
            >
            <button
              type="button"
              class="absolute inset-y-0 right-0 px-3 flex items-center text-gray-400 hover:text-white"
              @click="roleMenuOpen = !roleMenuOpen"
            >
              <ChevronDown class="w-4 h-4" />
            </button>

            <div
              v-if="roleMenuOpen && projectStore.roles.length > 0"
              class="absolute z-50 w-full mt-1 py-1 bg-dark-surface border border-dark-border rounded-lg shadow-lg max-h-60 overflow-auto"
            >
              <button
                v-for="role in projectStore.roles"
                :key="role.name"
                type="button"
                class="w-full text-left px-3 py-2 text-sm text-gray-300 hover:bg-primary/20 hover:text-white"
                @mousedown.prevent="selectRole(role.name)"
              >
                {{ role.name }}
              </button>
            </div>
          </div>
        </div>

        <!-- Action name -->
        <div class="space-y-2 mt-6">
          <label class="block text-sm font-medium text-gray-300">{{ t('projectCreate.actionName') }}</label>
          <Input
            v-model="form.action"
            :placeholder="t('projectCreate.actionNamePlaceholder')"
            @input="projectStore.clearError()"
          />
        </div>

        <!-- Actions -->
        <div class="flex gap-3 pt-4">
          <Button
            variant="secondary"
            class="flex-1"
            @click="goBack"
          >
            {{ t('common.cancel') }}
          </Button>
          <Button
            class="flex-1"
            :loading="creating"
            :disabled="!canCreate"
            @click="createProject"
          >
            {{ t('projectCreate.createProject') }}
          </Button>
        </div>
      </Card>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { Dialog, DialogPanel, DialogTitle, TransitionChild, TransitionRoot } from '@headlessui/vue';
import { ArrowLeft, FolderOpen, AlertCircle, AlertTriangle, ChevronDown } from 'lucide-vue-next';
import { api } from '@/api';
import { useProjectStore } from '@/stores/project';
import type { VideoInfo, VideoValidation } from '@/types';
import Card from '@/components/common/Card.vue';
import Button from '@/components/common/Button.vue';
import Input from '@/components/common/Input.vue';
import Header from '@/components/layout/Header.vue';

const router = useRouter();
const route = useRoute();
const projectStore = useProjectStore();
const { t } = useI18n();

const form = reactive({
  role: '',
  action: '',
  videoPath: ''
});

const videoInfo = ref<VideoInfo>({ success: false });
const validation = ref<VideoValidation>({ success: false });
const creating = ref(false);
const roleMenuOpen = ref(false);
const showResolutionWarningModal = ref(false);

onMounted(async () => {
  const roleQuery = route.query.role;
  if (typeof roleQuery === 'string') {
    form.role = roleQuery;
  }
  await projectStore.loadProjects();
});

const canCreate = computed(() => {
  return form.action.trim() &&
         form.videoPath &&
         videoInfo.value.success &&
         (!validation.value.errors || validation.value.errors.length === 0);
});

async function selectVideo() {
  const path = await api.system.selectVideoFile();
  if (path) {
    form.videoPath = path;
    await loadVideoInfo();
  }
}

async function loadVideoInfo() {
  if (!form.videoPath) return;

  videoInfo.value = await api.video.getVideoInfo(form.videoPath);
  validation.value = await api.video.validateVideo(form.videoPath);
  showResolutionWarningModal.value = Boolean(validation.value.warnings?.length);

  // Auto-fill project name from filename
  if (!form.action && videoInfo.value.success) {
    const filename = form.videoPath.split(/[\\/]/).pop() || '';
    form.action = filename.replace(/\.[^/.]+$/, '');
  }
}

function selectRole(role: string) {
  form.role = role;
  roleMenuOpen.value = false;
  projectStore.clearError();
}

async function createProject() {
  if (!canCreate.value) return;

  creating.value = true;
  try {
    const project = await projectStore.createProject({
      role: form.role.trim(),
      action: form.action.trim(),
      video_path: form.videoPath,
      frame_interval: 1
    });

    if (project) {
      router.push('/editor');
    }
  } catch (e) {
    console.error('Failed to create project:', e);
  } finally {
    creating.value = false;
  }
}

function goBack() {
  router.push('/');
}
</script>
