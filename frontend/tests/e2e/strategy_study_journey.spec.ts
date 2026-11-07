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
  const completedRun = results.getByRole('button', { name: `Run ${runId}, completed, 8 artifacts` })
  await expect(completedRun).toBeVisible({ timeout: 15_000 })
  await completedRun.click()
  const resultDetail = results.locator(`article[aria-label="Research run ${runId} details"]`)
  await expect(resultDetail).toBeVisible()
  await expect(resultDetail.locator('.research-results-tool__artifacts > article')).toHaveCount(8, { timeout: 15_000 })

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
  const restoredResults = page.locator('.research-results-tool:visible').last()
  const restoredRun = restoredResults.getByRole('button', { name: `Run ${runId}, completed, 8 artifacts` })
  await expect(restoredRun).toBeVisible()
  await restoredRun.click()
  const restoredDetail = restoredResults.locator(`article[aria-label="Research run ${runId} details"]`)
  await expect(restoredDetail.locator('.research-results-tool__artifacts > article')).toHaveCount(8, { timeout: 15_000 })

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

test('Study prepares SPY before validating and completes a configured high-low breakout run', async ({ page, loggedIn, browserDiagnostics }) => {
  test.setTimeout(120_000)
  const requestOrder: string[] = []
  const observedRunStatuses: Array<{ id: number; status: string; error?: string | null }> = []
  const observedPreparationStatuses: Array<{ request_id?: string; status?: string; target?: { kind?: string; symbol?: string } }> = []
  let createdRunId: number | null = null
  page.on('request', request => {
    if (request.method() !== 'POST') return
    const path = new URL(request.url()).pathname
    if (path.endsWith('/data/ensure')) requestOrder.push('ensure')
    if (path.endsWith('/code/validate')) requestOrder.push('validate')
  })
  page.on('response', response => {
    if (response.request().method() !== 'GET') return
    const path = new URL(response.url()).pathname
    const preparationMatch = path.match(/\/data\/requests\/([^/]+)$/)
    if (preparationMatch) {
      void response.json().then((body: { request_id?: string; status?: string; target?: { kind?: string; symbol?: string } }) => {
        observedPreparationStatuses.push(body)
      }).catch(() => {})
      return
    }
    if (!/\/research\/runs\/\d+$/.test(path)) return
    void response.json().then((body: { id?: number; status?: string; error?: string | null }) => {
      if (body.id != null && body.status) observedRunStatuses.push({ id: body.id, status: body.status, error: body.error })
    }).catch(() => {})
  })

  await page.goto('/chart')
  await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: 'Study', exact: true }).click()
  await page.getByRole('button', { name: 'Add tool', exact: true }).click()
  await page.getByRole('menu', { name: 'Workstation tools' }).getByRole('menuitem', { name: 'Study Results', exact: true }).click()
  const study = page.locator('.study-lab-tool:visible').last()
  await expect(study).toBeVisible({ timeout: 15_000 })
  await study.getByRole('combobox', { name: 'Factory study' }).selectOption('high_low_breakouts')
  const lookback = study.getByRole('spinbutton', { name: 'Study parameter lookback' })
  await expect(lookback).toHaveValue('20')
  await expect(lookback).toHaveAttribute('min', '2')
  await expect(lookback).toHaveAttribute('max', '252')
  await lookback.fill('10')
  await study.getByRole('textbox', { name: 'Study symbol' }).fill('SPY')

  const preparationResponse = page.waitForResponse(response => response.request().method() === 'POST'
    && new URL(response.url()).pathname.endsWith('/data/ensure'))
  const validationResponse = page.waitForResponse(response => response.request().method() === 'POST'
    && new URL(response.url()).pathname.endsWith('/code/validate'))
  await study.getByRole('button', { name: 'Validate study' }).click()
  const prepared = await preparationResponse
  expect(prepared.ok()).toBe(true)
  const preparation = await prepared.json() as { request_id?: string; status?: string; target?: { kind?: string; symbol?: string } }
  expect(preparation.request_id).toBeTruthy()
  expect(prepared.request().postDataJSON()).toMatchObject({
    target: { kind: 'instrument', symbol: 'SPY' },
    datasets: ['history'],
    timeframe: 'D1',
    adjusted: true,
  })
  expect(preparation.target).toMatchObject({ kind: 'instrument', symbol: 'SPY' })
  await expect.poll(() => preparation.status === 'ready' || observedPreparationStatuses.some(status =>
    status.request_id === preparation.request_id && status.status === 'ready'
      && status.target?.kind === 'instrument' && status.target.symbol === 'SPY'), { timeout: 90_000 }).toBe(true)
  await expect(study.getByRole('status', { name: 'Study data preparation' })).toContainText('ready', { timeout: 90_000 })
  const validation = await validationResponse
  expect(validation.ok()).toBe(true)
  expect(await validation.json()).toMatchObject({ valid: true })
  expect(requestOrder.indexOf('ensure')).toBeGreaterThanOrEqual(0)
  expect(requestOrder.indexOf('validate')).toBeGreaterThan(requestOrder.indexOf('ensure'))
  await expect(study).toContainText('Validated for isolated execution', { timeout: 15_000 })

  const runResponse = page.waitForResponse(response => response.request().method() === 'POST'
    && new URL(response.url()).pathname.endsWith('/research/runs'))
  await study.getByRole('button', { name: 'Run study', exact: true }).click()
  const created = await runResponse
  expect(created.ok()).toBe(true)
  const run = await created.json() as { id?: number; code_version_id?: number }
  expect(Number.isInteger(run.id)).toBe(true)
  expect(Number.isInteger(run.code_version_id)).toBe(true)
  createdRunId = run.id!
  expect(created.request().postDataJSON()).toMatchObject({
    run_config: { symbol: 'SPY', parameters: { lookback: 10 } },
  })

  try {
    await expect(study.locator('.study-lab-tool__run-status--completed')).toBeVisible({ timeout: 90_000 })
    await expect(study.getByRole('status', { name: /new_high_count metric/ })).toBeVisible()
    await expect(study.getByRole('status', { name: /new_low_count metric/ })).toBeVisible()
  } catch (cause) {
    let persistedRun: unknown = null
    let readbackStatus: number | null = null
    try {
      const readback = await page.request.get(new URL(`/api/v1/research/runs/${createdRunId}`, page.url()).toString())
      readbackStatus = readback.status()
      persistedRun = await readback.json()
    } catch (readbackError) {
      persistedRun = { readback_error: readbackError instanceof Error ? readbackError.message : String(readbackError) }
    }
    await test.info().attach('high-low-study-run-status-diagnostic.json', {
      body: JSON.stringify({ run_id: createdRunId, readback_http_status: readbackStatus, persisted_run: persistedRun,
        observed_status_responses: observedRunStatuses.filter(item => item.id === createdRunId) }, null, 2),
      contentType: 'application/json',
    })
    throw cause
  }
  await browserDiagnostics.expectNoCriticalIssues()
})

