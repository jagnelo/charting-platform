import { test, expect } from './helpers'
import type { Frame, Page, Request } from '@playwright/test'
import type {
  ETFHolding,
  ETFHoldingsDate,
  ETFHoldingsPage,
  ETFHoldingsSnapshot,
  ETFHoldingsCapability,
  ETFProfile,
  ExpirationSummary,
  OptionsExposureResponse,
  OHLCVBar,
} from '../../src/types'
import type {
  ETFProfileAcquireResponse,
  HistoryAcquisitionRequest,
  HistoryAcquisitionResponse,
  HistoryAvailabilityResponse,
  InstrumentAcquireRequest,
  InstrumentAcquireResponse,
  InstrumentDiscoveryResponse,
} from '../../src/lib/onDemandAcquisition'
import type { DataEnsureRequest, DataEnsureResponse } from '../../src/lib/dataPreparation'

type DiscoveryRequest = { query: string; types: string[]; limit: number; request_id: string }
type HistoryRequestBody = HistoryAcquisitionRequest & { request_id: string }
type IssuerRequest = { request_id: string; refresh: boolean; instrument_id?: number }
type InstrumentRequestBody = InstrumentAcquireRequest
type HistoryAvailabilityFixture = {
  instrumentId: number
  symbol: string
  timeframes: readonly string[]
  adjusted: boolean
}

// Mirrors the backend CalendarEvent response model consumed by UPlotChart.
// This test's fictional symbol has no events, so the valid typed response is
// an empty list rather than an untyped catch-all fixture.
type InstrumentCalendarEvent = {
  id: number
  date: string
  event_time: string
  fetched_at: string
  event_type: string
  symbol: string
  title: string
  value?: number | null
  actual?: number | null
  eps_estimate?: number | null
  eps_actual?: number | null
  eps_surprise?: number | null
  eps_surprise_pct?: number | null
  dividend_amount?: number | null
  split_ratio?: number | null
  currency?: string | null
  time_hint: string
  source: string
  is_estimate: boolean
}

const fixtureOutcome = {
  provider: 'test-fixture',
  capability: 'fixture_only',
  operation: 'deterministic_ui_test',
  status: 'used' as const,
}

async function expectSelectionHoldingsDetails(page: Page, symbol: string, detailText: string) {
  const notice = page.locator('.workstation__selection-acquisition')
    .filter({ has: page.locator('summary[aria-label^="Holdings"]') }).last()
  const summary = notice.locator('summary')
  const details = notice.locator('details')
  await expect(summary).toBeVisible()
  await expect(summary).toHaveAttribute('aria-label', new RegExp(`Holdings[^]*${symbol}`))
  if (!await details.evaluate(element => (element as HTMLDetailsElement).open)) await summary.click()
  await expect(notice.locator('.compact-status__detail')).toContainText(new RegExp(`holdings for ${symbol}`, 'i'))
  await expect(notice.locator('.compact-status__detail')).toContainText(detailText)
}

function resolvedIdentity(request: InstrumentRequestBody, instrumentId: number, instrumentType = 'ETF'): InstrumentAcquireResponse {
  return {
    request_id: request.request_id,
    status: 'resolved',
    instrument: {
      instrument_id: instrumentId,
      symbol: request.symbol,
      identity_status: 'resolved',
      instrument_type: instrumentType,
    },
    source_outcomes: [fixtureOutcome],
  } satisfies InstrumentAcquireResponse
}

function heldHistory(
  request: HistoryRequestBody,
  instrumentId: number,
  symbol: string,
): HistoryAcquisitionResponse {
  return {
    request_id: request.request_id,
    status: 'held',
    reason_code: 'test_fixture_hold',
    instrument_id: instrumentId,
    symbol,
    timeframe: request.timeframe,
    adjusted: request.adjusted,
    requested_start: request.start,
    requested_end: request.end,
    coverage: {
      status: 'missing',
      bar_count: 0,
      missing_slices: [{ start: request.start, end: request.end }],
    },
    bars: [],
    source_outcomes: [{ ...fixtureOutcome, status: 'held', reason_code: 'test_fixture_hold' }],
  } satisfies HistoryAcquisitionResponse
}

function historyPreparation(
  request: DataEnsureRequest,
  instrumentId: number,
  symbol: string,
  outcome: 'unavailable' | 'partial',
  bar?: OHLCVBar,
): DataEnsureResponse {
  historyPreparationSequence += 1
  const now = '2026-11-07T12:00:00.000Z'
  const datasets = request.datasets?.length ? request.datasets : ['history']
  return {
    request_id: `fixture-ensure-${symbol}-${request.timeframe ?? 'D1'}-${historyPreparationSequence}`,
    status: outcome,
    created_at: now,
    updated_at: now,
    version: 1,
    target: request.target,
    dependencies: datasets.map(dataset => ({
      dependency_id: `fixture-${symbol}-${dataset}`,
      depends_on: [],
      instrument_id: instrumentId,
      symbol,
      dataset,
      status: dataset === 'history' ? outcome : 'ready',
      requested_start: request.start_at ?? null,
      requested_end: request.end_at ?? null,
      covered_start: bar?.ts ?? null,
      covered_end: bar?.ts ?? null,
      reason_code: dataset === 'history' && outcome === 'unavailable' ? 'test_fixture_hold' : null,
      retry_at: null,
      updated_at: now,
      covered_ranges: bar ? [{
        start_at: bar.ts,
        end_at: bar.ts,
        data_source_id: null,
        market_series_id: null,
        adjustment_basis: 'split_adjusted',
        adjustment_version: 'fixture-v1',
        is_adjusted: request.adjusted !== false,
      }] : [],
    })),
    completed: datasets.length,
    total: datasets.length,
    last_progress_at: now,
    has_pending_work: false,
  }
}

let historyPreparationSequence = 0

function ensureInstrumentId(request: DataEnsureRequest): number | null {
  return request.target.kind === 'instrument' && 'instrument_id' in request.target
    ? request.target.instrument_id
    : null
}

async function installHistoryAvailabilityFixtures(
  page: import('@playwright/test').Page,
  fixtures: readonly HistoryAvailabilityFixture[],
): Promise<HistoryAvailabilityResponse[]> {
  const requests: HistoryAvailabilityResponse[] = []
  await page.route(url => /^\/api\/v1\/instruments\/\d+\/history-availability$/.test(new URL(url).pathname), async route => {
    const request = route.request()
    const url = new URL(request.url())
    const instrumentId = Number(url.pathname.match(/\/instruments\/(\d+)\/history-availability$/)?.[1])
    const fixture = fixtures.find(item => item.instrumentId === instrumentId)
    if (!fixture) {
      await route.continue()
      return
    }
    expect(request.method()).toBe('GET')
    const timeframe = url.searchParams.get('timeframe') ?? ''
    const adjusted = url.searchParams.get('adjusted') === 'true'
    expect(fixture.timeframes, `declared availability fixture for ${fixture.symbol}`).toContain(timeframe)
    expect(adjusted).toBe(fixture.adjusted)
    const response: HistoryAvailabilityResponse = {
      instrument_id: instrumentId,
      symbol: fixture.symbol,
      timeframe: timeframe as HistoryAvailabilityResponse['timeframe'],
      adjusted,
      status: 'eligible',
      earliest_start: '2024-01-01T00:00:00Z',
      max_requested_bars: 2000,
      reason_code: null,
    }
    requests.push(response)
    await route.fulfill({ status: 200, json: response })
  })
  return requests
}

function expectHistoryAvailabilityRead(
  requests: HistoryAvailabilityResponse[],
  instrumentId: number,
  symbol: string,
  historyRequest: HistoryRequestBody,
) {
  expect(requests).toContainEqual(expect.objectContaining({
    instrument_id: instrumentId,
    symbol,
    timeframe: historyRequest.timeframe,
    adjusted: historyRequest.adjusted,
    status: 'eligible',
    earliest_start: '2024-01-01T00:00:00Z',
    max_requested_bars: 2000,
  }))
}

function expectBoundedM1Request(request: HistoryRequestBody) {
  expect(request).toMatchObject({ timeframe: 'M1', adjusted: true })
  expect(request.request_id).toMatch(/^[0-9a-f-]{36}$/i)
  expect(request.start).toMatch(/(?:Z|[+-]\d{2}:\d{2})$/i)
  expect(request.end).toMatch(/(?:Z|[+-]\d{2}:\d{2})$/i)
  const start = Date.parse(request.start)
  const end = Date.parse(request.end)
  expect(end).toBeGreaterThan(start)
  expect(Math.ceil((end - start) / 60_000) + 1).toBeLessThanOrEqual(2000)
}

function expectBoundedD1Request(request: HistoryRequestBody) {
  expect(request).toMatchObject({ timeframe: 'D1', adjusted: true })
  expect(request.request_id).toMatch(/^[0-9a-f-]{36}$/i)
  expect(request.start).toMatch(/(?:Z|[+-]\d{2}:\d{2})$/i)
  expect(request.end).toMatch(/(?:Z|[+-]\d{2}:\d{2})$/i)
  const start = Date.parse(request.start)
  const end = Date.parse(request.end)
  expect(end).toBeGreaterThan(start)
  expect(Math.ceil((end - start) / 86_400_000) + 1).toBeLessThanOrEqual(2000)
}

async function expectGoldenLayoutTabsWithinAllocatedHeaders(page: Page) {
  await expect(page.locator('.lm_header .lm_tabs > .lm_tab').first()).toBeVisible()
  await expect(page.locator('.tool-window__title').first()).toBeVisible()
  const geometry = await page.evaluate(() => {
    const rect = (element: Element) => {
      const bounds = element.getBoundingClientRect()
      return { x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height, bottom: bounds.bottom, right: bounds.right }
    }
    const visible = (element: Element) => {
      const bounds = element.getBoundingClientRect()
      const style = getComputedStyle(element)
      return bounds.width > 0 && bounds.height > 0 && style.visibility !== 'hidden' && style.display !== 'none'
    }
    const tabs = [...document.querySelectorAll('.lm_header .lm_tabs > .lm_tab')].filter(visible).map(element => {
      const style = getComputedStyle(element)
      const header = element.closest('.lm_header')
      return {
        text: element.textContent?.trim() ?? '',
        rect: rect(element),
        header: header ? rect(header) : null,
        boxSizing: style.boxSizing,
        marginTop: style.marginTop,
      }
    })
    const titles = [...document.querySelectorAll('.tool-window__title')].filter(visible).map(element => ({
      text: element.textContent?.trim() ?? '',
      rect: rect(element),
    }))
    const overlaps = tabs.flatMap(tab => titles
      .filter(title => Math.min(tab.rect.right, title.rect.right) - Math.max(tab.rect.x, title.rect.x) > 1
        && Math.min(tab.rect.bottom, title.rect.bottom) - Math.max(tab.rect.y, title.rect.y) > 1)
      .map(title => ({ tab: tab.text, title: title.text })))
    return { tabs, titles, overlaps }
  })
  expect(geometry.tabs.length).toBeGreaterThan(0)
  expect(geometry.titles.length).toBeGreaterThan(0)
  for (const tab of geometry.tabs) {
    expect(tab.header, `${tab.text} has an allocated header`).not.toBeNull()
    expect(tab.boxSizing).toBe('border-box')
    expect(tab.marginTop).toBe('0px')
    expect(tab.rect.bottom).toBeLessThanOrEqual(tab.header!.bottom + 1)
  }
  expect(geometry.overlaps).toEqual([])
}

function missingCoverage(url: URL) {
  const start = url.searchParams.get('start') ?? ''
  const end = url.searchParams.get('end') ?? ''
  return {
    status: 'missing',
    covered_start: null,
    covered_end: null,
    bar_count: 0,
    missing_slices: [{ start, end }],
  }
}

test('Workstation search resolves an unknown ticker and reports shared history preparation without stale chart data', async ({ page, loggedIn, browserDiagnostics }) => {
  void loggedIn
  await page.goto('/chart/SPY')

  const fixtureInstrumentId = 990010
  let canonicalInstrumentResolved = false
  const discoveryRequests: DiscoveryRequest[] = []
  const identityRequests: InstrumentRequestBody[] = []
  const preparationRequests: DataEnsureRequest[] = []
  const legacyHistoryRequests: string[] = []
  const canonicalInstrumentLookups: Array<{ symbol: string; canonicalOnly: string | null }> = []
  let releaseCanonicalLookup!: () => void
  let notifyCanonicalLookupStarted!: () => void
  let canonicalLookupWasDelayed = false
  const canonicalLookupGate = new Promise<void>(resolve => { releaseCanonicalLookup = resolve })
  const canonicalLookupStarted = new Promise<void>(resolve => { notifyCanonicalLookupStarted = resolve })
  const search = page.getByRole('combobox', { name: 'Active symbol' })
  await expect(search).toBeVisible()
  await expect(search).toHaveValue('SPY')
  const previousChart = page.locator('.chart-tool:visible').getByRole('region', { name: 'Chart workspace' }).first()
  await expect(previousChart).toBeVisible()
  await expect(previousChart).toHaveAttribute('aria-busy', 'false')
  const previousChartProvenance = previousChart.locator('.sr-only').first()
  const previousChartProvenanceText = await previousChartProvenance.innerText()
  expect(previousChartProvenanceText).toMatch(/\d+ bars;/)
  page.on('request', request => {
    const url = new URL(request.url())
    if (request.method() !== 'GET' || url.pathname !== '/api/v1/instruments/TCNEW') return
    canonicalInstrumentLookups.push({ symbol: url.pathname.split('/').at(-1) ?? '', canonicalOnly: url.searchParams.get('canonical_only') })
  })

  await page.route('**/api/v1/instruments/search**', async route => {
    const url = new URL(route.request().url())
    if (route.request().method() !== 'GET' || url.searchParams.get('q')?.toUpperCase() !== 'TCNEW') return route.continue()
    await route.fulfill({ status: 200, json: canonicalInstrumentResolved ? [{
      symbol: 'TCNEW', name: 'Unknown ticker (controlled test fixture)', exchange: 'TEST', type: 'Stock',
      instrument_id: fixtureInstrumentId, identity_status: 'resolved',
    }] : [] })
  })
  await page.route('**/api/v1/instruments/discover**', async route => {
    const body = route.request().postDataJSON() as DiscoveryRequest
    discoveryRequests.push(body)
    await route.fulfill({ status: 200, json: {
      request_id: body.request_id,
      status: 'complete',
      candidates: [{ symbol: 'TCNEW', name: 'Unknown ticker (controlled test fixture)', exchange: 'TEST', type: 'Stock', provider: 'test-fixture', instrument_id: null, identity_status: 'unresolved' }],
      source_outcomes: [{ ...fixtureOutcome, capability: 'instrument_search', operation: 'search', status: 'returned', result_count: 1 }],
    } satisfies InstrumentDiscoveryResponse })
  })
  await page.route('**/api/v1/instruments/acquire**', async route => {
    const body = route.request().postDataJSON() as InstrumentRequestBody
    if (body.symbol.toUpperCase() !== 'TCNEW') return route.continue()
    identityRequests.push(body)
    expect(body.provider_candidate).toMatchObject({ provider: 'test-fixture', symbol: 'TCNEW', exchange: 'TEST' })
    canonicalInstrumentResolved = true
    await route.fulfill({ status: 200, json: resolvedIdentity(body, fixtureInstrumentId, 'Common Stock') })
  })
  await page.route(url => url.pathname === '/api/v1/instruments/TCNEW'
    && url.searchParams.get('canonical_only') === 'true', async route => {
    if (route.request().method() !== 'GET') return route.continue()
    if (!canonicalLookupWasDelayed) {
      canonicalLookupWasDelayed = true
      notifyCanonicalLookupStarted()
      await canonicalLookupGate
    }
    await route.fulfill({ status: 200, json: {
      id: fixtureInstrumentId,
      symbol: 'TCNEW',
      name: 'Unknown ticker (controlled test fixture)',
      currency: 'USD',
      is_active: true,
      stats: { week52_high: 12 },
    } })
  })
  await page.route('**/api/v1/data/ensure', async route => {
    const request = route.request().postDataJSON() as DataEnsureRequest
    const isTCNEW = request.target.kind === 'instrument' && (
      ('instrument_id' in request.target && request.target.instrument_id === fixtureInstrumentId)
      || ('symbol' in request.target && request.target.symbol?.toUpperCase() === 'TCNEW')
    )
    if (!isTCNEW) return route.continue()
    preparationRequests.push(request)
    await route.fulfill({ status: 200, json: historyPreparation(request, fixtureInstrumentId, 'TCNEW', 'unavailable') })
  })
  await page.route('**/api/v1/instruments/*/history-acquisitions**', async route => {
    if (!new URL(route.request().url()).pathname.includes('/instruments/990010/')) return route.continue()
    legacyHistoryRequests.push(route.request().url())
    await route.fulfill({ status: 500, json: { detail: 'History preparation is owned by POST /data/ensure.' } })
  })
  await page.route('**/api/v1/ohlcv/local/TCNEW/**', route => route.fulfill({ status: 200, json: [] }))

  const discoveryReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'POST' && url.pathname === '/api/v1/instruments/discover'
      && (response.request().postDataJSON() as DiscoveryRequest).query.toUpperCase() === 'TCNEW'
  })
  await search.fill('TCNEW')
  const discovery = await discoveryReady
  expect(await discovery.json()).toMatchObject({ candidates: [{ symbol: 'TCNEW', identity_status: 'unresolved' }] })
  expect(discoveryRequests).toHaveLength(1)
  const resolveReady = page.waitForResponse(response => response.request().method() === 'POST'
    && new URL(response.url()).pathname === '/api/v1/instruments/acquire')
  const preparationStarted = page.waitForRequest(request => request.method() === 'POST'
    && new URL(request.url()).pathname === '/api/v1/data/ensure'
    && (() => {
      const body = request.postDataJSON() as DataEnsureRequest
      return body.target.kind === 'instrument'
        && (('instrument_id' in body.target && body.target.instrument_id === fixtureInstrumentId)
          || ('symbol' in body.target && body.target.symbol?.toUpperCase() === 'TCNEW'))
    })())
  await page.getByRole('button', { name: /Use TCNEW · TEST/ }).click()
  const identityResponse = await resolveReady
  expect(identityResponse.status()).toBe(200)
  expect(await identityResponse.json()).toMatchObject({ instrument: { instrument_id: fixtureInstrumentId, symbol: 'TCNEW', identity_status: 'resolved' } })
  // Stop the independent metadata read before checking that selection has
  // already updated the active chart and URL.
  await canonicalLookupStarted
  await expect(search).toHaveValue('TCNEW')
  await expect(page).toHaveURL(/\/chart\/TCNEW$/)
  expect(identityRequests).toHaveLength(1)
  // Hold one independent canonical metadata lookup open. Selection and the
  // governed history request must still proceed from the confirmed identity.
  await preparationStarted
  expect(canonicalLookupWasDelayed).toBe(true)
  expect(canonicalInstrumentLookups).toContainEqual({ symbol: 'TCNEW', canonicalOnly: 'true' })
  releaseCanonicalLookup()
  expect(identityRequests[0]).toMatchObject({ symbol: 'TCNEW', provider_candidate: { provider: 'test-fixture', exchange: 'TEST' } })

  await expect.poll(() => preparationRequests.length).toBeGreaterThan(0)
  const selectedPreparation = preparationRequests.find(request => request.target.kind === 'instrument'
    && 'instrument_id' in request.target && request.target.instrument_id === fixtureInstrumentId)
  expect(selectedPreparation).toMatchObject({
    target: { kind: 'instrument', instrument_id: fixtureInstrumentId },
    datasets: ['identity', 'profile', 'history'],
    timeframe: 'D1',
    adjusted: true,
  })
  expect(selectedPreparation).not.toHaveProperty('start_at')
  expect(selectedPreparation).not.toHaveProperty('end_at')
  const selectedChart = page.locator('.chart-tool:visible').getByRole('region', { name: 'Chart workspace' }).first()
  await expect(selectedChart).toBeVisible()
  await expect(selectedChart.locator('.sr-only')).toContainText('chart; no OHLCV bars loaded.')
  expect(await selectedChart.locator('.sr-only').innerText()).not.toBe(previousChartProvenanceText)
  await expect(search).toHaveValue('TCNEW')
  await expect(page.locator('.workstation__selection-acquisition').filter({ hasText: 'No reviewed data source can provide this request.' })).toBeVisible()
  expect(legacyHistoryRequests).toEqual([])
  await browserDiagnostics.expectNoCriticalIssues()
})

