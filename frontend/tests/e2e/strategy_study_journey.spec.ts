import { test, expect } from './helpers'
import type { Page } from '@playwright/test'

const retainedStudyStartDate = '2024-01-02'
const retainedStudyEndDate = '2025-12-29'

async function activateDockToolTab(page: Page, title: string) {
  const tab = page.locator(`.lm_tab[title="${title}"]`).last()
  await expect(tab).toBeVisible()
  await tab.click()
  await expect(tab).toHaveClass(/lm_active/)
}

async function authenticatedJson(page: Page, path: string) {
  return page.evaluate(async url => {
    const token = localStorage.getItem('access_token')
    const response = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
    return { status: response.status, body: await response.json() }
  }, path)
}

async function openStudyResultsTool(page: Page) {
  await page.goto('/chart')
  await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: 'Study', exact: true }).click()
  await activateDockToolTab(page, 'Study Results')
  const results = page.locator('.research-results-tool:visible').last()
  await expect(results).toBeVisible({ timeout: 15_000 })
  await expect(page.locator('.research-results-tool:visible')).toHaveCount(1)
  return results
}

function recoveryRun(id: number, status: string, artifactCount = 0, artifacts: Array<Record<string, unknown>> = []) {
  return {
    id,
    status,
    created_at: `2026-11-07T10:${String(id % 60).padStart(2, '0')}:00Z`,
    code_version_id: id + 100,
    output_contract: 'study',
    reproducibility_hash: `controlled-recovery-${id}`,
    run_config: {},
    dataset_manifest: { source: 'controlled-browser-fixture', symbols: ['SPY'] },
    diagnostics: [],
    warnings: [],
    artifacts,
    artifact_count: artifactCount,
  }
}

function controlledResponseUrl(path: string) {
  return new URL(`/api/v1${path}`, process.env.STACK_URL ?? 'http://localhost').href
}

function controlled503(responseId: string) {
  return {
    status: 503,
    headers: { 'x-controlled-response-id': responseId },
    contentType: 'application/json',
    body: JSON.stringify({ detail: 'Controlled temporary failure', response_id: responseId }),
  }
}

function isStudyHistoryEnsure(
  request: import('@playwright/test').Request,
  symbols: ReadonlySet<string>,
  startAt: string | null = null,
  endAt: string | null = null,
) {
  if (request.method() !== 'POST' || new URL(request.url()).pathname !== '/api/v1/data/ensure') return false
  let body: {
    target?: { kind?: string; symbol?: string }
    datasets?: string[]
    timeframe?: string
    adjusted?: boolean
    start_at?: string | null
    end_at?: string | null
  }
  try {
    body = request.postDataJSON() as typeof body
  } catch {
    return false
  }
  const datasets = body.datasets ?? []
  const matchesRequestedHistory = datasets.length === 1 && datasets[0] === 'history'
  const matchesDate = (actual: string | null | undefined, expected: string | null) => expected === null
    ? actual == null
    : actual === expected
  return body.target?.kind === 'instrument'
    && typeof body.target.symbol === 'string'
    && symbols.has(body.target.symbol.toUpperCase())
    && matchesRequestedHistory
    && body.timeframe === 'D1'
    && body.adjusted === true
    && matchesDate(body.start_at, startAt)
    && matchesDate(body.end_at, endAt)
}

function isWorkspaceSnapshotWithStudyVersion(
  request: import('@playwright/test').Request,
  versionId: number,
  source: string,
) {
  if (request.method() !== 'PUT' || !/^\/api\/v1\/workspaces\/\d+\/snapshot$/.test(new URL(request.url()).pathname)) return false
  let body: { tabs?: Array<{ windows?: Array<{ tool_type?: string; configuration?: Record<string, unknown> }> }> }
  try {
    body = request.postDataJSON() as typeof body
  } catch {
    return false
  }
  return body.tabs?.some(tab => tab.windows?.some(window => window.tool_type === 'study_lab'
    && window.configuration?.study_asset_version_id === versionId
    && window.configuration?.study_source === source)) ?? false
}

