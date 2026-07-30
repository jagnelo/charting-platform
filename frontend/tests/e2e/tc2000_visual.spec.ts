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
    await expect(page).toHaveScreenshot('application-shell-default.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
    browserDiagnostics.expectNoCriticalIssues()
  })
})
