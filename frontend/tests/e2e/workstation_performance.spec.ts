import { test, expect } from './helpers'

test.describe('TC2000 workstation performance guards', () => {
  test('initializes multiple chart windows and recovers without canvas or tool growth', async ({ page, context, loggedIn, browserDiagnostics }) => {
    await page.goto('/chart')
    await expect(page.locator('.tool-window').first()).toBeVisible({ timeout: 10_000 })
    await expect.poll(() => page.locator('canvas').count(), { timeout: 10_000 }).toBeGreaterThan(0)
    // Chart panes can add their volume/indicator canvases after the primary
    // canvas appears. Settle the one-time initialization before recording the
    // source baseline used by the pop-out recovery assertion.
    await page.waitForTimeout(2_000)
    const sourceToolCount = await page.locator('.tool-window').count()
    const sourceCanvasCount = await page.locator('canvas').count()
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
    await expect.poll(() => page.locator('canvas').count()).toBe(sourceCanvasCount)
    const elapsed = await page.evaluate((start) => performance.now() - start, started)
    expect(elapsed).toBeLessThan(20_000)
    await browserDiagnostics.expectNoCriticalIssues()
  })
})