test('Study journey keeps saved identity, refreshes Results, and returns from Python Library on the immutable version', async ({ page, loggedIn, browserDiagnostics }) => {
  test.setTimeout(150_000)
  const studyName = `Study journey ${Date.now()}`
  const strategyLabV2Writes: string[] = []
  const runRequests: Array<{
    code_version_id?: number
    run_config?: { symbol?: string; start_date?: string; end_date?: string }
    dataset_manifest?: { symbol?: string; start_date?: string; end_date?: string }
  }> = []
  let codeAssetCreations = 0
  page.on('request', request => {
    const url = new URL(request.url())
    if (url.pathname.startsWith('/api/v1/strategy-lab/v2/') && request.method() !== 'GET') {
      strategyLabV2Writes.push(`${request.method()} ${url.pathname}`)
    }
    if (request.method() !== 'POST') return
    const pathname = url.pathname
    if (pathname.endsWith('/research/runs')) runRequests.push(request.postDataJSON() as typeof runRequests[number])
    if (pathname.endsWith('/code/assets')) codeAssetCreations += 1
  })
  await page.goto('/chart')
  await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: 'Study', exact: true }).click()

  await activateDockToolTab(page, 'Study Lab')
  const compactStudy = page.locator('.study-lab-tool:visible').last()
  const compactHeader = compactStudy.locator('.study-lab-tool__header-main')
  await expect.poll(() => compactHeader.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true)
  await expect(compactHeader.getByRole('textbox', { name: 'Study name' })).toBeVisible()
  await expect(compactHeader.getByRole('textbox', { name: 'Study symbol' })).toBeVisible()
  await expect(compactHeader.getByRole('combobox', { name: 'Factory study' })).toBeVisible()
  await activateDockToolTab(page, 'Study Results')
  const results = page.locator('.research-results-tool:visible').last()
  await expect(results).toBeVisible({ timeout: 15_000 })
  await expect(page.locator('.research-results-tool:visible')).toHaveCount(1)
  const resultsRegion = page.getByRole('region', { name: 'Study Lab research results' }).last()
  await expect(resultsRegion.getByRole('status')).toContainText('No persisted studies yet. Run a study in the adjacent Study Lab pane.')

  await activateDockToolTab(page, 'Study Lab')
  const study = page.locator('.study-lab-tool:visible').last()
  await expect(study).toBeVisible({ timeout: 15_000 })
  await study.getByRole('combobox', { name: 'Factory study' }).selectOption('positive_streak')
  await study.getByRole('textbox', { name: 'Study name' }).fill(studyName)
  await study.getByRole('textbox', { name: 'Study symbol' }).fill('SPY')
  await study.getByLabel('Study start date').fill(retainedStudyStartDate)
  await study.getByLabel('Study end date').fill(retainedStudyEndDate)
  const immutableSource = await study.getByRole('textbox', { name: 'Study Python source' }).inputValue()
  const preparationSymbols = new Set(['SPY'])
  const preparationResponse = page.waitForResponse(response => isStudyHistoryEnsure(
    response.request(),
    preparationSymbols,
    `${retainedStudyStartDate}T00:00:00.000Z`,
    `${retainedStudyEndDate}T23:59:59.999Z`,
  ))
  await study.getByRole('button', { name: 'Validate study' }).click()
  const prepared = await preparationResponse
  expect(prepared.ok()).toBe(true)
  expect(prepared.request().postDataJSON()).toMatchObject({
    target: { kind: 'instrument', symbol: 'SPY' },
    datasets: ['history'],
    timeframe: 'D1',
    adjusted: true,
    start_at: `${retainedStudyStartDate}T00:00:00.000Z`,
    end_at: `${retainedStudyEndDate}T23:59:59.999Z`,
  })
  await expect(study.getByRole('status', { name: 'Study data preparation' })).toContainText('ready', { timeout: 90_000 })
  await expect(study).toContainText('Validated for isolated execution', { timeout: 15_000 })
  const firstRunRequest = page.waitForRequest(request => request.method() === 'POST' && new URL(request.url()).pathname.endsWith('/research/runs'))
  await study.getByRole('button', { name: 'Run study', exact: true }).click()
  const firstRunBody = (await firstRunRequest).postDataJSON() as { code_version_id?: number }
  expect(Number.isInteger(firstRunBody.code_version_id)).toBe(true)
  expect(runRequests[0]).toMatchObject({
    run_config: { start_date: retainedStudyStartDate, end_date: retainedStudyEndDate },
    dataset_manifest: { start_date: retainedStudyStartDate, end_date: retainedStudyEndDate },
  })
  expect(codeAssetCreations).toBe(1)
  await expect(study.locator('.study-lab-tool__run-status--completed')).toBeVisible({ timeout: 90_000 })

  const runLabel = await study.locator('.study-lab-tool__run > div > strong').innerText()
  const runId = runLabel.match(/Run #(\d+)/)?.[1]
  expect(runId).toBeTruthy()
  await expect(study.getByRole('status', { name: 'Saved run dataset' })).toContainText(`Saved run #${runId} dataset: symbol SPY`)
  await expect(study.getByRole('status', { name: 'Saved run dataset' })).toContainText(`from ${retainedStudyStartDate}`)
  await expect(study.getByRole('status', { name: 'Saved run dataset' })).toContainText(`through ${retainedStudyEndDate}`)
  await activateDockToolTab(page, 'Study Results')
  const activeResults = page.locator('.research-results-tool:visible').last()
  const completedRun = activeResults.getByRole('button', { name: `Run ${runId}, completed, 8 artifacts` })
  await expect(completedRun).toBeVisible({ timeout: 15_000 })
  await completedRun.click()
  const resultDetail = activeResults.locator(`article[aria-label="Research run ${runId} details"]`)
  await expect(resultDetail).toBeVisible()
  await expect(resultDetail.locator('.research-results-tool__artifacts > article')).toHaveCount(8, { timeout: 15_000 })

  await activateDockToolTab(page, 'Study Lab')
  const savedDraft = page.waitForResponse(response => response.request().method() === 'PUT' && new URL(response.url()).pathname.endsWith('/snapshot'))
  await study.getByRole('textbox', { name: 'Study symbol' }).fill('XLB')
  expect((await savedDraft).ok()).toBe(true)
  await study.getByRole('button', { name: 'Validate study' }).click()
  await expect(study).toContainText('Validated for isolated execution', { timeout: 15_000 })
  await expect(study.locator('.study-lab-tool__dataset-summary')).toContainText('Current draft dataset: XLB')
  await expect(study.locator('.study-lab-tool__dataset-summary')).toContainText(`${retainedStudyStartDate} → ${retainedStudyEndDate}`)
  await expect(study.getByRole('status', { name: 'Saved run dataset' })).toContainText(`Saved run #${runId} dataset: symbol SPY`)
  await expect(study.locator('.study-lab-tool__metrics article').filter({ hasText: 'current_streak' })).toBeVisible()

  const restoredRunDetailResponse = page.waitForResponse(response => response.request().method() === 'GET'
    && new URL(response.url()).pathname === `/api/v1/research/runs/${runId}`)
  await page.reload()
  await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
  const restoredRunDetail = await restoredRunDetailResponse
  expect(restoredRunDetail.status()).toBe(200)
  const restoredRunPayload = await restoredRunDetail.json() as {
    id?: number
    run_config?: { symbol?: string }
    dataset_manifest?: { symbol?: string }
  }
  expect(restoredRunPayload).toMatchObject({
    id: Number(runId),
    run_config: { symbol: 'SPY' },
    dataset_manifest: { symbol: 'SPY' },
  })
  await page.getByRole('button', { name: 'Study', exact: true }).click()
  const restoredStudy = page.locator('.study-lab-tool:visible').last()
  await expect(restoredStudy.locator('.study-lab-tool__dataset-summary')).toContainText('Current draft dataset: XLB')
  await expect(restoredStudy.locator('.study-lab-tool__dataset-summary')).toContainText(`${retainedStudyStartDate} → ${retainedStudyEndDate}`)
  await expect(restoredStudy.getByRole('status', { name: 'Saved run dataset' })).toContainText(`Saved run #${runId} dataset: symbol SPY`)
  await expect(restoredStudy.getByRole('status', { name: 'Saved run dataset' })).toContainText(`from ${retainedStudyStartDate}`)
  await expect(restoredStudy.getByRole('status', { name: 'Saved run dataset' })).toContainText(`through ${retainedStudyEndDate}`)
  await expect(restoredStudy.locator('.study-lab-tool__metrics article').filter({ hasText: 'current_streak' })).toBeVisible()
  await activateDockToolTab(page, 'Study Results')
  const restoredResults = page.locator('.research-results-tool:visible').last()
  const restoredRun = restoredResults.getByRole('button', { name: `Run ${runId}, completed, 8 artifacts` })
  await expect(restoredRun).toBeVisible()
  await restoredRun.click()
  const restoredDetail = restoredResults.locator(`article[aria-label="Research run ${runId} details"]`)
  await expect(restoredDetail.locator('.research-results-tool__artifacts > article')).toHaveCount(8, { timeout: 15_000 })

  const inspectorLink = restoredDetail.getByRole('link', { name: /^Inspect .* immutable Study lineage in Strategy Lab v2$/ }).first()
  await expect(inspectorLink).toBeVisible()
  const inspectorHref = await inspectorLink.getAttribute('href')
  expect(inspectorHref).toMatch(new RegExp(`/legacy/strategy-lab-v2\\?researchRunId=${runId}&artifactId=[1-9][0-9]*`))
  const inspectorReferenceRead = page.waitForResponse(response => response.request().method() === 'GET'
    && new URL(response.url()).pathname.match(/^\/api\/v1\/strategy-lab\/v2\/study-artifact-references\/[1-9][0-9]*\/[1-9][0-9]*$/) !== null)
  await inspectorLink.click()
  await expect(page.getByRole('heading', { name: 'Strategy Lab v2' })).toBeVisible()
  const inspectorResponse = await inspectorReferenceRead
  expect(inspectorResponse.status()).toBe(200)
  const inspectorPin = await inspectorResponse.json() as { data?: { attributes?: Record<string, unknown> } }
  const pin = inspectorPin.data?.attributes
  expect(pin).toMatchObject({ research_run_id: Number(runId), output_contract: 'study' })
  expect(String(pin?.run_reproducibility_hash)).toMatch(/^[0-9a-f]{64}$/)
  for (const digest of ['code_version_digest', 'dataset_manifest_digest', 'artifact_content_digest']) {
    expect(typeof pin?.[digest], `${digest} is part of the immutable Study pin`).toBe('string')
    expect(String(pin?.[digest])).toMatch(/^sha256:[0-9a-f]{64}$/)
  }
  const resolvedPin = page.getByRole('region', { name: 'Resolved Study pin' })
  await expect(resolvedPin).toContainText(new RegExp(String(Number(runId))))
  await expect(page.getByRole('region', { name: 'Execution boundary' })).toContainText('does not start a backtest')
  await expect(page.getByRole('region', { name: 'Execution boundary' })).toContainText('Native, broker and capital actions remain unavailable')
  for (const [label, endpoint] of [['Trials', '/trials'], ['Artifacts', '/artifacts']] as const) {
    const collectionRead = page.waitForResponse(response => response.request().method() === 'GET'
      && new URL(response.url()).pathname === `/api/v1/strategy-lab/v2${endpoint}`)
    await page.getByRole('button', { name: new RegExp(`^${label}`) }).click()
    expect((await collectionRead).status()).toBe(200)
  }
  const returnLink = page.getByRole('link', { name: 'Back to workstation', exact: true })
  await returnLink.click()
  await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
  expect(strategyLabV2Writes).toEqual([])

  await page.getByRole('button', { name: 'Add tool', exact: true }).click()
  await page.getByRole('menu', { name: 'Workstation tools' }).getByRole('menuitem', { name: 'Python Library', exact: true }).click()
  await activateDockToolTab(page, 'Python Library')
  const library = page.locator('.code-library-tool:visible').last()
  await expect(library.getByRole('button', { name: `Open ${studyName} in Study Lab`, exact: true })).toBeVisible({ timeout: 15_000 })
  const libraryAsset = library.locator('.code-library-tool__asset').filter({ hasText: studyName }).first()
  await libraryAsset.locator('summary').click()
  const libraryEditedSource = `${immutableSource.trim()}\n# Saved as an immutable version from the Python Library.\n`
  await libraryAsset.getByRole('textbox', { name: `Python source for ${studyName}` }).fill(libraryEditedSource)
  const libraryValidationRequest = page.waitForRequest(request => {
    if (request.method() !== 'POST' || new URL(request.url()).pathname !== '/api/v1/code/validate') return false
    try {
      const body = request.postDataJSON() as { source?: string }
      return body.source === libraryEditedSource
    } catch {
      return false
    }
  })
  await libraryAsset.getByRole('button', { name: 'Validate', exact: true }).click()
  const editedLibraryValidation = await libraryValidationRequest
  expect(editedLibraryValidation.postDataJSON()).toEqual({ source: libraryEditedSource })
  const editedLibraryValidationResponse = await editedLibraryValidation.response()
  expect(editedLibraryValidationResponse?.status()).toBe(200)
  const editedLibraryValidationResult = await editedLibraryValidationResponse!.json() as { valid?: boolean }
  expect(editedLibraryValidationResult.valid).toBe(true)
  const editedLibraryValidationNotice = libraryAsset.locator('.code-library-tool__validation')
  await expect(editedLibraryValidationNotice).toHaveAttribute('role', 'status')
  await expect(editedLibraryValidationNotice.locator('strong')).toHaveText('Validated', { timeout: 15_000 })
  const savedVersionResponse = page.waitForResponse(response => response.request().method() === 'POST' && /\/code\/assets\/\d+\/versions$/.test(new URL(response.url()).pathname))
  await libraryAsset.getByRole('button', { name: 'Save as new version', exact: true }).click()
  const savedVersion = await savedVersionResponse
  expect(savedVersion.ok()).toBe(true)
  const savedVersionBody = await savedVersion.json() as { id?: number; source?: string; version_number?: number }
  expect(Number.isInteger(savedVersionBody.id)).toBe(true)
  // CodeLibraryTool.saveVersion canonicalizes editor whitespace with trim()
  // before POSTing. Use the returned immutable CodeVersion source as the
  // authoritative value for the later Study return, while asserting that
  // documented normalization exactly.
  expect(savedVersionBody.source).toBe(libraryEditedSource.trim())
  await expect(libraryAsset).toContainText('2 versions', { timeout: 15_000 })

  const historicalVersionId = firstRunBody.code_version_id!
  await libraryAsset.getByRole('combobox', { name: `Base version for ${studyName}`, exact: true }).selectOption('1')
  const historicalVersionSnapshot = page.waitForResponse(response => isWorkspaceSnapshotWithStudyVersion(
    response.request(),
    historicalVersionId,
    immutableSource,
  ))
  await libraryAsset.getByRole('button', { name: `Open version 1 of ${studyName} in Study Lab`, exact: true }).click()
  const historicalSnapshot = await historicalVersionSnapshot
  expect(historicalSnapshot.ok()).toBe(true)
  const persistedHistoricalWorkspace = await historicalSnapshot.json() as {
    tabs?: Array<{ windows?: Array<{ tool_type?: string; configuration?: Record<string, unknown> }> }>
  }
  expect(persistedHistoricalWorkspace.tabs?.some(tab => tab.windows?.some(window => window.tool_type === 'study_lab'
    && window.configuration?.study_asset_version_id === historicalVersionId
    && window.configuration?.study_source === immutableSource))).toBe(true)
  const historicalStudy = page.locator('.study-lab-tool:visible').last()
  await expect(historicalStudy.getByRole('textbox', { name: 'Study name' })).toHaveValue(studyName)
  await expect(historicalStudy.getByRole('textbox', { name: 'Study Python source' })).toHaveValue(immutableSource)
  expect(runRequests).toHaveLength(1)

  await activateDockToolTab(page, 'Python Library')
  await library.getByRole('button', { name: `Open ${studyName} in Study Lab`, exact: true }).click()

  const returnedStudy = page.locator('.study-lab-tool:visible').last()
  await expect(returnedStudy).toBeVisible({ timeout: 15_000 })
  await expect(returnedStudy.getByRole('textbox', { name: 'Study name' })).toHaveValue(studyName)
  await expect(returnedStudy.getByRole('textbox', { name: 'Study Python source' })).toHaveValue(savedVersionBody.source!)
  await expect(returnedStudy.getByRole('textbox', { name: 'Study symbol' })).toHaveValue('XLB')
  await expect(returnedStudy.getByLabel('Study start date')).toHaveValue(retainedStudyStartDate)
  await expect(returnedStudy.getByLabel('Study end date')).toHaveValue(retainedStudyEndDate)
  expect(runRequests).toHaveLength(1)

  const returnedStudySymbols = new Set(['XLB'])
  const returnedPreparation = page.waitForResponse(response => isStudyHistoryEnsure(
    response.request(),
    returnedStudySymbols,
    `${retainedStudyStartDate}T00:00:00.000Z`,
    `${retainedStudyEndDate}T23:59:59.999Z`,
  ))
  await returnedStudy.getByRole('button', { name: 'Validate study' }).click()
  expect((await returnedPreparation).ok()).toBe(true)
  await expect(returnedStudy).toContainText('Validated for isolated execution', { timeout: 15_000 })
  const returnedRunRequest = page.waitForRequest(request => request.method() === 'POST' && new URL(request.url()).pathname.endsWith('/research/runs'))
  const returnedRunCreateResponse = page.waitForResponse(response => response.request().method() === 'POST'
    && new URL(response.url()).pathname.endsWith('/research/runs'))
  await returnedStudy.getByRole('button', { name: 'Run study', exact: true }).click()
  const returnedRunBody = (await returnedRunRequest).postDataJSON() as typeof runRequests[number]
  const returnedRunAccepted = await returnedRunCreateResponse
  expect(returnedRunAccepted.status()).toBe(202)
  expect(returnedRunBody.code_version_id).toBe(savedVersionBody.id)
  expect(returnedRunBody).toMatchObject({
    run_config: { symbol: 'XLB', start_date: retainedStudyStartDate, end_date: retainedStudyEndDate },
    dataset_manifest: { start_date: retainedStudyStartDate, end_date: retainedStudyEndDate },
  })
  const acceptedRun = await returnedRunAccepted.json() as { id?: number }
  expect(Number.isInteger(acceptedRun.id)).toBe(true)
  await expect(returnedStudy.locator('.study-lab-tool__run-status--completed')).toBeVisible({ timeout: 90_000 })
  const returnedRunDetailRead = await authenticatedJson(page, `/api/v1/research/runs/${acceptedRun.id}`)
  expect(returnedRunDetailRead.status).toBe(200)
  const returnedRunDetail = returnedRunDetailRead.body as {
    status?: string
    evaluation_status?: string
    run_config?: { symbol?: string; start_date?: string; end_date?: string }
    dataset_manifest?: {
      source?: string
      symbol?: string
      instrument_id?: number
      timeframe?: string
      adjustment?: string
      session?: string
      start_date?: string
      end_date?: string
      timestamps?: string[]
      closes?: Array<number | null>
      metadata?: { symbol?: string; instrument_id?: number }
      coverage_preflight?: { items?: Array<{ instrument_id?: number; status?: string }> }
    }
  }
  expect(returnedRunDetail).toMatchObject({
    status: 'completed',
    evaluation_status: 'completed',
    run_config: { symbol: 'XLB', start_date: retainedStudyStartDate, end_date: retainedStudyEndDate },
    dataset_manifest: {
      source: 'canonical_database',
      symbol: 'XLB',
      timeframe: 'D1',
      adjustment: 'split_adjusted',
      session: 'regular',
      start_date: retainedStudyStartDate,
      end_date: retainedStudyEndDate,
    },
  })
  const returnedManifest = returnedRunDetail.dataset_manifest!
  expect(Number.isInteger(returnedManifest.instrument_id)).toBe(true)
  expect(returnedManifest.instrument_id).toBeGreaterThan(0)
  expect(returnedManifest.metadata).toMatchObject({ symbol: 'XLB', instrument_id: returnedManifest.instrument_id })
  expect(returnedManifest.timestamps?.length).toBeGreaterThan(0)
  expect(returnedManifest.timestamps?.length).toBe(returnedManifest.closes?.length)
  expect(returnedManifest.closes?.every(value => typeof value === 'number' && Number.isFinite(value))).toBe(true)
  const firstReturnedBar = Date.parse(returnedManifest.timestamps![0])
  const lastReturnedBar = Date.parse(returnedManifest.timestamps![returnedManifest.timestamps!.length - 1])
  expect(Number.isFinite(firstReturnedBar)).toBe(true)
  expect(Number.isFinite(lastReturnedBar)).toBe(true)
  expect(firstReturnedBar).toBeGreaterThanOrEqual(Date.parse(`${retainedStudyStartDate}T00:00:00.000Z`))
  expect(lastReturnedBar).toBeLessThanOrEqual(Date.parse(`${retainedStudyEndDate}T23:59:59.999Z`))
  const coverage = returnedManifest.coverage_preflight?.items?.find(item => item.instrument_id === returnedManifest.instrument_id)
  expect(coverage).toMatchObject({ instrument_id: returnedManifest.instrument_id, status: 'ready' })
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
  await activateDockToolTab(page, 'Study Lab')
  const study = page.locator('.study-lab-tool:visible').last()
  await expect(study).toBeVisible({ timeout: 15_000 })
  await study.getByRole('combobox', { name: 'Factory study' }).selectOption('high_low_breakouts')
  const lookback = study.getByRole('spinbutton', { name: 'Study parameter lookback' })
  await expect(lookback).toHaveValue('20')
  await expect(lookback).toHaveAttribute('min', '2')
  await expect(lookback).toHaveAttribute('max', '252')
  await lookback.fill('10')
  await study.getByRole('textbox', { name: 'Study symbol' }).fill('SPY')
  await study.getByLabel('Study start date').fill(retainedStudyStartDate)
  await study.getByLabel('Study end date').fill(retainedStudyEndDate)

  const preparationResponse = page.waitForResponse(response => isStudyHistoryEnsure(
    response.request(),
    new Set(['SPY']),
    `${retainedStudyStartDate}T00:00:00.000Z`,
    `${retainedStudyEndDate}T23:59:59.999Z`,
  ))
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
    start_at: `${retainedStudyStartDate}T00:00:00.000Z`,
    end_at: `${retainedStudyEndDate}T23:59:59.999Z`,
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
    run_config: {
      symbol: 'SPY',
      parameters: { lookback: 10 },
      start_date: retainedStudyStartDate,
      end_date: retainedStudyEndDate,
    },
    dataset_manifest: { start_date: retainedStudyStartDate, end_date: retainedStudyEndDate },
  })

  try {
    await expect(study.locator('.study-lab-tool__run-status--completed')).toBeVisible({ timeout: 90_000 })
    await expect(study.getByRole('status', { name: /new_high_count metric/ })).toBeVisible()
    await expect(study.getByRole('status', { name: /new_low_count metric/ })).toBeVisible()
    const highCount = Number(await study.getByRole('status', { name: /new_high_count metric/ }).locator('strong').innerText())
    const lowCount = Number(await study.getByRole('status', { name: /new_low_count metric/ }).locator('strong').innerText())
    expect(Number.isFinite(highCount)).toBe(true)
    expect(highCount).toBeGreaterThan(0)
    expect(Number.isFinite(lowCount)).toBe(true)
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

test('legacy Strategy Lab creates, edits, reloads, and safely deletes a supported definition', async ({ page, loggedIn, browserDiagnostics }) => {
  const name = `Strategy lifecycle ${Date.now()}`
  const description = 'Ordinary supported local backtest definition lifecycle.'
  let localRunDispatches = 0
  page.on('request', request => {
    if (request.method() === 'POST' && /\/api\/v1\/strategy-lab\/versions\/\d+\/runs$/.test(new URL(request.url()).pathname)) localRunDispatches += 1
  })

  await page.goto('/chart')
  await expect(page.locator('.workspace-layout-host')).toBeVisible()
  await page.goto('/legacy/strategy-lab')
  await expect(page.locator('.strategy-lab-view')).toBeVisible()
  await page.getByRole('button', { name: 'Create new strategy', exact: true }).click()
  await page.getByPlaceholder('Momentum Continuation').fill(name)
  await page.getByLabel('Universe type').selectOption('symbols')
  const symbolPicker = page.getByRole('combobox', { name: 'Add symbol (e.g. AAPL)', exact: true })
  await symbolPicker.fill('SPY')
  const spyChoice = page.getByRole('listbox', { name: 'Symbol search results' }).getByRole('option', { name: /^SPY\b/ }).first()
  await expect(spyChoice).toBeVisible({ timeout: 15_000 })
  await spyChoice.click()
  const assertSelectedSpy = async () => {
    const spyChip = page.locator('.symbol-chip').filter({
      has: page.getByRole('button', { name: 'Remove SPY', exact: true }),
    })
    await expect(spyChip).toHaveCount(1)
    await expect(spyChip).toContainText(/^SPY/)
    await expect(spyChip.getByRole('button', { name: 'Remove SPY', exact: true })).toBeVisible()
  }
  await assertSelectedSpy()

  const createResponsePromise = page.waitForResponse(response => response.request().method() === 'POST'
    && new URL(response.url()).pathname === '/api/v1/strategy-lab/definitions')
  await page.getByRole('button', { name: 'Create strategy', exact: true }).click()
  const createResponse = await createResponsePromise
  expect(createResponse.status()).toBe(201)
  expect(createResponse.request().postDataJSON()).toMatchObject({
    initial_version: { universe_config: { symbols: ['SPY'] } },
  })
  const created = await createResponse.json() as { id?: number; name?: string; versions?: Array<{ id?: number; version_number?: number }> }
  expect(Number.isInteger(created.id)).toBe(true)
  expect(created.name).toBe(name)
  expect(created.versions?.length).toBeGreaterThan(0)
  const strategyTile = page.getByRole('button', { name: `Open strategy ${name}`, exact: true })
  await expect(strategyTile).toBeVisible()
  await expect(strategyTile).toContainText('v1')

  await page.getByPlaceholder('What market behaviour is this strategy trying to capture?').fill(description)
  const profileUpdatePromise = page.waitForResponse(response => response.request().method() === 'PATCH'
    && new URL(response.url()).pathname === `/api/v1/strategy-lab/definitions/${created.id}`)
  await page.getByRole('button', { name: 'Save profile', exact: true }).click()
  const profileUpdate = await profileUpdatePromise
  expect(profileUpdate.ok()).toBe(true)
  expect(profileUpdate.request().postDataJSON()).toMatchObject({ name, description })

  const entryLogic = page.locator('.panel').filter({ has: page.getByRole('button', { name: 'Entry logic', exact: true }) }).first()
  const entryLogicToggle = entryLogic.getByRole('button', { name: 'Entry logic', exact: true })
  if (await entryLogicToggle.getAttribute('aria-expanded') !== 'true') await entryLogicToggle.click()
  await entryLogic.getByRole('button', { name: /Add technical condition/ }).click()
  const rsiCondition = entryLogic.getByRole('group', { name: 'Condition 1 rule', exact: true })
  const conditionType = rsiCondition.getByRole('combobox', { name: 'Condition type', exact: true })
  await conditionType.selectOption({ label: 'Indicator vs Value' })
  await expect(conditionType).toHaveValue('indicator_threshold')
  const indicator = rsiCondition.getByRole('combobox', { name: 'Indicator', exact: true })
  await indicator.selectOption({ label: 'RSI - Relative Strength Index' })
  await expect(indicator).toHaveValue('rsi')
  const indicatorPeriod = rsiCondition.getByRole('spinbutton', { name: 'Period', exact: true })
  await indicatorPeriod.fill('14')
  await expect(indicatorPeriod).toHaveValue('14')
  const relationship = rsiCondition.getByRole('combobox', { name: 'Relationship', exact: true })
  await relationship.selectOption({ label: '>' })
  await expect(relationship).toHaveValue('gt')
  const thresholdValue = rsiCondition.getByRole('spinbutton', { name: 'Value', exact: true })
  await thresholdValue.fill('50')
  await expect(thresholdValue).toHaveValue('50')
  const revisionNote = entryLogic.getByRole('textbox', { name: 'Revision note', exact: true })
  await revisionNote.fill('Add a supported RSI entry rule for the retained local history window.')
  await expect(revisionNote).toHaveValue('Add a supported RSI entry rule for the retained local history window.')
  const publishRevisionPromise = page.waitForResponse(response => response.request().method() === 'POST'
    && new URL(response.url()).pathname === `/api/v1/strategy-lab/definitions/${created.id}/versions`)
  await page.getByRole('button', { name: 'Publish revision', exact: true }).click()
  const publishedVersionResponse = await publishRevisionPromise
  expect(publishedVersionResponse.status()).toBe(201)
  const publishedVersion = await publishedVersionResponse.json() as { id?: number; version_number?: number }
  expect(Number.isInteger(publishedVersion.id)).toBe(true)
  expect(publishedVersion.version_number).toBe(2)
  await expect(page.getByRole('button', { name: `Open strategy ${name}`, exact: true })).toContainText('v2')

  await page.reload()
  await expect(page.locator('.strategy-lab-view')).toBeVisible()
  await page.getByRole('button', { name: `Open strategy ${name}`, exact: true }).click()
  await expect(page.getByPlaceholder('Momentum Continuation')).toHaveValue(name)
  await expect(page.getByPlaceholder('What market behaviour is this strategy trying to capture?')).toHaveValue(description)
  await assertSelectedSpy()

  const runHistoryToggle = page.getByRole('button', { name: /^Research runs/ })
  if (await runHistoryToggle.getAttribute('aria-expanded') !== 'true') await runHistoryToggle.click()
  await page.getByLabel('Date from').fill('2024-01-01')
  await page.getByLabel('Date to').fill('2025-12-29')
  await page.getByLabel('Run timeframe').selectOption('D1')
  await expect(page.getByRole('button', { name: 'Backtest', exact: true })).toHaveAttribute('aria-pressed', 'true')
  const runSubmissionPromise = page.waitForResponse(response => response.request().method() === 'POST'
    && new URL(response.url()).pathname === `/api/v1/strategy-lab/versions/${publishedVersion.id}/runs`)
  await page.getByRole('button', { name: 'Run backtest', exact: true }).click()
  const runSubmission = await runSubmissionPromise
  expect(runSubmission.status()).toBe(201)
  const submittedRun = await runSubmission.json() as { id?: number; strategy_id?: number; strategy_version_id?: number; test_mode?: string; status?: string }
  expect(Number.isInteger(submittedRun.id)).toBe(true)
  expect(submittedRun).toMatchObject({ strategy_id: created.id, strategy_version_id: publishedVersion.id, test_mode: 'backtest' })
  expect(runSubmission.request().postDataJSON()).toMatchObject({
    test_mode: 'backtest',
    timeframe: 'D1',
    date_from: '2024-01-01T00:00:00Z',
    date_to: '2025-12-29T23:59:59Z',
  })
  expect(localRunDispatches).toBe(1)
  await expect(page.locator('.run-batch--active .status-chip--completed')).toBeVisible()
  await expect(page.locator('.panel--results .run-detail')).toBeVisible()
  const persistedRunRead = await authenticatedJson(page, `/api/v1/strategy-lab/runs/${submittedRun.id}`)
  expect(persistedRunRead.status).toBe(200)
  expect(persistedRunRead.body).toMatchObject({
    id: submittedRun.id,
    strategy_id: created.id,
    strategy_version_id: publishedVersion.id,
    test_mode: 'backtest',
    status: 'completed',
  })
  expect(String(persistedRunRead.body.date_from)).toMatch(/^2024-01-01T00:00:00/)
  expect(String(persistedRunRead.body.date_to)).toMatch(/^2025-12-29T23:59:59/)
  const localResult = persistedRunRead.body.result_summary as {
    result_kind?: string
    timeframe?: string
    equity_curve?: Array<{ equity?: unknown }>
    universe?: { resolved_symbols?: string[] }
    coverage?: {
      requested_date_from?: string
      requested_date_to?: string
      simulatable_symbols?: string[]
      simulatable_instrument_count?: number
      total_bars?: number
    }
    performance?: { initial_capital?: number; ending_capital?: number; trade_count?: number }
  }
  expect(localResult.result_kind).toBe('rules_backtest')
  expect(localResult.timeframe).toBe('D1')
  expect(localResult.universe?.resolved_symbols).toContain('SPY')
  expect(localResult.coverage?.simulatable_symbols).toContain('SPY')
  expect(localResult.coverage?.simulatable_instrument_count).toBeGreaterThan(0)
  expect(localResult.coverage?.total_bars).toBeGreaterThan(0)
  expect(localResult.coverage?.requested_date_from).toMatch(/^2024-01-01T00:00:00/)
  expect(localResult.coverage?.requested_date_to).toMatch(/^2025-12-29T23:59:59/)
  expect(localResult.equity_curve?.length).toBeGreaterThan(1)
  expect(localResult.equity_curve?.every(point => typeof point.equity === 'number' && Number.isFinite(point.equity))).toBe(true)
  expect(Number.isFinite(localResult.performance?.initial_capital)).toBe(true)
  expect(Number.isFinite(localResult.performance?.ending_capital)).toBe(true)
  expect(Number.isInteger(localResult.performance?.trade_count)).toBe(true)
  expect(localResult.performance?.trade_count).toBeGreaterThan(0)
  expect(persistedRunRead.body.artifact_manifest).toMatchObject({ result_kind: 'rules_backtest' })

  const researchRunsPanel = page.locator('.panel').filter({
    has: page.getByRole('button', { name: 'Research runs', exact: true }),
  }).first()
  await expect(researchRunsPanel.getByRole('button', { name: 'Research runs', exact: true }))
    .toHaveAttribute('aria-expanded', 'true')
  await expect(researchRunsPanel.getByRole('button', { name: /Run history \d+ batch(?:es)?/ }))
    .toHaveAttribute('aria-expanded', 'true')
  await expect(researchRunsPanel.locator('.run-item[aria-pressed="true"]')).toHaveCount(1)
  const resultsPanel = page.locator('.panel.panel--results')
  await expect(resultsPanel.getByRole('button', { name: 'Results', exact: true }))
    .toHaveAttribute('aria-expanded', 'true')
  await expect(resultsPanel.locator('.run-detail')).toBeVisible()
  await expect(resultsPanel.getByText('Realized return', { exact: true })).toBeVisible()

  const exportPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export', exact: true }).click()
  await page.getByRole('menuitem', { name: 'Export summary', exact: true }).click()
  const summaryDownload = await exportPromise
  expect(summaryDownload.suggestedFilename()).toBe(`strategy-run-${submittedRun.id}.json`)

  await page.getByRole('button', { name: 'Delete strategy', exact: true }).click()
  const deleteDialog = page.getByRole('dialog', { name: 'Delete Strategy' })
  await expect(deleteDialog).toBeVisible()
  await deleteDialog.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(deleteDialog).toHaveCount(0)
  await expect(page.getByRole('button', { name: `Open strategy ${name}`, exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Delete strategy', exact: true }).click()
  const confirmDialog = page.getByRole('dialog', { name: 'Delete Strategy' })
  const deleteResponsePromise = page.waitForResponse(response => response.request().method() === 'DELETE'
    && new URL(response.url()).pathname === `/api/v1/strategy-lab/definitions/${created.id}`)
  await confirmDialog.getByRole('button', { name: 'Delete', exact: true }).click()
  expect((await deleteResponsePromise).ok()).toBe(true)
  await expect(page.getByRole('button', { name: `Open strategy ${name}`, exact: true })).toHaveCount(0)
  await page.goBack()
  await expect(page.locator('.workspace-layout-host')).toBeVisible()
  await browserDiagnostics.expectNoCriticalIssues()
})

test('Strategy Lab v2 reads a selected owner resource and recovers from a denied reference without writes', async ({ page, loggedIn, browserDiagnostics }) => {
  test.setTimeout(60_000)
  const resource = { type: 'strategies', id: 'controlled-owner-resource', attributes: { name: 'Controlled read-only owner resource', status: 'saved' } }
  const pinAttributes = {
    research_run_id: 41,
    code_version_id: 57,
    artifact_id: 73,
    artifact_name: 'current_streak',
    artifact_type: 'scalar',
    output_contract: 'study',
    run_reproducibility_hash: 'a'.repeat(64),
    code_version_digest: `sha256:${'b'.repeat(64)}`,
    dataset_manifest_digest: `sha256:${'c'.repeat(64)}`,
    artifact_content_digest: `sha256:${'d'.repeat(64)}`,
  }
  const writes: string[] = []
  let pinAttempts = 0
  page.on('request', request => {
    const url = new URL(request.url())
    if (url.pathname.startsWith('/api/v1/strategy-lab/v2/') && request.method() !== 'GET') writes.push(`${request.method()} ${url.pathname}`)
  })
  await page.route(url => url.pathname === '/api/v1/strategy-lab/v2/strategies', async route => {
    if (route.request().method() !== 'GET') return route.continue()
    await route.fulfill({ status: 200, json: { data: [resource], links: {} } })
  })
  await page.route(url => url.pathname === '/api/v1/strategy-lab/v2/strategies/controlled-owner-resource', async route => {
    if (route.request().method() !== 'GET') return route.continue()
    await route.fulfill({ status: 200, json: { data: resource } })
  })
  await page.route(url => url.pathname === '/api/v1/strategy-lab/v2/trials', async route => {
    if (route.request().method() !== 'GET') return route.continue()
    await route.fulfill({ status: 200, json: { data: [], links: {} } })
  })
  await page.route(url => url.pathname === '/api/v1/strategy-lab/v2/artifacts', async route => {
    if (route.request().method() !== 'GET') return route.continue()
    await route.fulfill({ status: 200, json: { data: [], links: {} } })
  })
  await page.route(url => url.pathname.startsWith('/api/v1/strategy-lab/v2/study-artifact-references/41/'), async route => {
    if (route.request().method() !== 'GET') return route.continue()
    pinAttempts += 1
    if (new URL(route.request().url()).pathname.endsWith('/999')) {
      await route.fulfill({ status: 404, json: { detail: 'Study artifact reference not found' } })
      return
    }
    await route.fulfill({ status: 200, json: { data: { type: 'study-artifact-references', id: '41:73', attributes: pinAttributes } } })
  })

  await page.goto('/legacy/strategy-lab-v2')
  for (const [label, path, empty] of [
    ['Trials', '/api/v1/strategy-lab/v2/trials', 'No trials are available for this account yet.'],
    ['Artifacts', '/api/v1/strategy-lab/v2/artifacts', 'No artifacts are available for this account yet.'],
  ] as const) {
    const collectionRead = page.waitForResponse(response => response.request().method() === 'GET'
      && new URL(response.url()).pathname === path)
    await page.getByRole('button', { name: new RegExp(`^${label}`) }).click()
    expect((await collectionRead).status()).toBe(200)
    await expect(page.getByText(empty, { exact: true })).toBeVisible()
  }
  await page.getByRole('button', { name: /^Strategies/ }).click()
  const strategyRow = page.getByRole('button', { name: /Controlled read-only owner resource/ })
  await expect(strategyRow).toBeVisible()
  await strategyRow.click()
  await expect(page.getByRole('article', { name: 'Selected resource detail' })).toContainText('Controlled read-only owner resource')
  await expect(page.getByText('Persisted attributes')).toBeVisible()

  await page.getByRole('textbox', { name: 'Research run ID' }).fill('41')
  await page.getByRole('textbox', { name: 'Artifact ID' }).fill('999')
  await page.getByRole('button', { name: 'Inspect immutable pin', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Study artifact reference not found')
  await page.getByRole('textbox', { name: 'Artifact ID' }).fill('73')
  await page.getByRole('button', { name: 'Inspect immutable pin', exact: true }).click()
  const resolvedPin = page.getByRole('region', { name: 'Resolved Study pin' })
  await expect(resolvedPin).toContainText('current_streak')
  await expect(resolvedPin).toContainText('artifact_content_digest')
  expect(pinAttempts).toBe(2)
  expect(writes).toEqual([])
  await page.getByRole('link', { name: 'Back to workstation', exact: true }).click()
  await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
  await browserDiagnostics.expectNoCriticalIssues()
})

test('Study preparation submits every universe member and benchmark while one member is held', async ({ page, loggedIn, browserDiagnostics }) => {
  const submittedTargets: Array<{ kind: string; symbol?: string }> = []
  const requestedDatasets = new Map<string, string[]>()
  let resolveAllSubmitted!: () => void
  const allSubmitted = new Promise<void>(resolve => { resolveAllSubmitted = resolve })
  let resolveHeldPrimary!: () => void
  const heldPrimary = new Promise<void>(resolve => { resolveHeldPrimary = resolve })
  const responseFor = (requestId: string, status: 'queued' | 'ready' | 'unavailable', version: number, symbol: string, datasets: readonly string[]) => {
    const dependencies = datasets.map(dataset => {
      const dependencyStatus = status === 'unavailable' && dataset === 'history' ? 'unavailable' : status === 'unavailable' ? 'ready' : status
      return {
        dependency_id: `${requestId}:${dataset}`,
        depends_on: [],
        instrument_id: null,
        symbol,
        dataset,
        status: dependencyStatus,
        requested_start: null,
        requested_end: null,
        covered_start: null,
        covered_end: null,
        reason_code: dependencyStatus === 'unavailable' ? 'no_eligible_history_provider' : null,
        retry_at: null,
        updated_at: '2026-11-06T12:00:01Z',
        covered_ranges: [],
      }
    })
    const completed = dependencies.filter(dependency => !['queued', 'running', 'partial'].includes(dependency.status)).length
    return {
      request_id: requestId,
      status,
      has_pending_work: status === 'queued',
      created_at: '2026-11-06T12:00:00Z',
      updated_at: '2026-11-06T12:00:01Z',
      version,
      target: { kind: 'instrument', symbol },
      dependencies,
      completed,
      total: dependencies.length,
      last_progress_at: '2026-11-06T12:00:01Z',
    }
  }

  const studySymbols = new Set(['SPY', 'XLK', 'QQQ'])
  await page.route('**/api/v1/data/**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    // Workstation shell identity/profile/history startup requests pass through;
    // only Study Lab's history-only fan-out is counted in this held-member fixture.
    if (isStudyHistoryEnsure(request, studySymbols)) {
      const body = request.postDataJSON() as { target: { kind: string; symbol?: string }; datasets?: string[] }
      submittedTargets.push(body.target)
      if (submittedTargets.length === 3) resolveAllSubmitted()
      const symbol = body.target.symbol ?? `target-${submittedTargets.length}`
      const datasets = body.datasets ?? ['history']
      requestedDatasets.set(`study-${symbol}`, datasets)
      await route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify(responseFor(`study-${symbol}`, 'queued', 1, symbol, datasets)) })
      return
    }
    const poll = url.pathname.match(/\/api\/v1\/data\/requests\/(study-[^/]+)$/)
    if (request.method() === 'GET' && poll) {
      const requestId = decodeURIComponent(poll[1])
      const symbol = requestId.replace(/^study-/, '')
      if (symbol === 'SPY') await heldPrimary
      const status = symbol === 'SPY' ? 'unavailable' : 'ready'
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(responseFor(requestId, status, 2, symbol, requestedDatasets.get(requestId) ?? ['history'])) })
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
  await activateDockToolTab(page, 'Study Lab')
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

  const studySymbols = new Set(['SPY', 'QQQ', 'XLB'])
  await page.route('**/api/v1/data/**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    if (isStudyHistoryEnsure(request, studySymbols)) {
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
    const poll = url.pathname.match(/\/api\/v1\/data\/requests\/(context-[^/]+)$/)
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
  await activateDockToolTab(page, 'Study Lab')
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
  await activateDockToolTab(page, 'Study Results')
  const results = page.locator('.research-results-tool:visible').last()
  await expect(results).toBeVisible({ timeout: 20_000 })
  await expect(page.locator('.research-results-tool:visible')).toHaveCount(1)
  await expect(results.getByRole('button', { name: 'Run 8000, completed, 3 artifacts' })).toBeVisible()
  const runList = results.getByRole('list', { name: 'Persisted research runs' })
  await expect(runList.getByRole('button', { name: 'Run 8000, completed, 3 artifacts', exact: true })).toBeVisible()
  await expect(runList.getByRole('button', { name: 'Run 7999, queued, 0 artifacts', exact: true })).toBeVisible()
  const selectedDetail = results.locator('article[aria-label="Research run 8000 details"]')
  await expect(selectedDetail.locator('.research-results-tool__artifacts > article')).toHaveCount(3)

  await results.getByRole('button', { name: 'Load older runs', exact: true }).click()
  await expect(results.getByRole('button', { name: 'Run 7900, completed, 0 artifacts' })).toBeVisible()

  await results.getByRole('checkbox', { name: 'Compare run 8000' }).check()
  await results.getByRole('checkbox', { name: 'Compare run 7999' }).check()
  await results.getByRole('button', { name: 'Compare', exact: true }).click()
  await expect(results).toContainText('Run 8000 vs 7999')

  await results.getByRole('button', { name: 'Run 8000, completed, 3 artifacts' }).click()
  await selectedDetail.getByRole('searchbox', { name: 'occurrences symbol filter' }).fill('SPY')
  await selectedDetail.getByRole('combobox', { name: 'occurrences event type filter' }).selectOption('member_entered')
  await expect(selectedDetail.getByRole('list', { name: 'occurrences filtered occurrences' }).getByRole('listitem')).toHaveCount(1)

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

test('Results detail exposes a single controlled failure and explicit Retry loads saved artifacts', async ({ page, loggedIn, browserDiagnostics }) => {
  const responseId = crypto.randomUUID()
  const summary = recoveryRun(8201, 'completed', 1)
  const detail = recoveryRun(8201, 'completed', 1, [
    { id: 9201, name: 'current_streak', artifact_type: 'scalar', payload: { type: 'scalar', value: 4 } },
  ])
  let detailRequests = 0
  await page.route('**/api/v1/research/runs**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    if (request.method() === 'GET' && url.pathname === '/api/v1/research/runs') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([summary]) })
      return
    }
    if (request.method() === 'GET' && url.pathname === '/api/v1/research/runs/8201') {
      detailRequests += 1
      if (detailRequests === 1) {
        await route.fulfill(controlled503(responseId))
      } else {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(detail) })
      }
      return
    }
    await route.continue()
  })
  browserDiagnostics.allowExpectedControlledApiResponseFault(
    controlledResponseUrl('/research/runs/8201'), 'GET', responseId,
  )

  const results = await openStudyResultsTool(page)
  await expect(results.getByRole('button', { name: 'Run 8201, completed, 1 artifact' })).toBeVisible()
  await expect(results.getByRole('alert')).toContainText(responseId)
  expect(detailRequests).toBe(1)

  const retryRequest = page.waitForRequest(request =>
    request.method() === 'GET' && new URL(request.url()).pathname === '/api/v1/research/runs/8201',
  )
  await results.getByRole('button', { name: 'Retry', exact: true }).click()
  await retryRequest
  const selectedDetail = results.locator('article[aria-label="Research run 8201 details"]')
  await expect(selectedDetail.locator('.research-results-tool__artifacts > article[aria-label="current_streak scalar result"]')).toBeVisible()
  await expect(selectedDetail.locator('.research-results-tool__artifacts > article')).toHaveCount(1)
  expect(detailRequests).toBe(2)
  await browserDiagnostics.expectNoCriticalIssues()
})

test('Results keeps queued cancel available after one controlled failure and retries to canceled', async ({ page, loggedIn, browserDiagnostics }) => {
  const responseId = crypto.randomUUID()
  let currentRun = recoveryRun(8202, 'queued')
  let cancelRequests = 0
  await page.route('**/api/v1/research/runs**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    if (request.method() === 'GET' && url.pathname === '/api/v1/research/runs') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([currentRun]) })
      return
    }
    if (request.method() === 'POST' && url.pathname === '/api/v1/research/runs/8202/cancel') {
      cancelRequests += 1
      if (cancelRequests === 1) {
        await route.fulfill(controlled503(responseId))
      } else {
        currentRun = { ...currentRun, status: 'canceled' }
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(currentRun) })
      }
      return
    }
    await route.continue()
  })
  browserDiagnostics.allowExpectedControlledApiResponseFault(
    controlledResponseUrl('/research/runs/8202/cancel'), 'POST', responseId,
  )

  const results = await openStudyResultsTool(page)
  await expect(results.getByRole('button', { name: 'Run 8202, queued, 0 artifacts' })).toBeVisible()
  await results.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(results.getByRole('alert')).toContainText(responseId)
  await expect(results.getByRole('button', { name: 'Cancel', exact: true })).toBeEnabled()
  expect(cancelRequests).toBe(1)
  const runList = results.getByRole('list', { name: 'Persisted research runs' })
  await expect(runList.getByRole('button', { name: 'Run 8202, queued, 0 artifacts', exact: true })).toHaveCount(1)

  await results.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(results.getByRole('button', { name: 'Run 8202, canceled, 0 artifacts' })).toBeVisible()
  expect(cancelRequests).toBe(2)
  await browserDiagnostics.expectNoCriticalIssues()
})

