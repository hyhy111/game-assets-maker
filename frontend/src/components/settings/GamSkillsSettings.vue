<template>
  <SeedancePanel
    id="gam-skills"
    class="mb-5"
    :title="t('skillsInstall.title')"
    :description="t('skillsInstall.description')"
    data-test="gam-skills-settings"
  >
    <label class="block max-w-sm text-sm text-gray-300">
      {{ t('skillsInstall.agent') }}
      <Select
        v-model="agent"
        class="mt-2"
        :options="agentOptions"
        :disabled="installing"
        :aria-label="t('skillsInstall.agent')"
        data-test="gam-skills-agent"
      />
    </label>
    <div class="mt-4 flex flex-wrap items-center gap-3">
      <Button
        type="button"
        :loading="installing"
        :disabled="checking || installing || !status?.can_install || !status?.node_available"
        data-test="gam-skills-install"
        @click="installSkills"
      >
        {{ t(status?.source === 'npx' ? 'skillsInstall.installOrUpdate' : 'skillsInstall.install') }}
      </Button>
      <Button
        v-if="status?.source === 'npx'"
        type="button"
        variant="secondary"
        :disabled="checking || installing || !status.can_check"
        data-test="gam-skills-check"
        @click="refreshStatus"
      >
        {{ t('skillsInstall.checkUpdates') }}
      </Button>
      <span
        v-if="checking || installing"
        class="text-sm text-gray-400"
        role="status"
      >
        {{ t(installing ? 'skillsInstall.installing' : 'skillsInstall.checking') }}
      </span>
    </div>
    <p
      v-if="status && !checking"
      class="mt-3 text-sm"
      :class="status.status === 'update_available' ? 'text-primary' : 'text-gray-400'"
      role="status"
      data-test="gam-skills-status"
    >
      {{ t(`skillsInstall.states.${status.status}`, { count: status.installed_count, total: status.total_count, updates: status.outdated.length }) }}
    </p>
    <p
      v-if="status && !status.node_available"
      class="mt-2 text-sm text-primary"
      data-test="gam-skills-node-required"
    >
      {{ t('skillsInstall.nodeRequired') }}
    </p>
    <p
      v-if="operationError || status?.error"
      class="mt-2 text-sm text-primary"
      role="alert"
      data-test="gam-skills-error"
    >
      {{ errorMessage(operationError || status?.error || '') }}
    </p>
    <p
      v-if="installed"
      class="mt-2 text-sm text-success"
      role="status"
    >
      {{ t('skillsInstall.installed') }}
    </p>
    <div class="mt-4 flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start">
      <pre class="min-w-0 flex-1 whitespace-pre-wrap break-all rounded-lg border border-dark-border bg-dark-bg p-3 text-sm text-gray-200"><code data-test="gam-skills-command">{{ command }}</code></pre>
      <Button
        type="button"
        variant="secondary"
        data-test="gam-skills-copy"
        @click="copyCommand"
      >
        {{ copied ? t('common.copied') : t('common.copy') }}
      </Button>
    </div>
    <p class="mt-3 text-xs text-[var(--seedance-muted)]">
      {{ t('skillsInstall.hint') }}
    </p>
    <p
      v-if="copied"
      class="mt-2 text-sm text-success"
      role="status"
    >
      {{ t('common.copied') }}
    </p>
    <p
      v-if="copyFailed"
      class="mt-2 text-sm text-danger"
      role="alert"
    >
      {{ t('skillsInstall.copyFailed') }}
    </p>
  </SeedancePanel>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute } from 'vue-router';
import { api } from '@/api';
import { useGamSkillsUpdatesStore } from '@/stores/gamSkillsUpdates';
import type { GamSkillsStatus } from '@/types';
import Button from '@/components/common/Button.vue';
import Select from '@/components/common/Select.vue';
import SeedancePanel from '@/components/seedance/SeedancePanel.vue';

const { t } = useI18n();
const route = useRoute();
const skillsUpdates = useGamSkillsUpdatesStore();
const agentOptions = [
  { value: 'codex', label: 'Codex' },
  { value: 'claude-code', label: 'Claude Code' },
  { value: 'cursor', label: 'Cursor' },
  { value: 'opencode', label: 'OpenCode' },
  { value: 'gemini-cli', label: 'Gemini CLI' },
  { value: 'github-copilot', label: 'GitHub Copilot' },
  { value: 'windsurf', label: 'Windsurf' },
];
const requestedAgent = route.query.skillsAgent;
const agent = ref(typeof requestedAgent === 'string' && agentOptions.some(option => option.value === requestedAgent) ? requestedAgent : 'codex');
const command = computed(() => `npx skills add hyhy111/gam-skills -g -a ${agent.value} --skill "*"`);
const copied = ref(false);
const copyFailed = ref(false);
const status = ref<GamSkillsStatus | null>(null);
const checking = ref(false);
const installing = ref(false);
const installed = ref(false);
const operationError = ref('');
let requestId = 0;

watch(agent, () => {
  copied.value = false;
  copyFailed.value = false;
  installed.value = false;
  void refreshStatus();
});

function errorMessage(code: string) {
  const key = `skillsInstall.errors.${code}`;
  const text = t(key);
  return text === key ? t('skillsInstall.errors.DETECTION_FAILED') : text;
}

async function refreshStatus() {
  const id = ++requestId;
  const selected = agent.value;
  status.value = null;
  checking.value = true;
  operationError.value = '';
  try {
    const result = await api.system.getGamSkillsStatus(selected, true);
    if (id === requestId) {
      status.value = result;
      skillsUpdates.record(selected, result);
    }
  } catch {
    if (id === requestId) {
      operationError.value = 'DETECTION_FAILED';
      skillsUpdates.record(selected, null);
    }
  } finally {
    if (id === requestId) checking.value = false;
  }
}

async function installSkills() {
  if (installing.value || checking.value || !status.value?.can_install || !status.value.node_available) return;
  installing.value = true;
  installed.value = false;
  operationError.value = '';
  const id = ++requestId;
  try {
    const result = await api.system.installGamSkills(agent.value);
    if (id !== requestId) return;
    status.value = result.state;
    installed.value = result.success;
    if (!result.success) operationError.value = result.state.error || 'INSTALL_FAILED';
    else {
      skillsUpdates.record(agent.value, result.state);
      await skillsUpdates.refresh();
      await refreshStatus();
    }
  } catch {
    if (id === requestId) operationError.value = 'INSTALL_FAILED';
  } finally {
    installing.value = false;
  }
}

onMounted(() => { void refreshStatus(); });
onBeforeUnmount(() => { requestId += 1; });

async function copyCommand() {
  const text = command.value;
  copied.value = false;
  copyFailed.value = false;
  try {
    if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
    await navigator.clipboard.writeText(text);
  } catch {
    const textarea = document.createElement('textarea');
    const previousFocus = document.activeElement as HTMLElement | null;
    textarea.value = text;
    textarea.style.cssText = 'position:fixed;opacity:0;pointer-events:none;';
    document.body.append(textarea);
    textarea.select();
    try {
      if (!document.execCommand('copy')) throw new Error('Copy failed');
    } catch {
      copyFailed.value = command.value === text;
      return;
    } finally {
      textarea.remove();
      previousFocus?.focus();
    }
  }
  copied.value = command.value === text;
}
</script>
