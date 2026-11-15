<template>
  <nav class="flex items-center gap-2 bg-dark-surface border border-dark-border p-2 rounded-xl">
    <button
      v-for="step in steps"
      :key="step.id"
      :disabled="!canAccessStep(step.id)"
      :class="[
        'flex items-center gap-2 px-4 py-2 rounded-lg transition-all duration-200',
        currentStep === step.id
          ? 'bg-primary text-dark-bg shadow-lg shadow-primary/25'
          : canAccessStep(step.id)
            ? 'text-gray-300 hover:bg-dark-border cursor-pointer'
            : 'text-gray-600 cursor-not-allowed'
      ]"
      @click="goToStep(step.id)"
    >
      <span
        :class="[
          'flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold',
          currentStep === step.id
            ? 'bg-dark-bg text-primary'
            : isStepCompleted(step.id)
              ? 'bg-success-500/20 text-success-500'
              : canAccessStep(step.id)
                ? 'bg-dark-border text-gray-300'
                : 'bg-dark-border text-gray-700'
        ]"
      >
        <template v-if="isStepCompleted(step.id)">
          <Check class="w-4 h-4" />
        </template>
        <template v-else>
          {{ step.id }}
        </template>
      </span>
      <span class="font-medium">{{ step.name }}</span>
    </button>

    <!-- Navigation arrows -->
    <div class="flex gap-2 ml-auto">
      <button
        type="button"
        class="step-action icon-button control-tooltip"
        :disabled="isProcessing || !projectStore.currentProject"
        :aria-label="t('header.openFolder')"
        :data-tooltip="isProcessing ? t('common.processing') : t('header.openFolder')"
        data-test="step-open-project-folder"
        @click="openProjectFolder"
      >
        <FolderOpen class="h-5 w-5" />
      </button>
      <button
        v-if="currentStep > 1"
        :disabled="!canGoPrev || isProcessing"
        :aria-label="t('steps.previous')"
        :data-tooltip="isProcessing ? t('common.processing') : t('steps.previous')"
        class="step-action icon-button control-tooltip"
        @click="processStore.prevStep()"
      >
        <ArrowLeft class="h-5 w-5" />
      </button>
      <button
        v-if="currentStep < 3"
        :disabled="!canGoNext || isProcessing"
        :aria-label="t('steps.next')"
        :data-tooltip="isProcessing ? t('common.processing') : t('steps.next')"
        class="step-action icon-button control-tooltip"
        @click="processStore.nextStep()"
      >
        <ArrowRight class="h-5 w-5" />
      </button>
      <button
        v-if="currentStep === 3"
        :disabled="isProcessing"
        :aria-label="t('steps.finish')"
        :data-tooltip="isProcessing ? t('common.processing') : t('buttonHints.finishEditing')"
        class="step-action icon-button control-tooltip"
        @click="finishEditing"
      >
        <Check class="h-5 w-5" />
      </button>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import { storeToRefs } from 'pinia';
import { useI18n } from 'vue-i18n';
import { ArrowLeft, ArrowRight, Check, FolderOpen } from 'lucide-vue-next';
import { api } from '@/api';
import { useProcessStore } from '@/stores/process';
import { useProjectStore } from '@/stores/project';

const router = useRouter();
const processStore = useProcessStore();
const projectStore = useProjectStore();
const { t } = useI18n();

const { currentStep, canGoNext, canGoPrev, isProcessing } = storeToRefs(processStore);

const steps = computed(() => [
  { id: 1, name: t('steps.frameExtraction') },
  { id: 2, name: t('steps.backgroundRemoval') },
  { id: 3, name: t('steps.holePunchAlignment') }
]);

const isStepCompleted = (stepId: number) => {
  return projectStore.isStepCompleted(stepId);
};

const canAccessStep = (stepId: number) => {
  // Disable step switching during processing
  if (isProcessing.value) {
    return stepId === currentStep.value; // Only allow clicking current step (no-op)
  }
  // Step 1 is always accessible
  if (stepId === 1) {
    return true;
  }
  // Steps 2 and 3 require step 1 to be processed
  // Use projectStore.isStepCompleted(1) instead of s1Params.value.processed
  if (stepId >= 2 && !isStepCompleted(1)) {
    return false;
  }
  // Step 3 also requires step 2 to be completed
  if (stepId === 3 && !isStepCompleted(2)) {
    return false;
  }
  // Can access if completed or current step
  if (isStepCompleted(stepId) || stepId === currentStep.value) {
    return true;
  }
  // Can access next step if previous is completed
  if (stepId > 1 && isStepCompleted(stepId - 1)) {
    return true;
  }
  return false;
};

async function finishEditing() {
  if (isProcessing.value) return;
  const failure = await router.push('/');
  if (!failure) projectStore.setCurrentProject(null);
}

async function openProjectFolder() {
  if (isProcessing.value || !projectStore.currentProject) return;
  await api.system.openProjectFolder(projectStore.currentProject.path);
}

const goToStep = (stepId: number) => {
  if (canAccessStep(stepId)) {
    processStore.goToStep(stepId);
  }
};
</script>

<style scoped>
.step-action {
  @apply rounded-lg border-0 bg-transparent text-gray-400 transition duration-200 enabled:hover:-translate-y-0.5 enabled:hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:cursor-not-allowed disabled:opacity-40 motion-reduce:transition-none motion-reduce:hover:translate-y-0;
}
</style>