test('Study preparation submits every universe member and benchmark while one member is held', async ({ page, loggedIn, browserDiagnostics }) => {
  const submittedTargets: Array<{ kind: string; symbol?: string }> = []
  let resolveAllSubmitted!: () => void
  const allSubmitted = new Promise<void>(resolve => { resolveAllSubmitted = resolve })
  let resolveHeldPrimary!: () => void
  const heldPrimary = new Promise<void>(resolve => { resolveHeldPrimary = resolve })
  const responseFor = (requestId: string, status: 'queued' | 'ready' | 'unavailable', version: number, symbol: string) => ({
    request_id: requestId,
    status,
    has_pending_work: status === 'queued',
    created_at: '2026-11-06T12:00:00Z',
    updated_at: '2026-11-06T12:00:01Z',
    version,
    target: { kind: 'instrument', symbol },
    dependencies: [{
      dependency_id: `${requestId}:history`,
      depends_on: [],
      instrument_id: null,
      symbol,
      dataset: 'history',
      status,
      requested_start: null,
      requested_end: null,
      covered_start: null,
      covered_end: null,
      reason_code: status === 'unavailable' ? 'no_eligible_history_provider' : null,
      retry_at: null,
      updated_at: '2026-11-06T12:00:01Z',
      covered_ranges: [],
    }],
    completed: status === 'queued' ? 0 : 1,
    total: 1,
    last_progress_at: '2026-11-06T12:00:01Z',
  })

  await page.route('**/api/v1/data/**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    if (request.method() === 'POST' && url.pathname.endsWith('/data/ensure')) {
      const body = request.postDataJSON() as { target: { kind: string; symbol?: string } }
      submittedTargets.push(body.target)
      if (submittedTargets.length === 3) resolveAllSubmitted()
      const symbol = body.target.symbol ?? `target-${submittedTargets.length}`
      await route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify(responseFor(`study-${symbol}`, 'queued', 1, symbol)) })
      return
    }
    const poll = url.pathname.match(/\/data\/requests\/study-([^/]+)$/)
    if (request.method() === 'GET' && poll) {
      const symbol = decodeURIComponent(poll[1])
      if (symbol === 'SPY') await heldPrimary
      const status = symbol === 'SPY' ? 'unavailable' : 'ready'
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(responseFor(`study-${symbol}`, status, 2, symbol)) })
      return
    }
    await route.continue()
  })

  let validationRequests = 0
  let runRequests = 0
  page.on('request', request => {
    if (request.method() !== 'POST') return
    const pathname = new URL(request.url()).pathname
    if (pathname.endsWith('/code/validate')) validationRequests += 1
    if (pathname.endsWith('/research/runs')) runRequests += 1
  })
  await page.goto('/chart')
  await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: 'Study', exact: true }).click()
  await page.getByRole('button', { name: 'Add tool', exact: true }).click()
  await page.getByRole('menu', { name: 'Workstation tools' }).getByRole('menuitem', { name: 'Study Results', exact: true }).click()
  const study = page.locator('.study-lab-tool:visible').last()
  await expect(study).toBeVisible({ timeout: 15_000 })
  await study.getByRole('textbox', { name: 'Study universe' }).fill('SPY, XLK')
  await study.getByRole('textbox', { name: 'Study benchmark' }).fill('QQQ')
  const validation = study.getByRole('button', { name: 'Validate study' })
  await validation.click()

  await allSubmitted
  expect(submittedTargets).toEqual([
    { kind: 'instrument', symbol: 'SPY' },
    { kind: 'instrument', symbol: 'XLK' },
    { kind: 'instrument', symbol: 'QQQ' },
  ])
  const outcomes = study.getByRole('list', { name: 'Study data preparation outcomes' })
  await expect(outcomes).toContainText('XLK: Requested data is ready.', { timeout: 10_000 })
  await expect(outcomes).toContainText('QQQ: Requested data is ready.', { timeout: 10_000 })
  await expect(validation).toBeDisabled()
  await expect(study.getByRole('button', { name: 'Run study', exact: true })).toBeDisabled()
  expect(validationRequests).toBe(0)
  expect(runRequests).toBe(0)

  resolveHeldPrimary()
  await expect(outcomes).toContainText('SPY: No reviewed data source can provide this request.', { timeout: 10_000 })
  await expect(study.getByRole('status', { name: 'Study data preparation' })).toContainText('Some selected Study data is not ready')
  expect(validationRequests).toBe(0)
  expect(runRequests).toBe(0)
  await browserDiagnostics.expectNoCriticalIssues()
})

