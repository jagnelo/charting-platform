import { test, expect } from './helpers'

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
      const closed = popup.waitForEvent('close')
      await popup.locator('button[title="Close"]').click()
      await closed
    }
    await expect.poll(() => context.pages().length).toBe(1)
    await expect(page.locator('.tool-window')).toHaveCount(sourceToolCount)
    await expect.poll(() => settledCanvasCount()).toBe(sourceCanvasCount)
    const elapsed = await page.evaluate((start) => performance.now() - start, started)
    expect(elapsed).toBeLessThan(20_000)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('repeated multi-window churn keeps the source workspace bounded', async ({ page, context, loggedIn, browserDiagnostics }) => {
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
    const sourceToolCount = await page.locator('.tool-window').count()
    const sourceCanvasCount = await settledCanvasCount()
    const sourceChartCount = await page.locator('.chart-tool').count()
    const rounds = 5

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
        const closed = popup.waitForEvent('close')
        await popup.locator('button[title="Close"]').click()
        await closed
      }
      await expect.poll(() => context.pages().length).toBe(1)
      await expect(page.locator('.tool-window')).toHaveCount(sourceToolCount)
      await expect.poll(() => settledCanvasCount()).toBe(sourceCanvasCount)
      await expect(page.locator('.chart-tool')).toHaveCount(sourceChartCount)
    }

    const memory = await page.evaluate(() => {
      const performanceWithMemory = performance as Performance & { memory?: { usedJSHeapSize: number } }
      return performanceWithMemory.memory?.usedJSHeapSize ?? null
    })
    // Chromium does not expose performance.memory in every environment; when it does,
    // reject unbounded churn without making the guard browser-engine dependent.
    if (memory != null) expect(memory).toBeLessThan(512 * 1024 * 1024)
    await browserDiagnostics.expectNoCriticalIssues()
  })
})