test('an unresolved ETF holding row explicitly resolves its reported equity and carries lineage into D1 history', async ({ page, loggedIn, browserDiagnostics }) => {
  await page.goto('about:blank')

  const profileId = 779001
  const snapshotId = 779002
  const rowId = 779003
  const instrumentId = 779004
  const symbol = 'UNXQ'
  let resolved = false
  let historyCompleted = false
  let localReadCount = 0
  const optionsExposureReads: string[] = []
  const optionsExpirationReads: string[] = []
  const calendarReads: Array<{ symbol: string; start: string; end: string }> = []
  const discoveryRequests: DiscoveryRequest[] = []
  const identityRequests: InstrumentRequestBody[] = []
  const historyRequests: DataEnsureRequest[] = []
  const legacyHistoryRequests: string[] = []
  const localReadBars: OHLCVBar[][] = []
  let signalHistoryRequest!: () => void
  let releaseHistoryResponse!: () => void
  const historyRequestArrived = new Promise<void>(resolve => { signalHistoryRequest = resolve })
  const historyResponseGate = new Promise<void>(resolve => { releaseHistoryResponse = resolve })
  const bar: OHLCVBar = {
    ts: '2026-10-29T00:00:00Z', open: 24, high: 26, low: 23, close: 25,
    volume: 12000, is_adjusted: true, is_derived: false,
  }
  const capability = {
    availability: 'current', source_tier: 'issuer_native', identity_verified: true,
    usable_for_current_analysis: true, displayable_last_known: true,
    consecutive_failures: 0, reason: 'Controlled fixture capability only.',
    symbol_audit: { tier: 0, outcome: 'not_run', evidence_state: 'test_fixture', next_action: '', evidence_refs: [] },
  }
  const profile: ETFProfile = {
    id: profileId, instrument_id: 779000, symbol: 'OIH', name: 'Controlled Oil Services ETF',
    issuer: 'test-fixture', fund_family: 'controlled browser fixture', adapter_status: 'ready',
    latest_composition_date: '2026-10-27', latest_snapshot_id: snapshotId,
    resolved_count: 0, unresolved_count: 1, holdings_capability: capability,
  }
  const holding: ETFHolding = {
    id: rowId, snapshot_id: snapshotId, constituent_instrument_id: null,
    constituent_symbol: null, constituent_name: null, reported_symbol: symbol,
    reported_name: 'Uncached Example Equity', position: 1, source_row_id: 'issuer-row-779003',
    holding_type: 'equity', row_type: 'security', is_resolved: false, weight: 0.01,
  }
  const snapshot: ETFHoldingsSnapshot = {
    id: snapshotId, etf_profile_id: profileId, etf_instrument_id: 779000,
    etf_symbol: 'OIH', etf_name: profile.name, composition_date: '2026-10-27',
    known_at: '2026-10-28T12:00:00Z', published_at: null,
    provenance: 'controlled_fixture', source_provider: 'test-fixture',
    source_quality: 'fixture only', completeness_status: 'complete', row_count: 1,
    resolved_count: 0, unresolved_count: 1, total_weight: 0.01,
    parser_version: 'browser-fixture-v1', holdings: [holding],
  }
  const holdingsPage: ETFHoldingsPage = {
    snapshot, holdings: [holding], total: 1, limit: 100, offset: 0, has_next: false,
  }
  const noInstrumentCalendarEvents: InstrumentCalendarEvent[] = []
  const dates: ETFHoldingsDate[] = [{
    snapshot_id: snapshotId, composition_date: snapshot.composition_date,
    as_of_date: snapshot.as_of_date ?? null, known_at: snapshot.known_at ?? null,
    published_at: null, cadence: 'fixture', parser_version: snapshot.parser_version,
    provenance: snapshot.provenance, source_provider: snapshot.source_provider,
    source_identifier: 'fixture:OIH:UNXQ', row_count: 1, resolved_count: 0,
    unresolved_count: 1, source_quality: snapshot.source_quality,
  }]

  await page.route('**/api/v1/etf-holdings**', async route => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/v1/etf-holdings' && route.request().method() === 'GET') {
      await route.fulfill({ status: 200, json: [profile] })
    } else if (url.pathname === `/api/v1/etf-holdings/OIH/dates`) {
      await route.fulfill({ status: 200, json: dates })
    } else if (url.pathname === `/api/v1/etf-holdings/OIH/holdings`) {
      await route.fulfill({ status: 200, json: holdingsPage })
    } else if (url.pathname === `/api/v1/etf-holdings/OIH/weight-evolution`) {
      await route.fulfill({ status: 200, json: { etf_symbol: 'OIH', etf_name: profile.name, snapshot_count: 1, series: [] } })
    } else if (url.pathname === `/api/v1/etf-holdings/OIH/transitions`) {
      await route.fulfill({ status: 200, json: { etf_symbol: 'OIH', etf_name: profile.name, snapshot_count: 1, transition_count: 0, transitions: [] } })
    } else {
      await route.continue()
    }
  })
  // ChartView performs this bounded side-read only after local chart bars are
  // available. Match the one fictional symbol and endpoint exactly so a typo
  // or unrelated calendar URL still reaches the shared strict diagnostics.
  await page.route(url => {
    const parsed = new URL(url)
    return parsed.pathname === `/api/v1/calendar/instruments/${symbol}/calendar`
  }, async route => {
    const request = route.request()
    expect(request.method()).toBe('GET')
    const url = new URL(request.url())
    expect(url.pathname).toBe(`/api/v1/calendar/instruments/${symbol}/calendar`)
    const start = url.searchParams.get('start')
    const end = url.searchParams.get('end')
    expect(start, 'the chart calendar read is bounded by its loaded bars').not.toBeNull()
    expect(end, 'the chart calendar read is bounded by its loaded bars').not.toBeNull()
    expect(Date.parse(end!)).toBeGreaterThan(Date.parse(start!))
    calendarReads.push({ symbol, start: start!, end: end! })
    await route.fulfill({ status: 200, json: noInstrumentCalendarEvents })
  })
  await page.route('**/api/v1/instruments/discover**', async route => {
    const body = route.request().postDataJSON() as DiscoveryRequest
    discoveryRequests.push(body)
    expect(body.query).toBe(symbol)
    expect(body.types).toEqual(['Equity', 'Stock', 'CS'])
    const providerCandidate = {
      symbol, name: holding.reported_name ?? symbol, exchange: 'XNYS', type: 'CS',
      provider: 'test-fixture', instrument_id: null, identity_status: 'unresolved' as const,
    }
    // Match the backend's raw-type substring filter so a native CS candidate
    // is returned only when the outgoing request includes the verified code.
    const matchingCandidates = body.types.some(type =>
      providerCandidate.type.toUpperCase().includes(type.trim().toUpperCase()),
    )
    await route.fulfill({ status: 200, json: {
      request_id: body.request_id, status: 'complete',
      candidates: matchingCandidates ? [providerCandidate] : [],
      source_outcomes: [fixtureOutcome],
    } satisfies InstrumentDiscoveryResponse })
  })
  await page.route('**/api/v1/instruments/acquire**', async route => {
    const body = route.request().postDataJSON() as InstrumentRequestBody
    identityRequests.push(body)
    if (body.provider_candidate) {
      expect(body).toMatchObject({ symbol, provider_candidate: { provider: 'test-fixture', symbol, exchange: 'XNYS' } })
      resolved = true
    } else {
      expect(resolved, 'history identity check follows explicit row candidate resolution').toBe(true)
      expect(body.symbol).toBe(symbol)
    }
    await route.fulfill({ status: 200, json: resolvedIdentity(body, instrumentId, 'Common Stock') })
  })
  await page.route('**/api/v1/instruments/UNXQ', async route => {
    if (!resolved) {
      await route.fulfill({ status: 404, json: { detail: 'No pre-existing instrument in this controlled fixture.' } })
      return
    }
    await route.fulfill({ status: 200, json: {
      id: instrumentId, symbol, name: holding.reported_name, currency: 'USD',
      is_active: true, is_synthetic: false, stats: { week52_high: 30 },
    } })
  })
  await page.route('**/api/v1/instrument-indicators/779004**', route => route.fulfill({ status: 200, json: { indicators: [] } }))
  await page.route('**/api/v1/ohlcv/local/UNXQ/D1**', async route => {
    localReadCount += 1
    const bars = historyCompleted ? [bar] : []
    localReadBars.push(bars)
    await route.fulfill({ status: 200, json: bars })
  })
  await page.route('**/api/v1/instruments/UNXQ/data-coverage**', route => route.fulfill({ status: 200, json: { symbol, is_fetching: false } }))
  await page.route('**/api/v1/coverage/instruments/UNXQ/ohlcv**', async route => {
    const url = new URL(route.request().url())
    await route.fulfill({ status: 200, json: missingCoverage(url) })
  })
  await page.route('**/api/v1/instruments/UNXQ/options/exposure', async route => {
    const url = new URL(route.request().url())
    expect(route.request().method()).toBe('GET')
    expect(url.pathname).toBe('/api/v1/instruments/UNXQ/options/exposure')
    optionsExposureReads.push(url.pathname)
    await route.fulfill({ status: 200, json: {
      symbol, spot: null, expirations: [], active_expirations: [], computed_at: '2026-10-27T00:00:00Z',
      ladder: [], key_levels: { call_wall: null, put_wall: null, gamma_flip: null, max_pain: null },
      pcr_oi: null, pcr_volume: null, implied_move_pct: null, total_gex: 0, total_net_dex: 0,
    } satisfies OptionsExposureResponse })
  })
  await page.route('**/api/v1/instruments/UNXQ/options/exposure/expirations', async route => {
    const url = new URL(route.request().url())
    expect(route.request().method()).toBe('GET')
    expect(url.pathname).toBe('/api/v1/instruments/UNXQ/options/exposure/expirations')
    optionsExpirationReads.push(url.pathname)
    const noExpirations: ExpirationSummary[] = []
    await route.fulfill({ status: 200, json: noExpirations })
  })
  await page.route('**/api/v1/data/ensure', async route => {
    const body = route.request().postDataJSON() as DataEnsureRequest
    const requestedId = ensureInstrumentId(body)
    if (requestedId !== instrumentId) return route.continue()
    expect(body.timeframe).toBe('D1')
    expect(body.datasets).toContain('history')
    expect(body.adjusted).toBe(true)
    expect(body.start_at).toBeUndefined()
    expect(body.end_at).toBeUndefined()
    historyRequests.push(body)
    signalHistoryRequest()
    await historyResponseGate
    historyCompleted = true
    const response = historyPreparation(body, instrumentId, symbol, 'partial', bar)
    await route.fulfill({ status: 200, json: response })
  })
  await page.route('**/api/v1/instruments/*/history-acquisitions**', async route => {
    legacyHistoryRequests.push(route.request().url())
    await route.fulfill({ status: 500, json: { detail: 'Selected history is coordinated through POST /data/ensure.' } })
  })
  await page.route('**/api/v1/ohlcv/UNXQ/D1**', route => route.fulfill({ status: 200, json: [] }))
  await page.route('**/api/v1/drawings**', route => route.fulfill({ status: 200, json: [] }))
  await page.route('**/api/v1/alerts**', route => route.fulfill({ status: 200, json: [] }))

  await page.goto('/etf-holdings')
  const holdingButton = page.locator('button.holding-row').filter({ hasText: symbol })
  await expect(holdingButton).toContainText(symbol)
  expect(discoveryRequests).toHaveLength(0)
  expect(identityRequests).toHaveLength(0)
  expect(historyRequests).toHaveLength(0)
  expect(localReadCount).toBe(0)
  expect(calendarReads).toHaveLength(0)

  const discoveryResponseReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'POST' && url.pathname === '/api/v1/instruments/discover'
  })
  await holdingButton.click()
  await page.getByRole('button', { name: `Resolve reported holding ${symbol}` }).click()
  expect(discoveryRequests).toHaveLength(0)
  expect((await discoveryResponseReady).status()).toBe(200)
  expect(discoveryRequests).toHaveLength(1)
  expect(identityRequests).toHaveLength(0)
  const historyResponseReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'POST'
      && url.pathname === '/api/v1/data/ensure'
  })
  await page.getByRole('option', { name: /Use UNXQ · XNYS/ }).click()
  await expect(page).toHaveURL(/\/chart\/UNXQ\?/)
  expect(identityRequests).toHaveLength(1)
  await historyRequestArrived
  expect(historyRequests).toHaveLength(1)
  expect(historyRequests[0]).toMatchObject({ target: { kind: 'instrument', instrument_id: instrumentId }, timeframe: 'D1', adjusted: true })
  expect(historyRequests[0]?.datasets).toContain('history')
  expect(historyRequests[0]?.start_at).toBeUndefined()
  expect(historyRequests[0]?.end_at).toBeUndefined()
  await expect.poll(() => localReadCount).toBeGreaterThan(0)
  expect(localReadBars[0]).toEqual([])
  expect(calendarReads).toHaveLength(0)

  // Keep the initial empty-chart assertions ahead of the acquired response.
  // Bars make the bounded calendar side-read eligible, so release only after
  // the no-bars/no-calendar state has been observed.
  releaseHistoryResponse()
  const historyResponse = await historyResponseReady
  expect(historyResponse.status()).toBe(200)
  expect(historyRequests).toHaveLength(1)
  expect(historyRequests[0]).toMatchObject({ target: { kind: 'instrument', instrument_id: instrumentId }, timeframe: 'D1', adjusted: true })
  expect(localReadCount).toBeGreaterThan(0)

  const lineageUrl = new URL(page.url())
  expect(lineageUrl.searchParams.get('holding_snapshot_id')).toBe(String(snapshotId))
  expect(lineageUrl.searchParams.get('holding_composition_date')).toBe(snapshot.composition_date)
  expect(lineageUrl.searchParams.get('holding_known_at')).toBe(snapshot.known_at)
  expect(lineageUrl.searchParams.get('holding_provenance')).toBe(snapshot.provenance)
  expect(lineageUrl.searchParams.get('holding_source_provider')).toBe(snapshot.source_provider)
  expect(lineageUrl.searchParams.get('holding_row_id')).toBe(String(rowId))
  expect(lineageUrl.searchParams.get('holding_source_row_id')).toBe(holding.source_row_id)
  expect(lineageUrl.searchParams.get('holding_reported_symbol')).toBe(symbol)
  expect(lineageUrl.searchParams.get('holding_reported_name')).toBe(holding.reported_name)
  await expect(page.locator('.historical-holding-context')).toContainText('UNXQ')
  await expect(page.locator('.historical-holding-context')).toContainText('controlled_fixture')

  await expect(page.getByRole('status').filter({ hasText: 'Loaded 1 local D1 bars for UNXQ.' })).toBeVisible()
  expect(historyRequests).toHaveLength(1)
  expect(historyRequests[0]?.timeframe).toBe('D1')
  await expect.poll(() => localReadCount).toBeGreaterThan(1)
  expect(localReadBars.at(-1)).toEqual([bar])

  const readsBeforeReload = localReadCount
  const calendarReadsBeforeReload = calendarReads.length
  const mainFrame = page.mainFrame()
  let mainDocumentEpoch = 0
  const requestDocumentEpoch = new WeakMap<Request, number>()
  const recordMainFrameNavigation = (frame: Frame) => {
    if (frame === mainFrame) mainDocumentEpoch += 1
  }
  const recordMainFrameRequest = (request: Request) => {
    if (request.frame() === mainFrame) requestDocumentEpoch.set(request, mainDocumentEpoch)
  }
  page.on('framenavigated', recordMainFrameNavigation)
  page.on('request', recordMainFrameRequest)
  const documentEpochBeforeReload = mainDocumentEpoch
  const calendarResponseAfterReloadReady = page.waitForResponse(response => {
    const request = response.request()
    const url = new URL(request.url())
    return request.frame() === mainFrame
      && (requestDocumentEpoch.get(request) ?? 0) > documentEpochBeforeReload
      && request.method() === 'GET'
      && url.pathname === `/api/v1/calendar/instruments/${symbol}/calendar`
  }).then(async response => {
    const request = response.request()
    return {
      method: request.method(),
      pathname: new URL(request.url()).pathname,
      status: response.status(),
      body: await response.json(),
    }
  })
  await page.reload()
  const calendarResponseAfterReload = await calendarResponseAfterReloadReady
  page.off('framenavigated', recordMainFrameNavigation)
  page.off('request', recordMainFrameRequest)
  expect(calendarResponseAfterReload.method).toBe('GET')
  expect(calendarResponseAfterReload.pathname).toBe(`/api/v1/calendar/instruments/${symbol}/calendar`)
  expect(calendarResponseAfterReload.status).toBe(200)
  expect(calendarResponseAfterReload.body).toEqual(noInstrumentCalendarEvents)
  await expect(page).toHaveURL(/\/chart\/UNXQ\?/)
  await expect(page.locator('.historical-holding-context')).toContainText('UNXQ')
  await expect.poll(() => localReadCount).toBeGreaterThan(readsBeforeReload)
  expect(localReadBars.at(-1)).toEqual([bar])
  expect(historyRequests).toHaveLength(1)
  expect(optionsExposureReads.length).toBeGreaterThan(0)
  expect(optionsExpirationReads.length).toBeGreaterThan(0)
  await expect.poll(() => calendarReads.length).toBeGreaterThan(calendarReadsBeforeReload)
  expect(calendarReads.at(-1)).toMatchObject({ symbol, start: bar.ts })
  expect(calendarReads.every(read => read.symbol === symbol)).toBe(true)
  expect(legacyHistoryRequests).toEqual([])
  await browserDiagnostics.expectNoCriticalIssues()
})

