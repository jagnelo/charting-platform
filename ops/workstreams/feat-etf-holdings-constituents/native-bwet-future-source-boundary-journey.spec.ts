import { expect, test } from '../../../frontend/tests/e2e/helpers'
import type { APIRequestContext, Page, Request, TestInfo } from '@playwright/test'

type Listing = { instrument_id: number; symbol: string; name: string }
type Bar = { ts: string; open: number; high: number; low: number; close: number }
type PreparationDependency = {
  dataset: string
  instrument_id: number | null
  symbol: string | null
  status: string
  reason_code: string | null
  covered_start: string | null
  covered_end: string | null
  covered_ranges: Array<{ start_at: string; end_at: string }>
}
type Preparation = {
  request_id: string
  status: string
  dependencies: PreparationDependency[]
}

function selectedDatasetEnsure(request: Request, symbol: string, instrumentId: number, dataset: 'history' | 'holdings'): boolean {
  if (request.method() !== 'POST' || new URL(request.url()).pathname !== '/api/v1/data/ensure') return false
  try {
    const body = request.postDataJSON() as {
      target?: { kind?: string; symbol?: string; instrument_id?: number }
      datasets?: string[]
    }
    return body.target?.kind === 'instrument'
      && body.target.instrument_id === instrumentId
      && (!body.target.symbol || body.target.symbol.trim().toUpperCase() === symbol)
      && (body.datasets ?? []).includes(dataset)
  } catch { return false }
}

async function selectKnownBWET(page: Page): Promise<{
  listing: Listing
  historyRequest: Promise<Request>
  holdingsRequest: Promise<Request>
}> {
  const input = page.getByRole('combobox', { name: 'Active symbol' })
  const searchPromise = page.waitForResponse(response => {
    const url = new URL(response.url())
    return url.pathname === '/api/v1/instruments/search' && url.searchParams.get('q')?.toUpperCase() === 'BWET'
  })
  await input.fill('BWET')
  const search = await searchPromise
  expect(search.status(), 'Normal BWET symbol search').toBe(200)
  const listings = (await search.json() as Listing[]).filter(item => item.symbol.trim().toUpperCase() === 'BWET')
  expect(listings, 'The ordinary local picker must resolve one canonical BWET listing').toHaveLength(1)

  const listing = listings[0]!
  const option = page.getByRole('option', { name: /^BWET\b/ })
  await expect(option).toHaveCount(1)
  const historyRequest = page.waitForRequest(item => selectedDatasetEnsure(item, 'BWET', listing.instrument_id, 'history'), { timeout: 30_000 })
  const holdingsRequest = page.waitForRequest(item => selectedDatasetEnsure(item, 'BWET', listing.instrument_id, 'holdings'), { timeout: 30_000 })
  await option.click()
  await expect(input).toHaveValue('BWET')
  return { listing, historyRequest, holdingsRequest }
}

async function readPreparation(request: APIRequestContext, requestId: string, token: string): Promise<Preparation> {
  const response = await request.get(`/api/v1/data/requests/${encodeURIComponent(requestId)}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(response.status(), `Read ordinary preparation status ${requestId}`).toBe(200)
  const body = await response.json() as Preparation
  expect(body.request_id).toBe(requestId)
  return body
}

async function waitForFutureDatedHoldings(
  request: APIRequestContext,
  requestId: string,
  token: string,
): Promise<Preparation> {
  let latest: Preparation | null = null
  await expect.poll(async () => {
    const response = await request.get(`/api/v1/data/requests/${encodeURIComponent(requestId)}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (response.status() !== 200) return false
    latest = await response.json() as Preparation
    const dependency = latest.dependencies.find(item => item.dataset === 'holdings')
    return dependency?.status === 'failed' && dependency.reason_code === 'future_dated_source'
  }, {
    message: 'Normal BWET preparation status should retain the typed future-source boundary',
    timeout: 120_000,
    intervals: [250, 500, 1_000, 2_000],
  }).toBeTruthy()
  expect(latest).toBeTruthy()
  return latest!
}

