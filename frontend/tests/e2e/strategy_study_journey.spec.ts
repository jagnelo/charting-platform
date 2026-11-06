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

test('Results supports ordinary controls through a controlled persisted-run API', async ({ page, loggedIn, browserDiagnostics }) => {
  const breadthRun = {
    id: 8000,
    status: 'completed',
    created_at: '2026-11-06T12:00:00Z',
    code_version_id: 88,
    output_contract: 'study',
    reproducibility_hash: 'controlled-run-8000',
    run_config: { execution_mode: 'breadth_history' },
    dataset_manifest: { source: 'controlled-browser-fixture', symbols: ['SPY'] },
    diagnostics: [],
    warnings: [],
    artifacts: [
      { id: 801, name: 'breadth_history', artifact_type: 'breadth_history', payload: { value: { points: [], occurrences: [] } } },
      { id: 802, name: 'occurrences', artifact_type: 'events', payload: { value: [
        { symbol: 'SPY', timestamp: '2026-11-05T00:00:00Z', kind: 'member_entered', instrument_id: 7 },
        { symbol: 'SPY', timestamp: '2026-11-04T00:00:00Z', kind: 'member_exited', instrument_id: 7 },
        { symbol: 'AAPL', timestamp: '2026-11-03T00:00:00Z', kind: 'member_entered', instrument_id: 8 },
      ] } },
      { id: 803, name: 'sample_count', artifact_type: 'scalar', payload: { value: 3 } },
    ],
    artifact_count: 3,
  }
  const makeRun = (id: number, status = 'completed', createdAt = new Date(Date.UTC(2026, 10, 6, 11, 59 - (8000 - id), 0)).toISOString()) => ({
    id,
    status,
    created_at: createdAt,
    code_version_id: id + 100,
    output_contract: 'study',
    reproducibility_hash: `controlled-run-${id}`,
    run_config: {},
    dataset_manifest: { source: 'controlled-browser-fixture', symbols: ['SPY'] },
    diagnostics: [],
    warnings: [],
    artifacts: [],
    artifact_count: 0,
  })
  const queuedRun = makeRun(7999, 'queued', '2026-11-06T11:59:00Z')
  let persistedRuns = [breadthRun, queuedRun, ...Array.from({ length: 24 }, (_, index) => makeRun(7998 - index))]
  const olderRun = makeRun(7900, 'completed', '2026-11-06T00:00:00Z')
  let nextRunId = 8100
  const rerunRequests: Array<{ sourceRunId: number; snapshot: string | null }> = []

  await page.route('**/api/v1/research/runs**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const pathname = url.pathname
    if (request.method() === 'GET' && pathname.endsWith('/research/runs')) {
      const pageRows = url.searchParams.has('before_created_at') ? [olderRun] : persistedRuns.slice(0, 26)
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(pageRows) })
      return
    }
    const detail = pathname.match(/\/research\/runs\/(\d+)$/)
    if (request.method() === 'GET' && detail) {
      const run = persistedRuns.find(item => item.id === Number(detail[1])) ?? olderRun
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(run) })
      return
    }
    const cancel = pathname.match(/\/research\/runs\/(\d+)\/cancel$/)
    if (request.method() === 'POST' && cancel) {
      const runId = Number(cancel[1])
      persistedRuns = persistedRuns.map(run => run.id === runId ? { ...run, status: 'canceled' } : run)
      const canceled = persistedRuns.find(run => run.id === runId)!
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(canceled) })
      return
    }
    const rerun = pathname.match(/\/research\/runs\/(\d+)\/rerun$/)
    if (request.method() === 'POST' && rerun) {
      const sourceRunId = Number(rerun[1])
      const snapshot = url.searchParams.get('snapshot')
      rerunRequests.push({ sourceRunId, snapshot })
      const source = persistedRuns.find(run => run.id === sourceRunId) ?? breadthRun
      const queued = makeRun(nextRunId++, 'queued', new Date(Date.UTC(2026, 10, 6, 12, 10 + rerunRequests.length, 0)).toISOString())
      queuedRun.artifacts = []
      persistedRuns = [queued, ...persistedRuns.filter(run => run.id !== queued.id)]
      await route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify({ ...queued, code_version_id: source.code_version_id }) })
      return
    }
    await route.continue()
  })
  await page.route('**/api/v1/analysis/breadth/python/runs/*/promote-scan', async route => {
    await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ id: 810, name: 'Controlled breadth scan' }) })
  })

  await page.goto('/chart')
  await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: 'Study', exact: true }).click()
  await page.getByRole('button', { name: 'Add tool', exact: true }).click()
  await page.getByRole('menu', { name: 'Workstation tools' }).getByRole('menuitem', { name: 'Study Results', exact: true }).click()
  const results = page.locator('.research-results-tool:visible').last()
  await expect(results.getByRole('button', { name: 'Run 8000, completed, 3 artifacts' })).toBeVisible()
  const runList = results.getByRole('list', { name: 'Persisted research runs' })
  await expect(runList.locator('.research-results-tool__run-select').nth(0)).toHaveAccessibleName('Run 8000, completed, 3 artifacts')
  await expect(runList.locator('.research-results-tool__run-select').nth(1)).toHaveAccessibleName('Run 7999, queued, 0 artifacts')

  await results.getByRole('button', { name: 'Load older runs', exact: true }).click()
  await expect(results.getByRole('button', { name: 'Run 7900, completed, 0 artifacts' })).toBeVisible()

  await results.getByRole('checkbox', { name: 'Compare run 8000' }).check()
  await results.getByRole('checkbox', { name: 'Compare run 7999' }).check()
  await results.getByRole('button', { name: 'Compare', exact: true }).click()
  await expect(results).toContainText('Run 8000 vs 7999')

  await results.getByRole('button', { name: 'Run 8000, completed, 3 artifacts' }).click()
  await results.getByRole('searchbox', { name: 'occurrences symbol filter' }).fill('SPY')
  await results.getByRole('combobox', { name: 'occurrences event type filter' }).selectOption('member_entered')
  await expect(results.getByRole('list', { name: 'occurrences filtered occurrences' }).getByRole('listitem')).toHaveCount(1)

  const exportReady = page.waitForEvent('download')
  await results.locator('[aria-label="sample_count scalar result"] button[title="Export sample_count"]').click()
  expect((await exportReady).suggestedFilename()).toBe('study-run-8000-sample_count.json')

  await results.getByRole('button', { name: 'Promote to EasyScan', exact: true }).click()
  await expect(results).toContainText('EasyScan “Controlled breadth scan” (#810) created')

  await results.getByRole('button', { name: 'Run 7999, queued, 0 artifacts' }).click()
  await results.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(results.getByRole('button', { name: 'Run 7999, canceled, 0 artifacts' })).toBeVisible()

  await results.getByRole('button', { name: 'Run 8000, completed, 3 artifacts' }).click()
  await results.getByRole('button', { name: 'Rerun snapshot', exact: true }).click()
  await expect(results.getByRole('button', { name: 'Run 8100, queued, 0 artifacts' })).toBeVisible()
  await expect(runList.locator('.research-results-tool__run-select').first()).toHaveAccessibleName('Run 8100, queued, 0 artifacts')
  await results.getByRole('button', { name: 'Rerun latest', exact: true }).click()
  await expect(results.getByRole('button', { name: 'Run 8101, queued, 0 artifacts' })).toBeVisible()
  expect(rerunRequests).toEqual([
    { sourceRunId: 8000, snapshot: 'true' },
    { sourceRunId: 8100, snapshot: 'false' },
  ])
  await browserDiagnostics.expectNoCriticalIssues()
})