test('Results creates no rerun after a controlled failure and the explicit retry queues one snapshot', async ({ page, loggedIn, browserDiagnostics }) => {
  const responseId = crypto.randomUUID()
  const sourceRun = recoveryRun(8203, 'completed')
  let runs = [sourceRun]
  let rerunRequests = 0
  const acceptedRun = recoveryRun(8210, 'queued')
  await page.route('**/api/v1/research/runs**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    if (request.method() === 'GET' && url.pathname === '/api/v1/research/runs') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(runs) })
      return
    }
    if (request.method() === 'POST' && url.pathname === '/api/v1/research/runs/8203/rerun') {
      expect(url.searchParams.get('snapshot')).toBe('true')
      rerunRequests += 1
      if (rerunRequests === 1) {
        await route.fulfill(controlled503(responseId))
      } else {
        runs = [acceptedRun, sourceRun]
        await route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify(acceptedRun) })
      }
      return
    }
    await route.continue()
  })
  browserDiagnostics.allowExpectedControlledApiResponseFault(
    controlledResponseUrl('/research/runs/8203/rerun?snapshot=true'), 'POST', responseId,
  )

  const results = await openStudyResultsTool(page)
  await expect(results.getByRole('button', { name: 'Run 8203, completed, 0 artifacts' })).toBeVisible()
  await results.getByRole('button', { name: 'Rerun snapshot', exact: true }).click()
  await expect(results.getByRole('alert')).toContainText(responseId)
  await expect(results.getByRole('button', { name: 'Run 8210, queued, 0 artifacts' })).toHaveCount(0)
  await expect(results.getByRole('button', { name: 'Rerun snapshot', exact: true })).toBeEnabled()
  expect(rerunRequests).toBe(1)
  const runList = results.getByRole('list', { name: 'Persisted research runs' })
  await expect(runList.getByRole('button', { name: 'Run 8203, completed, 0 artifacts', exact: true })).toHaveCount(1)

  await results.getByRole('button', { name: 'Rerun snapshot', exact: true }).click()
  await expect(results.getByRole('button', { name: 'Run 8210, queued, 0 artifacts' })).toBeVisible()
  await expect(runList.getByRole('button', { name: 'Run 8210, queued, 0 artifacts', exact: true })).toHaveCount(1)
  expect(rerunRequests).toBe(2)
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
  const seededAssetsResponsePromise = page.waitForResponse(response => response.request().method() === 'GET'
    && new URL(response.url()).pathname === '/api/v1/code/assets')
  await page.getByRole('menu', { name: 'Workstation tools' }).getByRole('menuitem', { name: 'Python Library', exact: true }).click()
  await activateDockToolTab(page, 'Python Library')
  const library = page.locator('.code-library-tool:visible').last()
  const seededAssetsResponse = await seededAssetsResponsePromise
  expect(seededAssetsResponse.status()).toBe(200)
  const seededAssets = await seededAssetsResponse.json() as Array<{ stable_key?: string; name?: string }>
  expect(seededAssets).toEqual(expect.arrayContaining([expect.objectContaining({ stable_key: 'seed-study', name: 'Seed Study' })]))
  await expect(library).toBeVisible({ timeout: 20_000 })
  await expect(library.getByRole('listitem').filter({ hasText: 'Seed Study' })).toBeVisible({ timeout: 20_000 })

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

  // The visible control is a text input (textbox), not type=search/searchbox.
  await library.getByRole('textbox', { name: 'Filter Python assets' }).fill('Imported')
  await expect(imported).toBeVisible()
  await expect(created).toHaveCount(0)
  await browserDiagnostics.expectNoCriticalIssues()
})