async function assertExistingBWETPriceHistory(
  page: Page,
  request: APIRequestContext,
  token: string,
): Promise<Bar[]> {
  await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue('BWET')
  await expect.poll(async () => {
    const response = await request.get('/api/v1/ohlcv/local/BWET/D1', {
      headers: { Authorization: `Bearer ${token}` }, params: { limit: 500, adjusted: 'true' },
    })
    return response.status() === 200 ? (await response.json() as Bar[]).length : 0
  }, { message: 'Existing BWET daily history must remain available independently of holdings', timeout: 30_000 })
    .toBeGreaterThan(1)
  const response = await request.get('/api/v1/ohlcv/local/BWET/D1', {
    headers: { Authorization: `Bearer ${token}` }, params: { limit: 500, adjusted: 'true' },
  })
  expect(response.status()).toBe(200)
  const bars = await response.json() as Bar[]
  expect(bars.every(bar => Number.isFinite(Date.parse(bar.ts))
    && [bar.open, bar.high, bar.low, bar.close].every(Number.isFinite))).toBeTruthy()

  const chart = page.getByRole('region', { name: 'Chart workspace' }).first()
  await expect(chart).toHaveAttribute('aria-busy', 'false')
  const plot = chart.locator('.uplot').first()
  await expect(plot).toBeVisible()
  // This is the same rendered price-canvas witness used by the frozen native
  // three-ETF proof: overlay existence alone cannot satisfy the assertion.
  await expect.poll(() => plot.locator('canvas:not(.drawing-canvas)').first().evaluate(canvas => {
    const element = canvas as HTMLCanvasElement
    if (element.width < 2 || element.height < 2) return 0
    const data = element.getContext('2d')?.getImageData(0, 0, element.width, element.height).data
    if (!data) return 0
    const colors = new Set<string>()
    let painted = 0
    for (let y = Math.floor(element.height * 0.05); y < element.height * 0.95; y += 1) {
      for (let x = Math.floor(element.width * 0.1); x < element.width * 0.98; x += 1) {
        const offset = (y * element.width + x) * 4
        if (data[offset + 3] === 0) continue
        painted += 1
        colors.add(`${data[offset]},${data[offset + 1]},${data[offset + 2]}`)
      }
    }
    return colors.size >= 3 ? painted : 0
  }), { message: 'Actual BWET price series should paint the price canvas', timeout: 15_000 }).toBeGreaterThan(10)

  const box = await plot.boundingBox()
  expect(box && box.width > 100 && box.height > 80).toBeTruthy()
  await page.mouse.move(box!.x + box!.width * 0.62, box!.y + box!.height * 0.48)
  const tooltip = chart.locator('.ohlcv-info')
  await expect(tooltip).toBeVisible()
  const close = (await tooltip.locator('.tt-item').filter({ hasText: /^C\s/ }).innerText())
    .replace(/^C\s*/, '').trim()
  const bar = bars.find(item => item.close.toFixed(4) === close)
  expect(bar, 'BWET tooltip close must match a real returned local bar').toBeTruthy()
  const date = await page.evaluate(ts => {
    const value = new Date(ts)
    return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`
  }, bar!.ts)
  await expect(tooltip.locator('.tt-date')).toHaveText(date)
  return bars
}

async function assertNoCurrentBWETHoldings(request: APIRequestContext, token: string): Promise<void> {
  const latest = await request.get('/api/v1/etf-holdings/BWET/latest', {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(latest.status(), 'Future-dated BWET composition must not become a current snapshot').toBe(404)
}

async function assertFutureReasonVisible(page: Page): Promise<void> {
  const notice = page.locator('.workstation__selection-acquisition')
    .filter({ has: page.locator('summary[aria-label^="Holdings"]') }).first()
  await expect(notice, 'The selected BWET context should expose its separate holdings outcome').toBeVisible()
  const summary = notice.locator('summary')
  await expect(summary).toHaveAttribute('aria-label', /Holdings.*current view remains usable/i)
  await summary.click()
  await expect(notice.locator('.compact-status__detail'))
    .toContainText('A reviewed data source could not complete this request.')
  await expect(notice.locator('.compact-status__detail')).toContainText('Your current view remains usable.')
}

async function assertNoPriorFundRows(page: Page): Promise<void> {
  await expect(page.getByTestId('active-holding-lineage')).toHaveCount(0)
  await expect(page.locator('.constituent-tool').getByRole('option')).toHaveCount(0)
}

async function awaitObservedDatasetRequest(request: Request): Promise<{ request: Request; requestId: string }> {
  const response = await request.response()
  expect(response, 'Normal selected-fund preparation should return an HTTP response').toBeTruthy()
  expect(response!.status(), 'Normal selected-fund preparation is accepted').toBe(202)
  const body = await response!.json() as { request_id?: string }
  expect(body.request_id, 'Normal selected-fund preparation has a durable request ID').toBeTruthy()
  return { request, requestId: body.request_id! }
}

async function assertSelectedHistoryPreparation(request: APIRequestContext, requestId: string, token: string): Promise<Preparation> {
  let latest: Preparation | null = null
  await expect.poll(async () => {
    latest = await readPreparation(request, requestId, token)
    const history = latest.dependencies.find(item => item.dataset === 'history')
    return Boolean(history && ['ready', 'partial'].includes(history.status)
      && (history.covered_ranges.length > 0 || (history.covered_start && history.covered_end)))
  }, { message: 'BWET history preparation should retain actual local coverage', timeout: 60_000 })
    .toBeTruthy()
  return latest!
}

test('genuine BWET future-dated composition stays held while existing price history remains usable', async (
  { page, request, loggedIn, browserDiagnostics }, testInfo: TestInfo,
) => {
  test.setTimeout(240_000)
  expect(loggedIn).toBeUndefined()
  await page.goto('/chart')
  await expect(page.locator('.workspace-layout-host')).toBeVisible()
  const token = await page.evaluate(() => localStorage.getItem('access_token'))
  expect(token).toBeTruthy()

  const selection = await selectKnownBWET(page)
  const { listing } = selection
  const historyRequest = await awaitObservedDatasetRequest(await selection.historyRequest)
  const holdingsRequest = await awaitObservedDatasetRequest(await selection.holdingsRequest)
  const history = await assertSelectedHistoryPreparation(request, historyRequest.requestId, token!)
  const bars = await assertExistingBWETPriceHistory(page, request, token!)
  const holdings = await waitForFutureDatedHoldings(request, holdingsRequest.requestId, token!)
  const holdingsDependency = holdings.dependencies.find(item => item.dataset === 'holdings')!
  expect(holdingsDependency.instrument_id).toBe(listing.instrument_id)
  expect(holdingsDependency.symbol?.toUpperCase()).toBe('BWET')
  expect(holdingsDependency.status).toBe('failed')
  expect(holdingsDependency.reason_code).toBe('future_dated_source')
  expect(history.dependencies.find(item => item.dataset === 'history')?.reason_code).not.toBe('future_dated_source')
  await assertFutureReasonVisible(page)
  await assertNoCurrentBWETHoldings(request, token!)
  await assertNoPriorFundRows(page)

  const reloadHistoryPromise = page.waitForRequest(item => selectedDatasetEnsure(item, 'BWET', listing.instrument_id, 'history'), { timeout: 30_000 })
  const reloadHoldingsPromise = page.waitForRequest(item => selectedDatasetEnsure(item, 'BWET', listing.instrument_id, 'holdings'), { timeout: 30_000 })
  const reloadHistoryResponsePromise = page.waitForResponse(response => {
    const requestBody = response.request()
    return selectedDatasetEnsure(requestBody, 'BWET', listing.instrument_id, 'history')
  }, { timeout: 30_000 })
  const reloadHoldingsResponsePromise = page.waitForResponse(response => {
    const requestBody = response.request()
    return selectedDatasetEnsure(requestBody, 'BWET', listing.instrument_id, 'holdings')
  }, { timeout: 30_000 })
  await page.reload()
  await expect(page.locator('.workspace-layout-host')).toBeVisible()
  const reloadedHistoryRequest = await reloadHistoryPromise
  const reloadedHoldingsRequest = await reloadHoldingsPromise
  const historyResponse = await reloadHistoryResponsePromise
  const holdingsResponse = await reloadHoldingsResponsePromise
  expect(historyResponse.request()).toBe(reloadedHistoryRequest)
  expect(holdingsResponse.request()).toBe(reloadedHoldingsRequest)
  expect(historyResponse.status()).toBe(202)
  expect(holdingsResponse.status()).toBe(202)
  const reloadHistoryBody = await historyResponse.json() as { request_id?: string }
  const reloadHoldingsBody = await holdingsResponse.json() as { request_id?: string }
  expect(reloadHistoryBody.request_id).toBeTruthy()
  expect(reloadHoldingsBody.request_id).toBeTruthy()
  await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue('BWET')
  const reloadedBars = await assertExistingBWETPriceHistory(page, request, token!)
  expect(reloadedBars.length).toBeGreaterThan(1)
  const reloadedStatus = await waitForFutureDatedHoldings(request, reloadHoldingsBody.request_id!, token!)
  expect(reloadedStatus.dependencies.find(item => item.dataset === 'holdings')?.reason_code).toBe('future_dated_source')
  await assertFutureReasonVisible(page)
  await assertNoCurrentBWETHoldings(request, token!)
  await assertNoPriorFundRows(page)

  await testInfo.attach('native-bwet-future-source-boundary.json', {
    body: Buffer.from(JSON.stringify({
      symbol: 'BWET', instrumentId: listing.instrument_id,
      originalHistoryRequestId: history.request_id,
      originalHoldingsRequestId: holdings.request_id,
      historyStatus: history.status,
      historyCoveredRanges: history.dependencies.find(item => item.dataset === 'history')?.covered_ranges.length ?? 0,
      holdingsStatus: holdingsDependency.status,
      holdingsReasonCode: holdingsDependency.reason_code,
      currentSnapshotHttpStatus: 404,
      originalPriceBarCount: bars.length,
      reloadHistoryRequestId: reloadHistoryBody.request_id,
      reloadHoldingsRequestId: reloadHoldingsBody.request_id,
      reloadHoldingsReasonCode: reloadedStatus.dependencies.find(item => item.dataset === 'holdings')?.reason_code,
      reloadPriceBarCount: reloadedBars.length,
    }, null, 2)),
    contentType: 'application/json',
  })
  await browserDiagnostics.expectNoCriticalIssues()
})
