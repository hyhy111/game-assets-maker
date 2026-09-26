<template>
  <fieldset
    :aria-describedby="describedBy"
    :aria-required="required || undefined"
    :class="[
      compact ? 'relative w-[68px] shrink-0' : '',
      dragActive ? 'rounded-md ring-2 ring-primary ring-offset-2 ring-offset-[#1b1c20]' : '',
    ]"
    :data-drag-active="dragActive || undefined"
    @dragenter="onDragEnter"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
  >
    <legend :class="compact ? 'sr-only' : 'text-sm font-medium text-gray-200'">
      {{ label }}
      <span v-if="required" class="text-danger" aria-hidden="true">*</span>
    </legend>
    <p
      :id="helpId"
      :class="compact ? 'sr-only' : 'mt-1 whitespace-pre-line text-xs leading-5 text-[var(--seedance-muted)]'"
    >
      {{ help }}
    </p>

    <div v-if="compact" class="relative h-[82px] w-[68px]">
      <div v-if="modelValue" class="group relative h-full w-full">
        <button
          type="button"
          class="h-full w-full overflow-hidden rounded-[4px] border-2 border-gray-300/80 bg-[#2b2e36] p-0.5 shadow-lg shadow-black/30 transition hover:border-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          :title="editLabel || changeLabel"
          @click="openSelectedImage"
        >
          <img :src="previewUrl" alt="" class="h-full w-full rounded-[2px] object-cover">
          <span class="sr-only">{{ editLabel || changeLabel }}</span>
        </button>
        <button
          type="button"
          class="absolute -right-1.5 -top-1.5 grid h-5 w-5 place-items-center rounded-full border border-white/25 bg-[#292b31] text-gray-300 shadow-md transition hover:bg-[#3a3d45] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          :title="removeLabel"
          @click="emit('clear')"
        >
          <X :size="12" stroke-width="2.4" aria-hidden="true" />
          <span class="sr-only">{{ removeLabel }}</span>
        </button>
      </div>

      <button
        v-else
        type="button"
        class="flex h-full w-full flex-col items-center justify-center gap-0.5 rounded-[4px] border border-white/[0.07] bg-[#2b2e36] text-gray-500 shadow-lg shadow-black/20 transition hover:border-white/15 hover:bg-[#32353e] hover:text-gray-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        :title="selectLabel"
        @click="emit('select')"
      >
        <Plus :size="20" stroke-width="2" aria-hidden="true" />
        <span class="text-[11px] font-medium leading-none">
          {{ cardLabel || label }}<span
            v-if="required"
            class="ml-0.5 text-danger"
            data-test="seedance-frame-required"
            aria-hidden="true"
          >*</span>
        </span>
        <span
          v-if="optionalLabel"
          class="text-[9px] leading-none text-gray-600"
          data-test="seedance-frame-optional"
        >
          {{ optionalLabel }}
        </span>
      </button>
      <div
        v-if="dragActive"
        class="pointer-events-none absolute inset-0 z-20 grid place-items-center rounded-[4px] bg-primary/90 px-2 text-center text-[11px] font-semibold leading-tight text-dark-bg shadow-xl"
        aria-hidden="true"
      >
        {{ dropLabel || label }}
      </div>
    </div>

    <div
      v-else
      class="mt-3 min-h-44 overflow-hidden rounded-xl border border-dashed border-[var(--seedance-border)] bg-black/10"
      data-density="default"
    >
      <div
        v-if="modelValue"
        class="relative flex min-h-44 items-center gap-3 p-3"
      >
        <img
          :src="previewUrl"
          alt=""
          class="h-36 w-40 rounded-lg bg-black/30 object-contain"
        >
        <div class="min-w-0 flex-1">
          <p class="truncate text-sm font-medium text-gray-200">{{ fileName }}</p>
          <p class="mt-1 text-xs text-[var(--seedance-muted)]">{{ selectedLabel }}</p>
          <div class="mt-4 flex flex-wrap gap-2">
            <button type="button" class="btn-secondary px-3 py-1.5 text-xs" @click="emit('select')">
              {{ changeLabel }}
            </button>
            <button
              v-if="editLabel"
              type="button"
              class="btn-secondary px-3 py-1.5 text-xs"
              data-test="seedance-edit-image"
              @click="emit('edit')"
            >
              {{ editLabel }}
            </button>
            <button type="button" class="px-3 py-1.5 text-xs text-gray-400 hover:text-white" @click="emit('clear')">
              {{ removeLabel }}
            </button>
          </div>
        </div>
      </div>

      <button
        v-else
        type="button"
        class="flex min-h-44 w-full flex-col items-center justify-center gap-3 px-5 text-center text-gray-400 transition hover:bg-white/[0.03] hover:text-white"
        @click="emit('select')"
      >
        <span class="grid h-11 w-11 place-items-center rounded-xl bg-white/[0.05]">
          <ImagePlus :size="21" aria-hidden="true" />
        </span>
        <span class="text-sm font-medium">{{ selectLabel }}</span>
      </button>
    </div>

    <p
      v-if="error"
      :id="errorId"
      :class="compact ? 'sr-only' : 'mt-2 text-sm text-danger'"
      role="alert"
    >
      {{ error }}
    </p>
  </fieldset>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { ImagePlus, Plus, X } from 'lucide-vue-next';
import { hasSeedreamImageDrag, readSeedreamImageDrag, type SeedreamImageDragPayload } from '@/seedream-image-drag';

const props = withDefaults(defineProps<{
  modelValue: string | null;
  previewUrl: string;
  label: string;
  required?: boolean;
  help: string;
  helpId: string;
  error?: string;
  errorId?: string;
  selectLabel: string;
  changeLabel: string;
  editLabel?: string;
  removeLabel: string;
  selectedLabel: string;
  cardLabel?: string;
  optionalLabel?: string;
  dropLabel?: string;
  compact?: boolean;
}>(), {
  required: false,
  error: '',
  errorId: '',
  editLabel: '',
  cardLabel: '',
  optionalLabel: '',
  dropLabel: '',
  compact: false,
});

const emit = defineEmits<{
  select: [];
  edit: [];
  clear: [];
  'drop-image': [payload: SeedreamImageDragPayload];
}>();

const dragActive = ref(false);
const fileName = computed(() => props.modelValue?.split(/[\\/]/).pop() ?? '');
const describedBy = computed(() => (
  props.error && props.errorId ? `${props.helpId} ${props.errorId}` : props.helpId
));

function openSelectedImage() {
  if (props.editLabel) emit('edit');
  else emit('select');
}

function onDragEnter(event: DragEvent) {
  if (!hasSeedreamImageDrag(event.dataTransfer)) return;
  event.preventDefault();
  dragActive.value = true;
}

function onDragOver(event: DragEvent) {
  if (!hasSeedreamImageDrag(event.dataTransfer)) return;
  event.preventDefault();
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy';
  dragActive.value = true;
}

function onDragLeave(event: DragEvent) {
  const fieldset = event.currentTarget as HTMLElement | null;
  const nextTarget = event.relatedTarget as Node | null;
  if (fieldset && nextTarget && fieldset.contains(nextTarget)) return;
  dragActive.value = false;
}

function onDrop(event: DragEvent) {
  const payload = readSeedreamImageDrag(event.dataTransfer);
  if (!payload) return;
  event.preventDefault();
  dragActive.value = false;
  emit('drop-image', payload);
}
</script>
