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
        v-if="currentStep > 1"
        :disabled="!canGoPrev || isProcessing"
        :title="isProcessing ? t('common.processing') : ''"
        class="px-3 py-2 rounded-lg bg-dark-border hover:bg-gray-700 text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed transition-all hover:shadow-lg hover:shadow-gray-500/25"
        @click="processStore.prevStep()"
      >
        {{ t('steps.previous') }}
      </button>
      <button
        v-if="currentStep < 3"
        :disabled="!canGoNext || isProcessing"
        :title="isProcessing ? t('common.processing') : ''"
        class="px-3 py-2 rounded-lg bg-primary hover:bg-primary-600 text-dark-bg disabled:opacity-50 disabled:cursor-not-allowed transition-all hover:shadow-lg hover:shadow-primary/25"
        @click="processStore.nextStep()"
      >
        {{ t('steps.next') }}
      </button>
      <button
        v-if="currentStep === 3"
        :disabled="isProcessing"
        :title="isProcessing ? t('common.processing') : ''"
        class="px-3 py-2 rounded-lg bg-primary hover:bg-primary-600 text-dark-bg disabled:opacity-50 disabled:cursor-not-allowed transition-all hover:shadow-lg hover:shadow-primary/25"
        @click="finishEditing"
      >
        {{ t('steps.finish') }}
      </button>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import { storeToRefs } from 'pinia';
import { useI18n } from 'vue-i18n';
import { Check } from 'lucide-vue-next';
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

const goToStep = (stepId: number) => {
  if (canAccessStep(stepId)) {
    processStore.goToStep(stepId);
  }
};
</script>
