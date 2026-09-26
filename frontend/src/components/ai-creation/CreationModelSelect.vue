<template>
  <Listbox
    v-slot="{ open }"
    v-model="selectedValue"
  >
    <div class="relative">
      <ListboxButton
        class="flex h-10 items-center gap-2 rounded-xl border border-[#414141] bg-[#2d2d2d] px-3 text-sm text-gray-200 transition-colors hover:border-[#555] hover:bg-[#353535] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        :aria-label="label"
        :data-test="testId"
      >
        <Sparkles
          :size="15"
          class="text-gray-400"
          aria-hidden="true"
        />
        <span class="whitespace-nowrap">{{ selectedLabel }}</span>
        <ChevronDown
          :size="14"
          class="text-[#777] transition-transform"
          :class="open ? 'rotate-180' : ''"
          aria-hidden="true"
        />
      </ListboxButton>

      <Transition
        enter-active-class="transition duration-100 ease-out"
        enter-from-class="scale-95 opacity-0"
        enter-to-class="scale-100 opacity-100"
        leave-active-class="transition duration-75 ease-in"
        leave-from-class="scale-100 opacity-100"
        leave-to-class="scale-95 opacity-0"
      >
        <ListboxOptions
          class="absolute left-0 top-full z-40 mt-2 min-w-full overflow-hidden rounded-xl border border-[#3b3b3b] bg-[#1f1f1f] p-1 shadow-2xl shadow-black/50 focus:outline-none"
        >
          <ListboxOption
            v-for="option in options"
            :key="option.value"
            v-slot="{ active, selected }"
            as="template"
            :value="option.value"
          >
            <li
              class="flex cursor-pointer items-center justify-between gap-4 rounded-lg px-3 py-2 text-sm whitespace-nowrap"
              :class="selected
                ? 'bg-primary/20 text-primary-200'
                : active
                  ? 'bg-[#303030] text-white'
                  : 'text-gray-400'"
            >
              <span>{{ option.label }}</span>
              <Check
                v-if="selected"
                :size="14"
                class="text-primary-200"
                aria-hidden="true"
              />
            </li>
          </ListboxOption>
        </ListboxOptions>
      </Transition>
    </div>
  </Listbox>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { Listbox, ListboxButton, ListboxOption, ListboxOptions } from '@headlessui/vue';
import { Check, ChevronDown, Sparkles } from 'lucide-vue-next';

interface ModelOption {
  value: string;
  label: string;
}

const props = defineProps<{
  modelValue: string;
  options: ModelOption[];
  label: string;
  testId: string;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: string];
}>();

const selectedValue = computed({
  get: () => props.modelValue,
  set: (value: string) => emit('update:modelValue', value),
});

const selectedLabel = computed(() => (
  props.options.find(option => option.value === props.modelValue)?.label ?? props.modelValue
));
</script>
