<template>
  <SeedancePanel :title="t('seedance.handoff.title')">
    <div class="grid grid-cols-2 rounded-lg bg-black/20 p-1">
      <button
        type="button"
        class="rounded-md px-3 py-2 text-sm transition"
        :class="mode === 'existing' ? 'bg-white/[0.08] text-white' : 'text-gray-400 hover:text-white'"
        :aria-pressed="mode === 'existing'"
        @click="mode = 'existing'"
      >
        {{ t('seedance.handoff.existingRole') }}
      </button>
      <button
        type="button"
        class="rounded-md px-3 py-2 text-sm transition"
        :class="mode === 'new' ? 'bg-white/[0.08] text-white' : 'text-gray-400 hover:text-white'"
        :aria-pressed="mode === 'new'"
        @click="mode = 'new'"
      >
        {{ t('seedance.handoff.newRole') }}
      </button>
    </div>

    <form class="mt-4 space-y-4" @submit.prevent="submit">
      <label v-if="mode === 'existing' && roles.length" class="block text-sm text-gray-300">
        <span class="flex items-center justify-between gap-3">
          <span>{{ t('seedance.ui.role') }}</span>
          <span class="text-xs text-[var(--seedance-muted)]">
            {{ t('seedance.handoff.usedActions', { count: selectedRole?.projectCount ?? 0 }) }}
          </span>
        </span>
        <select v-model="role" class="seedance-control mt-2" :disabled="disabled">
          <option v-for="item in roles" :key="item.name" :value="item.name">
            {{ item.name }}
          </option>
        </select>
      </label>

      <div v-else-if="mode === 'existing'" class="rounded-lg border border-[var(--seedance-border)] p-4 text-sm">
        <p class="text-[var(--seedance-muted)]">{{ t('seedance.handoff.noRoles') }}</p>
        <button type="button" class="mt-3 text-primary hover:text-primary-300" @click="mode = 'new'">
          {{ t('seedance.handoff.createRole') }}
        </button>
      </div>

      <label v-else class="block text-sm text-gray-300">
        {{ t('seedance.handoff.roleName') }}
        <input
          v-model="role"
          class="seedance-control mt-2"
          :placeholder="t('seedance.handoff.rolePlaceholder')"
          :disabled="disabled"
        >
      </label>

      <label class="block text-sm text-gray-300">
        {{ t('seedance.handoff.actionName') }}
        <input
          v-model="action"
          class="seedance-control mt-2"
          :placeholder="t('seedance.handoff.actionPlaceholder')"
          :disabled="disabled"
        >
      </label>

      <button
        type="submit"
        class="btn-primary w-full"
        :class="{ 'cursor-wait opacity-60': creating }"
        :disabled="disabled || creating || !canSubmit"
      >
        {{ creating ? t('seedance.handoff.creatingProject') : t('seedance.handoff.submit') }}
      </button>
    </form>
  </SeedancePanel>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import type { RoleSummary } from '@/types';
import SeedancePanel from './SeedancePanel.vue';

const props = withDefaults(defineProps<{
  disabled: boolean;
  creating?: boolean;
  roles: RoleSummary[];
}>(), {
  creating: false,
});
const emit = defineEmits<{
  handoff: [payload: { role: string; action: string }];
}>();
const { t } = useI18n();
const mode = ref<'existing' | 'new'>('existing');
const role = ref(props.roles[0]?.name ?? '');
const action = ref('');
const selectedRole = computed(() => props.roles.find((item) => item.name === role.value));
const canSubmit = computed(() => Boolean(role.value.trim() && action.value.trim()));

watch(() => props.roles, (roles) => {
  if (mode.value === 'existing' && !role.value && roles.length) role.value = roles[0].name;
});
watch(mode, (value) => {
  role.value = value === 'existing' ? props.roles[0]?.name ?? '' : '';
});

function submit() {
  if (props.disabled || props.creating || !canSubmit.value) return;
  emit('handoff', { role: role.value.trim(), action: action.value.trim() });
}
</script>