test('Study ignores obsolete preparation after the selected symbol changes and validates the new context', async ({ page, loggedIn, browserDiagnostics }) => {
  const submittedTargets: string[] = []
  let resolveInitialSubmission!: () => void
  const initialSubmission = new Promise<void>(resolve => { resolveInitialSubmission = resolve })
  let resolveCurrentSubmission!: () => void
  const currentSubmission = new Promise<void>(resolve => { resolveCurrentSubmission = resolve })
  let resolveOldPoll!: () => void
  const oldPoll = new Promise<void>(resolve => { resolveOldPoll = resolve })
  let releaseOldPoll!: () => void
  const heldOldPoll = new Promise<void>(resolve => { releaseOldPoll = resolve })
  const requestSymbols = new Map<string, string>()
  const responseFor = (requestId: string, status: 'queued' | 'ready', version: number, symbol: string) => ({
    request_id: requestId,
    status,
    has_pending_work: status === 'queued',
    created_at: '2026-11-07T00:00:00Z',
    updated_at: '2026-11-07T00:00:01Z',
    version,
    target: { kind: 'instrument', symbol },
    dependencies: [{
      dependency_id: `${requestId}:history`,
      depends_on: [],
      instrument_id: null,
      symbol,
      dataset: 'history',
      status,
      requested_start: null,
      requested_end: null,
      covered_start: null,
      covered_end: null,
      reason_code: null,
      retry_at: null,
      updated_at: '2026-11-07T00:00:01Z',
      covered_ranges: [],
    }],
    completed: status === 'queued' ? 0 : 1,
    total: 1,
    last_progress_at: '2026-11-07T00:00:01Z',
  })

  await page.route('**/api/v1/data/**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    if (request.method() === 'POST' && url.pathname.endsWith('/data/ensure')) {
      const body = request.postDataJSON() as { target: { symbol?: string } }
      const symbol = body.target.symbol ?? 'unknown'
      submittedTargets.push(symbol)
      if (submittedTargets.length === 2) resolveInitialSubmission()
      if (submittedTargets.length === 4) resolveCurrentSubmission()
      const requestId = `context-${symbol}-${submittedTargets.length}`
      requestSymbols.set(requestId, symbol)
      await route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify(responseFor(requestId, 'queued', 1, symbol)) })
      return
    }
    const poll = url.pathname.match(/\/data\/requests\/(context-[^/]+)$/)
    if (request.method() === 'GET' && poll) {
      const requestId = decodeURIComponent(poll[1])
      if (requestId === 'context-SPY-1') {
        resolveOldPoll()
        await heldOldPoll
        try {
          await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(responseFor(requestId, 'ready', 2, requestSymbols.get(requestId)!)) })
        } catch {
          // The test deliberately aborts this obsolete poll when the user changes context.
        }
        return
      }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(responseFor(requestId, 'ready', 2, requestSymbols.get(requestId)!)) })
      return
    }
    await route.continue()
  })

  let validationRequests = 0
  let runRequests = 0
  page.on('request', request => {
    if (request.method() !== 'POST') return
    const pathname = new URL(request.url()).pathname
    if (pathname.endsWith('/code/validate')) validationRequests += 1
    if (pathname.endsWith('/research/runs')) runRequests += 1
  })
  await page.goto('/chart')
  await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: 'Study', exact: true }).click()
  await page.getByRole('button', { name: 'Add tool', exact: true }).click()
  await page.getByRole('menu', { name: 'Workstation tools' }).getByRole('menuitem', { name: 'Study Results', exact: true }).click()
  const study = page.locator('.study-lab-tool:visible').last()
  await expect(study).toBeVisible({ timeout: 15_000 })
  await study.getByRole('textbox', { name: 'Study symbol' }).fill('SPY')
  await study.getByRole('textbox', { name: 'Study benchmark' }).fill('QQQ')
  const validate = study.getByRole('button', { name: 'Validate study' })
  await validate.click()
  await initialSubmission
  await oldPoll
  await expect(study.getByRole('list', { name: 'Study data preparation outcomes' })).toContainText('QQQ: Requested data is ready.')

  const obsoletePollAborted = page.waitForEvent('requestfailed', request => new URL(request.url()).pathname.endsWith('/data/requests/context-SPY-1'))
  await study.getByRole('textbox', { name: 'Study symbol' }).fill('XLB')
  await obsoletePollAborted
  releaseOldPoll()
  await expect(validate).toBeEnabled()

  await validate.click()
  await currentSubmission
  expect(submittedTargets).toEqual(['SPY', 'QQQ', 'XLB', 'QQQ'])
  const outcomes = study.getByRole('list', { name: 'Study data preparation outcomes' })
  await expect(outcomes).toContainText('XLB: Requested data is ready.')
  await expect(outcomes).toContainText('QQQ: Requested data is ready.')
  await expect(outcomes).not.toContainText('SPY:')
  await expect(study).toContainText('Validated for isolated execution', { timeout: 15_000 })
  expect(validationRequests).toBe(1)
  expect(runRequests).toBe(0)

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
  let cancelAttempts = 0
  let detailAttempts = 0
  let firstSnapshotRerun = true
  const rerunRequests: Array<{ sourceRunId: number; snapshot: string | null }> = []

  await page.route('**/api/v1/research/runs**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const pathname = url.pathname
    if (request.method() === 'GET' && pathname.endsWith('/research/runs')) {
      const pageRows = (url.searchParams.has('before_created_at') ? [olderRun] : persistedRuns.slice(0, 26))
        .map(run => ({ ...run, artifacts: [] }))
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(pageRows) })
      return
    }
    const detail = pathname.match(/\/research\/runs\/(\d+)$/)
    if (request.method() === 'GET' && detail) {
      detailAttempts += 1
      if (detailAttempts === 1) {
        await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'controlled result detail unavailable' }) })
        return
      }
      const run = persistedRuns.find(item => item.id === Number(detail[1])) ?? olderRun
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(run) })
      return
    }
    const cancel = pathname.match(/\/research\/runs\/(\d+)\/cancel$/)
    if (request.method() === 'POST' && cancel) {
      cancelAttempts += 1
      if (cancelAttempts === 1) {
        await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'controlled cancellation unavailable' }) })
        return
      }
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
      if (sourceRunId === 8000 && snapshot === 'true' && firstSnapshotRerun) {
        firstSnapshotRerun = false
        await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'controlled rerun unavailable' }) })
        return
      }
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
  const selectedDetail = results.locator('article[aria-label="Research run 8000 details"]')
  await expect(selectedDetail.getByRole('alert')).toBeVisible()
  expect(detailAttempts).toBe(1)
  await selectedDetail.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(selectedDetail.locator('.research-results-tool__artifacts > article')).toHaveCount(3)
  expect(detailAttempts).toBe(2)

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
  await expect(results.getByRole('alert')).toContainText('Unable to cancel run #7999:')
  await expect(results.getByRole('button', { name: 'Cancel', exact: true })).toBeEnabled()
  await results.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(results.getByRole('button', { name: 'Run 7999, canceled, 0 artifacts' })).toBeVisible()

  await results.getByRole('button', { name: 'Run 8000, completed, 3 artifacts' }).click()
  await results.getByRole('button', { name: 'Rerun snapshot', exact: true }).click()
  await expect(results.getByRole('alert')).toContainText('Unable to queue rerun for run #8000:')
  await expect(results.getByRole('button', { name: 'Rerun snapshot', exact: true })).toBeEnabled()
  await results.getByRole('button', { name: 'Rerun snapshot', exact: true }).click()
  await expect(results.getByRole('button', { name: 'Run 8100, queued, 0 artifacts' })).toBeVisible()
  await expect(runList.locator('.research-results-tool__run-select').first()).toHaveAccessibleName('Run 8100, queued, 0 artifacts')
  await results.getByRole('button', { name: 'Rerun latest', exact: true }).click()
  await expect(results.getByRole('button', { name: 'Run 8101, queued, 0 artifacts' })).toBeVisible()
  expect(rerunRequests).toEqual([
    { sourceRunId: 8000, snapshot: 'true' },
    { sourceRunId: 8000, snapshot: 'true' },
    { sourceRunId: 8100, snapshot: 'false' },
  ])
  await browserDiagnostics.expectNoCriticalIssues()
})

