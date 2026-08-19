import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      // golden-layout 2.6.0 currently publishes TypeScript source without its
      // advertised dist directory. Vite compiles the verified source entry.
      'golden-layout': fileURLToPath(new URL('./node_modules/golden-layout/src/index.ts', import.meta.url)),
    },
  },
  server: {
    host: '0.0.0.0',
    port: Number(process.env.VITE_PORT ?? 5173),
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
        ws: true,  // proxies ws://localhost:5173/api/... → ws://localhost:8000/api/...
      },
      '/health': {
        target: apiProxyTarget,
        changeOrigin: true,
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
