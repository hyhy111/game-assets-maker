<template>
  <Listbox v-model="selectedValue">
    <div class="relative">
      <ListboxButton
        class="w-full px-3 py-2 bg-dark-bg border border-dark-border rounded-lg text-sm text-white focus:outline-none focus:border-primary cursor-pointer flex justify-between items-center"
      >
        <span>{{ displayLabel }}</span>
        <ChevronDown class="w-4 h-4 text-gray-400" />
      </ListboxButton>

      <transition
        enter-active-class="transition duration-100 ease-out"
        enter-from-class="transform scale-95 opacity-0"
        enter-to-class="transform scale-100 opacity-100"
        leave-active-class="transition duration-75 ease-in"
        leave-from-class="transform scale-100 opacity-100"
        leave-to-class="transform scale-95 opacity-0"
      >
        <ListboxOptions
          class="absolute z-50 w-full mt-1 py-1 bg-dark-surface border border-dark-border rounded-lg shadow-lg max-h-60 overflow-auto"
        >
          <ListboxOption
            v-for="option in options"
            :key="option.value"
            v-slot="{ active, selected }"
            :value="option.value"
          >
            <li
              :class="[
                'px-3 py-2 text-sm cursor-pointer',
                active ? 'bg-primary/20 text-white' : 'text-gray-300',
                selected ? 'text-primary font-medium' : ''
              ]"
            >
              {{ option.label }}
            </li>
          </ListboxOption>
        </ListboxOptions>
      </transition>
    </div>
  </Listbox>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { Listbox, ListboxButton, ListboxOptions, ListboxOption } from '@headlessui/vue';
import { ChevronDown } from 'lucide-vue-next';

interface Option {
  value: string;
  label: string;
}

const props = defineProps<{
  modelValue: string;
  options: Option[];
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void;
}>();

const selectedValue = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
});

const displayLabel = computed(() => {
  const option = props.options.find(o => o.value === props.modelValue);
  return option?.label || props.modelValue;
});
</script>
