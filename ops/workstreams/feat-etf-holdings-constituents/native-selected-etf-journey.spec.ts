import { expect, test } from '../../../frontend/tests/e2e/helpers'
import type { APIRequestContext, Page, Request, Response, TestInfo } from '@playwright/test'

type Listing = { instrument_id: number; symbol: string; name: string }
type Bar = { ts: string; open: number; high: number; low: number; close: number }
type Holding = {
  id: number; snapshot_id: number; constituent_instrument_id: number | null
  constituent_symbol: string | null; reported_symbol: string | null; constituent_name: string | null
  holding_type: string; row_type: string; is_resolved: boolean; source_row_id?: string | null
  extra_data?: Record<string, unknown> | null
}
type Snapshot = {
  id: number; etf_profile_id: number; etf_instrument_id: number; etf_symbol: string
  composition_date: string; known_at: string | null; provenance: string; source_provider: string
  source_identifier: string | null; source_quality: string; completeness_status: string
  row_count: number; resolved_count: number; unresolved_count: number
}
type PreparationDependency = { dataset: string; status: string | null; reasonCode: string | null; retryAt: string | null }
type Preparation = {
  symbol: string; requestId: string | null; httpStatus: number; status: string | null
  reasonCode: string | null; retryAt: string | null; datasets: string[]; dependencies: PreparationDependency[]
}
type FundEvidence = {
  symbol: string; instrumentId: number; snapshotId: number; compositionDate: string; knownAt: string | null
  provenance: string; sourceProvider: string; sourceIdentifier: string | null; completeness: string; rowCount: number
  rowTypes: Array<{ holdingType: string; rowType: string; count: number }>
}

async function json<T>(request: APIRequestContext, path: string, token: string, params?: Record<string, string | number>): Promise<T> {
  const response = await request.get(path, { headers: { Authorization: `Bearer ${token}` }, ...(params ? { params } : {}) })
  expect(response.status(), `Authenticated read ${path} should succeed`).toBe(200)
  return await response.json() as T
}

function selectedEnsure(request: Request, symbol: string, instrumentId: number): boolean {
  if (request.method() !== 'POST' || new URL(request.url()).pathname !== '/api/v1/data/ensure') return false
  try {
    const body = request.postDataJSON() as { target?: { kind?: string; symbol?: string; instrument_id?: number }; datasets?: string[] }
    return body.target?.kind === 'instrument'
      && body.target.instrument_id === instrumentId
      && (!body.target.symbol || body.target.symbol.trim().toUpperCase() === symbol)
      && (body.datasets ?? []).some(dataset => ['history', 'holdings'].includes(dataset))
  } catch { return false }
}

