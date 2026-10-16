import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('@playwright/test', () => ({
  defineConfig: (configuration: unknown) => configuration,
  devices: { 'Desktop Chrome': {} },
}))

afterEach(() => { vi.unstubAllEnvs(); vi.resetModules() })

describe('Playwright flaky-test acceptance gate', () => {
  it('fails CI on retry-passing tests while retaining the diagnostic retry', async () => {
    vi.stubEnv('CI', 'true')
    vi.resetModules()
    const { default: configuration } = await import('../../../playwright.config')
    expect(configuration.failOnFlakyTests).toBe(true)
    expect(configuration.retries).toBe(1)
    expect(configuration.forbidOnly).toBe(true)
    expect(configuration.projects).toHaveLength(5)
  })

  it('keeps local default retries and the existing complete project selection', async () => {
    vi.stubEnv('CI', '')
    vi.resetModules()
    const { default: configuration } = await import('../../../playwright.config')
    expect(configuration.retries).toBe(0)
    expect(configuration.projects?.map(project => project.name)).toEqual([
      'chromium', 'visual-1080p-100', 'visual-1080p-125', 'visual-1440p-100', 'visual-1440p-125',
    ])
  })
})
