import { test, expect } from './helpers'

test('TC2000 date pointer shortcut cycles the active chart through all display modes', async ({ page, loggedIn, browserDiagnostics }) => {
  await page.goto('/chart')
  const chart = page.locator('.chart-tool .chart-root').first()
  await expect(chart).toBeVisible()
  await expect(chart).toHaveAttribute('data-date-pointer-mode', 'on_with_values')

  await chart.click()
  await page.keyboard.press('.')
  await expect(chart).toHaveAttribute('data-date-pointer-mode', 'off')
  await expect(chart).toBeFocused()
  await expect(chart.locator('.ohlcv-info')).toHaveCount(0)

  await page.keyboard.press('.')
  await expect(chart).toHaveAttribute('data-date-pointer-mode', 'on')
  await expect(chart).toBeFocused()
  await expect(chart.locator('.ohlcv-info')).toHaveCount(0)

  await page.keyboard.press('.')
  await expect(chart).toHaveAttribute('data-date-pointer-mode', 'on_with_values')
  await expect(chart.locator('.ohlcv-info')).toBeVisible()
  await browserDiagnostics.expectNoCriticalIssues()
})
