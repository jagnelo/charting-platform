import { test, expect } from './helpers'

test('Study journey keeps saved identity, refreshes Results, and returns from Python Library on the immutable version', async ({ page, loggedIn, browserDiagnostics }) => {
  test.setTimeout(150_000)
  const studyName = `Study journey ${Date.now()}`
  const runRequests: Array<{ code_version_id?: number }> = []
  let codeAssetCreations = 0
  page.on('request', request => {
    if (request.method() !== 'POST') return
    const pathname = new URL(request.url()).pathname
    if (pathname.endsWith('/research/runs')) runRequests.push(request.postDataJSON() as { code_version_id?: number })
    if (pathname.endsWith('/code/assets')) codeAssetCreations += 1
  })
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
  await study.getByRole('textbox', { name: 'Study name' }).fill(studyName)
  await study.getByRole('textbox', { name: 'Study symbol' }).fill('SPY')
  const immutableSource = await study.getByRole('textbox', { name: 'Study Python source' }).inputValue()
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
  const firstRunRequest = page.waitForRequest(request => request.method() === 'POST' && new URL(request.url()).pathname.endsWith('/research/runs'))
  await study.getByRole('button', { name: 'Run study', exact: true }).click()
  const firstRunBody = (await firstRunRequest).postDataJSON() as { code_version_id?: number }
  expect(Number.isInteger(firstRunBody.code_version_id)).toBe(true)
  expect(codeAssetCreations).toBe(1)
  await expect(study.locator('.study-lab-tool__run-status--completed')).toBeVisible({ timeout: 90_000 })

  const runLabel = await study.locator('.study-lab-tool__run > div > strong').innerText()
  const runId = runLabel.match(/Run #(\d+)/)?.[1]
  expect(runId).toBeTruthy()
  await expect(study.getByRole('status', { name: 'Saved run dataset' })).toContainText(`Saved run #${runId} dataset: symbol SPY`)
  await expect(results.getByRole('button', { name: `Run ${runId}, completed, 8 artifacts` })).toBeVisible({ timeout: 15_000 })

  const savedDraft = page.waitForResponse(response => response.request().method() === 'PUT' && new URL(response.url()).pathname.endsWith('/snapshot'))
  await study.getByRole('textbox', { name: 'Study symbol' }).fill('XLB')
  expect((await savedDraft).ok()).toBe(true)
  await study.getByRole('button', { name: 'Validate study' }).click()
  await expect(study).toContainText('Validated for isolated execution', { timeout: 15_000 })
  await expect(study.locator('.study-lab-tool__dataset-summary')).toContainText('Current draft dataset: XLB')
  await expect(study.getByRole('status', { name: 'Saved run dataset' })).toContainText(`Saved run #${runId} dataset: symbol SPY`)
  await expect(study.locator('.study-lab-tool__metrics article').filter({ hasText: 'current_streak' })).toBeVisible()

  await page.reload()
  await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: 'Study', exact: true }).click()
  const restoredStudy = page.locator('.study-lab-tool:visible').last()
  await expect(restoredStudy.locator('.study-lab-tool__dataset-summary')).toContainText('Current draft dataset: XLB')
  await expect(restoredStudy.getByRole('status', { name: 'Saved run dataset' })).toContainText(`Saved run #${runId} dataset: symbol SPY`)
  await expect(restoredStudy.locator('.study-lab-tool__metrics article').filter({ hasText: 'current_streak' })).toBeVisible()
  await expect(page.locator('.research-results-tool:visible').last().getByRole('button', { name: `Run ${runId}, completed, 8 artifacts` })).toBeVisible()

  await page.getByRole('button', { name: 'Add tool', exact: true }).click()
  await page.getByRole('menu', { name: 'Workstation tools' }).getByRole('menuitem', { name: 'Python Library', exact: true }).click()
  const library = page.locator('.code-library-tool:visible').last()
  await expect(library.getByRole('button', { name: `Open ${studyName} in Study Lab`, exact: true })).toBeVisible({ timeout: 15_000 })
  const libraryAsset = library.locator('.code-library-tool__asset').filter({ hasText: studyName }).first()
  await libraryAsset.locator('summary').click()
  const libraryEditedSource = `${immutableSource.trim()}\n# Saved as an immutable version from the Python Library.\n`
  await libraryAsset.getByRole('textbox', { name: `Python source for ${studyName}` }).fill(libraryEditedSource)
  await libraryAsset.getByRole('button', { name: 'Validate', exact: true }).click()
  await expect(libraryAsset).toContainText('Validated', { timeout: 15_000 })
  const savedVersionResponse = page.waitForResponse(response => response.request().method() === 'POST' && /\/code\/assets\/\d+\/versions$/.test(new URL(response.url()).pathname))
  await libraryAsset.getByRole('button', { name: 'Save as new version', exact: true }).click()
  const savedVersion = await savedVersionResponse
  expect(savedVersion.ok()).toBe(true)
  const savedVersionBody = await savedVersion.json() as { id?: number }
  expect(Number.isInteger(savedVersionBody.id)).toBe(true)
  await expect(libraryAsset).toContainText('2 versions', { timeout: 15_000 })
  await library.getByRole('button', { name: `Open ${studyName} in Study Lab`, exact: true }).click()

  const returnedStudy = page.locator('.study-lab-tool:visible').last()
  await expect(returnedStudy).toBeVisible({ timeout: 15_000 })
  await expect(returnedStudy.getByRole('textbox', { name: 'Study name' })).toHaveValue(studyName)
  await expect(returnedStudy.getByRole('textbox', { name: 'Study Python source' })).toHaveValue(libraryEditedSource)
  expect(runRequests).toHaveLength(1)

  const returnedPreparation = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/data/ensure'))
  await returnedStudy.getByRole('button', { name: 'Validate study' }).click()
  expect((await returnedPreparation).ok()).toBe(true)
  await expect(returnedStudy).toContainText('Validated for isolated execution', { timeout: 15_000 })
  const returnedRunRequest = page.waitForRequest(request => request.method() === 'POST' && new URL(request.url()).pathname.endsWith('/research/runs'))
  await returnedStudy.getByRole('button', { name: 'Run study', exact: true }).click()
  const returnedRunBody = (await returnedRunRequest).postDataJSON() as { code_version_id?: number }
  expect(returnedRunBody.code_version_id).toBe(savedVersionBody.id)
  await expect(returnedStudy.locator('.study-lab-tool__run-status--completed')).toBeVisible({ timeout: 90_000 })
  expect(runRequests).toHaveLength(2)
  expect(codeAssetCreations).toBe(1)
  await browserDiagnostics.expectNoCriticalIssues()
})
