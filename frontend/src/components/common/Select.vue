<template>
  <Listbox v-model="selectedValue">
    <div class="relative">
      <!--
        Consumers wrap this select in a <label>. A label forwards clicks on
        non-interactive content to its labelable control (the button), which
        would toggle the listbox a second time: the button click would never
        open it, and an option click would re-open it right after Headless UI
        closed it. preventDefault on both click paths suppresses the label's
        activation behavior while Headless UI's own listeners still run.
      -->
      <ListboxButton
        class="flex h-[42px] w-full items-center justify-between rounded-lg border border-dark-border bg-dark-bg px-3 text-sm text-white cursor-pointer focus:outline-none focus:border-primary"
        :aria-label="ariaLabel"
        :data-test="dataTest"
        @click.prevent
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
          @click.prevent
        >
          <ListboxOption
            v-for="option in options"
            :key="option.value"
            v-slot="{ active, selected }"
            :value="option.value"
            as="template"
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
  value: string | number;
  label: string;
}

const props = defineProps<{
  modelValue: string | number;
  options: Option[];
  placeholder?: string;
  ariaLabel?: string;
  dataTest?: string;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: string | number): void;
}>();

const selectedValue = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
});

const displayLabel = computed(() => {
  const option = props.options.find(o => o.value === props.modelValue);
  return option?.label || props.placeholder || String(props.modelValue);
});
</script>
