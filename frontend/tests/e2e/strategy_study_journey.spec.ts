import { test, expect } from './helpers'

test('Study journey keeps completed output identity separate and refreshes Results automatically', async ({ page, loggedIn, browserDiagnostics }) => {
  test.setTimeout(150_000)
  await page.goto('/chart')
  await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: 'Study', exact: true }).click()

  const addTool = page.getByRole('button', { name: 'Add tool', exact: true })
  await addTool.click()
  await page.getByRole('menu', { name: 'Workstation tools' }).getByRole('menuitem', { name: 'Study Results', exact: true }).click()
  const results = page.locator('.research-results-tool:visible').last()
  await expect(results).toBeVisible({ timeout: 15_000 })
  await expect(results.getByRole('list', { name: 'Persisted research runs' })).toBeVisible()

  const study = page.locator('.study-lab-tool:visible').last()
  await expect(study).toBeVisible({ timeout: 15_000 })
  await study.getByRole('combobox', { name: 'Factory study' }).selectOption('positive_streak')
  await study.getByRole('textbox', { name: 'Study name' }).fill(`Study journey ${Date.now()}`)
  await study.getByRole('textbox', { name: 'Study symbol' }).fill('SPY')
  const preparationResponse = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/data/ensure'))
  await study.getByRole('button', { name: 'Validate study' }).click()
  const prepared = await preparationResponse
  expect(prepared.ok()).toBe(true)
  expect(prepared.request().postDataJSON()).toMatchObject({
    target: { kind: 'instrument', symbol: 'SPY' },
    datasets: ['history'],
    timeframe: 'D1',
    adjusted: true,
  })
  await expect(study.getByRole('status', { name: 'Study data preparation' })).toContainText('ready', { timeout: 90_000 })
  await expect(study).toContainText('Validated for isolated execution', { timeout: 15_000 })
  await study.getByRole('button', { name: 'Run study', exact: true }).click()
  await expect(study.locator('.study-lab-tool__run-status--completed')).toBeVisible({ timeout: 90_000 })

  const runLabel = await study.locator('.study-lab-tool__run > div > strong').innerText()
  const runId = runLabel.match(/Run #(\d+)/)?.[1]
  expect(runId).toBeTruthy()
  await expect(study.getByRole('status', { name: 'Saved run dataset' })).toContainText(`Saved run #${runId} dataset: symbol SPY`)
  await expect(results.getByRole('button', { name: `Run ${runId}, completed, 8 artifacts` })).toBeVisible({ timeout: 15_000 })

  await study.getByRole('textbox', { name: 'Study symbol' }).fill('XLB')
  await study.getByRole('button', { name: 'Validate study' }).click()
  await expect(study).toContainText('Validated for isolated execution', { timeout: 15_000 })
  await expect(study.locator('.study-lab-tool__dataset-summary')).toContainText('Current draft dataset: XLB')
  await expect(study.getByRole('status', { name: 'Saved run dataset' })).toContainText(`Saved run #${runId} dataset: symbol SPY`)
  await expect(study.locator('.study-lab-tool__metrics article').filter({ hasText: 'current_streak' })).toBeVisible()
  await browserDiagnostics.expectNoCriticalIssues()
})
