import { type Page } from '@playwright/test'
import { test, expect } from './helpers'

async function closePopupWhenOpen(popup: Page) {
  if (popup.isClosed()) return
  const closed = popup.waitForEvent('close', { timeout: 10_000 }).catch((error: unknown) => {
    if (!popup.isClosed()) throw error
  })
  try {
    await popup.locator('button[title="Close"]').click()
  } catch (error) {
    // Golden Layout can close a sibling popup while it reconciles the source
    // workspace. Treat that narrow teardown race as already closed; the caller
    // still asserts that the browser context converges to one page.
    if (!popup.isClosed()) throw error
  }
  await closed
}

test.describe('TC2000 workstation performance guards', () => {
  test('initializes multiple chart windows and recovers without canvas or tool growth', async ({ page, context, loggedIn, browserDiagnostics }) => {
    await page.goto('/chart')
    await expect(page.locator('.tool-window').first()).toBeVisible({ timeout: 10_000 })
    await expect.poll(() => page.locator('canvas').count(), { timeout: 10_000 }).toBeGreaterThan(0)
    // Chart panes can add their volume/indicator canvases after the primary
    // canvas appears. Settle the one-time initialization before recording the
    // source baseline used by the pop-out recovery assertion.
    const settledCanvasCount = async () => {
      let previous = -1
      let stableSamples = 0
      for (let sample = 0; sample < 20; sample += 1) {
        const current = await page.locator('canvas').count()
        stableSamples = current === previous ? stableSamples + 1 : 0
        previous = current
        if (stableSamples >= 3) return current
        await page.waitForTimeout(250)
      }
      return previous
    }
    await page.waitForTimeout(1_000)
    // The factory mounts ratio and relative-rotation surfaces even when they
    // are hidden behind another Golden Layout tab. Their local data requests
    // can finish after the primary chart's first canvas appears; wait for
    // those explicit readiness states before recording the exact canvas
    // baseline, otherwise a legitimate late renderer looks like a leak.
    const ratioTools = page.locator('.ratio-chart')
    if (await ratioTools.count()) {
      await expect.poll(() => page.locator('.ratio-chart[aria-busy="false"]').count(), { timeout: 30_000 }).toBe(await ratioTools.count())
    }
    const rotationTools = page.locator('.rotation-tool')
    if (await rotationTools.count()) {
      await expect.poll(() => page.locator('.rotation-tool[aria-busy="false"]').count(), { timeout: 30_000 }).toBe(await rotationTools.count())
    }
    const sourceToolCount = await page.locator('.tool-window').count()
    const sourceCanvasCount = await settledCanvasCount()
    const started = await page.evaluate(() => performance.now())
    const popups = []

    for (let index = 0; index < 2; index += 1) {
      const floatButton = page.locator('button[title="Float"]').nth(index)
      await expect(floatButton).toBeVisible({ timeout: 10_000 })
      const popupPromise = context.waitForEvent('page')
      await floatButton.click()
      const popup = await popupPromise
      popups.push(popup)
      await popup.waitForLoadState('domcontentloaded')
      await expect(popup.locator('.workstation__popout .tool-window')).toBeVisible({ timeout: 10_000 })
      if (await popup.locator('.chart-tool').count()) {
        await expect.poll(() => popup.locator('canvas').count(), { timeout: 10_000 }).toBeGreaterThan(0)
      }
    }

    await expect.poll(() => context.pages().length).toBe(3)
    const activeSymbolInput = page.locator('input[aria-label="Active symbol"]')
    await activeSymbolInput.fill('XLB')
    await page.getByRole('button', { name: 'Go', exact: true }).click()
    await expect(activeSymbolInput).toHaveValue('XLB')
    await expect(page.locator('.workstation__footer')).toContainText('XLB')
    for (const popup of popups) {
      await expect.poll(() => popup.locator('.tool-window__symbol').allTextContents()).toContain('XLB')
    }
    await expect.poll(() => page.locator('.tool-window').count()).toBe(sourceToolCount)

    for (const popup of popups) {
      await closePopupWhenOpen(popup)
    }
    await expect.poll(() => context.pages().length).toBe(1)
    await expect(page.locator('.tool-window')).toHaveCount(sourceToolCount)
    // Popup teardown can dispose chart panes asynchronously. Give the browser
    // a bounded cleanup window, while retaining the exact baseline assertion so
    // a genuine canvas leak still fails the performance gate.
    await expect.poll(() => page.locator('canvas').count(), {
      timeout: 15_000,
      intervals: [250, 500, 1_000],
    }).toBe(sourceCanvasCount)
    const elapsed = await page.evaluate((start) => performance.now() - start, started)
    expect(elapsed).toBeLessThan(20_000)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('repeated multi-window churn keeps the source workspace bounded', async ({ page, context, loggedIn, browserDiagnostics }) => {
    // Long lifecycle acceptance runs must not fail at Playwright's 30-second default
    // before all configured browser-window cycles can complete.
    const configuredRounds = Number(process.env.TC2000_POP_OUT_CHURN_ROUNDS ?? 5)
    const requestedRounds = Number.isInteger(configuredRounds) && configuredRounds > 0 ? configuredRounds : 5
    // Keep the soak bounded for CI while allowing an explicitly requested
    // long run to exercise substantially more lifecycle churn than the normal
    // smoke/default setting. Indefinite endurance remains a separate gate.
    test.setTimeout(Math.max(60_000, Math.min(requestedRounds, 500) * 2_500 + 120_000))
    await page.goto('/chart')
    await expect(page.locator('.tool-window').first()).toBeVisible({ timeout: 10_000 })
    await expect.poll(() => page.locator('canvas').count(), { timeout: 10_000 }).toBeGreaterThan(0)
    // Establish a settled baseline before exercising repeated browser-window churn.
    const settledCanvasCount = async () => {
      let previous = -1
      let stableSamples = 0
      for (let sample = 0; sample < 20; sample += 1) {
        const current = await page.locator('canvas').count()
        stableSamples = current === previous ? stableSamples + 1 : 0
        previous = current
        if (stableSamples >= 3) return current
        await page.waitForTimeout(250)
      }
      return previous
    }
    await page.waitForTimeout(1_000)
    const ratioTools = page.locator('.ratio-chart')
    if (await ratioTools.count()) {
      await expect.poll(() => page.locator('.ratio-chart[aria-busy="false"]').count(), { timeout: 30_000 }).toBe(await ratioTools.count())
    }
    const rotationTools = page.locator('.rotation-tool')
    if (await rotationTools.count()) {
      await expect.poll(() => page.locator('.rotation-tool[aria-busy="false"]').count(), { timeout: 30_000 }).toBe(await rotationTools.count())
    }
    const sourceToolCount = await page.locator('.tool-window').count()
    const sourceCanvasCount = await settledCanvasCount()
    const sourceChartCount = await page.locator('.chart-tool').count()
    // Keep an explicit upper bound so CI cannot accidentally become unbounded, but allow
    // the acceptance job to exercise a genuine long-duration lifecycle soak rather than
    // silently truncating every run to the short default smoke limit.
    const rounds = Number.isInteger(configuredRounds) && configuredRounds > 0
      ? Math.min(configuredRounds, 500)
      : 5
    const memorySamples: number[] = []
    const readHeap = async () => page.evaluate(() => {
      const performanceWithMemory = performance as Performance & { memory?: { usedJSHeapSize: number } }
      return performanceWithMemory.memory?.usedJSHeapSize ?? null
    })
    const initialMemory = await readHeap()
    if (initialMemory != null) memorySamples.push(initialMemory)

    for (let round = 0; round < rounds; round += 1) {
      const popups = []
      for (let index = 0; index < 2; index += 1) {
        const floatButton = page.locator('button[title="Float"]').nth(index)
        await expect(floatButton).toBeVisible({ timeout: 10_000 })
        const popupPromise = context.waitForEvent('page')
        await floatButton.click()
        const popup = await popupPromise
        popups.push(popup)
        await popup.waitForLoadState('domcontentloaded')
        await expect(popup.locator('.workstation__popout .tool-window')).toBeVisible({ timeout: 10_000 })
      }

      await expect.poll(() => context.pages().length).toBe(3)
      for (const popup of popups) {
        await closePopupWhenOpen(popup)
      }
      await expect.poll(() => context.pages().length).toBe(1)
      await expect(page.locator('.tool-window')).toHaveCount(sourceToolCount)
      // Cleanup is asynchronous, but must converge back to the original
      // canvas count within a bounded interval after every churn round.
      await expect.poll(() => page.locator('canvas').count(), {
        timeout: 15_000,
        intervals: [250, 500, 1_000],
      }).toBe(sourceCanvasCount)
      await expect(page.locator('.chart-tool')).toHaveCount(sourceChartCount)
      const currentMemory = await readHeap()
      if (currentMemory != null) memorySamples.push(currentMemory)
    }

    // Chromium does not expose performance.memory in every environment; when it does,
    // reject unbounded churn without making the guard browser-engine dependent. The
    // absolute ceiling catches catastrophic growth; the relative ceiling catches a
    // leak that remains below the ceiling during a short run.
    if (memorySamples.length) {
      expect(Math.max(...memorySamples)).toBeLessThan(512 * 1024 * 1024)
      expect(Math.max(...memorySamples) - memorySamples[0]).toBeLessThan(256 * 1024 * 1024)
    }
    await browserDiagnostics.expectNoCriticalIssues()
  })
})
