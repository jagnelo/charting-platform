import { test, expect } from './helpers'

function workspaceSnapshotHasBarType(response: import('@playwright/test').Response, barType: string) {
  if (!response.url().includes('/workspaces/') || !response.url().endsWith('/snapshot') || response.request().method() !== 'PUT') return false
  try {
    const payload = response.request().postDataJSON() as {
      tabs?: Array<{ windows?: Array<{ instance_key: string; configuration?: Record<string, unknown> }> }>
    }
    const chart = payload.tabs?.flatMap(tab => tab.windows ?? []).find(window => window.instance_key === 'primary-chart')
    return chart?.configuration?.bar_type === barType
  } catch {
    return false
  }
}

test('TC2000 function key loads its assigned chart template on the active chart', async ({ page, loggedIn, browserDiagnostics }) => {
  await page.goto('/chart')
  const chart = page.locator('.chart-tool .chart-root').first()
  await expect(chart).toBeVisible()

  await page.getByRole('button', { name: 'Chart templates' }).first().click()
  const templates = page.getByRole('dialog', { name: 'Chart templates panel' })
  await templates.getByLabel('Chart bar type').selectOption('line')
  await templates.getByLabel('Chart template name').fill('F5 line template')
  await templates.getByRole('button', { name: 'Save', exact: true }).click()
  const template = templates.getByRole('button', { name: 'F5 line template v1', exact: true })
  await expect(template).toBeVisible()

  const savedCandles = page.waitForResponse(response => workspaceSnapshotHasBarType(response, 'candles'))
  await templates.getByLabel('Chart bar type').selectOption('candles')
  await savedCandles

  const assignmentSaved = page.waitForResponse(response => response.url().includes('/workspaces/library/items/chart_template/')
    && response.request().method() === 'PUT'
    && response.request().postDataJSON()?.payload?.function_key === 'F5')
  await templates.getByLabel('Function key for F5 line template').selectOption('F5')
  await assignmentSaved
  await templates.getByRole('button', { name: 'Close chart templates' }).click()

  const savedLineTemplate = page.waitForResponse(response => workspaceSnapshotHasBarType(response, 'line'))
  await chart.click()
  await page.keyboard.press('F5')
  await savedLineTemplate
  await browserDiagnostics.expectNoCriticalIssues()
})
