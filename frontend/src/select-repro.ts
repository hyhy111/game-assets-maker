import { createApp, h, ref } from 'vue';
import Select from './components/common/Select.vue';

createApp({
  setup() {
    const value = ref('one');
    return () => h('main', [
      // Matches the settings page: the select is wrapped in a <label>, which
      // used to re-open the dropdown right after an option was chosen.
      h('label', [
        'Test setting',
        h(Select, {
          modelValue: value.value,
          'onUpdate:modelValue': (nextValue: string | number) => { value.value = String(nextValue); },
          ariaLabel: 'Test setting',
          options: [{ value: 'one', label: 'One' }, { value: 'two', label: 'Two' }],
        }),
      ]),
      h('output', value.value),
    ]);
  },
}).mount('#app');