test('closing Study Lab while run creation is pending preserves the durable run in Results', async ({ page, loggedIn, browserDiagnostics }) => {
  test.setTimeout(150_000)
  let signalCreateStarted!: () => void
  let releaseCreate!: () => void
  const createStarted = new Promise<void>(resolve => { signalCreateStarted = resolve })
  const createGate = new Promise<void>(resolve => { releaseCreate = resolve })
  const cancellationRequests: string[] = []
  await page.route('**/api/v1/research/runs', async route => {
    const request = route.request()
    if (request.method() === 'POST') {
      signalCreateStarted()
      await createGate
    }
    await route.continue()
  })
  page.on('request', request => {
    if (request.method() === 'POST' && new URL(request.url()).pathname.endsWith('/cancel')) {
      cancellationRequests.push(new URL(request.url()).pathname)
    }
  })

  await page.goto('/chart')
  await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: 'Study', exact: true }).click()
  await activateDockToolTab(page, 'Study Results')
  const results = page.locator('.research-results-tool:visible').last()
  await expect(results).toBeVisible({ timeout: 20_000 })
  const resultsRegion = page.getByRole('region', { name: 'Study Lab research results' }).last()
  await expect(resultsRegion.getByRole('status')).toContainText('No persisted studies yet. Run a study in the adjacent Study Lab pane.')
  await activateDockToolTab(page, 'Study Lab')
  const study = page.locator('.study-lab-tool:visible').last()
  await study.getByRole('textbox', { name: 'Study symbol' }).fill('SPY')
  await study.getByLabel('Study start date').fill(retainedStudyStartDate)
  await study.getByLabel('Study end date').fill(retainedStudyEndDate)
  const preparationResponse = page.waitForResponse(response => isStudyHistoryEnsure(
    response.request(),
    new Set(['SPY']),
    `${retainedStudyStartDate}T00:00:00.000Z`,
    `${retainedStudyEndDate}T23:59:59.999Z`,
  ))
  const validationResponse = page.waitForResponse(response => response.request().method() === 'POST'
    && new URL(response.url()).pathname.endsWith('/code/validate'))
  await study.getByRole('button', { name: 'Validate study', exact: true }).click()
  const prepared = await preparationResponse
  expect(prepared.ok()).toBe(true)
  expect(prepared.request().postDataJSON()).toMatchObject({
    target: { kind: 'instrument', symbol: 'SPY' },
    datasets: ['history'],
    timeframe: 'D1',
    adjusted: true,
    start_at: `${retainedStudyStartDate}T00:00:00.000Z`,
    end_at: `${retainedStudyEndDate}T23:59:59.999Z`,
  })
  expect((await validationResponse).ok()).toBe(true)
  await expect(study).toContainText('Validated for isolated execution', { timeout: 90_000 })

  const createdRequest = page.waitForRequest(request => request.method() === 'POST'
    && new URL(request.url()).pathname.endsWith('/research/runs'))
  const createdResponse = page.waitForResponse(response => response.request().method() === 'POST'
    && new URL(response.url()).pathname.endsWith('/research/runs'))
  await study.getByRole('button', { name: 'Run study', exact: true }).click()
  await createStarted
  expect((await createdRequest).postDataJSON()).toMatchObject({
    run_config: { start_date: retainedStudyStartDate, end_date: retainedStudyEndDate },
    dataset_manifest: { start_date: retainedStudyStartDate, end_date: retainedStudyEndDate },
  })
  const studyWindow = page.locator('.tool-window').filter({ has: study })
  await studyWindow.getByRole('button', { name: 'Close tool', exact: true }).click()
  await expect(study).toBeHidden()

  releaseCreate()
  const created = await createdResponse
  expect(created.status()).toBe(202)
  const run = await created.json() as { id: number }
  await activateDockToolTab(page, 'Study Results')
  const runRow = results.getByRole('button', { name: new RegExp(`^Run ${run.id},`) })
  await expect(runRow).toBeVisible({ timeout: 15_000 })
  expect(await runRow.getAttribute('aria-label')).not.toContain('canceled')
  expect(cancellationRequests).toEqual([])
  await browserDiagnostics.expectNoCriticalIssues()
})
