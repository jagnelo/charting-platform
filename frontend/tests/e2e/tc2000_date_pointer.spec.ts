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
  await expect(chart).toBeFocused()
  await expect(chart.locator('.ohlcv-info')).toBeVisible()

  const savedOffMode = page.waitForResponse(response => {
    const request = response.request()
    if (!response.url().includes('/workspaces/') || !response.url().endsWith('/snapshot') || request.method() !== 'PUT') return false
    try {
      const payload = request.postDataJSON() as { tabs?: Array<{ windows?: Array<{ instance_key: string; configuration?: Record<string, unknown> }> }> }
      const chartWindow = payload.tabs?.flatMap(tab => tab.windows ?? []).find(window => window.instance_key === 'primary-chart')
      return chartWindow?.configuration?.date_pointer_mode === 'off'
    } catch {
      return false
    }
  })
  await page.keyboard.press('.')
  await expect(chart).toHaveAttribute('data-date-pointer-mode', 'off')
  await savedOffMode
  await page.reload()
  const reloadedChart = page.locator('.chart-tool .chart-root').first()
  await expect(reloadedChart).toBeVisible()
  await expect(reloadedChart).toHaveAttribute('data-date-pointer-mode', 'off')
  await browserDiagnostics.expectNoCriticalIssues()
})