test('main Workstation automatically discovers an unknown ticker and loads missing bars after selection', async ({ page, loggedIn, browserDiagnostics }) => {
  await page.goto('about:blank')

  const fixtureInstrumentId = 990014
  let canonicalInstrumentResolved = false
  let historyAcquired = false
  let acquiredBar: OHLCVBar | null = null
  const discoveryRequests: DiscoveryRequest[] = []
  const instrumentRequests: InstrumentRequestBody[] = []
  const tcnewPreparationRequests: DataEnsureRequest[] = []
  const legacyHistoryRequests: string[] = []
  const directOhlcvWrites: string[] = []
  const canonicalSearchRequests: string[] = []
  const localBarReadbacks: Array<{ symbol: string; timeframe: string; rows: OHLCVBar[]; afterAcquisition: boolean }> = []
  const calendarRequests: string[] = []
  page.on('request', request => {
    const url = new URL(request.url())
    const path = url.pathname
    const isTCNEWPath = /TCNEW/i.test(path) || path.includes(`/${fixtureInstrumentId}/`)
    if (/\/ohlcv\//i.test(path) && isTCNEWPath && request.method() !== 'GET') {
      directOhlcvWrites.push(`${request.method()} ${path}`)
    }
  })

  // UPlotChart reads the instrument calendar when local bars become available.
  // TCNEW exists only in this page's controlled fixture, so return the API's
  // real empty-list response instead of allowing the backend to bootstrap it.
  await page.route(url => new URL(url).pathname === '/api/v1/calendar/instruments/TCNEW/calendar', async route => {
    const request = route.request()
    expect(request.method()).toBe('GET')
    const url = new URL(request.url())
    const match = url.pathname.match(/^\/api\/v1\/calendar\/instruments\/([^/]+)\/calendar$/)
    const symbol = decodeURIComponent(match?.[1] ?? '')
    expect(symbol, 'the synthetic identity must scope calendar reads to TCNEW').toBe('TCNEW')
    calendarRequests.push(symbol)
    await route.fulfill({ status: 200, json: [] })
  })

  await page.route('**/api/v1/instruments/search**', async route => {
    const url = new URL(route.request().url())
    const query = url.searchParams.get('q')?.toUpperCase()
    if (route.request().method() !== 'GET' || !['TCNEW', 'BWET'].includes(query ?? '')) {
      await route.continue()
      return
    }
    canonicalSearchRequests.push(query ?? '')
    if (query === 'BWET') {
      await route.fulfill({ status: 200, json: [] })
      return
    }
    await route.fulfill({
      status: 200,
      json: canonicalInstrumentResolved ? [{
        symbol: 'TCNEW',
        name: 'Unknown ticker (controlled test fixture)',
        exchange: 'TEST',
        type: 'Stock',
        instrument_id: fixtureInstrumentId,
        identity_status: 'resolved',
      }] : [],
    })
  })

  await page.route('**/api/v1/instruments/TCNEW**', async route => {
    if (route.request().method() !== 'GET') return route.continue()
    if (!canonicalInstrumentResolved) {
      await route.fulfill({ status: 404, json: { detail: 'Not present before explicit fixture resolution.' } })
      return
    }
    await route.fulfill({
      status: 200,
      json: {
        id: fixtureInstrumentId,
        symbol: 'TCNEW',
        name: 'Unknown ticker (controlled test fixture)',
        currency: 'USD',
        is_active: true,
        stats: { week52_high: 12 },
      },
    })
  })
  await page.route('**/api/v1/instruments/TCNEW/data-coverage', async route => {
    await route.fulfill({ status: 200, json: { instrument_id: fixtureInstrumentId, symbol: 'TCNEW', coverage: {}, is_fetching: false, fetch_progress: null } })
  })
  await page.route('**/api/v1/instruments/TCNEW/options/exposure', async route => {
    await route.fulfill({ status: 200, json: {
      symbol: 'TCNEW', spot: null, expirations: [], active_expirations: [], computed_at: '2026-10-27T00:00:00Z',
      ladder: [], key_levels: { call_wall: null, put_wall: null, gamma_flip: null, max_pain: null },
      pcr_oi: null, pcr_volume: null, implied_move_pct: null, total_gex: 0, total_net_dex: 0,
    } satisfies OptionsExposureResponse })
  })
  await page.route('**/api/v1/instruments/TCNEW/options/exposure/expirations', async route => {
    const noExpirations: ExpirationSummary[] = []
    await route.fulfill({ status: 200, json: noExpirations })
  })
  await page.route('**/api/v1/ohlcv/local/TCNEW/**', async route => {
    const timeframe = new URL(route.request().url()).pathname.split('/').at(-1) ?? ''
    const rows = historyAcquired && acquiredBar ? [acquiredBar] : []
    localBarReadbacks.push({ symbol: 'TCNEW', timeframe, rows, afterAcquisition: historyAcquired })
    await route.fulfill({ status: 200, json: rows })
  })

  await page.route('**/api/v1/instruments/discover**', async route => {
    const body = route.request().postDataJSON() as DiscoveryRequest
    discoveryRequests.push(body)
    const hasControlledListing = body.query.trim().toUpperCase() === 'TCNEW'
    const response = {
      request_id: body.request_id,
      status: hasControlledListing ? 'complete' : 'no_match',
      candidates: hasControlledListing ? [{
        symbol: 'TCNEW', name: 'Unknown ticker (controlled test fixture)', exchange: 'TEST', type: 'Stock',
        provider: 'test-fixture', instrument_id: null, identity_status: 'unresolved',
      }] : [],
      source_outcomes: hasControlledListing
        ? [{ ...fixtureOutcome, capability: 'instrument_search', operation: 'search', status: 'returned', result_count: 1 }]
        : [{ ...fixtureOutcome, capability: 'instrument_search', operation: 'search', status: 'no_match', result_count: 0 }],
    } satisfies InstrumentDiscoveryResponse
    await route.fulfill({ status: 200, json: response })
  })
  await page.route('**/api/v1/instruments/acquire**', async route => {
    const body = route.request().postDataJSON() as InstrumentRequestBody
    if (body.symbol.trim().toUpperCase() !== 'TCNEW') {
      await route.continue()
      return
    }
    instrumentRequests.push(body)
    expect(body.symbol).toBe('TCNEW')
    canonicalInstrumentResolved = true
    await route.fulfill({ status: 200, json: resolvedIdentity(body, fixtureInstrumentId, 'Common Stock') })
  })
  await page.route('**/api/v1/data/ensure', async route => {
    expect(route.request().method()).toBe('POST')
    const body = route.request().postDataJSON() as DataEnsureRequest
    const target = body.target
    const isTCNEWTarget = target.kind === 'instrument' && (
      'instrument_id' in target && target.instrument_id === fixtureInstrumentId
      || 'symbol' in target && target.symbol?.trim().toUpperCase() === 'TCNEW'
    )
    if (!isTCNEWTarget) {
      await route.continue()
      return
    }
    tcnewPreparationRequests.push(body)
    const isCanonicalM1Selection = body.timeframe === 'M1'
      && target.kind === 'instrument'
      && 'instrument_id' in target
      && target.instrument_id === fixtureInstrumentId
    if (isCanonicalM1Selection) {
      expect(body.target).toEqual({ kind: 'instrument', instrument_id: fixtureInstrumentId })
      expect(body.datasets).toEqual(['identity', 'profile', 'history'])
      expect(body.adjusted).toBe(true)
      acquiredBar = {
        ts: '2026-11-06T15:00:00.000Z', open: 10, high: 11, low: 9, close: 10.5, volume: 100,
        is_adjusted: true, is_derived: false,
      }
      historyAcquired = true
    }
    const now = new Date().toISOString()
    const historyDependency = {
      dependency_id: `history-${body.timeframe ?? 'D1'}-${tcnewPreparationRequests.length}`,
      depends_on: [],
      instrument_id: fixtureInstrumentId,
      symbol: 'TCNEW',
      dataset: 'history',
      status: isCanonicalM1Selection ? 'partial' : 'unavailable',
      requested_start: null,
      requested_end: null,
      covered_start: isCanonicalM1Selection ? acquiredBar!.ts : null,
      covered_end: isCanonicalM1Selection ? acquiredBar!.ts : null,
      reason_code: isCanonicalM1Selection ? null : 'fixture_no_data_for_other_timeframe',
      retry_at: null,
      updated_at: now,
      covered_ranges: isCanonicalM1Selection ? [{
        start_at: acquiredBar!.ts,
        end_at: acquiredBar!.ts,
        data_source_id: null,
        market_series_id: null,
        adjustment_basis: 'split_adjusted',
        adjustment_version: 'fixture-v1',
        is_adjusted: true,
      }] : [],
    }
    const response = {
      request_id: `fixture-preparation-${tcnewPreparationRequests.length}`,
      status: isCanonicalM1Selection ? 'partial' : 'unavailable',
      created_at: now,
      updated_at: now,
      version: 1,
      target: body.target,
      dependencies: [historyDependency],
      completed: 1,
      total: 1,
      last_progress_at: now,
      has_pending_work: false,
    } satisfies DataEnsureResponse
    await route.fulfill({ status: 200, json: response })
  })
  await page.route('**/api/v1/instruments/*/history-acquisitions**', async route => {
    const url = new URL(route.request().url())
    if (url.pathname.includes(`/instruments/${fixtureInstrumentId}/`) || url.pathname.includes('/instruments/TCNEW/')) {
      legacyHistoryRequests.push(route.request().url())
      await route.fulfill({ status: 500, json: { detail: 'The shared preparation contract owns this journey.' } })
      return
    }
    await route.continue()
  })

  await page.goto('/')
  const search = page.getByRole('combobox', { name: 'Active symbol' })
  await expect(search).toBeVisible()
  await page.getByLabel('Linked timeframe').selectOption('M1')
  expect(discoveryRequests).toHaveLength(0)
  expect(instrumentRequests).toHaveLength(0)
  expect(tcnewPreparationRequests).toHaveLength(0)

  const canonicalSearchReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'GET'
      && url.pathname === '/api/v1/instruments/search'
      && url.searchParams.get('q')?.toUpperCase() === 'TCNEW'
  })
  const discoveryReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'POST' && url.pathname === '/api/v1/instruments/discover'
  }, { timeout: 10_000 })
  await search.click()
  await search.fill('')
  await search.pressSequentially('TCNEW', { delay: 25 })
  const canonicalSearch = await canonicalSearchReady
  expect(await canonicalSearch.json()).toEqual([])
  expect(canonicalSearchRequests).toEqual(['TCNEW'])
  expect(discoveryRequests).toHaveLength(0)
  expect(instrumentRequests).toHaveLength(0)

  const discovery = await discoveryReady
  expect(discovery.status()).toBe(200)
  expect(await discovery.json()).toMatchObject({ candidates: [{ symbol: 'TCNEW', identity_status: 'unresolved' }] })
  expect(discoveryRequests).toHaveLength(1)
  expect(discoveryRequests[0]).toMatchObject({ query: 'TCNEW', types: [], limit: 10 })
  expect(discoveryRequests[0]?.request_id).toMatch(/^[0-9a-f-]{36}$/i)

  const candidateResolveReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'POST' && url.pathname === '/api/v1/instruments/acquire'
  }, { timeout: 10_000 })
  const historyReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'POST'
      && url.pathname === '/api/v1/data/ensure'
      && (() => {
        const body = response.request().postDataJSON() as DataEnsureRequest
        return body.timeframe === 'M1' && body.target.kind === 'instrument'
          && 'instrument_id' in body.target && body.target.instrument_id === fixtureInstrumentId
      })()
  }, { timeout: 15_000 })
  let acquiredLocalRows: OHLCVBar[] | null = null
  // The initial chart request may still be in flight when ensure reports
  // covered history. The chart store waits for that exact load to settle
  // before issuing a fresh local read, so wait for the matching response
  // rather than the generic five-second expect.poll interval.
  const acquiredLocalBarReadback = page.waitForResponse(async response => {
    const url = new URL(response.url())
    if (response.request().method() !== 'GET'
      || url.pathname !== '/api/v1/ohlcv/local/TCNEW/M1'
      || response.status() !== 200
      || !historyAcquired
      || !acquiredBar) return false
    const rows = await response.json() as OHLCVBar[]
    const matchesCoveredBar = rows.length === 1
      && rows[0]?.ts === acquiredBar.ts
      && rows[0]?.close === acquiredBar.close
    if (matchesCoveredBar) acquiredLocalRows = rows
    return matchesCoveredBar
  }, { timeout: 15_000 })
  await page.getByRole('button', { name: /Use TCNEW · TEST/ }).click()
  const candidateResolve = await candidateResolveReady
  expect(candidateResolve.status()).toBe(200)
  await expect(search).toHaveValue('TCNEW')
  await expect(page).toHaveURL(/\/$/)
  expect(instrumentRequests).toHaveLength(1)
  expect(instrumentRequests[0]).toMatchObject({
    symbol: 'TCNEW',
    provider_candidate: { provider: 'test-fixture', symbol: 'TCNEW', exchange: 'TEST' },
  })
  // Candidate resolution itself returns the trusted canonical identity. The
  // chart consumes that exact response instead of issuing a redundant lookup.
  expect(await candidateResolve.json()).toMatchObject({
    instrument: { instrument_id: fixtureInstrumentId, symbol: 'TCNEW', identity_status: 'resolved' },
  })
  const historyResponse = await historyReady
  expect(historyResponse.status()).toBe(200)
  const preparationResult = await historyResponse.json() as DataEnsureResponse
  expect(preparationResult).toMatchObject({
    status: 'partial',
    has_pending_work: false,
    dependencies: [{
      instrument_id: fixtureInstrumentId,
      symbol: 'TCNEW',
      dataset: 'history',
      covered_ranges: [{ is_adjusted: true }],
    }],
  })
  expect(tcnewPreparationRequests.filter(request => request.timeframe === 'M1'
    && request.target.kind === 'instrument'
    && 'instrument_id' in request.target
    && request.target.instrument_id === fixtureInstrumentId)).toEqual([{
    target: { kind: 'instrument', instrument_id: fixtureInstrumentId },
    datasets: ['identity', 'profile', 'history'],
    timeframe: 'M1',
    adjusted: true,
  }])
  expect(instrumentRequests).toHaveLength(1)

  const chartWorkspace = page.getByRole('region', { name: 'Chart workspace' })
  await chartWorkspace.click()
  await expect(page.locator('.chart-tool:visible').getByRole('region', { name: 'Chart workspace' })).toBeVisible()

  await acquiredLocalBarReadback
  expect(acquiredLocalRows).toEqual([acquiredBar])
  expect(localBarReadbacks.some(readback => readback.afterAcquisition
    && readback.symbol === 'TCNEW'
    && readback.timeframe === 'M1'
    && readback.rows.length === 1
    && readback.rows[0]?.ts === acquiredBar?.ts)).toBe(true)
  expect(localBarReadbacks.filter(readback => readback.afterAcquisition).every(readback => readback.symbol === 'TCNEW' && readback.timeframe === 'M1')).toBe(true)
  await expect(page.getByTestId('workstation-history-acquisition')).toHaveCount(0)
  const visibleChart = page.locator('.chart-tool:visible .chart-root')
  await expect(visibleChart).toHaveAttribute('aria-busy', 'false', { timeout: 10_000 })
  await expect(visibleChart.locator('.sr-only')).toContainText('M1 chart; 1 bars')
  await expect.poll(() => calendarRequests.length).toBeGreaterThan(0)
  expect(calendarRequests.every(symbol => symbol === 'TCNEW')).toBe(true)
  expect(tcnewPreparationRequests.filter(request => request.timeframe === 'M1'
    && request.target.kind === 'instrument'
    && 'instrument_id' in request.target
    && request.target.instrument_id === fixtureInstrumentId)).toHaveLength(1)
  expect(legacyHistoryRequests).toEqual([])
  expect(directOhlcvWrites).toEqual([])

  // A second unknown ticker with no controlled candidate stays a search result:
  // it does not resolve an identity or replace the already loaded chart.
  const noMatchSearchReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'GET'
      && url.pathname === '/api/v1/instruments/search'
      && url.searchParams.get('q')?.toUpperCase() === 'BWET'
  })
  const noMatchDiscoveryReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'POST' && url.pathname === '/api/v1/instruments/discover'
      && (response.request().postDataJSON() as DiscoveryRequest).query.trim().toUpperCase() === 'BWET'
  }, { timeout: 10_000 })
  await search.fill('BWET')
  expect(await (await noMatchSearchReady).json()).toEqual([])
  const noMatchDiscovery = await noMatchDiscoveryReady
  expect(noMatchDiscovery.status()).toBe(200)
  expect(await noMatchDiscovery.json()).toMatchObject({ status: 'no_match', candidates: [] })
  await expect(page.getByRole('button', { name: /Search free sources/ })).toHaveCount(0)
  expect(discoveryRequests.map(request => request.query.trim().toUpperCase())).toEqual(['TCNEW', 'BWET'])
  expect(instrumentRequests).toHaveLength(1)
  expect(tcnewPreparationRequests.filter(request => request.timeframe === 'M1'
    && request.target.kind === 'instrument'
    && 'instrument_id' in request.target
    && request.target.instrument_id === fixtureInstrumentId)).toHaveLength(1)
  await expect(page.locator('.chart-tool:visible .chart-root')).toHaveAttribute('aria-busy', 'false')
  await browserDiagnostics.expectNoCriticalIssues()
})

