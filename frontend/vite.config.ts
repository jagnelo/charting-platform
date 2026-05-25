import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,  // proxies ws://localhost:5173/api/... → ws://localhost:8000/api/...
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('/vue') || id.includes('/pinia') || id.includes('/vue-router')) {
            return 'vendor-vue'
          }
          if (id.includes('/uplot')) return 'vendor-charting'
          if (id.includes('/axios')) return 'vendor-network'
          return 'vendor'
        },
      },
    },
  },
})
