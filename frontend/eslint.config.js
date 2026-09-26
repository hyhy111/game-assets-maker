import pluginVue from 'eslint-plugin-vue'
import tseslint from '@vue/eslint-config-typescript'

export default [
  ...pluginVue.configs['flat/recommended'],
  ...tseslint(),
  {
    files: ['**/*.{ts,vue}'],
    rules: {
      'vue/multi-word-component-names': 'off',
      'vue/require-default-prop': 'off',
      '@typescript-eslint/no-unused-vars': 'warn',
      '@typescript-eslint/no-explicit-any': 'warn',
      'no-console': 'warn',
      'eqeqeq': ['error', 'always'],
      'prefer-const': 'error',
      'no-var': 'error',
    }
  }
]