async function chooseETF(page: Page, symbol: string): Promise<{ listing: Listing; preparation: Preparation }> {
  const input = page.getByRole('combobox', { name: 'Active symbol' })
  const searchPromise = page.waitForResponse(response => {
    const url = new URL(response.url())
    return url.pathname === '/api/v1/instruments/search' && url.searchParams.get('q')?.toUpperCase() === symbol
  })
  const discoveryResponses: Response[] = []
  const captureDiscovery = (response: Response) => {
    const request = response.request()
    if (request.method() !== 'POST' || new URL(response.url()).pathname !== '/api/v1/instruments/discover') return
    try {
      if ((request.postDataJSON() as { query?: string }).query?.toUpperCase() === symbol) discoveryResponses.push(response)
    } catch { /* unrelated or malformed discovery request */ }
  }
  page.on('response', captureDiscovery)
  await input.fill(symbol)
  const search = await searchPromise
  expect(search.status(), `Canonical search for ${symbol}`).toBe(200)
  const exact = (await search.json() as Listing[]).filter(row => row.symbol.toUpperCase() === symbol)
  if (exact.length) page.off('response', captureDiscovery)
  expect(exact.length, `Local ${symbol} search must not present ambiguous exact listings`).toBeLessThanOrEqual(1)

  if (exact.length === 1) {
    const listing = exact[0]!
    const ensureRequest = page.waitForRequest(request => selectedEnsure(request, symbol, listing.instrument_id))
    await page.getByRole('option', { name: new RegExp(`^${symbol}\\b`) }).click()
    await expect(input).toHaveValue(symbol)
    const request = await ensureRequest
    const response = await page.waitForResponse(item => item.request() === request)
    const preparation = await preparationFromResponse(response, symbol, request, test.info())
    return { listing, preparation }
  }

  // A first-use ticker is absent from the canonical local catalogue. Follow
  // Workstation's visible discovery choice and its normal acquisition request;
  // never prewarm an API or treat a provider candidate as verified identity.
  const discoveryChoices = page.getByRole('group', { name: 'Matching ticker listings' })
  await expect(discoveryChoices, `Workstation should discover uncached ${symbol} after its empty exact local search`)
    .toBeVisible({ timeout: 120_000 })
  expect(discoveryResponses.length, `${symbol} visible discovery choice must have a public discovery response`).toBeGreaterThan(0)
  const discovered = discoveryResponses.at(-1)!
  expect(discovered.status(), `${symbol} public discovery response`).toBe(200)
  const discoveryBody = await discovered.json() as {
    request_id?: string; status: string; retry_at?: string | null
    source_outcomes?: Array<{ provider?: string; status?: string; reason_code?: string | null; retry_at?: string | null }>
    candidates: Array<{ symbol: string; name: string; exchange: string; type: string; provider: string; instrument_id: number | null; identity_status: string }>
  }
  expect(['complete', 'partial']).toContain(discoveryBody.status)
  const exactCandidates = discoveryBody.candidates.filter(candidate => candidate.symbol.trim().toUpperCase() === symbol)
  // Provider discovery may include a weak issuer hint alongside a real
  // exchange-qualified listing. Only the latter can be selected as this ETF;
  // bind acquisition to the exact provider/exchange candidate from the public
  // response and fail closed if that same listing is duplicated.
  const selectedListings = exactCandidates.filter(candidate =>
    candidate.provider.trim() !== '' && candidate.exchange.trim().toUpperCase() === 'ARCX',
  )
  expect(selectedListings, `Discovery must expose one exact ${symbol} ARCX listing; weak issuer hints do not count as listings`)
    .toHaveLength(1)
  const candidate = selectedListings[0]!
  const candidateType = candidate.type.trim().toUpperCase().replace(/[_-]+/g, ' ').replace(/\s+/g, ' ')
  expect(['ETF', 'ETV', 'ETP', 'EXCHANGE TRADED FUND', 'EXCHANGE TRADED VEHICLE', 'EXCHANGE TRADED PRODUCT'],
    `${candidate.provider}/ARCX candidate must retain a supported exchange-traded type`)
    .toContain(candidateType)
  const discoveryAttempts = await Promise.all(discoveryResponses.map(async response => {
    const body = await response.json() as {
      request_id?: string; status?: string; reason_code?: string | null; retry_at?: string | null
      source_outcomes?: Array<{ provider?: string; status?: string; reason_code?: string | null; retry_at?: string | null }>
      candidates?: Array<{ symbol?: string; provider?: string; exchange?: string }>
    }
    return {
      httpStatus: response.status(), requestId: body.request_id ?? null,
      status: body.status ?? null, reasonCode: body.reason_code ?? null,
      retryAt: body.retry_at ?? body.source_outcomes?.find(outcome => outcome.status === 'held' && outcome.retry_at)?.retry_at ?? null,
      sourceOutcomes: (body.source_outcomes ?? []).map(outcome => ({
        provider: outcome.provider ?? null, status: outcome.status ?? null,
        reasonCode: outcome.reason_code ?? null, retryAt: outcome.retry_at ?? null,
      })),
      exactCandidateCount: (body.candidates ?? []).filter(item => item.symbol?.trim().toUpperCase() === symbol).length,
    }
  }))
  const acquisitionAttempts: Array<{
    httpStatus: number; requestId: string | null; status: string | null; reasonCode: string | null
    retryAt: string | null; instrumentId: number | null; symbol: string | null
  }> = []
  const ensureRequests: Request[] = []
  const ensureResponses = new Map<Request, Response>()
  const captureEnsureRequest = (request: Request) => {
    if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/v1/data/ensure') ensureRequests.push(request)
  }
  const captureEnsureResponse = (response: Response) => {
    const request = response.request()
    if (request.method() === 'POST' && new URL(response.url()).pathname === '/api/v1/data/ensure') {
      ensureResponses.set(request, response)
    }
  }
  page.on('request', captureEnsureRequest)
  page.on('response', captureEnsureResponse)
  try {
    const listingButton = page.getByRole('button', {
      name: `Use ${symbol} · ${candidate.exchange} ${candidate.name}`,
      exact: true,
    })
    await expect(listingButton, `The exact ${symbol} ${candidate.provider}/${candidate.exchange} discovery choice should be visible`)
      .toHaveCount(1)
    const acquisitionPromise = page.waitForResponse(async response => {
      const request = response.request()
      if (request.method() !== 'POST' || new URL(response.url()).pathname !== '/api/v1/instruments/acquire') return false
      try {
        const body = request.postDataJSON() as { symbol?: string; provider_candidate?: { provider?: string; symbol?: string; exchange?: string | null } }
        const matchesCandidate = body.symbol?.toUpperCase() === symbol
          && body.provider_candidate?.symbol?.toUpperCase() === symbol
          && body.provider_candidate.provider === candidate.provider
          && (body.provider_candidate.exchange ?? '') === candidate.exchange
        if (!matchesCandidate) return false
        const result = await response.json() as {
          request_id?: string; status?: string; reason_code?: string | null; retry_at?: string | null
          source_outcomes?: Array<{ status?: string; retry_at?: string | null }>
          instrument?: { instrument_id?: number; symbol?: string }
        }
        const retryAt = result.retry_at
          ?? result.source_outcomes?.find(outcome => outcome.status === 'held' && outcome.retry_at)?.retry_at
          ?? null
        acquisitionAttempts.push({
          httpStatus: response.status(), requestId: result.request_id ?? null,
          status: result.status ?? null, reasonCode: result.reason_code ?? null, retryAt,
          instrumentId: result.instrument?.instrument_id ?? null, symbol: result.instrument?.symbol ?? null,
        })
        // Workstation retries a held acquisition only when the API supplies a
        // known retry time. Keep observing until that public flow resolves or
        // reaches a terminal result, under the bounded Playwright wait below.
        return !(result.status === 'held' && retryAt)
      } catch {
        acquisitionAttempts.push({ httpStatus: response.status(), requestId: null,
          status: null, reasonCode: null, retryAt: null, instrumentId: null, symbol: null })
        return true
      }
    }, { timeout: 120_000 })
    await listingButton.click()
    const acquiredResponse = await acquisitionPromise
    expect(acquiredResponse.status(), `${symbol} normal canonical acquisition`).toBe(200)
    const acquired = await acquiredResponse.json() as {
      request_id?: string; status?: string; instrument?: {
        instrument_id?: number; symbol?: string; identity_status?: string
        instrument_type?: string | null; primary_listing_mic?: string | null
      }
    }
    expect(acquired.status, `${symbol} canonical acquisition result`).toBe('resolved')
    expect(acquired.instrument?.symbol?.toUpperCase()).toBe(symbol)
    expect(Number.isSafeInteger(acquired.instrument?.instrument_id) && acquired.instrument!.instrument_id! > 0).toBeTruthy()
    expect(['resolved', 'verified']).toContain(acquired.instrument?.identity_status?.trim().toLowerCase())
    expect(acquired.instrument?.primary_listing_mic?.trim().toUpperCase(), `${symbol} selected canonical primary listing`)
      .toBe(candidate.exchange.trim().toUpperCase())
    const listing: Listing = {
      instrument_id: acquired.instrument!.instrument_id!, symbol: acquired.instrument!.symbol!,
      name: candidate.name,
    }
    await expect(input).toHaveValue(symbol)
    await expect.poll(() => {
      const request = ensureRequests.find(item => selectedEnsure(item, symbol, listing.instrument_id))
      return Boolean(request && ensureResponses.has(request))
    }, { message: `${symbol} selection should automatically prepare the acquired canonical instrument`, timeout: 30_000 }).toBeTruthy()
    const ensureRequest = ensureRequests.find(item => selectedEnsure(item, symbol, listing.instrument_id))!
    const ensureResponse = ensureResponses.get(ensureRequest)!
    const preparation = await preparationFromResponse(ensureResponse, symbol, ensureRequest, test.info())
    await test.info().attach(`native-acquisition-${symbol.toLowerCase()}.json`, {
      body: Buffer.from(JSON.stringify({
        discoveryAttempts,
        candidate: { symbol: candidate.symbol, exchange: candidate.exchange, provider: candidate.provider },
        acquisition: { requestId: acquired.request_id ?? null, status: acquired.status,
          instrumentId: listing.instrument_id, symbol: listing.symbol,
          identityStatus: acquired.instrument?.identity_status ?? null, attempts: acquisitionAttempts },
        ensureRequestId: preparation.requestId,
      }, null, 2)),
      contentType: 'application/json',
    })
    return { listing, preparation }
  } finally {
    page.off('request', captureEnsureRequest)
    page.off('response', captureEnsureResponse)
    page.off('response', captureDiscovery)
  }
}

