import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./tests/unit/setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      exclude: [
        'node_modules/**',
        'tests/**',
        'src/main.ts',
        'src/router/**',
        '**/*.d.ts',
      ],
      thresholds: {
        lines:      70,
        functions:  70,
        branches:   65,
        statements: 70,
      },
    },
    include: ['tests/unit/**/*.{test,spec}.ts'],
  },
})