test('held IWM issuer and constituent-history actions preserve snapshot lineage and current-analysis eligibility', async ({ page, loggedIn, browserDiagnostics }) => {
  await page.goto('about:blank')

  const identityRequests: InstrumentRequestBody[] = []
  const discoveryRequests: DiscoveryRequest[] = []
  const issuerRequests: IssuerRequest[] = []
  const historyRequests: DataEnsureRequest[] = []
  let selectedProfile: ETFProfile | null = null
  let amdInstrumentId = 0
  let iwmInstrumentId = 0

  await page.route('**/api/v1/instruments/acquire**', async route => {
    const body = route.request().postDataJSON() as InstrumentRequestBody
    identityRequests.push(body)
    const ids: Record<string, number> = {
      IWM: iwmInstrumentId,
      AMD: amdInstrumentId,
    }
    const symbol = body.symbol.trim().toUpperCase()
    const instrumentId = ids[symbol]
    expect(instrumentId, `identity fixture must use the local canonical ${symbol} ID`).toBeGreaterThan(0)
    await route.fulfill({ status: 200, json: resolvedIdentity(body, instrumentId, symbol === 'AMD' ? 'Common Stock' : 'ETF') })
  })

  await page.route('**/api/v1/instruments/discover**', async route => {
    const body = route.request().postDataJSON() as DiscoveryRequest
    discoveryRequests.push(body)
    const response = {
      request_id: body.request_id,
      status: 'no_match',
      candidates: [],
      source_outcomes: [],
    } satisfies InstrumentDiscoveryResponse
    await route.fulfill({ status: 200, json: response })
  })

  await page.route('**/api/v1/etf-holdings/IWM/acquire**', async route => {
    const body = route.request().postDataJSON() as IssuerRequest
    issuerRequests.push(body)
    if (!selectedProfile) throw new Error('Expected the seeded IWM profile before its explicit issuer request')
    const response = {
      request_id: body.request_id,
      instrument_id: selectedProfile.instrument_id,
      symbol: selectedProfile.symbol,
      outcome: 'held',
      refresh: body.refresh,
      refresh_attempted: true,
      refresh_succeeded: false,
      profile: { ...selectedProfile, holdings_capability: iwmUnknownCapability },
      capability: iwmUnknownCapability,
      provider_request_log_ids: [],
      message: 'Deterministic test-fixture hold; the stored snapshot remains available.',
    } satisfies ETFProfileAcquireResponse
    await route.fulfill({ status: 200, json: response })
  })

  // The stored IWM snapshot is marked stale in this controlled fixture, so an
  // explicit profile selection should confirm identity once and then attempt
  // the governed refresh while retaining that snapshot.
  const iwmUnknownCapability: ETFHoldingsCapability = {
    availability: 'unknown', source_tier: 'none', identity_verified: true,
    usable_for_current_analysis: false, displayable_last_known: true,
    consecutive_failures: 0, reason: 'Controlled fixture requires a governed refresh.',
    symbol_audit: { tier: 0, outcome: 'not_run', evidence_state: 'test_fixture', next_action: '', evidence_refs: [] },
  }
  await page.route(url => url.pathname.replace(/\/+$/, '') === '/api/v1/etf-holdings', async route => {
    if (route.request().method() !== 'GET') return route.continue()
    const response = await route.fetch()
    const profiles = await response.json() as ETFProfile[]
    await route.fulfill({
      response,
      json: profiles.map(profile => profile.symbol === 'IWM'
        ? { ...profile, holdings_capability: iwmUnknownCapability }
        : profile),
    })
  })
  await page.route('**/api/v1/etf-holdings/IWM/capability', async route => {
    await route.fulfill({ status: 200, json: iwmUnknownCapability })
  })

  await page.route('**/api/v1/coverage/instruments/AMD/ohlcv*', async route => {
    await route.fulfill({ status: 200, json: missingCoverage(new URL(route.request().url())) })
  })

  const directHistoryRequests: string[] = []
  await page.route('**/api/v1/instruments/*/history-acquisitions**', async route => {
    directHistoryRequests.push(route.request().url())
    await route.fulfill({ status: 500, json: { detail: 'Chart history must use the shared preparation coordinator.' } })
  })
  await page.route('**/api/v1/data/ensure', async route => {
    const body = route.request().postDataJSON() as DataEnsureRequest
    const requestedId = ensureInstrumentId(body)
    if (requestedId !== amdInstrumentId) return route.continue()
    expect(body.datasets).toContain('history')
    expect(body.adjusted).toBe(true)
    expect(body.start_at).toBeUndefined()
    expect(body.end_at).toBeUndefined()
    historyRequests.push(body)
    await route.fulfill({ status: 200, json: historyPreparation(body, requestedId, 'AMD', 'unavailable') })
  })

  const profilesReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'GET'
      && url.pathname === '/api/v1/etf-holdings'
      && !url.searchParams.has('q')
  })
  await page.goto('/etf-holdings')
  const profiles = await (await profilesReady).json() as ETFProfile[]
  selectedProfile = profiles.find(profile => profile.symbol === 'IWM') ?? null
  expect(selectedProfile?.latest_snapshot_id).toBeTruthy()
  expect(selectedProfile?.holdings_capability).toEqual(iwmUnknownCapability)
  expect(issuerRequests).toHaveLength(0)
  expect(identityRequests).toHaveLength(0)
  expect(discoveryRequests).toHaveLength(0)
  await expect(page.locator('.profile-list .state-line')).toHaveCount(0)

  const etfSearch = page.getByPlaceholder('Search ETF instrument')
  const typedSearch = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'GET'
      && url.pathname === '/api/v1/instruments/search'
      && url.searchParams.get('q')?.toUpperCase() === 'IWM'
  })
  await etfSearch.fill('IWM')
  const iwmSearchResults = await (await typedSearch).json() as Array<{ symbol: string; instrument_id?: number | null }>
  iwmInstrumentId = Number(iwmSearchResults.find(result => result.symbol === 'IWM')?.instrument_id ?? 0)
  expect(iwmInstrumentId, 'issuer identity uses the actual local canonical IWM ID').toBeGreaterThan(0)
  expect(issuerRequests).toHaveLength(0)
  expect(identityRequests).toHaveLength(0)
  expect(discoveryRequests).toHaveLength(0)

  const holdingsReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'GET'
      && url.pathname === '/api/v1/etf-holdings/IWM/holdings'
  })
  const iwmIdentityResponseReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'POST'
      && url.pathname.replace(/\/+$/, '') === '/api/v1/instruments/acquire'
  }, { timeout: 10_000 })
  const firstIwmIssuerResponseReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'POST' && url.pathname === '/api/v1/etf-holdings/IWM/acquire'
  }, { timeout: 10_000 })
  await page.locator('.profile-card').filter({ hasText: 'IWM' }).first().click()
  const originalPage = await (await holdingsReady).json() as ETFHoldingsPage
  const amdRow = originalPage.holdings.find(row => (row.constituent_symbol || row.reported_symbol) === 'AMD' && row.is_resolved)
  amdInstrumentId = Number(amdRow?.constituent_instrument_id ?? 0)
  expect(amdInstrumentId, 'history identity uses the actual selected constituent ID').toBeGreaterThan(0)

  const lineage = page.getByTestId('etf-snapshot-lineage')
  await expect(lineage).toBeVisible()
  const originalLineage = await lineage.innerText()
  const snapshotPanel = page.locator('.holdings-main > .workspace-panel').filter({ has: lineage })
  await expect(snapshotPanel.locator('.panel-title-row > .panel-meta')).toContainText(/unknown/i)
  const originalEligibility = await snapshotPanel.locator('.panel-title-row > .panel-meta').innerText()
  const compositionLine = await page.locator('.snapshot-date-line').innerText()
  const compositionDate = compositionLine.match(/Composition (\d{4}-\d{2}-\d{2})/)?.[1]
  const knownAt = await page.getByTestId('etf-snapshot-known-at').getAttribute('datetime')
  expect(compositionDate).toBeTruthy()
  expect(knownAt).toBeTruthy()
  const rowLocator = page.locator('.holdings-table .holding-row:not(.holding-row--head)')
  const originalRowCount = await rowLocator.count()
  expect(originalRowCount).toBeGreaterThan(0)

  // The first deliberate stale-profile selection above is itself the approved
  // refresh intent; identity is confirmed once before its issuer request.
  const iwmIdentityResponse = await iwmIdentityResponseReady
  expect(iwmIdentityResponse.status()).toBe(200)
  expect(await iwmIdentityResponse.json()).toMatchObject({ status: 'resolved', instrument: { symbol: 'IWM', identity_status: 'resolved' } })
  const firstIwmIssuerResponse = await firstIwmIssuerResponseReady
  expect(firstIwmIssuerResponse.status()).toBe(200)
  expect(await firstIwmIssuerResponse.json()).toMatchObject({
    outcome: 'held',
    symbol: 'IWM',
    profile: { holdings_capability: iwmUnknownCapability },
    capability: iwmUnknownCapability,
  })
  await expect(page.getByRole('status').filter({ hasText: 'The holdings update did not complete.' })).toBeVisible()
  expect(identityRequests).toHaveLength(1)
  expect(identityRequests[0]).toMatchObject({ symbol: 'IWM' })
  expect(issuerRequests).toHaveLength(1)
  expect(issuerRequests[0]).toMatchObject({ refresh: true })
  expect(await lineage.innerText()).toBe(originalLineage)
  expect(await snapshotPanel.locator('.panel-title-row > .panel-meta').innerText()).toBe(originalEligibility)
  await expect(page.getByTestId('etf-snapshot-known-at')).toHaveAttribute('datetime', String(knownAt))
  await expect(rowLocator).toHaveCount(originalRowCount)

  const manualRetryReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'POST' && url.pathname === '/api/v1/etf-holdings/IWM/acquire'
  }, { timeout: 10_000 })
  await page.getByTestId('etf-request-issuer').click()
  expect((await manualRetryReady).status()).toBe(200)
  expect(identityRequests).toHaveLength(1) // the already confirmed ID is reused on retry
  expect(issuerRequests).toHaveLength(2)
  expect(issuerRequests[1]).toMatchObject({ refresh: true, instrument_id: iwmInstrumentId })

  const initialChartCoverageReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'GET'
      && url.pathname === '/api/v1/instruments/AMD/data-coverage'
  })
  const automaticD1HistoryReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'POST'
      && url.pathname === '/api/v1/data/ensure'
      && (response.request().postDataJSON() as DataEnsureRequest).timeframe === 'D1'
  })
  await page.locator('button.holding-row').filter({ hasText: 'AMD' }).click()
  await page.getByRole('button', { name: 'View history' }).click()
  await expect(page).toHaveURL(/\/chart\/AMD(?:\?|$)/)
  expect((await initialChartCoverageReady).status()).toBe(200)
  const automaticD1History = await automaticD1HistoryReady
  expect(automaticD1History.status()).toBe(200)
  expect(await automaticD1History.json()).toMatchObject({
    status: 'unavailable',
    has_pending_work: false,
    dependencies: [{ status: 'unavailable', dataset: 'history', symbol: 'AMD', instrument_id: amdInstrumentId }],
  })
  expect(historyRequests).toHaveLength(1)
  expect(historyRequests[0]).toMatchObject({ target: { kind: 'instrument', instrument_id: amdInstrumentId }, timeframe: 'D1', adjusted: true })
  expect(identityRequests).toHaveLength(2)
  expect(identityRequests[1]).toMatchObject({ symbol: 'AMD' })
  await expect(page.getByRole('status').filter({ hasText: 'Some requested data is unavailable. Available results remain usable.' })).toBeVisible()
  const historyUrl = new URL(page.url())
  expect(historyUrl.pathname).toBe('/chart/AMD')
  expect(historyUrl.searchParams.get('holding_snapshot_id')).toBe(String(selectedProfile?.latest_snapshot_id))
  expect(historyUrl.searchParams.get('holding_composition_date')).toBe(compositionDate)
  expect(historyUrl.searchParams.get('holding_known_at')).toBe(knownAt)
  expect(historyUrl.searchParams.get('holding_provenance')).toBe('controlled_fixture')
  expect(Number(historyUrl.searchParams.get('holding_instrument_id'))).toBe(amdInstrumentId)

  const historicalContext = page.locator('.historical-holding-context')
  await expect(historicalContext).toBeVisible()
  await expect(historicalContext).toContainText('AMD')
  await expect(historicalContext).toContainText(String(compositionDate))
  await expect(historicalContext).toContainText(String(knownAt))
  await expect(historicalContext).toContainText('controlled_fixture')
  await expect(historicalContext).toContainText('does not establish current ETF analysis eligibility')

  const chartCanvases = page.locator('.chart-body canvas')
  await expect(chartCanvases.first()).toBeVisible()
  const m1HistoryReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'POST'
      && url.pathname === '/api/v1/data/ensure'
      && (response.request().postDataJSON() as DataEnsureRequest).timeframe === 'M1'
  })
  const m1LocalBarsReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'GET'
      && url.pathname === '/api/v1/ohlcv/local/AMD/M1'
  })
  const m1CoverageReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'GET'
      && url.pathname === '/api/v1/instruments/AMD/data-coverage'
  })
  await page.locator('.tf-select').selectOption('M1')
  await expect(page.locator('.tf-select')).toHaveValue('M1')
  const [m1LocalBars, m1Coverage] = await Promise.all([m1LocalBarsReady, m1CoverageReady])
  expect(m1LocalBars.status()).toBe(200)
  expect(m1Coverage.status()).toBe(200)
  expect(await m1Coverage.json()).toMatchObject({ symbol: 'AMD', is_fetching: false })
  await expect(page.locator('.chart-root').first()).toHaveAttribute('aria-busy', 'false')
  await expect(chartCanvases.first()).toBeVisible()
  const canvasCountBefore = await chartCanvases.count()
  const identityBeforeExplicitM1 = identityRequests.length
  await page.getByTestId('history-load-missing').click()
  await expect(page.getByRole('status').filter({ hasText: 'Some requested data is unavailable. Available results remain usable.' })).toBeVisible()
  const m1History = await m1HistoryReady
  expect(m1History.status()).toBe(200)
  expect(await m1History.json()).toMatchObject({
    status: 'unavailable',
    has_pending_work: false,
    dependencies: [{ status: 'unavailable', dataset: 'history', symbol: 'AMD', instrument_id: amdInstrumentId }],
  })
  expect(identityRequests).toHaveLength(identityBeforeExplicitM1 + 1)
  expect(identityRequests.at(-1)).toMatchObject({ symbol: 'AMD' })
  await expect(historicalContext).toBeVisible()
  await expect(chartCanvases).toHaveCount(canvasCountBefore)
  expect(identityRequests).toHaveLength(3)
  expect(identityRequests.map(request => request.symbol)).toEqual(['IWM', 'AMD', 'AMD'])
  expect(historyRequests).toHaveLength(2)
  expect(historyRequests.map(request => request.body.timeframe)).toEqual(['D1', 'M1'])
  expect(historyRequests.every(request => ensureInstrumentId(request) === amdInstrumentId)).toBe(true)
  expect(historyRequests[0]?.start_at).toBeUndefined()
  expect(historyRequests[0]?.end_at).toBeUndefined()
  expect(historyRequests[1]?.start_at).toBeUndefined()
  expect(historyRequests[1]?.end_at).toBeUndefined()
  expect(directHistoryRequests).toEqual([])
  await browserDiagnostics.expectNoCriticalIssues()
})

