import { defineConfig, devices } from '@playwright/test'

/**
 * E2E tests run against the full Docker Compose stack.
 * Set STACK_URL to the running frontend URL (default: http://localhost:4173).
 * Set TEST_USER / TEST_PASS for the test account (created if it doesn't exist).
 *
 * Run:
 *   docker compose up -d
 *   npx playwright test                        # all E2E tests
 *   npx playwright test --headed               # watch mode
 *   npx playwright test tests/e2e/auth.spec.ts # single file
 */
export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,       // run serially — tests share DB state
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  timeout: 30_000,
  reporter: [['html', { outputFolder: 'playwright-report' }], ['line']],
  use: {
    baseURL: process.env.STACK_URL ?? 'http://localhost:4173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
