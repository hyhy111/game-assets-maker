<template>
  <SeedancePanel
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
        :aria-label="t('skillsInstall.agent')"
        data-test="gam-skills-agent"
      />
    </label>
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
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import Button from '@/components/common/Button.vue';
import Select from '@/components/common/Select.vue';
import SeedancePanel from '@/components/seedance/SeedancePanel.vue';

const { t } = useI18n();
const agent = ref('codex');
const agentOptions = [
  { value: 'codex', label: 'Codex' },
  { value: 'claude-code', label: 'Claude Code' },
  { value: 'cursor', label: 'Cursor' },
  { value: 'opencode', label: 'OpenCode' },
  { value: 'gemini-cli', label: 'Gemini CLI' },
  { value: 'github-copilot', label: 'GitHub Copilot' },
  { value: 'windsurf', label: 'Windsurf' },
];
const command = computed(() => `npx skills add hyhy111/gam-skills -g -a ${agent.value} --skill "*"`);
const copied = ref(false);
const copyFailed = ref(false);

watch(agent, () => { copied.value = false; copyFailed.value = false; });

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