test('a no-snapshot ETF first use acquires fixture holdings and loads a resolved holding history into the chart', async ({ page, loggedIn, browserDiagnostics }) => {
  await page.goto('about:blank')

  let fixtureInstrumentId = 0
  const fixtureProfileId = 990002
  const fixtureSnapshotId = 990003
  const identityRequests: InstrumentRequestBody[] = []
  const discoveryRequests: DiscoveryRequest[] = []
  const issuerRequests: IssuerRequest[] = []
  const historyRequests: DataEnsureRequest[] = []
  let amdInstrumentId = 0
  let iwmInstrumentId = 0
  let acquiredCoverage: {
    status: 'partial'
    covered_start: string
    covered_end: string
    bar_count: number
    missing_slices: Array<{ start: string; end: string }>
  } | null = null
  let acquiredFixtureBar: OHLCVBar | null = null
  let successfulHistoryResponseReceived = false
  let localReadbackCount = 0

  function fixtureBarAt(ts: string): OHLCVBar {
    return {
      ts,
      open: 100,
      high: 102,
      low: 99,
      close: 101,
      volume: 1200,
      is_adjusted: true,
      is_derived: false,
    }
  }
  const fixtureHolding: ETFHolding = {
    id: 990004,
    snapshot_id: fixtureSnapshotId,
    // Filled from local canonical search before this fixture DTO is returned.
    constituent_instrument_id: 0,
    constituent_symbol: 'AMD',
    constituent_name: 'Advanced Micro Devices (local fixture identity)',
    position: 0,
    reported_symbol: 'AMD',
    reported_name: 'Advanced Micro Devices (local fixture identity)',
    weight: 0.01,
    shares: 100,
    market_value: 10000,
    currency: 'USD',
    country: 'US',
    exchange: 'XNAS',
    holding_type: 'equity',
    row_type: 'security',
    is_resolved: true,
    resolution_confidence: 1,
    resolution_note: 'Controlled Playwright fixture row; not issuer evidence.',
    extra_data: { controlled_fixture: true, seed: 'playwright' },
  }

  const capability = {
    availability: 'unknown',
    source_tier: 'none',
    identity_verified: true,
    usable_for_current_analysis: false,
    displayable_last_known: true,
    consecutive_failures: 0,
    reason: 'Controlled UI fixture only; no current ETF analysis eligibility is claimed.',
    symbol_audit: {
      tier: 0,
      outcome: 'not_run',
      evidence_state: 'test_fixture',
      next_action: '',
      evidence_refs: [],
    },
  } satisfies NonNullable<ETFProfile['holdings_capability']>

  const fixtureProfile: ETFProfile = {
    id: fixtureProfileId,
    instrument_id: fixtureInstrumentId,
    symbol: 'OIH',
    name: 'Test-only newly acquired fund profile',
    issuer: 'test-fixture',
    fund_family: 'Playwright controlled data',
    adapter_status: 'ready',
    latest_composition_date: '2026-01-02',
    latest_snapshot_id: fixtureSnapshotId,
    resolved_count: 1,
    unresolved_count: 0,
    holdings_capability: capability,
  }

  const fixtureSnapshot: ETFHoldingsSnapshot = {
    id: fixtureSnapshotId,
    etf_profile_id: fixtureProfileId,
    etf_instrument_id: fixtureInstrumentId,
    etf_symbol: 'OIH',
    etf_name: fixtureProfile.name,
    composition_date: '2026-01-02',
    as_of_date: '2026-01-02',
    known_at: '2026-01-03T00:00:00Z',
    published_at: null,
    provenance: 'controlled_fixture',
    source_provider: 'test-fixture',
    source_url: 'controlled://playwright-test-fixture',
    source_identifier: 'playwright:OIH:2026-01-02',
    source_quality: 'deterministic fixture only',
    completeness_status: 'complete',
    row_count: 1,
    resolved_count: 1,
    unresolved_count: 0,
    total_weight: 0.01,
    parser_version: 'playwright-fixture-v1',
    notes: 'Synthetic UI test data; not issuer, SEC, or market evidence.',
    extra_data: { controlled_fixture: true, seed: 'playwright' },
    holdings: [fixtureHolding],
  }

  await page.route('**/api/v1/instruments/discover**', async route => {
    const body = route.request().postDataJSON() as DiscoveryRequest
    discoveryRequests.push(body)
    const response = {
      request_id: body.request_id,
      status: 'complete',
      candidates: [{
        symbol: 'OIH',
        name: fixtureProfile.name,
        exchange: 'TEST',
        type: 'ETF',
        provider: 'test-fixture',
        instrument_id: null,
        identity_status: 'unresolved',
      }],
      source_outcomes: [{ ...fixtureOutcome, capability: 'instrument_search', operation: 'search', status: 'returned', result_count: 1 }],
    } satisfies InstrumentDiscoveryResponse
    await route.fulfill({ status: 200, json: response })
  })

  await page.route('**/api/v1/instruments/acquire**', async route => {
    const body = route.request().postDataJSON() as InstrumentRequestBody
    identityRequests.push(body)
    const symbol = body.symbol.trim().toUpperCase()
    const id = symbol === 'OIH' ? fixtureInstrumentId
      : symbol === 'AMD' ? amdInstrumentId
        : symbol === 'IWM' ? iwmInstrumentId : 0
    expect(id, `identity fixture must use the local canonical ${symbol} ID`).toBeGreaterThan(0)
    await route.fulfill({ status: 200, json: resolvedIdentity(body, id, symbol === 'AMD' ? 'Common Stock' : 'ETF') })
  })

  await page.route('**/api/v1/etf-holdings/OIH/acquire**', async route => {
    const body = route.request().postDataJSON() as IssuerRequest
    issuerRequests.push(body)
    const response = {
      request_id: body.request_id,
      instrument_id: fixtureInstrumentId,
      symbol: 'OIH',
      outcome: 'acquired',
      refresh: body.refresh,
      refresh_attempted: true,
      refresh_succeeded: true,
      profile: fixtureProfile,
      snapshot: fixtureSnapshot,
      capability,
      source_provider: 'test-fixture',
      source_operation: 'playwright-fixture-only',
      provider_request_log_ids: [],
      message: 'Controlled Playwright fixture data was returned; this is not an issuer response.',
    } satisfies ETFProfileAcquireResponse
    await route.fulfill({ status: 200, json: response })
  })

  const fixtureDates: ETFHoldingsDate[] = [{
    snapshot_id: fixtureSnapshotId,
    composition_date: fixtureSnapshot.composition_date,
    as_of_date: fixtureSnapshot.as_of_date,
    known_at: fixtureSnapshot.known_at,
    published_at: fixtureSnapshot.published_at,
    cadence: 'test_fixture',
    parser_version: fixtureSnapshot.parser_version,
    provenance: fixtureSnapshot.provenance,
    source_provider: fixtureSnapshot.source_provider,
    source_identifier: fixtureSnapshot.source_identifier,
    row_count: 1,
    resolved_count: 1,
    unresolved_count: 0,
    source_quality: fixtureSnapshot.source_quality,
  }]
  const fixtureHoldingsPage: ETFHoldingsPage = {
    snapshot: fixtureSnapshot,
    holdings: [fixtureHolding],
    total: 1,
    limit: 100,
    offset: 0,
    has_next: false,
  }
  await page.route('**/api/v1/etf-holdings/OIH/dates*', route => route.fulfill({ status: 200, json: fixtureDates }))
  await page.route('**/api/v1/etf-holdings/OIH/holdings*', route => route.fulfill({ status: 200, json: fixtureHoldingsPage }))
  await page.route('**/api/v1/etf-holdings/OIH/weight-evolution*', route => route.fulfill({
    status: 200,
    json: { etf_symbol: 'OIH', etf_name: fixtureProfile.name, snapshot_count: 1, series: [] },
  }))
  await page.route('**/api/v1/etf-holdings/OIH/transitions*', route => route.fulfill({
    status: 200,
    json: { etf_symbol: 'OIH', etf_name: fixtureProfile.name, snapshot_count: 1, transition_count: 0, transitions: [] },
  }))
  await page.route('**/api/v1/coverage/instruments/AMD/ohlcv*', async route => {
    const response = acquiredCoverage ?? missingCoverage(new URL(route.request().url()))
    await route.fulfill({ status: 200, json: response })
  })
  const directHistoryRequests: string[] = []
  await page.route('**/api/v1/instruments/*/history-acquisitions**', async route => {
    directHistoryRequests.push(route.request().url())
    await route.fulfill({ status: 500, json: { detail: 'Selected chart history uses POST /data/ensure.' } })
  })
  await page.route('**/api/v1/data/ensure', async route => {
    const body = route.request().postDataJSON() as DataEnsureRequest
    const requestedId = ensureInstrumentId(body)
    if (requestedId !== amdInstrumentId) return route.continue()
    expect(body.datasets).toContain('history')
    expect(body.adjusted).toBe(true)
    expect(body.timeframe).toMatch(/^(D1|M1)$/)
    expect(body.start_at).toBeUndefined()
    expect(body.end_at).toBeUndefined()
    historyRequests.push(body)
    const timestamp = body.timeframe === 'D1' ? '2026-01-02T00:00:00.000Z' : '2026-01-02T00:01:00.000Z'
    acquiredFixtureBar = fixtureBarAt(timestamp)
    acquiredCoverage = {
      status: 'partial',
      covered_start: acquiredFixtureBar.ts,
      covered_end: acquiredFixtureBar.ts,
      bar_count: 1,
      missing_slices: [],
    }
    successfulHistoryResponseReceived = true
    await route.fulfill({ status: 200, json: historyPreparation(body, amdInstrumentId, 'AMD', 'partial', acquiredFixtureBar) })
  })
  await page.route('**/api/v1/etf-holdings/IWM/capability', async route => {
    await route.fulfill({ status: 200, json: {
      availability: 'current', source_tier: 'issuer_native', identity_verified: true,
      usable_for_current_analysis: true, displayable_last_known: true,
      consecutive_failures: 0, reason: 'Current controlled fixture cache.',
      symbol_audit: { tier: 0, outcome: 'not_run', evidence_state: 'test_fixture', next_action: '', evidence_refs: [] },
    } satisfies ETFHoldingsCapability })
  })
  await page.route('**/api/v1/ohlcv/local/AMD/M1*', async route => {
    if (!successfulHistoryResponseReceived) return route.continue()
    localReadbackCount += 1
    await route.fulfill({ status: 200, json: acquiredFixtureBar ? [acquiredFixtureBar] : [] })
  })

  await page.goto('/etf-holdings')
  const search = page.getByPlaceholder('Search ETF instrument')
  await expect(search).toBeVisible()
  expect(identityRequests).toHaveLength(0)
  expect(discoveryRequests).toHaveLength(0)
  expect(issuerRequests).toHaveLength(0)

  const iwmSearchReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'GET' && url.pathname === '/api/v1/instruments/search'
      && url.searchParams.get('q')?.toUpperCase() === 'IWM'
  })
  await search.fill('IWM')
  const iwmSearchResults = await (await iwmSearchReady).json() as Array<{ symbol: string; instrument_id?: number | null }>
  iwmInstrumentId = Number(iwmSearchResults.find(result => result.symbol === 'IWM')?.instrument_id ?? 0)
  expect(iwmInstrumentId, 'IWM identity uses its actual local canonical ID').toBeGreaterThan(0)
  await search.fill('')
  expect(identityRequests).toHaveLength(0)
  expect(issuerRequests).toHaveLength(0)

  // ETF search is intentionally scoped to ETF/Fund identities, so obtain the
  // selected constituent's real canonical ID from the existing local IWM
  // holdings read rather than treating an equity search miss as identity.
  const iwmHoldingsReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'GET'
      && url.pathname === '/api/v1/etf-holdings/IWM/holdings'
  })
  await page.locator('.profile-card').filter({ hasText: 'IWM' }).first().click()
  const iwmHoldings = await (await iwmHoldingsReady).json() as ETFHoldingsPage
  amdInstrumentId = Number(iwmHoldings.holdings.find(row => (row.constituent_symbol || row.reported_symbol) === 'AMD' && row.is_resolved)?.constituent_instrument_id ?? 0)
  expect(amdInstrumentId, 'history identity uses the actual local AMD constituent ID').toBeGreaterThan(0)

  const amdSearchReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'GET'
      && url.pathname === '/api/v1/instruments/search'
      && url.searchParams.get('q')?.toUpperCase() === 'AMD'
  })
  await search.fill('AMD')
  const amdSearchResponse = await amdSearchReady
  const amdResults = await amdSearchResponse.json() as Array<{ symbol: string; instrument_id?: number | null }>
  expect(amdResults).toHaveLength(0)
  fixtureHolding.constituent_instrument_id = amdInstrumentId
  expect(identityRequests).toHaveLength(0)
  expect(discoveryRequests).toHaveLength(0)
  expect(issuerRequests).toHaveLength(0)

  const oihSearchReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'GET'
      && url.pathname === '/api/v1/instruments/search'
      && url.searchParams.get('q')?.toUpperCase() === 'OIH'
  })
  await search.fill('OIH')
  const oihSearchResponse = await oihSearchReady
  const oihResults = await oihSearchResponse.json() as Array<{ symbol: string; instrument_id?: number | null }>
  fixtureInstrumentId = oihResults.find(result => result.symbol === 'OIH')?.instrument_id ?? 0
  expect(fixtureInstrumentId, 'the selected OIH scaffold uses its actual local canonical identity').toBeGreaterThan(0)
  fixtureProfile.instrument_id = fixtureInstrumentId
  fixtureSnapshot.etf_instrument_id = fixtureInstrumentId
  expect(identityRequests).toHaveLength(0)
  expect(discoveryRequests).toHaveLength(0)
  expect(issuerRequests).toHaveLength(0)

  const oihOption = page.getByRole('option', { name: /^OIH\b/ })
  await expect(oihOption).toBeVisible()
  const oihIdentityReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'POST' && url.pathname.replace(/\/+$/, '') === '/api/v1/instruments/acquire'
  }, { timeout: 10_000 })
  const firstUseIssuerReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'POST'
      && url.pathname === '/api/v1/etf-holdings/OIH/acquire'
  }, { timeout: 10_000 })
  await oihOption.click()
  const oihIdentityResponse = await oihIdentityReady
  expect(oihIdentityResponse.status()).toBe(200)
  expect(await oihIdentityResponse.json()).toMatchObject({ status: 'resolved', instrument: { symbol: 'OIH', instrument_id: fixtureInstrumentId } })
  expect(fixtureProfile.instrument_id).toBe(fixtureInstrumentId)
  expect(fixtureSnapshot.etf_instrument_id).toBe(fixtureInstrumentId)
  expect(fixtureHolding.constituent_instrument_id).toBe(amdInstrumentId)
  expect(discoveryRequests).toHaveLength(0)
  expect(identityRequests).toHaveLength(1)
  expect(identityRequests[0]).toMatchObject({ symbol: 'OIH' })

  const firstUseIssuerResponse = await firstUseIssuerReady
  expect(firstUseIssuerResponse.status()).toBe(200)
  expect(await firstUseIssuerResponse.json()).toMatchObject({
    symbol: 'OIH',
    instrument_id: fixtureInstrumentId,
    outcome: 'acquired',
    refresh: true,
  })
  expect(issuerRequests).toHaveLength(1)
  expect(issuerRequests[0]).toMatchObject({ refresh: true })
  expect(issuerRequests[0]?.request_id).toMatch(/^[0-9a-f-]{36}$/i)
  await expect(page.getByTestId('etf-snapshot-lineage')).toBeVisible()
  await expect(page.getByTestId('etf-snapshot-known-at')).toHaveAttribute('datetime', fixtureSnapshot.known_at!)
  // The page reports current-analysis eligibility separately from the newly
  // stored, explicitly test-fixture snapshot; it has no generic completion
  // banner with the old wording.
  await expect(page.getByText('Current holdings are not verified.')).toBeVisible()
  const holdingButton = page.locator('button.holding-row').filter({ hasText: 'AMD' })
  await expect(holdingButton).toBeVisible()
  await expect(holdingButton).toContainText('Advanced Micro Devices (local fixture identity)')
  await expect(holdingButton).toContainText('1.00%')

  const initialChartCoverageReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'GET'
      && url.pathname === '/api/v1/instruments/AMD/data-coverage'
  })
  const automaticD1HistoryReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'POST'
      && url.pathname === '/api/v1/data/ensure'
      && (response.request().postDataJSON() as DataEnsureRequest).timeframe === 'D1'
  })
  await holdingButton.click()
  await page.getByRole('button', { name: 'View history' }).click()
  await expect(page).toHaveURL(/\/chart\/AMD(?:\?|$)/)
  expect((await initialChartCoverageReady).status()).toBe(200)
  const historyUrl = new URL(page.url())
  expect(historyUrl.pathname).toBe('/chart/AMD')
  expect(historyUrl.searchParams.get('holding_snapshot_id')).toBe(String(fixtureSnapshotId))
  expect(historyUrl.searchParams.get('holding_composition_date')).toBe(fixtureSnapshot.composition_date)
  expect(historyUrl.searchParams.get('holding_known_at')).toBe(fixtureSnapshot.known_at)
  expect(historyUrl.searchParams.get('holding_provenance')).toBe('controlled_fixture')
  expect(Number(historyUrl.searchParams.get('holding_instrument_id'))).toBe(amdInstrumentId)

  const historicalContext = page.locator('.historical-holding-context')
  await expect(historicalContext).toBeVisible()
  await expect(historicalContext).toContainText('does not establish current ETF analysis eligibility')
  await expect(page.locator('.chart-root').first()).toHaveAttribute('aria-busy', 'false')
  const automaticD1History = await automaticD1HistoryReady
  expect(automaticD1History.status()).toBe(200)
  const automaticD1Result = await automaticD1History.json() as DataEnsureResponse
  expect(automaticD1Result).toMatchObject({
    status: 'partial',
    has_pending_work: false,
    dependencies: [{ status: 'partial', dataset: 'history', symbol: 'AMD', instrument_id: amdInstrumentId, covered_ranges: [{ is_adjusted: true }] }],
  })
  expect(historyRequests).toHaveLength(1)
  expect(ensureInstrumentId(historyRequests[0]!)).toBe(amdInstrumentId)
  expect(historyRequests[0]?.start_at).toBeUndefined()
  expect(historyRequests[0]?.end_at).toBeUndefined()
  expect(identityRequests.map(request => request.symbol)).toEqual(['OIH', 'AMD'])
  await expect(page.getByRole('status').filter({ hasText: /^Some D1 history for AMD loaded; the rest remains unavailable\.$/ })).toBeVisible()
  const m1LocalBarsReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'GET'
      && url.pathname === '/api/v1/ohlcv/local/AMD/M1'
  })
  const m1CoverageReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'GET'
      && url.pathname === '/api/v1/instruments/AMD/data-coverage'
  })
  await page.locator('.tf-select').selectOption('M1')
  await expect(page.locator('.tf-select')).toHaveValue('M1')
  const [m1LocalBars, m1Coverage] = await Promise.all([m1LocalBarsReady, m1CoverageReady])
  expect(m1LocalBars.status()).toBe(200)
  expect(m1Coverage.status()).toBe(200)
  expect(await m1Coverage.json()).toMatchObject({ symbol: 'AMD', is_fetching: false })
  await expect(page.locator('.chart-root').first()).toHaveAttribute('aria-busy', 'false')

  const localReadbackReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return successfulHistoryResponseReceived
      && response.request().method() === 'GET'
      && url.pathname === '/api/v1/ohlcv/local/AMD/M1'
  })
  const identityCountBeforeM1 = identityRequests.length
  await page.getByTestId('history-load-missing').click()
  await expect(page.getByRole('status').filter({ hasText: /^Some history loaded;/ })).toBeVisible()
  const localReadback = await localReadbackReady
  const readbackBars = await localReadback.json() as OHLCVBar[]
  expect(historyRequests).toHaveLength(2)
  expect(historyRequests.map(request => request.timeframe)).toEqual(['D1', 'M1'])
  expect(historyRequests.every(request => ensureInstrumentId(request) === amdInstrumentId)).toBe(true)
  expect(historyRequests.every(request => request.start_at === undefined && request.end_at === undefined)).toBe(true)
  expect(acquiredFixtureBar).not.toBeNull()
  expect(identityRequests).toHaveLength(identityCountBeforeM1 + 1)
  expect(identityRequests.map(request => request.symbol)).toEqual(['OIH', 'AMD', 'AMD'])
  expect(identityRequests.at(-1)).toMatchObject({ symbol: 'AMD' })
  expect(directHistoryRequests).toEqual([])
  expect(successfulHistoryResponseReceived).toBe(true)
  expect(localReadbackCount).toBeGreaterThan(0)
  expect(readbackBars).toHaveLength(1)
  expect(readbackBars[0]).toMatchObject({ ts: acquiredFixtureBar!.ts, close: acquiredFixtureBar!.close })
  await expect(page.locator('.chart-root').first()).toContainText('M1 chart; 1 bars; adjusted; provider-observed lineage.')
  await expect(historicalContext).toBeVisible()
  await browserDiagnostics.expectNoCriticalIssues()
})

