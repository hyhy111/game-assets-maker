import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// https://vitejs.dev/config/
const channelCode = process.env.GAM_BUILD_CHANNEL_CODE ?? '';
if (channelCode.length > 64 || /[\x00-\x1f\x7f]/.test(channelCode)) {
  throw new Error('Channel code must contain at most 64 characters and no control characters');
}

export default defineConfig({
  define: { __GAM_CHANNEL_CODE__: JSON.stringify(channelCode) },
  plugins: [vue(), {
    name: 'gam-channel-manifest',
    generateBundle() {
      this.emitFile({ type: 'asset', fileName: 'channel-code.json', source: JSON.stringify({ channelCode }) });
    },
  }],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    hmr: true,
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor': ['vue', 'pinia', 'vue-router'],
        },
      },
    },
  },
})