async function preparationFromResponse(response: import('@playwright/test').Response, symbol: string, request: Request, testInfo: TestInfo): Promise<Preparation> {
  const requested = request.postDataJSON() as { request_id?: string; datasets?: string[] }
  let body: {
    request_id?: string; status?: string; reason_code?: string | null; retry_at?: string | null
    dependencies?: Array<{ dataset?: string; status?: string | null; reason_code?: string | null; retry_at?: string | null }>
  } | null = null
  try { body = await response.json() as typeof body } catch { /* retain status/request evidence for non-JSON errors */ }
  const dependencies = (body?.dependencies ?? []).map(item => ({
    dataset: item.dataset ?? '', status: item.status ?? null,
    reasonCode: item.reason_code ?? null, retryAt: item.retry_at ?? null,
  }))
  const evidence: Preparation = {
    symbol, requestId: body?.request_id ?? requested.request_id ?? null, httpStatus: response.status(),
    status: body?.status ?? null, reasonCode: body?.reason_code ?? null, retryAt: body?.retry_at ?? null,
    datasets: (body?.dependencies ?? []).map(item => item.dataset ?? '').filter(Boolean), dependencies,
  }
  await testInfo.attach(`native-ensure-${symbol.toLowerCase()}-${evidence.requestId ?? 'no-request-id'}.json`, {
    body: Buffer.from(JSON.stringify({
      ...evidence,
      requestedDatasets: requested.datasets ?? [],
      responseBodyParsed: body !== null,
    }, null, 2)),
    contentType: 'application/json',
  })
  expect([200, 202], `${symbol} automatic preparation public response`).toContain(response.status())
  expect(evidence.requestId, `${symbol} automatic preparation request id`).toBeTruthy()
  expect(evidence.status, `${symbol} automatic preparation status`).toBeTruthy()
  expect(['held', 'failed', 'unavailable', 'blocked']).not.toContain(evidence.status)
  expect(evidence.datasets.some(dataset => ['history', 'holdings'].includes(dataset))).toBeTruthy()
  expect(evidence.dependencies.filter(item => ['history', 'holdings'].includes(item.dataset))
    .every(item => !['held', 'failed', 'unavailable', 'blocked'].includes(item.status ?? ''))).toBeTruthy()
  return evidence
}