test('main Workstation keeps selected ETF chart history independent and ignores late prior-fund holdings', async ({ page, loggedIn, browserDiagnostics }) => {
  await page.goto('about:blank')

  const instruments = {
    SPY: { id: 991000, name: 'Controlled S&P 500 ETF' },
    XHB: { id: 991001, name: 'Controlled Homebuilders ETF' },
    OIH: { id: 991002, name: 'Controlled Oil Services ETF' },
    IGV: { id: 991003, name: 'Controlled Software ETF' },
    RSP: { id: 991004, name: 'Controlled Equal Weight ETF' },
    QQQ: { id: 991005, name: 'Controlled Nasdaq 100 ETF' },
    BWET: { id: 991007, name: 'Controlled Exchange Traded Vehicle' },
    UNXQ: { id: 991006, name: 'Unlisted Example Software Corp' },
  } as const
  type FixtureSymbol = keyof typeof instruments
  type FixtureETF = Exclude<FixtureSymbol, 'UNXQ'>
  const historyRequests: Array<{ symbol: FixtureSymbol; body: DataEnsureRequest }> = []
  const holdingsPreparationRequests: Array<{ symbol: FixtureSymbol; body: DataEnsureRequest }> = []
  const preparationResponseIds: string[] = []
  const holdingsEnsureRequests: Array<{ symbol: FixtureSymbol; body: DataEnsureRequest; requestId: string }> = []
  const discoveryRequests: DiscoveryRequest[] = []
  const holdingsReads: FixtureSymbol[] = []
  const industryReads: FixtureSymbol[] = []
  const calendarReads: string[] = []
  const localReadbacks: Array<{ symbol: FixtureSymbol; timeframe: string; bars: OHLCVBar[] }> = []
  const acquired = new Set<FixtureSymbol>()
  const bars = new Map<FixtureSymbol, OHLCVBar>()
  function deferred() {
    let resolve!: () => void
    const promise = new Promise<void>(done => { resolve = done })
    return { promise, resolve }
  }
  const xhbEnsureStarted = deferred()
  const xhbEnsureGate = deferred()
  const oihEnsureStarted = deferred()
  const oihStatusPollGate = deferred()
  const oihStatusPollStarted = deferred()
  const oihFailureStarted = deferred()
  const oihFailureGate = deferred()
  const igvEnsureStarted = deferred()
  const igvEnsureGate = deferred()
  const unresolvedDiscoveryStarted = deferred()
  const unresolvedDiscoveryGate = deferred()
  let oihEnsureCount = 0
  let xhbEnsureCount = 0
  let delayedOihFailureUrl: string | null = null
  let delayedOihFailureRequestId: string | null = null
  const pendingHoldings = new Map<string, { symbol: FixtureSymbol; terminal: 'ready' | 'unavailable' | 'failed'; response: DataEnsureResponse }>()
  let igvSnapshotAvailable = false
  const capabilityReads: FixtureETF[] = []
  let unxqDiscoveryCount = 0
  const identityRequests: InstrumentRequestBody[] = []
  const locallySearchedSymbols = new Set<FixtureSymbol>()
  const cancelledPreparationStatusIds: string[] = []
  page.on('requestfailed', request => {
    const url = new URL(request.url())
    if (request.method() !== 'GET' || !/^\/api\/v1\/data\/requests\/[^/]+$/.test(url.pathname)) return
    cancelledPreparationStatusIds.push(url.pathname.split('/').at(-1) ?? '')
  })
  const igvSnapshotId = 991203
  const unxqHolding: ETFHolding = {
    id: 991601,
    snapshot_id: igvSnapshotId,
    constituent_instrument_id: null,
    constituent_symbol: null,
    constituent_name: null,
    reported_symbol: 'UNXQ',
    reported_name: 'Unlisted Example Software Corp',
    position: 1,
    weight: '0.125',
    holding_type: 'equity',
    row_type: 'security',
    source_row_id: 'igv-controlled-row-991601',
    is_resolved: false,
  }
  const fixtureFuture: ETFHolding = {
    id: 991602,
    snapshot_id: igvSnapshotId,
    constituent_instrument_id: null,
    constituent_symbol: null,
    constituent_name: null,
    reported_symbol: 'FUTURE-A',
    reported_name: 'Controlled futures position',
    position: 2,
    weight: '0.01',
    holding_type: 'future',
    row_type: 'derivative',
    source_row_id: 'igv-controlled-row-991602',
    is_resolved: false,
  }
  const fixtureCash: ETFHolding = {
    id: 991603,
    snapshot_id: igvSnapshotId,
    constituent_instrument_id: null,
    constituent_symbol: null,
    constituent_name: null,
    reported_symbol: null,
    reported_name: 'Cash and equivalents',
    position: 3,
    weight: '0.0025',
    holding_type: 'cash',
    row_type: 'cash',
    source_row_id: 'igv-controlled-row-991603',
    is_resolved: false,
  }
  const igvSnapshot: ETFHoldingsSnapshot = {
    id: igvSnapshotId,
    etf_profile_id: instruments.IGV.id + 100,
    etf_instrument_id: instruments.IGV.id,
    etf_symbol: 'IGV',
    etf_name: 'Controlled mixed-type fixture fund',
    composition_date: '2026-11-02',
    known_at: '2026-11-03T08:15:00Z',
    provenance: 'controlled_fixture_only',
    source_provider: 'test-fixture',
    source_quality: 'controlled_fixture',
    completeness_status: 'complete',
    row_count: 3,
    resolved_count: 0,
    unresolved_count: 3,
    parser_version: 'fixture-v1',
    holdings: [unxqHolding, fixtureFuture, fixtureCash],
  }
  const igvHoldingsPage: ETFHoldingsPage = {
    snapshot: igvSnapshot,
    holdings: [unxqHolding, fixtureFuture, fixtureCash],
    total: 3,
    limit: 500,
    offset: 0,
    has_next: false,
  }

  await page.route('**/api/v1/instruments/search**', async route => {
    const url = new URL(route.request().url())
    const symbol = (url.searchParams.get('q') ?? '').trim().toUpperCase() as FixtureSymbol
    if (route.request().method() !== 'GET' || !(symbol in instruments)) return route.continue()
    if (symbol === 'UNXQ') {
      await route.fulfill({ status: 200, json: [] })
      return
    }
    await route.fulfill({ status: 200, json: [{
      symbol,
      name: instruments[symbol].name,
      exchange: 'TEST',
      type: symbol === 'BWET' ? 'Stock' : symbol === 'UNXQ' ? 'Equity' : 'ETF',
      instrument_id: instruments[symbol].id,
      identity_status: 'resolved',
    }] })
  })
  await page.route(url => /^\/api\/v1\/instruments\/(?:XHB|OIH|IGV|BWET|UNXQ)$/.test(new URL(url).pathname), async route => {
    const symbol = new URL(route.request().url()).pathname.split('/').at(-1) as FixtureSymbol
    if (route.request().method() !== 'GET') return route.continue()
    await route.fulfill({ status: 200, json: {
      id: instruments[symbol].id,
      symbol,
      name: instruments[symbol].name,
      currency: 'USD',
      is_active: true,
    } })
  })
  await page.route('**/api/v1/instruments/acquire', async route => {
    const body = route.request().postDataJSON() as InstrumentRequestBody
    const symbol = body.symbol.trim().toUpperCase() as FixtureSymbol
    expect(instruments[symbol], 'history identity must remain within the deliberately selected instrument').toBeTruthy()
    if (symbol === 'UNXQ') expect(body.provider_candidate).toMatchObject({ provider: 'test-fixture', symbol: 'UNXQ', exchange: 'TEST' })
    else expect(body.provider_candidate).toBeUndefined()
    identityRequests.push(body)
    const instrumentType = symbol === 'UNXQ'
      ? 'Common Stock'
      : symbol === 'BWET'
        ? 'Exchange Traded Vehicle'
        : 'ETF'
    await route.fulfill({ status: 200, json: resolvedIdentity(body, instruments[symbol].id, instrumentType) })
  })
  await page.route('**/api/v1/instruments/discover', async route => {
    const body = route.request().postDataJSON() as DiscoveryRequest
    discoveryRequests.push(body)
    if (body.query.trim().toUpperCase() === 'UNXQ') {
      unxqDiscoveryCount += 1
      if (unxqDiscoveryCount === 1) {
        unresolvedDiscoveryStarted.resolve()
        await unresolvedDiscoveryGate.promise
      }
      const response: InstrumentDiscoveryResponse = {
        request_id: body.request_id,
        status: 'complete',
        candidates: [{ symbol: 'UNXQ', name: instruments.UNXQ.name, exchange: 'TEST', type: 'CS', provider: 'test-fixture', instrument_id: null, identity_status: 'unresolved' }],
        source_outcomes: [fixtureOutcome],
      }
      await route.fulfill({ status: 200, json: response })
      return
    }
    await route.fulfill({ status: 200, json: {
      request_id: body.request_id,
      status: 'no_match',
      candidates: [],
      source_outcomes: [{ ...fixtureOutcome, status: 'no_match', result_count: 0 }],
    } satisfies InstrumentDiscoveryResponse })
  })
  await page.route('**/api/v1/coverage/instruments/*/ohlcv**', async route => {
    const url = new URL(route.request().url())
    const symbol = url.pathname.split('/')[5] as FixtureSymbol
    if (!(symbol in instruments)) return route.continue()
    expect(url.searchParams.get('mode')).toBe('historical')
    expect(url.searchParams.get('adjusted')).toBe('true')
    await route.fulfill({ status: 200, json: missingCoverage(url) })
  })
  const directHistoryRequests: string[] = []
  await page.route('**/api/v1/instruments/*/history-acquisitions**', async route => {
    directHistoryRequests.push(route.request().url())
    await route.fulfill({ status: 500, json: { detail: 'Selected chart history uses POST /data/ensure.' } })
  })
  await page.route('**/api/v1/data/ensure', async route => {
    const body = route.request().postDataJSON() as DataEnsureRequest
    const id = ensureInstrumentId(body)
    const symbol = (Object.keys(instruments) as FixtureSymbol[]).find(key => instruments[key].id === id)
    if (!symbol) return route.continue()
    const datasets = body.datasets ?? ['history']
    expect(datasets.length, 'each preparation request must identify its independent dataset work').toBeGreaterThan(0)
    if (!datasets.includes('history')) {
      expect(datasets).toEqual(['holdings'])
      holdingsPreparationRequests.push({ symbol, body })
      const requestId = crypto.randomUUID()
      holdingsEnsureRequests.push({ symbol, body, requestId })
      preparationResponseIds.push(requestId)
      let outcome: 'ready' | 'unavailable' = 'unavailable'
      let queuedTerminal: 'ready' | 'unavailable' | 'failed' | null = null
      if (symbol === 'XHB') {
        xhbEnsureCount += 1
        if (xhbEnsureCount === 1) {
          xhbEnsureStarted.resolve()
          queuedTerminal = 'unavailable'
        }
      } else if (symbol === 'OIH') {
        oihEnsureCount += 1
        if (oihEnsureCount === 1) {
          oihEnsureStarted.resolve()
          queuedTerminal = 'ready'
        } else {
          delayedOihFailureRequestId = requestId
          oihFailureStarted.resolve()
          queuedTerminal = 'failed'
        }
      } else if (symbol === 'IGV') {
        if (!igvSnapshotAvailable) {
          igvEnsureStarted.resolve()
          queuedTerminal = 'ready'
        } else outcome = 'ready'
      }
      const response = historyPreparation(body, id, symbol, outcome === 'ready' ? 'partial' : 'unavailable')
      response.request_id = requestId
      response.status = queuedTerminal ? 'queued' : outcome
      response.has_pending_work = queuedTerminal !== null
      response.completed = queuedTerminal ? 0 : outcome === 'ready' ? response.total : 0
      response.dependencies = response.dependencies.map(dependency => ({
        ...dependency,
        status: queuedTerminal ? 'queued' : outcome,
        reason_code: !queuedTerminal && outcome === 'unavailable' ? 'test_fixture_hold' : null,
      }))
      if (queuedTerminal) pendingHoldings.set(requestId, { symbol, terminal: queuedTerminal, response })
      await route.fulfill({ status: 200, json: response })
      return
    }
    expect(body).toMatchObject({ timeframe: 'D1', adjusted: true })
    expect(body.start_at).toBeUndefined()
    expect(body.end_at).toBeUndefined()
    historyRequests.push({ symbol, body })
    const bar: OHLCVBar = {
      ts: '2026-11-02T00:00:00.000Z',
      open: 41,
      high: 43,
      low: 40,
      close: 42,
      volume: 700,
      is_adjusted: true,
      is_derived: false,
    }
    bars.set(symbol, bar)
    acquired.add(symbol)
    const response = historyPreparation(body, id, symbol, 'partial', bar)
    preparationResponseIds.push(response.request_id)
    await route.fulfill({ status: 200, json: response })
  })
  await page.route('**/api/v1/data/requests/*', async route => {
    const requestId = new URL(route.request().url()).pathname.split('/').at(-1) ?? ''
    const pending = pendingHoldings.get(requestId)
    if (route.request().method() !== 'GET' || !pending) return route.continue()
    if (pending.symbol === 'OIH' && pending.terminal === 'ready') oihStatusPollStarted.resolve()
    if (pending.terminal === 'failed') {
      delayedOihFailureUrl = route.request().url()
      await oihFailureGate.promise
      await route.fulfill({
        status: 503,
        headers: { 'x-controlled-response-id': requestId },
        json: { request_id: requestId, detail: 'Controlled fixture error; no source request was made.' },
      })
      return
    }
    if (pending.symbol === 'XHB') await xhbEnsureGate.promise
    else if (pending.symbol === 'OIH') await oihStatusPollGate.promise
    else if (pending.symbol === 'IGV') {
      await igvEnsureGate.promise
      igvSnapshotAvailable = true
    }
    const response: DataEnsureResponse = {
      ...pending.response,
      version: pending.response.version + 1,
      status: pending.terminal,
      has_pending_work: false,
      completed: pending.terminal === 'ready' ? pending.response.total : 0,
      updated_at: '2026-11-07T12:00:01.000Z',
      last_progress_at: '2026-11-07T12:00:01.000Z',
      dependencies: pending.response.dependencies.map(dependency => ({
        ...dependency,
        status: pending.terminal,
        reason_code: pending.terminal === 'unavailable' ? 'test_fixture_hold' : null,
        updated_at: '2026-11-07T12:00:01.000Z',
      })),
    }
    pending.response = response
    try {
      await route.fulfill({ status: 200, json: response })
    } catch (error) {
      if (pending.symbol !== 'OIH' || pending.terminal !== 'ready' || !route.request().failure()) throw error
    }
  })
  await page.route('**/api/v1/ohlcv/local/*/*', async route => {
    const parts = new URL(route.request().url()).pathname.split('/')
    const symbol = parts.at(-2) as FixtureSymbol
    const timeframe = parts.at(-1) ?? ''
    if (!(symbol in instruments)) return route.continue()
    const rows = acquired.has(symbol) && bars.has(symbol) ? [bars.get(symbol)!] : []
    localReadbacks.push({ symbol, timeframe, bars: rows })
    await route.fulfill({ status: 200, json: rows })
  })
  await page.route('**/api/v1/instruments/*/data-coverage', async route => {
    const symbol = new URL(route.request().url()).pathname.split('/')[4] as FixtureSymbol
    if (!(symbol in instruments)) return route.continue()
    await route.fulfill({ status: 200, json: { symbol, is_fetching: false, coverage: {} } })
  })
  await page.route('**/api/v1/instruments/*/options/exposure**', async route => {
    const symbol = new URL(route.request().url()).pathname.split('/')[4] as FixtureSymbol
    if (!(symbol in instruments)) return route.continue()
    if (route.request().url().includes('/expirations')) {
      await route.fulfill({ status: 200, json: [] })
      return
    }
    await route.fulfill({ status: 200, json: {
      symbol, spot: null, expirations: [], active_expirations: [], computed_at: '2026-11-03T00:00:00Z',
      ladder: [], key_levels: { call_wall: null, put_wall: null, gamma_flip: null, max_pain: null },
      pcr_oi: null, pcr_volume: null, implied_move_pct: null, total_gex: 0, total_net_dex: 0,
    } satisfies OptionsExposureResponse })
  })
  await page.route(url => /^\/api\/v1\/calendar\/instruments\/[^/]+\/calendar$/.test(new URL(url).pathname), async route => {
    const request = route.request()
    const url = new URL(request.url())
    const symbol = decodeURIComponent(url.pathname.split('/')[5] ?? '').toUpperCase()
    if (request.method() !== 'GET' || !(symbol in instruments) && symbol !== 'SPY') return route.continue()
    calendarReads.push(symbol)
    await route.fulfill({ status: 200, json: [] })
  })
  await page.route('**/api/v1/etf-holdings/*/holdings**', async route => {
    const symbol = new URL(route.request().url()).pathname.split('/')[4] as FixtureSymbol
    if (!(symbol in instruments)) return route.continue()
    holdingsReads.push(symbol)
    if (symbol === 'IGV' && igvSnapshotAvailable) {
      await route.fulfill({ status: 200, json: igvHoldingsPage })
      return
    }
    await route.fulfill({ status: 404, json: { detail: 'No stored snapshot in this controlled fixture.' } })
  })
  await page.route('**/api/v1/etf-holdings/*/capability', async route => {
    const symbol = new URL(route.request().url()).pathname.split('/')[4] as FixtureSymbol
    if (!(symbol in instruments)) return route.continue()
    capabilityReads.push(symbol as FixtureETF)
    const current = symbol === 'IGV' && igvSnapshotAvailable
    const capability: ETFHoldingsCapability = {
      availability: current ? 'current' : 'unknown',
      source_tier: current ? 'issuer_native' : 'none',
      identity_verified: true,
      usable_for_current_analysis: current,
      displayable_last_known: current,
      consecutive_failures: 0,
      reason: current ? 'Current controlled cache fixture.' : 'No current controlled cache fixture.',
      symbol_audit: { tier: 0, outcome: 'not_run', evidence_state: 'test_fixture', next_action: '', evidence_refs: [] },
    }
    await route.fulfill({ status: 200, json: capability })
  })
  await page.route('**/api/v1/market-groups/etf/*/industries**', async route => {
    const symbol = new URL(route.request().url()).pathname.split('/')[5] as FixtureSymbol
    if (!(symbol in instruments)) return route.continue()
    industryReads.push(symbol)
    await route.fulfill({ status: 404, json: { detail: 'No point-in-time industry snapshot in this controlled fixture.' } })
  })
  try {
    await page.goto('/')
    const symbolSearch = page.getByRole('combobox', { name: 'Active symbol' })
    await expect(symbolSearch).toBeVisible()
    await expectGoldenLayoutTabsWithinAllocatedHeaders(page)
    expect(historyRequests).toHaveLength(0)
    expect(holdingsEnsureRequests).toHaveLength(0)
    expect(discoveryRequests).toHaveLength(0)

    async function chooseETF(symbol: FixtureSymbol) {
      // Search results may still be fresh in the Workstation's 30s query cache
      // after a fund switch. Require the first local request, then select the
      // visible cached result on repeat choices without waiting for a GET that
      // correctly does not occur.
      const localSearchReady = locallySearchedSymbols.has(symbol)
        ? null
        : page.waitForResponse(response => {
          const url = new URL(response.url())
          return response.request().method() === 'GET'
            && url.pathname === '/api/v1/instruments/search'
            && url.searchParams.get('q')?.toUpperCase() === symbol
        })
      await symbolSearch.fill(symbol)
      if (localSearchReady) {
        expect(await (await localSearchReady).json()).toMatchObject([{
          symbol,
          type: symbol === 'BWET' ? 'Stock' : 'ETF',
          instrument_id: instruments[symbol].id,
        }])
        locallySearchedSymbols.add(symbol)
      }
      const option = page.getByRole('listbox', { name: 'Symbol search results' })
        .getByRole('option', { name: new RegExp(`^${symbol}\\b`) })
      await expect(option).toBeVisible()
      await option.click()
      await expect(symbolSearch).toHaveValue(symbol)
    }

    const waitForDatasetEnsure = (symbol: FixtureSymbol, dataset: 'history' | 'holdings') => page.waitForResponse(response => {
      const url = new URL(response.url())
      if (response.request().method() !== 'POST' || url.pathname !== '/api/v1/data/ensure') return false
      const body = response.request().postDataJSON() as DataEnsureRequest
      return ensureInstrumentId(body) === instruments[symbol].id && body.datasets?.includes(dataset) === true
    })
    const waitForPreparationStatus = (requestId: string) => page.waitForResponse(response => {
      const url = new URL(response.url())
      return response.request().method() === 'GET'
        && url.pathname === `/api/v1/data/requests/${requestId}`
    })

    const xhbHistoryResponseReady = waitForDatasetEnsure('XHB', 'history')
    const xhbHoldingsResponseReady = waitForDatasetEnsure('XHB', 'holdings')
    await chooseETF('XHB')
    const xhbHistoryResponse = await xhbHistoryResponseReady
    expect(xhbHistoryResponse.status()).toBe(200)
    await xhbEnsureStarted.promise
    expect(holdingsEnsureRequests.map(request => request.symbol)).toContain('XHB')
    const xhbAccepted = await xhbHoldingsResponseReady
    expect(xhbAccepted.status()).toBe(200)
    expect(await xhbAccepted.json()).toMatchObject({ status: 'queued', has_pending_work: true })
    await expect.poll(() => localReadbacks.some(readback => readback.symbol === 'XHB' && readback.bars.length === 1)).toBe(true)
    expect(holdingsEnsureRequests.find(request => request.symbol === 'XHB')?.body).toMatchObject({ target: { kind: 'instrument', instrument_id: instruments.XHB.id }, datasets: ['holdings'] })
    expect(holdingsReads).toContain('XHB')
    expect(localReadbacks.find(readback => readback.symbol === 'XHB' && readback.bars.length === 1)?.timeframe).toBe('D1')

    const xhbRequestId = holdingsEnsureRequests.find(request => request.symbol === 'XHB')!.requestId
    const xhbStatusResponseReady = waitForPreparationStatus(xhbRequestId)
    xhbEnsureGate.resolve()
    expect((await xhbHoldingsResponseReady).status()).toBe(200)
    const xhbTerminal = await xhbStatusResponseReady
    expect(xhbTerminal.status()).toBe(200)
    expect(await xhbTerminal.json()).toMatchObject({
      request_id: xhbRequestId,
      status: 'unavailable',
      has_pending_work: false,
      dependencies: [{ dataset: 'holdings', status: 'unavailable', reason_code: 'test_fixture_hold' }],
    })
    await expectSelectionHoldingsDetails(page, 'XHB', 'Some requested data is unavailable.')

    for (const symbol of ['SPY', 'RSP', 'QQQ'] as const) {
      const historyResponseReady = waitForDatasetEnsure(symbol, 'history')
      const holdingsResponseReady = waitForDatasetEnsure(symbol, 'holdings')
      await chooseETF(symbol)
      expect((await historyResponseReady).status()).toBe(200)
      const holdingsResponse = await holdingsResponseReady
      expect(holdingsResponse.status()).toBe(200)
      expect(await holdingsResponse.json()).toMatchObject({
        status: 'unavailable',
        has_pending_work: false,
        dependencies: [{ dataset: 'holdings', status: 'unavailable' }],
      })
      await expect.poll(() => localReadbacks.some(readback => readback.symbol === symbol && readback.bars.length === 1)).toBe(true)
      await expectSelectionHoldingsDetails(page, symbol, 'Some requested data is unavailable.')
    }

    const oihHoldingsResponseReady = waitForDatasetEnsure('OIH', 'holdings')
    await chooseETF('OIH')
    await oihEnsureStarted.promise
    const oihRequestId = holdingsEnsureRequests.find(request => request.symbol === 'OIH')!.requestId
    const oihAccepted = await oihHoldingsResponseReady
    expect(oihAccepted.status()).toBe(200)
    expect(await oihAccepted.json()).toMatchObject({ request_id: oihRequestId, status: 'queued', has_pending_work: true })
    // Require the actual status poll to start while OIH is still current. The
    // next selection intentionally cancels that observer, so no later response
    // waiter should assume the canceled request will complete in the browser.
    await oihStatusPollStarted.promise
    const oihReadsBeforeSwitch = holdingsReads.filter(symbol => symbol === 'OIH').length

    const igvHoldingsResponseReady = waitForDatasetEnsure('IGV', 'holdings')
    await chooseETF('IGV')
    await igvEnsureStarted.promise
    const igvRequestId = holdingsEnsureRequests.find(request => request.symbol === 'IGV')!.requestId
    const igvAccepted = await igvHoldingsResponseReady
    expect(igvAccepted.status()).toBe(200)
    expect(await igvAccepted.json()).toMatchObject({ request_id: igvRequestId, status: 'queued', has_pending_work: true })
    const igvStatusResponseReady = waitForPreparationStatus(igvRequestId)
    await expectSelectionHoldingsDetails(page, 'IGV', 'Preparing holdings for IGV')
    await expect(page.locator('.workstation__selection-acquisition').filter({ hasText: 'Holdings for OIH' })).toHaveCount(0)
    expect(holdingsReads.at(-1)).toBe('IGV')
    igvEnsureGate.resolve()
    expect((await igvHoldingsResponseReady).status()).toBe(200)
    const igvTerminal = await igvStatusResponseReady
    expect(igvTerminal.status()).toBe(200)
    expect(await igvTerminal.json()).toMatchObject({ request_id: igvRequestId, status: 'ready', has_pending_work: false })
    await expectSelectionHoldingsDetails(page, 'IGV', 'Current holdings for IGV are available locally.')
    expect(industryReads.at(-1)).toBe('IGV')
    expect(holdingsReads.filter(symbol => symbol === 'IGV').length).toBeGreaterThan(0)
    const oihIndustryReadsBeforeLateResponse = industryReads.filter(symbol => symbol === 'OIH').length

    // OIH's controlled server job can finish after IGV is current, but its
    // obsolete status poll is canceled and cannot publish into IGV's UI.
    oihStatusPollGate.resolve()
    await expect.poll(() => cancelledPreparationStatusIds).toContain(oihRequestId)
    expect((await oihHoldingsResponseReady).status()).toBe(200)
    await expect(symbolSearch).toHaveValue('IGV')
    await expectSelectionHoldingsDetails(page, 'IGV', 'Current holdings for IGV are available locally.')
    expect(holdingsReads.filter(symbol => symbol === 'OIH')).toHaveLength(oihReadsBeforeSwitch)
    expect(industryReads.filter(symbol => symbol === 'OIH')).toHaveLength(oihIndustryReadsBeforeLateResponse)

    // A locally misclassified Stock hint must not preserve the prior IGV
    // constituents after canonical identity confirms this selected ticker as ETV.
    const igvContextGroup = page.getByRole('group', { name: 'Constituents' })
    const igvContextWidget = igvContextGroup.getByRole('listbox').first()
    await expect(igvContextWidget).toHaveAccessibleName(/^IGV holdings .* symbols$/)
    const priorIgvHolding = igvContextWidget.getByRole('option', { name: /UNXQ Unlisted Example Software Corp/ })
    await expect(igvContextGroup).toContainText('IGV')
    await expect(priorIgvHolding).toBeVisible()
    const bwetIdentityResponseReady = page.waitForResponse(response => {
      const url = new URL(response.url())
      return response.request().method() === 'POST' && url.pathname === '/api/v1/instruments/acquire'
        && (response.request().postDataJSON() as InstrumentRequestBody).symbol === 'BWET'
    })
    const bwetHistoryResponseReady = waitForDatasetEnsure('BWET', 'history')
    const bwetHoldingsResponseReady = waitForDatasetEnsure('BWET', 'holdings')
    await chooseETF('BWET')
    expect(await (await bwetIdentityResponseReady).json()).toMatchObject({
      status: 'resolved',
      instrument: {
        instrument_id: instruments.BWET.id,
        symbol: 'BWET',
        identity_status: 'resolved',
        instrument_type: 'Exchange Traded Vehicle',
      },
    })
    expect((await bwetHistoryResponseReady).status()).toBe(200)
    const bwetHoldingsResponse = await bwetHoldingsResponseReady
    expect(bwetHoldingsResponse.status()).toBe(200)
    expect(await bwetHoldingsResponse.json()).toMatchObject({
      status: 'unavailable',
      has_pending_work: false,
      dependencies: [{ dataset: 'holdings', status: 'unavailable' }],
    })
    expect(identityRequests.filter(request => request.symbol === 'BWET')).toHaveLength(1)
    expect(holdingsEnsureRequests.filter(request => request.symbol === 'BWET').map(request => request.body)).toEqual([
      expect.objectContaining({ target: { kind: 'instrument', instrument_id: instruments.BWET.id }, datasets: ['holdings'] }),
    ])
    expect(historyRequests.filter(request => request.symbol === 'BWET').map(request => request.body.timeframe)).toEqual(['D1'])
    expect(capabilityReads).toContain('BWET')
    await expect.poll(() => localReadbacks.some(readback => readback.symbol === 'BWET' && readback.bars.length === 1)).toBe(true)
    await expectSelectionHoldingsDetails(page, 'BWET', 'Current holdings are unavailable because the latest source snapshot is dated in the future.')
    await expect(igvContextGroup).toContainText('BWET')
    await expect(igvContextWidget).toBeVisible()
    await expect(igvContextWidget).toHaveAccessibleName(/^BWET holdings .* symbols$/)
    await expect(priorIgvHolding).toHaveCount(0)

    await chooseETF('OIH')
    await oihFailureStarted.promise
    const delayedOihFailureResponseReady = waitForPreparationStatus(delayedOihFailureRequestId!)
    const failedOihAccepted = await waitForDatasetEnsure('OIH', 'holdings')
    expect(failedOihAccepted.status()).toBe(200)
    expect(await failedOihAccepted.json()).toMatchObject({ request_id: delayedOihFailureRequestId, status: 'queued', has_pending_work: true })
    expect(delayedOihFailureRequestId).toMatch(/^[0-9a-f-]{36}$/i)
    expect(delayedOihFailureUrl).toBeTruthy()
    browserDiagnostics.allowExpectedControlledApiResponseFault(
      delayedOihFailureUrl!,
      'GET',
      delayedOihFailureRequestId!,
      503,
    )
    const xhbAfterFailureSelectionReady = waitForDatasetEnsure('XHB', 'holdings')
    await chooseETF('XHB')
    expect((await xhbAfterFailureSelectionReady).status()).toBe(200)
    await expectSelectionHoldingsDetails(page, 'XHB', 'Some requested data is unavailable.')
    oihFailureGate.resolve()
    igvEnsureGate.resolve()
    expect((await delayedOihFailureResponseReady).status()).toBe(503)
    await expectSelectionHoldingsDetails(page, 'XHB', 'Some requested data is unavailable.')
    await expect(page.locator('.workstation__selection-acquisition--error')).toHaveCount(0)

    expect(holdingsEnsureRequests.map(request => request.symbol)).toEqual(['XHB', 'SPY', 'RSP', 'QQQ', 'OIH', 'IGV', 'BWET', 'OIH', 'XHB'])
    expect(historyRequests.map(request => request.symbol)).toEqual(['XHB', 'SPY', 'RSP', 'QQQ', 'OIH', 'IGV', 'BWET', 'OIH', 'XHB'])
    expect(discoveryRequests).toHaveLength(0)
    expect(historyRequests.every(request => request.body.timeframe === 'D1' && request.body.adjusted)).toBe(true)
    expect(historyRequests.every(request => request.body.datasets?.includes('history'))).toBe(true)
    expect(historyRequests.every(request => request.body.start_at === undefined && request.body.end_at === undefined)).toBe(true)
    expect(holdingsPreparationRequests.some(request => request.symbol === 'IGV')).toBe(true)
    expect(holdingsPreparationRequests.every(request => request.body.datasets?.every(dataset => dataset !== 'history'))).toBe(true)
    expect(preparationResponseIds).toHaveLength(historyRequests.length + holdingsPreparationRequests.length)
    expect(new Set(preparationResponseIds).size).toBe(preparationResponseIds.length)
    expect(directHistoryRequests).toEqual([])
    const holdingsRequestIds = holdingsEnsureRequests.map(request => request.requestId)
    expect(holdingsRequestIds.every(requestId => /^[0-9a-f-]{36}$/i.test(requestId))).toBe(true)
    expect(new Set(holdingsRequestIds).size).toBe(holdingsRequestIds.length)
    expect(calendarReads.every(symbol => symbol === 'SPY' || symbol in instruments)).toBe(true)

    // The acquired IGV snapshot is a real-shape controlled fixture with zero
    // canonical equities. Reported values remain visible before identity work.
    const igvHoldingsEnsureCount = holdingsEnsureRequests.filter(request => request.symbol === 'IGV').length
    expect(igvHoldingsEnsureCount).toBe(1)
    expect(capabilityReads).toContain('IGV')
    await chooseETF('IGV')
    const igvGroup = page.getByRole('group', { name: 'Constituents' })
    await expect(igvGroup).toContainText('IGV')
    const igvWidget = igvGroup.getByRole('listbox', { name: 'Constituents symbols' })
    await expect(igvWidget).toBeVisible()
    const reportedHolding = igvWidget.getByRole('option', { name: /UNXQ Unlisted Example Software Corp/ })
    await expect(reportedHolding).toBeVisible()
    await expect(reportedHolding).toContainText('12.50%')
    await expect(reportedHolding).toHaveAccessibleName(/Reported type: security · equity/)
    await expect(reportedHolding).toHaveAccessibleName(/Identity: Equity identity not resolved\./)
    const futureHolding = igvWidget.getByRole('option', { name: /FUTURE-A Controlled futures position/ })
    const cashHolding = igvWidget.getByRole('option', { name: /— Cash and equivalents/ })
    await expect(futureHolding).toHaveAccessibleName(/Reported type: derivative · future/)
    await expect(cashHolding).toHaveAccessibleName(/Reported type: cash · cash/)
    const identityRequestsBeforeNonEquities = identityRequests.length
    const historyRequestsBeforeNonEquities = historyRequests.length
    await expect(symbolSearch).toHaveValue('IGV')
    await futureHolding.click()
    await expect(symbolSearch).toHaveValue('IGV')
    await expect(page.getByTestId('reported-holding-selection')).toContainText('FUTURE-A · Controlled futures position')
    await expect(page.getByRole('status').filter({ hasText: 'FUTURE-A · Controlled futures position is reported as future and cannot be opened as an equity chart.' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Review ETF holdings' })).toBeVisible()
    await cashHolding.click()
    await expect(symbolSearch).toHaveValue('IGV')
    await expect(page.getByTestId('reported-holding-selection')).toContainText('Cash and equivalents')
    await expect(page.getByRole('status').filter({ hasText: 'Cash and equivalents is reported as cash and cannot be opened as an equity chart.' })).toBeVisible()
    expect(holdingsEnsureRequests.filter(request => request.symbol === 'IGV')).toHaveLength(igvHoldingsEnsureCount)
    expect(identityRequests).toHaveLength(identityRequestsBeforeNonEquities)
    expect(historyRequests).toHaveLength(historyRequestsBeforeNonEquities)
    expect(unxqHolding.constituent_instrument_id).toBeNull()
    expect(unxqHolding.is_resolved).toBe(false)
    expect(identityRequests.filter(request => request.symbol === 'UNXQ')).toHaveLength(0)
    expect(historyRequests.filter(request => request.symbol === 'UNXQ')).toHaveLength(0)

    // Row selection starts bounded discovery; changing funds before that
    // response settles must invalidate the old snapshot-bound action.
    const staleDiscoveryReady = page.waitForResponse(response => {
      const url = new URL(response.url())
      return response.request().method() === 'POST'
        && url.pathname === '/api/v1/instruments/discover'
        && (response.request().postDataJSON() as DiscoveryRequest).query.toUpperCase() === 'UNXQ'
    })
    await reportedHolding.click()
    await unresolvedDiscoveryStarted.promise
    await chooseETF('XHB')
    unresolvedDiscoveryGate.resolve()
    expect((await staleDiscoveryReady).status()).toBe(200)
    await expect(symbolSearch).toHaveValue('XHB')
    await expect(page).toHaveURL(/\/$/)
    await expect(page.getByRole('listbox', { name: 'Symbol search results' }).getByRole('option', { name: /Use UNXQ · TEST/ })).toHaveCount(0)
    expect(identityRequests.filter(request => request.symbol === 'UNXQ')).toHaveLength(0)
    expect(historyRequests.filter(request => request.symbol === 'UNXQ')).toHaveLength(0)

    // Re-select the fund and explicitly select its same reported row. The exact
    // candidate is acquired once, the dashboard selects that equity while
    // retaining snapshot/row lineage, and chart history is loaded for it.
    await chooseETF('IGV')
    await expect(igvGroup).toContainText('IGV')
    await expect(igvWidget).toBeVisible()
    await expect(igvWidget.getByRole('option', { name: /UNXQ Unlisted Example Software Corp/ })).toBeVisible()
    const identityResponseReady = page.waitForResponse(response => {
      const url = new URL(response.url())
      return response.request().method() === 'POST' && url.pathname === '/api/v1/instruments/acquire'
        && (response.request().postDataJSON() as InstrumentRequestBody).symbol === 'UNXQ'
    })
    const historyResponseReady = page.waitForResponse(response => {
      const url = new URL(response.url())
      return response.request().method() === 'POST'
        && url.pathname === '/api/v1/data/ensure'
        && ensureInstrumentId(response.request().postDataJSON() as DataEnsureRequest) === instruments.UNXQ.id
    })
    await igvWidget.getByRole('option', { name: /UNXQ Unlisted Example Software Corp/ }).click()
    const candidate = page.getByTestId('reported-holding-selection')
      .getByRole('listbox', { name: 'Symbol search results' })
      .getByRole('option', { name: /Use UNXQ · TEST/ })
    await expect(candidate).toBeVisible()
    const candidateGeometry = await candidate.evaluate(element => {
      const rect = element.getBoundingClientRect()
      const body = element.closest('.tool-window__body')
      const bodyRect = body?.getBoundingClientRect()
      const selection = element.closest('[data-testid="reported-holding-selection"]') as HTMLElement | null
      const selectionRect = selection?.getBoundingClientRect()
      const x = rect.left + rect.width / 2
      const y = rect.top + rect.height / 2
      const hit = document.elementFromPoint(x, y)
      const withinBody = Boolean(bodyRect && x >= bodyRect.left && x <= bodyRect.right && y >= bodyRect.top && y <= bodyRect.bottom)
      const fullyWithinBody = Boolean(bodyRect && rect.left >= bodyRect.left && rect.right <= bodyRect.right
        && rect.top >= bodyRect.top && rect.bottom <= bodyRect.bottom)
      const fullyWithinSelection = Boolean(selectionRect && rect.left >= selectionRect.left && rect.right <= selectionRect.right
        && rect.top >= selectionRect.top && rect.bottom <= selectionRect.bottom)
      return {
        candidate: { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom, width: rect.width, height: rect.height },
        toolBody: bodyRect ? { left: bodyRect.left, top: bodyRect.top, right: bodyRect.right, bottom: bodyRect.bottom } : null,
        centerInsideToolBody: withinBody,
        fullyWithinToolBody: fullyWithinBody,
        selectionPanel: selectionRect ? { left: selectionRect.left, top: selectionRect.top, right: selectionRect.right, bottom: selectionRect.bottom } : null,
        fullyWithinSelectionPanel: fullyWithinSelection,
        toolBodyScrollLeft: (body as HTMLElement | null)?.scrollLeft ?? null,
        toolBodyClientWidth: (body as HTMLElement | null)?.clientWidth ?? null,
        toolBodyScrollWidth: (body as HTMLElement | null)?.scrollWidth ?? null,
        centerHitCandidate: Boolean(hit && (hit === element || element.contains(hit))),
        hitElement: hit ? `${hit.tagName.toLowerCase()}.${String(hit.className || '').toString().replace(/\s+/g, '.')}` : null,
      }
    })
    expect(candidateGeometry.centerInsideToolBody).toBe(true)
    expect(candidateGeometry.fullyWithinToolBody).toBe(true)
    expect(candidateGeometry.fullyWithinSelectionPanel).toBe(true)
    expect(candidateGeometry.toolBodyScrollLeft).toBe(0)
    expect(candidateGeometry.toolBodyScrollWidth).toBe(candidateGeometry.toolBodyClientWidth)
    expect(candidateGeometry.centerHitCandidate).toBe(true)
    await candidate.click()
    expect((await identityResponseReady).status()).toBe(200)
    expect((await historyResponseReady).status()).toBe(200)
    await expect(page).toHaveURL(/\/$/)
    await expect(symbolSearch).toHaveValue('UNXQ')
    const holdingLineage = page.getByTestId('active-holding-lineage')
    await expect(holdingLineage).toHaveText(`UNXQ from IGV holdings · ${igvSnapshot.composition_date}`)
    const holdingDetails = await holdingLineage.getAttribute('title')
    expect(await holdingLineage.getAttribute('aria-label')).toBe(holdingDetails)
    expect(holdingDetails).toContain(`from IGV holdings · snapshot ${igvSnapshot.id} · row ${unxqHolding.id}`)
    expect(holdingDetails).toContain(`composition ${igvSnapshot.composition_date}`)
    expect(holdingDetails).toContain(`known ${igvSnapshot.known_at}`)
    expect(holdingDetails).toContain(`${igvSnapshot.source_provider} / ${igvSnapshot.provenance}`)
    await expect(page.locator('[data-tool-key="constituent-list"] .tool-window__symbol')).toHaveText('IGV')
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue('UNXQ')
    expect(identityRequests.filter(request => request.symbol === 'UNXQ')).toHaveLength(1)
    expect(identityRequests.find(request => request.symbol === 'UNXQ')?.provider_candidate).toMatchObject({ provider: 'test-fixture', symbol: 'UNXQ', exchange: 'TEST' })
    const unxqHistory = historyRequests.filter(request => request.symbol === 'UNXQ')
    expect(unxqHistory).toHaveLength(1)
    expectBoundedD1Request(unxqHistory[0]!.body)
    const loadedUnxqBar = bars.get('UNXQ')
    await expect.poll(() => localReadbacks.some(readback => readback.symbol === 'UNXQ' && readback.bars.length === 1)).toBe(true)
    expect(localReadbacks.find(readback => readback.symbol === 'UNXQ' && readback.bars.length === 1)?.bars[0]).toMatchObject({ ts: loadedUnxqBar?.ts, close: loadedUnxqBar?.close })
    await expect(holdingLineage).toBeVisible()
    await browserDiagnostics.expectNoCriticalIssues()
  } finally {
    xhbEnsureGate.resolve()
    oihStatusPollGate.resolve()
    oihFailureGate.resolve()
    igvEnsureGate.resolve()
    unresolvedDiscoveryGate.resolve()
  }
})

test('ordinary Workstation, Chart, and reported-holding selection use the real seeded application APIs', async ({ page, loggedIn, browserDiagnostics }) => {
  // Unlike the controlled-response cases above, this path installs no
  // page.route handlers. The isolated backend's E2E_SEED_MARKET_DATA fixture
  // supplies explicitly labelled local bars and ETF rows; it does not prove
  // genuine issuer/provider acquisition.
  const sourceActionRequests: string[] = []
  page.on('request', request => {
    const url = new URL(request.url())
    if (request.method() === 'POST' && (
      url.pathname === '/api/v1/instruments/discover'
      || url.pathname === '/api/v1/instruments/acquire'
      || /\/api\/v1\/instruments\/\d+\/history-acquisitions$/.test(url.pathname)
      || /\/api\/v1\/etf-holdings\/[^/]+\/acquire$/.test(url.pathname)
    )) sourceActionRequests.push(`${request.method()} ${url.pathname}`)
  })

  const waitForSearch = (symbol: string) => page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'GET'
      && url.pathname === '/api/v1/instruments/search'
      && url.searchParams.get('q')?.toUpperCase() === symbol
  })
  const waitForBars = (symbol: string) => page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'GET'
      && new RegExp(`/api/v1/ohlcv/(?:local/)?${symbol}/D1$`).test(url.pathname)
      && response.status() === 200
  })

  await page.goto('/chart')
  await expect(page.locator('.workstation')).toBeVisible()
  const workstationSearch = page.getByRole('combobox', { name: 'Active symbol' })
  expect(sourceActionRequests).toHaveLength(0)
  const workstationSearchActionCount = sourceActionRequests.length
  const workstationSearchResponse = waitForSearch('AMD')
  await workstationSearch.fill('AMD')
  expect((await workstationSearchResponse).ok()).toBe(true)
  const workstationResults = page.getByRole('listbox', { name: 'Symbol search results' })
  await expect(workstationResults.getByRole('option', { name: /AMD/ }).first()).toBeVisible()
  expect(sourceActionRequests).toHaveLength(workstationSearchActionCount)
  const workstationBarsResponse = waitForBars('AMD')
  const workstationPreparationResponse = page.waitForResponse(response => {
    const url = new URL(response.url())
    if (response.request().method() !== 'POST' || url.pathname !== '/api/v1/data/ensure') return false
    const body = response.request().postDataJSON() as DataEnsureRequest
    return body.target.kind === 'instrument' && body.timeframe === 'D1' && body.datasets.includes('history')
  })
  await workstationResults.getByRole('option', { name: /AMD/ }).first().click()
  await expect(workstationSearch).toHaveValue('AMD')
  const workstationBars = await workstationBarsResponse
  expect(await workstationBars.json()).not.toHaveLength(0)
  const workstationPreparation = await workstationPreparationResponse
  expect(workstationPreparation.ok()).toBe(true)
  expect((workstationPreparation.request().postDataJSON() as DataEnsureRequest).start_at).toBeUndefined()
  expect((workstationPreparation.request().postDataJSON() as DataEnsureRequest).end_at).toBeUndefined()

  await page.goto('/chart')
  const chartSearch = page.getByRole('combobox', { name: 'Active symbol' })
  const chartSearchActionCount = sourceActionRequests.length
  await chartSearch.fill('')
  const chartSearchResponse = waitForSearch('NVDA')
  await chartSearch.fill('NVDA')
  expect((await chartSearchResponse).ok()).toBe(true)
  const chartResults = page.getByRole('listbox', { name: 'Symbol search results' })
  await expect(chartResults.getByRole('option', { name: /NVDA/ }).first()).toBeVisible()
  expect(sourceActionRequests).toHaveLength(chartSearchActionCount)
  const chartBarsResponse = waitForBars('NVDA')
  const chartPreparationResponse = page.waitForResponse(response => {
    const url = new URL(response.url())
    if (response.request().method() !== 'POST' || url.pathname !== '/api/v1/data/ensure') return false
    const body = response.request().postDataJSON() as DataEnsureRequest
    return body.target.kind === 'instrument' && body.timeframe === 'D1' && body.datasets.includes('history')
  })
  await chartResults.getByRole('option', { name: /NVDA/ }).first().click()
  await expect(chartSearch).toHaveValue('NVDA')
  const chartBars = await chartBarsResponse
  expect(await chartBars.json()).not.toHaveLength(0)
  const chartPreparation = await chartPreparationResponse
  expect(chartPreparation.ok()).toBe(true)
  expect((chartPreparation.request().postDataJSON() as DataEnsureRequest).start_at).toBeUndefined()
  expect((chartPreparation.request().postDataJSON() as DataEnsureRequest).end_at).toBeUndefined()

  await page.getByRole('link', { name: 'ETF Holdings' }).click()
  const spyProfile = page.locator('.profile-card').filter({ hasText: /\bSPY\b/ }).first()
  await expect(spyProfile).toBeVisible()
  const spyHoldingsResponse = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'GET'
      && url.pathname === '/api/v1/etf-holdings/SPY/holdings'
  })
  await spyProfile.click()
  const spyHoldingsResult = await spyHoldingsResponse
  expect(spyHoldingsResult.ok()).toBe(true)
  const spyPage = await spyHoldingsResult.json() as {
    snapshot: { id: number; composition_date: string; known_at: string; provenance: string }
    holdings: Array<{ id: number; constituent_instrument_id: number | null; constituent_symbol: string | null; is_resolved: boolean; holding_type: string }>
  }
  expect(spyPage.snapshot.provenance).toBe('controlled_fixture')
  const reportedNvda = spyPage.holdings.find(row => row.constituent_symbol === 'NVDA')
  expect(reportedNvda).toMatchObject({ is_resolved: true, holding_type: 'equity' })
  expect(reportedNvda?.constituent_instrument_id).toBeGreaterThan(0)
  await expect(page.getByTestId('etf-snapshot-lineage')).toBeVisible()
  // The browser's text locator sees adjacent NVDA/equity spans concatenated
  // as `NVDAequity`, so the word-boundary regex misses the visible row. Match
  // the rendered accessible name and keep the ordinary user click.
  const nvdaRow = page.getByRole('button', { name: /^NVDA equity NVIDIA Corporation/ }).first()
  await expect(nvdaRow).toBeVisible()
  await nvdaRow.click()
  const chartBarsAfterDrilldown = waitForBars('NVDA')
  const holdingHistoryPreparation = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'POST'
      && url.pathname === '/api/v1/data/ensure'
      && (() => {
        const body = response.request().postDataJSON() as DataEnsureRequest
        return body.target.kind === 'instrument' && 'instrument_id' in body.target
          && body.target.instrument_id === reportedNvda!.constituent_instrument_id
          && body.datasets.includes('history')
      })()
  })
  await page.getByRole('button', { name: 'View history' }).click()
  await page.waitForURL(url => url.pathname === '/chart/NVDA')
  const holdingPreparationResponse = await holdingHistoryPreparation
  expect(holdingPreparationResponse.ok()).toBe(true)
  const holdingPreparationRequest = holdingPreparationResponse.request().postDataJSON() as DataEnsureRequest
  expect(holdingPreparationRequest.start_at).toBeUndefined()
  expect(holdingPreparationRequest.end_at).toBeUndefined()
  const holdingChartUrl = new URL(page.url())
  expect(holdingChartUrl.searchParams.get('holding_snapshot_id')).toBe(String(spyPage.snapshot.id))
  expect(holdingChartUrl.searchParams.get('holding_composition_date')).toBe(spyPage.snapshot.composition_date)
  expect(holdingChartUrl.searchParams.get('holding_known_at')).toBe(spyPage.snapshot.known_at)
  expect(holdingChartUrl.searchParams.get('holding_provenance')).toBe(spyPage.snapshot.provenance)
  expect(holdingChartUrl.searchParams.get('holding_instrument_id')).toBe(String(reportedNvda!.constituent_instrument_id))
  expect(await (await chartBarsAfterDrilldown).json()).not.toHaveLength(0)
  await browserDiagnostics.expectNoCriticalIssues()
})
