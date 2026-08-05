/**
 * Approved-reference visual parity only. The npm command gates this suite through
 * the backend manifest validator before Playwright can create or compare a baseline.
 */
import { test, expect } from './helpers'

test.describe('TC2000 Version 25 approved visual parity', () => {
  test.skip(process.env.RUN_APPROVED_VISUAL_PARITY !== '1', 'requires approved protected V25 references')

  test('application shell default US Top Down workspace', async ({ page, loggedIn, browserDiagnostics }) => {
    await page.goto('/')
    await expect(page.locator('.workstation')).toBeVisible()
    await expect(page.locator('.workstation__menu')).toBeVisible()
    await expect(page.locator('.workstation__tabs')).toBeVisible()
    await expect(page.locator('canvas').first()).toBeVisible()
    // Do not capture the transient first-render state. The saved layout must be
    // present before visual comparison, and the expected unavailable-data 404s
    // must have reached the diagnostics classifier before it inspects the page.
    await expect(page.locator('.workstation__layout-state')).toHaveCount(0)
    await page.waitForTimeout(250)
    const overlapIssues = await page.evaluate(() => {
      const rect = (element: Element | null) => {
        if (!element) return null
        const box = element.getBoundingClientRect()
        return { left: box.left, right: box.right, top: box.top, bottom: box.bottom }
      }
      const overlaps = (left: ReturnType<typeof rect>, right: ReturnType<typeof rect>) => Boolean(
        left && right && left.left < right.right && left.right > right.left && left.top < right.bottom && left.bottom > right.top,
      )
      const issues: string[] = []
      document.querySelectorAll('.tool-window__header').forEach((header, index) => {
        if (overlaps(rect(header.querySelector('.tool-window__title')), rect(header.querySelector('.tool-window__actions')))) {
          issues.push(`header-${index}-title-actions`)
        }
        if (overlaps(rect(header.querySelector('.tool-window__symbol')), rect(header.querySelector('.tool-window__actions')))) {
          issues.push(`header-${index}-symbol-actions`)
        }
      })
      document.querySelectorAll('.chart-tool').forEach((chart, index) => {
        const toolbar = rect(chart.querySelector('.chart-tool__drawing-toolbar'))
        const surface = rect(chart.querySelector('.chart-tool__surface'))
        if (toolbar && surface && toolbar.right > surface.left) issues.push(`chart-${index}-toolbar-surface`)
      })
      return issues
    })
    expect(overlapIssues).toEqual([])
    await expect(page).toHaveScreenshot('application-shell-default.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
    await browserDiagnostics.expectNoCriticalIssues()
  })
})