async function reselectKnownETF(page: Page, listing: Listing): Promise<Preparation> {
  const input = page.getByRole('combobox', { name: 'Active symbol' })
  const ensureRequest = page.waitForRequest(request => selectedEnsure(request, listing.symbol, listing.instrument_id))
  await input.fill(listing.symbol)
  const option = page.getByRole('option', { name: new RegExp(`^${listing.symbol}\\b`) })
  await expect(option).toBeVisible()
  await option.click()
  await expect(input).toHaveValue(listing.symbol)
  const request = await ensureRequest
  const response = await page.waitForResponse(item => item.request() === request)
  return preparationFromResponse(response, listing.symbol, request, test.info())
}

async function assertSelectedBars(page: Page, request: APIRequestContext, symbol: string, token: string): Promise<Bar[]> {
  await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue(symbol)
  await expect.poll(async () => {
    const response = await request.get(`/api/v1/ohlcv/local/${symbol}/D1`, {
      headers: { Authorization: `Bearer ${token}` }, params: { limit: 500, adjusted: 'true' },
    })
    return response.status() === 200 ? (await response.json() as Bar[]).length : 0
  }, { message: `${symbol} should have persisted daily bars`, timeout: 90_000 }).toBeGreaterThan(1)
  const bars = await json<Bar[]>(request, `/api/v1/ohlcv/local/${symbol}/D1`, token, { limit: 500, adjusted: 'true' })
  expect(bars.every(bar => Number.isFinite(Date.parse(bar.ts)) && [bar.open, bar.high, bar.low, bar.close].every(Number.isFinite))).toBeTruthy()

  const chart = page.getByRole('region', { name: 'Chart workspace' }).first()
  await expect(chart).toHaveAttribute('aria-busy', 'false')
  const plot = chart.locator('.uplot').first()
  await expect(plot).toBeVisible()
  await expect.poll(() => plot.locator('canvas:not(.drawing-canvas)').first().evaluate(canvas => {
    const element = canvas as HTMLCanvasElement
    if (element.width < 2 || element.height < 2) return 0
    const data = element.getContext('2d')?.getImageData(0, 0, element.width, element.height).data
    if (!data) return 0
    const colors = new Set<string>()
    let painted = 0
    for (let y = Math.floor(element.height * 0.05); y < element.height * 0.95; y += 1) {
      for (let x = Math.floor(element.width * 0.1); x < element.width * 0.98; x += 1) {
        const i = (y * element.width + x) * 4
        if (data[i + 3] === 0) continue
        painted += 1
        colors.add(`${data[i]},${data[i + 1]},${data[i + 2]}`)
      }
    }
    return colors.size >= 3 ? painted : 0
  }), { message: `${symbol} actual price series should paint the chart`, timeout: 15_000 }).toBeGreaterThan(10)
  const box = await plot.boundingBox()
  expect(box && box.width > 100 && box.height > 80).toBeTruthy()
  await page.mouse.move(box!.x + box!.width * 0.62, box!.y + box!.height * 0.48)
  const tooltip = chart.locator('.ohlcv-info')
  await expect(tooltip).toBeVisible()
  const close = (await tooltip.locator('.tt-item').filter({ hasText: /^C\s/ }).innerText()).replace(/^C\s*/, '').trim()
  const bar = bars.find(item => item.close.toFixed(4) === close)
  expect(bar, `${symbol} tooltip close should match a persisted selected-symbol bar`).toBeTruthy()
  const date = await page.evaluate(ts => {
    const value = new Date(ts)
    return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`
  }, bar!.ts)
  await expect(tooltip.locator('.tt-date')).toHaveText(date)
  return bars
}

async function currentHoldings(request: APIRequestContext, symbol: string, instrumentId: number, token: string) {
  await expect.poll(async () => (await request.get(`/api/v1/etf-holdings/${symbol}/latest`, {
    headers: { Authorization: `Bearer ${token}` },
  })).status(), { message: `${symbol} selection should expose a real current holdings snapshot`, timeout: 90_000 }).toBe(200)
  const profiles = await json<Array<{
    id: number; instrument_id: number; symbol: string; latest_snapshot_id: number | null
    holdings_capability?: { availability: string; identity_verified: boolean; usable_for_current_analysis: boolean }
  }>>(request, '/api/v1/etf-holdings', token, { q: symbol })
  const profile = profiles.filter(item => item.symbol.toUpperCase() === symbol)
  expect(profile).toHaveLength(1)
  expect(profile[0]!.instrument_id).toBe(instrumentId)
  expect(profile[0]!.holdings_capability?.availability).toBe('current')
  expect(profile[0]!.holdings_capability?.identity_verified).toBe(true)
  expect(profile[0]!.holdings_capability?.usable_for_current_analysis).toBe(true)

  const snapshot = await json<Snapshot>(request, `/api/v1/etf-holdings/${symbol}/latest`, token)
  expect(snapshot.etf_symbol.toUpperCase()).toBe(symbol)
  expect(snapshot.etf_instrument_id).toBe(instrumentId)
  expect(snapshot.etf_profile_id).toBe(profile[0]!.id)
  expect(profile[0]!.latest_snapshot_id).toBe(snapshot.id)
  expect(snapshot.completeness_status).toBe('complete')
  expect(snapshot.row_count).toBeGreaterThan(0)
  expect(snapshot.composition_date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  expect(snapshot.known_at && snapshot.provenance.trim() && snapshot.source_provider.trim() && snapshot.source_quality.trim()).toBeTruthy()
  const page = await json<{ snapshot: Snapshot; holdings: Holding[]; total: number }>(
    request, `/api/v1/etf-holdings/${symbol}/holdings`, token, { snapshot_id: snapshot.id, limit: 500 },
  )
  expect(page.snapshot.id).toBe(snapshot.id)
  expect(page.total).toBe(snapshot.row_count)
  expect(page.holdings.length).toBeGreaterThan(0)
  expect(page.holdings.every(row => row.snapshot_id === snapshot.id)).toBeTruthy()
  return { snapshot, holdings: page.holdings }
}

function holdingRowTypes(holdings: Holding[]): FundEvidence['rowTypes'] {
  const counts = new Map<string, { holdingType: string; rowType: string; count: number }>()
  for (const row of holdings) {
    const holdingType = row.holding_type.trim().toLowerCase()
    const rowType = row.row_type.trim().toLowerCase()
    const key = `${holdingType}|${rowType}`
    const current = counts.get(key) ?? { holdingType, rowType, count: 0 }
    current.count += 1
    counts.set(key, current)
  }
  return [...counts.values()].sort((a, b) => `${a.holdingType}|${a.rowType}`.localeCompare(`${b.holdingType}|${b.rowType}`))
}

async function assertVisibleFundRows(page: Page, symbol: string, holdings: Holding[]) {
  const rows = page.locator('.constituent-tool').getByRole('option')
  await expect.poll(async () => {
    const labels = await rows.evaluateAll(items => items.map(item => item.getAttribute('aria-label') ?? ''))
    return labels.length > 0 && labels.every(label => holdings.some(row =>
      (row.constituent_symbol ?? row.reported_symbol)
      && label.startsWith(`${row.constituent_symbol ?? row.reported_symbol} `)))
  }, { message: `${symbol} visible rows must match its selected dated snapshot`, timeout: 30_000 }).toBeTruthy()
}

async function selectVisibleResolvedHolding(page: Page, holdings: Holding[]) {
  const resolved = new Map(holdings.filter(row => {
    const type = row.holding_type.trim().toLowerCase().replace(/[\s_-]+/g, '')
    const equityTypes = new Set(['equity', 'stock', 'commonstock', 'commonshares', 'ordinaryshares', 'realestateinvestmenttrust'])
    return row.is_resolved && (row.constituent_instrument_id ?? 0) > 0 && row.constituent_symbol
      && row.row_type.trim().toLowerCase() === 'security' && equityTypes.has(type)
      && !/^holding-/i.test(row.reported_symbol ?? '')
      && row.extra_data?.is_synthetic !== true && row.extra_data?.synthetic !== true
      && row.extra_data?.is_reference !== true && row.extra_data?.reference !== true
  }).map(row => [row.constituent_symbol!.toUpperCase(), row] as const))
  expect(resolved.size, 'The selected snapshot needs a resolved equity holding').toBeGreaterThan(0)
  const rows = page.locator('.constituent-tool').getByRole('option')
  await expect.poll(() => rows.count(), { message: 'Current reported holdings should render in Workstation', timeout: 30_000 }).toBeGreaterThan(0)
  const count = await rows.count()
  let holding: Holding | undefined
  for (let index = 0; index < count; index += 1) {
    const symbol = (await rows.nth(index).getAttribute('aria-label'))?.trim().split(/\s+/, 1)[0]?.toUpperCase()
    if (symbol) holding = resolved.get(symbol)
    if (holding) break
  }
  expect(holding, 'A visible Workstation row must be a resolved equity in this snapshot').toBeTruthy()
  await page.locator('.constituent-tool').getByRole('option', {
    name: new RegExp(`^${holding!.constituent_symbol!.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s`),
  }).click()
  return holding!
}

test('genuine BWET to XHB to IGV selection retains current holdings provenance on Workstation', async ({
  page, request, loggedIn, browserDiagnostics,
}, testInfo) => {
  test.setTimeout(480_000)
  expect(loggedIn).toBeUndefined()
  await page.goto('/chart')
  await expect(page.locator('.workspace-layout-host')).toBeVisible()
  const token = await page.evaluate(() => localStorage.getItem('access_token'))
  expect(token).toBeTruthy()
  const evidence: Preparation[] = []
  const fundEvidence: FundEvidence[] = []
  let igv: Awaited<ReturnType<typeof currentHoldings>> | null = null
  let igvListing: Listing | null = null

  for (const symbol of ['BWET', 'XHB', 'IGV']) {
    const { listing, preparation } = await chooseETF(page, symbol)
    evidence.push(preparation)
    await assertSelectedBars(page, request, symbol, token!)
    const fund = await currentHoldings(request, symbol, listing.instrument_id, token!)
    fundEvidence.push({
      symbol, instrumentId: listing.instrument_id, snapshotId: fund.snapshot.id,
      compositionDate: fund.snapshot.composition_date, knownAt: fund.snapshot.known_at,
      provenance: fund.snapshot.provenance, sourceProvider: fund.snapshot.source_provider,
      sourceIdentifier: fund.snapshot.source_identifier, completeness: fund.snapshot.completeness_status,
      rowCount: fund.snapshot.row_count, rowTypes: holdingRowTypes(fund.holdings),
    })
    await assertVisibleFundRows(page, symbol, fund.holdings)
    if (symbol !== 'BWET') await expect(page.getByTestId('active-holding-lineage')).toHaveCount(0)
    if (symbol === 'BWET') {
      expect(fund.snapshot.source_provider.toLowerCase()).toBe('amplify')
      expect(fund.holdings.every(row => row.holding_type.trim() && row.row_type.trim())).toBeTruthy()
      expect(fund.holdings.some(row => row.holding_type.trim().toLowerCase() === 'future'
        && row.row_type.trim().toLowerCase() === 'derivative' && !row.is_resolved
        && !row.constituent_instrument_id && row.reported_symbol?.trim())).toBeTruthy()
      expect(fund.holdings.some(row => row.holding_type.trim().toLowerCase() === 'cash')).toBeTruthy()
    }
    if (symbol === 'IGV') {
      igv = fund
      igvListing = listing
    }
  }

  expect(igv).toBeTruthy()
  const row = await selectVisibleResolvedHolding(page, igv!.holdings)
  const lineage = page.getByTestId('active-holding-lineage')
  await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue(row.constituent_symbol!)
  await expect(page).toHaveURL(/\/chart(?:\/|[?#]|$)/)
  await expect(page).not.toHaveURL(/\/legacy\/chart/)
  await expect(lineage).toContainText('from IGV holdings')
  const details = await lineage.getAttribute('aria-label')
  for (const proof of [`snapshot ${igv!.snapshot.id}`, `row ${row.id}`, `instrument ${row.constituent_instrument_id}`,
    `composition ${igv!.snapshot.composition_date}`, `known ${igv!.snapshot.known_at}`,
    `${igv!.snapshot.source_provider} / ${igv!.snapshot.provenance}`]) expect(details).toContain(proof)
  if (row.reported_symbol) expect(details).toContain(`reported ${row.reported_symbol}`)
  if (row.source_row_id) expect(details).toContain(`source row ${row.source_row_id}`)
  await assertSelectedBars(page, request, row.constituent_symbol!, token!)
  await page.screenshot({ path: testInfo.outputPath('native-selected-igv-holding.png') })

  expect(igvListing).toBeTruthy()
  const reopenPreparation = await reselectKnownETF(page, igvListing!)
  expect([200, 202]).toContain(reopenPreparation.httpStatus)
  await assertSelectedBars(page, request, 'IGV', token!)
  const reopenedFund = await currentHoldings(request, 'IGV', igvListing!.instrument_id, token!)
  expect(reopenedFund.snapshot.id).toBe(igv!.snapshot.id)
  await expect(page.getByTestId('active-holding-lineage')).toHaveCount(0)
  await assertVisibleFundRows(page, 'IGV', reopenedFund.holdings)

  await page.reload()
  await expect(page.locator('.workspace-layout-host')).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue('IGV')
  await expect(page.getByTestId('active-holding-lineage')).toHaveCount(0)
  await assertSelectedBars(page, request, 'IGV', token!)
  const reloadedFund = await currentHoldings(request, 'IGV', igvListing!.instrument_id, token!)
  expect(reloadedFund.snapshot.id).toBe(igv!.snapshot.id)
  await assertVisibleFundRows(page, 'IGV', reloadedFund.holdings)

  expect(evidence.map(item => item.symbol)).toEqual(['BWET', 'XHB', 'IGV'])
  expect(evidence.every(item => [200, 202].includes(item.httpStatus) && item.requestId && item.status)).toBeTruthy()
  await testInfo.attach('native-selection-public-evidence.json', {
    body: Buffer.from(JSON.stringify({ preparations: evidence, funds: fundEvidence, drilldown: {
      symbol: row.constituent_symbol, rowId: row.id, instrumentId: row.constituent_instrument_id,
      parentSnapshotId: igv!.snapshot.id,
    }, contextReopen: reopenPreparation }, null, 2)),
    contentType: 'application/json',
  })
  await browserDiagnostics.expectNoCriticalIssues()
})