test('Python Library supports create, import, clone, archive, export and filter through a controlled asset API', async ({ page, loggedIn, browserDiagnostics }) => {
  const makeAsset = (id: number, stableKey: string, name: string, source: string, archived = false) => ({
    id,
    stable_key: stableKey,
    name,
    kind: 'study',
    is_archived: archived,
    versions: [{ id: id * 10, version_number: 1, source, output_contract: 'study', parameter_schema: {}, default_parameters: {} }],
  })
  const initialAsset = makeAsset(41, 'seed-study', 'Seed Study', "output.scalar('seed', 1)")
  let assets = [initialAsset]
  let nextAssetId = 42
  const createRequests: Array<Record<string, unknown>> = []
  let importRequest: Record<string, unknown> | null = null
  let archiveRequest: { id: number; archived: boolean } | null = null

  await page.route('**/api/v1/code/**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const pathname = url.pathname
    if (request.method() === 'GET' && pathname.endsWith('/code/assets')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(assets) })
      return
    }
    if (request.method() === 'POST' && pathname.endsWith('/code/validate')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ valid: true, diagnostics: [], dependencies: [], output_contracts: ['study', 'scalar'] }) })
      return
    }
    if (request.method() === 'POST' && pathname.endsWith('/code/assets/import')) {
      importRequest = request.postDataJSON() as Record<string, unknown>
      const body = importRequest as { stable_key: string; name: string; versions: Array<Record<string, unknown>> }
      const imported = { id: nextAssetId++, stable_key: body.stable_key, name: body.name, kind: 'study', is_archived: false, versions: body.versions.map((version, index) => ({ ...version, id: 500 + index })) }
      assets = [...assets, imported]
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(imported) })
      return
    }
    if (request.method() === 'POST' && pathname.endsWith('/code/assets')) {
      const body = request.postDataJSON() as { stable_key: string; name: string; kind: string; initial_version: Record<string, unknown> }
      createRequests.push(body)
      const created = { id: nextAssetId++, stable_key: body.stable_key, name: body.name, kind: body.kind, is_archived: false, versions: [{ ...body.initial_version, id: 600 }] }
      assets = [...assets, created]
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(created) })
      return
    }
    const clone = pathname.match(/\/code\/assets\/(\d+)\/clone$/)
    if (request.method() === 'POST' && clone) {
      const source = assets.find(asset => asset.id === Number(clone[1]))!
      const body = request.postDataJSON() as { stable_key: string; name: string }
      const cloned = { ...source, id: nextAssetId++, stable_key: body.stable_key, name: body.name, versions: source.versions.map(version => ({ ...version, id: 700 })) }
      assets = [...assets, cloned]
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(cloned) })
      return
    }
    const archive = pathname.match(/\/code\/assets\/(\d+)\/archive$/)
    if (request.method() === 'POST' && archive) {
      const id = Number(archive[1])
      const body = request.postDataJSON() as { is_archived: boolean }
      archiveRequest = { id, archived: body.is_archived }
      assets = assets.map(asset => asset.id === id ? { ...asset, is_archived: body.is_archived } : asset)
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(assets.find(asset => asset.id === id)) })
      return
    }
    await route.continue()
  })

  await page.goto('/chart')
  await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: 'Study', exact: true }).click()
  await page.getByRole('button', { name: 'Add tool', exact: true }).click()
  await page.getByRole('menu', { name: 'Workstation tools' }).getByRole('menuitem', { name: 'Python Library', exact: true }).click()
  const library = page.locator('.code-library-tool:visible').last()
  await expect(library.getByRole('listitem').filter({ hasText: 'Seed Study' })).toBeVisible()

  await library.getByRole('button', { name: 'New', exact: true }).click()
  const createForm = library.getByRole('form', { name: 'Create Python asset' })
  await createForm.getByRole('textbox', { name: 'New Python asset name' }).fill('Created Study')
  await createForm.getByRole('textbox', { name: 'New Python asset key' }).fill('created-study')
  await createForm.getByRole('textbox', { name: 'New Python asset source' }).fill("output.scalar('value', 2)")
  await createForm.getByRole('button', { name: 'Validate', exact: true }).click()
  await expect(createForm.getByRole('status')).toContainText('Validated')
  await createForm.getByRole('button', { name: 'Create asset', exact: true }).click()
  const created = library.getByRole('listitem').filter({ hasText: 'Created Study' })
  await expect(created).toBeVisible()
  expect(createRequests).toHaveLength(1)
  expect(createRequests[0]).toMatchObject({ stable_key: 'created-study', kind: 'study', initial_version: { source: "output.scalar('value', 2)", output_contract: 'study' } })

  const exportReady = page.waitForEvent('download')
  await library.getByRole('listitem').filter({ hasText: 'Seed Study' }).locator('button[title="Export asset"]').click()
  expect((await exportReady).suggestedFilename()).toBe('seed-study.json')

  const importedPayload = { stable_key: 'imported-study', name: 'Imported Study', kind: 'study', versions: [{ version_number: 1, source: "output.scalar('imported', 3)", output_contract: 'study', parameter_schema: {}, default_parameters: {} }] }
  await library.locator('input[type="file"]').setInputFiles({ name: 'imported-study.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(importedPayload)) })
  const imported = library.getByRole('listitem').filter({ hasText: 'Imported Study' })
  await expect(imported).toBeVisible()
  expect(importRequest).toEqual(importedPayload)

  await created.locator('button[title="Clone asset"]').click()
  const cloned = library.getByRole('listitem').filter({ hasText: 'Created Study copy' })
  await expect(cloned).toBeVisible()
  await cloned.getByRole('button', { name: 'Archive asset' }).click()
  await expect(cloned.getByRole('button', { name: 'Unarchive asset' })).toHaveAttribute('aria-pressed', 'true')
  expect(archiveRequest).toMatchObject({ archived: true })

  await library.getByRole('searchbox', { name: 'Filter Python assets' }).fill('Imported')
  await expect(imported).toBeVisible()
  await expect(created).toHaveCount(0)
  await browserDiagnostics.expectNoCriticalIssues()
})
