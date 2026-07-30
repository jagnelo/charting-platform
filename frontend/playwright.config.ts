import { defineConfig, devices } from '@playwright/test'

/**
 * E2E tests run against the full Docker Compose stack.
 * Set STACK_URL to the running frontend URL (default: http://localhost).
 * Set TEST_USER / TEST_PASS for the test account (created if it doesn't exist).
 *
 * Run:
 *   make test-stack-up
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
    baseURL: process.env.STACK_URL ?? 'http://localhost',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      testIgnore: /tc2000_visual\.spec\.ts/,
      use: { ...devices['Desktop Chrome'] },
    },
    ...[
      ['visual-1080p-100', 1920, 1080, 1],
      ['visual-1080p-125', 1920, 1080, 1.25],
      ['visual-1440p-100', 2560, 1440, 1],
      ['visual-1440p-125', 2560, 1440, 1.25],
    ].map(([name, width, height, deviceScaleFactor]) => ({
      name: name as string,
      testMatch: /tc2000_visual\.spec\.ts/,
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: width as number, height: height as number },
        deviceScaleFactor: deviceScaleFactor as number,
        locale: 'en-US',
        timezoneId: 'UTC',
        colorScheme: 'dark' as const,
      },
    })),
  ],
})
