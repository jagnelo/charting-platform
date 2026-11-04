import { test, expect } from './helpers'
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
  InstrumentAcquireRequest,
  InstrumentAcquireResponse,
  InstrumentDiscoveryResponse,
} from '../../src/lib/onDemandAcquisition'

type DiscoveryRequest = { query: string; types: string[]; limit: number; request_id: string }
type HistoryRequestBody = HistoryAcquisitionRequest & { request_id: string }
type IssuerRequest = { request_id: string; refresh: boolean; instrument_id?: number }
type InstrumentRequestBody = InstrumentAcquireRequest

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

test('chart search discovers an unknown ticker automatically and deliberate identity selection starts bounded history', async ({ page, loggedIn, browserDiagnostics }) => {
  await page.goto('about:blank')

  const fixtureInstrumentId = 990010
  let canonicalInstrumentResolved = false
  const discoveryRequests: DiscoveryRequest[] = []
  const instrumentRequests: InstrumentRequestBody[] = []
  const historyRequests: HistoryRequestBody[] = []
  const canonicalSearchRequests: string[] = []

  // TCNEW is deliberately absent from the local canonical master in this
  // controlled browser case. Discovery follows the debounced local miss;
  // identity resolution and chart selection still require the user's choice.
  await page.route('**/api/v1/instruments/search**', async route => {
    const url = new URL(route.request().url())
    if (route.request().method() !== 'GET' || url.searchParams.get('q')?.toUpperCase() !== 'TCNEW') {
      await route.continue()
      return
    }
    canonicalSearchRequests.push(url.searchParams.get('q') ?? '')
    if (canonicalInstrumentResolved) {
      await route.fulfill({
        status: 200,
        json: [{
          symbol: 'TCNEW',
          name: 'Unknown ticker (controlled test fixture)',
          exchange: 'TEST',
          type: 'ETF',
          instrument_id: fixtureInstrumentId,
          identity_status: 'resolved',
        }],
      })
      return
    }
    await route.fulfill({ status: 200, json: [] })
  })

  // The explicit acquire mock stands in for the server-side canonical upsert.
  // Keep the subsequent instrument read consistent with that persisted result
  // so the workstation can load the selected ticker locally.
  await page.route('**/api/v1/instruments/TCNEW', async route => {
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
      },
    })
  })
  await page.route('**/api/v1/instruments/TCNEW/data-coverage', async route => {
    await route.fulfill({
      status: 200,
      json: {
        instrument_id: fixtureInstrumentId,
        symbol: 'TCNEW',
        coverage: {},
        is_fetching: false,
        fetch_progress: null,
      },
    })
  })
  const emptyOptionsExposure = {
    symbol: 'TCNEW',
    spot: null,
    expirations: [],
    active_expirations: [],
    computed_at: '2026-10-27T00:00:00Z',
    ladder: [],
    key_levels: { call_wall: null, put_wall: null, gamma_flip: null, max_pain: null },
    pcr_oi: null,
    pcr_volume: null,
    implied_move_pct: null,
    total_gex: 0,
    total_net_dex: 0,
  } satisfies OptionsExposureResponse
  await page.route('**/api/v1/instruments/TCNEW/options/exposure', async route => {
    await route.fulfill({ status: 200, json: emptyOptionsExposure })
  })
  await page.route('**/api/v1/instruments/TCNEW/options/exposure/expirations', async route => {
    const noExpirations: ExpirationSummary[] = []
    await route.fulfill({ status: 200, json: noExpirations })
  })
  await page.route('**/api/v1/ohlcv/local/TCNEW/**', async route => {
    await route.fulfill({ status: 200, json: [] })
  })

  await page.route('**/api/v1/instruments/discover**', async route => {
    const body = route.request().postDataJSON() as DiscoveryRequest
    discoveryRequests.push(body)
    const response = {
      request_id: body.request_id,
      status: 'complete',
      candidates: [{
        symbol: 'TCNEW',
        name: 'Unknown ticker (controlled test fixture)',
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
    instrumentRequests.push(body)
    expect(body.symbol).toBe('TCNEW')
    canonicalInstrumentResolved = true
    await route.fulfill({ status: 200, json: resolvedIdentity(body, fixtureInstrumentId) })
  })

  await page.route('**/api/v1/coverage/instruments/TCNEW/ohlcv*', async route => {
    await route.fulfill({ status: 200, json: missingCoverage(new URL(route.request().url())) })
  })

  await page.route('**/api/v1/instruments/*/history-acquisitions**', async route => {
    const body = route.request().postDataJSON() as HistoryRequestBody
    historyRequests.push(body)
    const requestedId = Number(new URL(route.request().url()).pathname.match(/\/instruments\/(\d+)\//)?.[1])
    expect(requestedId).toBe(fixtureInstrumentId)
    await route.fulfill({ status: 200, json: heldHistory(body, requestedId, 'TCNEW') })
  })

  const sourceActionCountBeforeChartMount = discoveryRequests.length + instrumentRequests.length + historyRequests.length
  await page.goto('/legacy/chart/SPY')
  expect(discoveryRequests.length + instrumentRequests.length + historyRequests.length).toBe(sourceActionCountBeforeChartMount)
  const search = page.getByPlaceholder('Symbol…')
  await expect(search).toBeVisible()
  await expect(page.locator('.symbol-info .sym')).toHaveText('SPY')
  await page.getByRole('button', { name: 'Single panel' }).click()
  await expect(page.locator('.tf-select')).toBeVisible()
  const previousChartReadout = page.locator('.chart-root .ohlcv-info')
  await expect(previousChartReadout).toBeVisible()
  const previousOhlcText = await previousChartReadout.innerText()
  await page.locator('.tf-select').selectOption('M1')
  await expect(page.locator('.tf-select')).toHaveValue('M1')
  expect(discoveryRequests).toHaveLength(0)
  expect(instrumentRequests).toHaveLength(0)
  expect(historyRequests).toHaveLength(0)

  const canonicalSearch = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'GET'
      && url.pathname === '/api/v1/instruments/search'
      && url.searchParams.get('q')?.toUpperCase() === 'TCNEW'
  })
  const discoveryResponseReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'POST' && url.pathname.replace(/\/+$/, '') === '/api/v1/instruments/discover'
  }, { timeout: 10_000 })
  await search.fill('')
  await search.pressSequentially('TCNEW', { delay: 25 })
  const canonicalResults = await canonicalSearch
  const matches = await canonicalResults.json() as Array<{ symbol: string; instrument_id?: number | null }>
  expect(matches).toHaveLength(0)
  expect(canonicalSearchRequests).toEqual(['TCNEW'])
  expect(discoveryRequests).toHaveLength(0)
  expect(instrumentRequests).toHaveLength(0)
  expect(historyRequests).toHaveLength(0)

  const discoveryResponse = await discoveryResponseReady
  expect(discoveryResponse.status()).toBe(200)
  expect(await discoveryResponse.json()).toMatchObject({ status: 'complete', candidates: [{ symbol: 'TCNEW', identity_status: 'unresolved' }] })
  expect(discoveryRequests).toHaveLength(1)
  expect(historyRequests).toHaveLength(0)
  const automaticHistoryReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'POST'
      && /\/api\/v1\/instruments\/\d+\/history-acquisitions$/.test(url.pathname)
  }, { timeout: 10_000 })
  const instrumentReadbackReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'GET'
      && url.pathname === '/api/v1/instruments/TCNEW'
  }, { timeout: 10_000 })
  // Discovery candidates are rendered as options in the shared result list,
  // even though the underlying element is a button for pointer interaction.
  await page.getByRole('option', { name: /Use TCNEW · TEST/ }).click()
  const instrumentReadback = await instrumentReadbackReady
  expect(instrumentReadback.status()).toBe(200)
  expect(await instrumentReadback.json()).toMatchObject({ id: fixtureInstrumentId, symbol: 'TCNEW' })
  await expect(search).toHaveValue('TCNEW')
  await expect(page).toHaveURL(/\/legacy\/chart\/TCNEW$/)
  expect(discoveryRequests).toHaveLength(1)
  expect(discoveryRequests[0]).toMatchObject({ query: 'TCNEW', types: [], limit: 10 })
  expect(discoveryRequests[0]?.request_id).toMatch(/^[0-9a-f-]{36}$/i)
  expect(instrumentRequests[0]).toMatchObject({
    symbol: 'TCNEW',
    provider_candidate: { provider: 'test-fixture', symbol: 'TCNEW', exchange: 'TEST' },
  })

  // The controlled identity POST represents the backend's canonical upsert;
  // deliberate selection then performs the one bounded first-use history request.
  await expect(page.locator('.symbol-info .sym')).toHaveText('TCNEW')
  await expect(page.locator('.chart-root .sr-only')).toContainText('M1 chart; no OHLCV bars loaded.')
  await expect(page.locator('.chart-root .ohlcv-info')).toHaveCount(0)
  expect(await page.locator('.chart-root').innerText()).not.toContain(previousOhlcText)
  const automaticHistory = await automaticHistoryReady
  expect(automaticHistory.status()).toBe(200)
  expect(await automaticHistory.json()).toMatchObject({ symbol: 'TCNEW', status: 'held' })
  const loadHistory = page.getByTestId('history-load-missing')
  await expect(loadHistory).toBeVisible()
  await expect(loadHistory).toBeEnabled() // a held result keeps the deliberate retry available
  await expect(page.getByRole('status').filter({ hasText: 'History for TCNEW is currently unavailable; saved chart data remains visible.' })).toBeVisible()

  expect(instrumentRequests).toHaveLength(1)
  expect(instrumentRequests[0]).toMatchObject({ symbol: 'TCNEW' })
  expect(historyRequests).toHaveLength(1)
  expectBoundedM1Request(historyRequests[0]!)
  await expect(page.getByTestId('history-load-missing')).toBeEnabled()
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
  const historyRequests: HistoryRequestBody[] = []
  const localReadBars: OHLCVBar[][] = []
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
  await page.route('**/api/v1/instruments/779004/history-acquisitions**', async route => {
    const body = route.request().postDataJSON() as HistoryRequestBody
    historyRequests.push(body)
    expect(body.timeframe).toBe('D1')
    historyCompleted = true
    const response: HistoryAcquisitionResponse = {
      request_id: body.request_id, status: 'complete', instrument_id: instrumentId,
      symbol, timeframe: 'D1', adjusted: body.adjusted, requested_start: body.start,
      requested_end: body.end,
      coverage: { status: 'partial', covered_start: bar.ts, covered_end: bar.ts, bar_count: 1, missing_slices: [] },
      bars: [bar], source_outcomes: [fixtureOutcome],
    }
    await route.fulfill({ status: 200, json: response })
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
      && url.pathname === `/api/v1/instruments/${instrumentId}/history-acquisitions`
  })
  await page.getByRole('option', { name: /Use UNXQ · XNYS/ }).click()
  await expect(page).toHaveURL(/\/legacy\/chart\/UNXQ\?/)
  expect(identityRequests).toHaveLength(1)
  const historyResponse = await historyResponseReady
  expect(historyResponse.status()).toBe(200)
  expect(historyRequests).toHaveLength(1)
  expectBoundedD1Request(historyRequests[0]!)
  expect(localReadCount).toBeGreaterThan(0)
  expect(localReadBars[0]).toEqual([])
  expect(calendarReads).toHaveLength(0)

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
  const calendarResponseAfterReloadReady = page.waitForRequest(request => {
    const url = new URL(request.url())
    return request.method() === 'GET'
      && url.pathname === `/api/v1/calendar/instruments/${symbol}/calendar`
  }).then(async request => {
    const response = await request.response()
    if (!response) throw new Error('Expected the post-reload calendar request to receive a response.')
    return {
      method: request.method(),
      pathname: new URL(request.url()).pathname,
      status: response.status(),
      body: await response.json(),
    }
  })
  await page.reload()
  const calendarResponseAfterReload = await calendarResponseAfterReloadReady
  expect(calendarResponseAfterReload.method).toBe('GET')
  expect(calendarResponseAfterReload.pathname).toBe(`/api/v1/calendar/instruments/${symbol}/calendar`)
  expect(calendarResponseAfterReload.status).toBe(200)
  expect(calendarResponseAfterReload.body).toEqual(noInstrumentCalendarEvents)
  await expect(page).toHaveURL(/\/legacy\/chart\/UNXQ\?/) 
  await expect(page.locator('.historical-holding-context')).toContainText('UNXQ')
  await expect.poll(() => localReadCount).toBeGreaterThan(readsBeforeReload)
  expect(localReadBars.at(-1)).toEqual([bar])
  expect(historyRequests).toHaveLength(1)
  expect(optionsExposureReads.length).toBeGreaterThan(0)
  expect(optionsExpirationReads.length).toBeGreaterThan(0)
  await expect.poll(() => calendarReads.length).toBeGreaterThan(calendarReadsBeforeReload)
  expect(calendarReads.at(-1)).toMatchObject({ symbol, start: bar.ts })
  expect(calendarReads.every(read => read.symbol === symbol)).toBe(true)
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
  const historyRequests: HistoryRequestBody[] = []
  const canonicalSearchRequests: string[] = []
  const canonicalInstrumentLookups: Array<{ symbol: string; canonicalOnly: string | null }> = []
  const localBarReadbacks: Array<{ symbol: string; timeframe: string; rows: OHLCVBar[]; afterAcquisition: boolean }> = []
  const calendarRequests: string[] = []

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
    const lookupUrl = new URL(route.request().url())
    canonicalInstrumentLookups.push({
      symbol: lookupUrl.pathname.split('/').at(-1) ?? '',
      canonicalOnly: lookupUrl.searchParams.get('canonical_only'),
    })
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
    instrumentRequests.push(body)
    expect(body.symbol).toBe('TCNEW')
    canonicalInstrumentResolved = true
    await route.fulfill({ status: 200, json: resolvedIdentity(body, fixtureInstrumentId, 'Common Stock') })
  })
  await page.route('**/api/v1/coverage/instruments/TCNEW/ohlcv**', async route => {
    await route.fulfill({ status: 200, json: missingCoverage(new URL(route.request().url())) })
  })
  await page.route('**/api/v1/instruments/*/history-acquisitions**', async route => {
    const body = route.request().postDataJSON() as HistoryRequestBody
    historyRequests.push(body)
    const requestedId = Number(new URL(route.request().url()).pathname.match(/\/instruments\/(\d+)\//)?.[1])
    expect(requestedId).toBe(fixtureInstrumentId)
    const startMs = Date.parse(body.start)
    const endMs = Date.parse(body.end)
    const barMs = Math.ceil(startMs / 60_000) * 60_000
    expect(barMs).toBeGreaterThanOrEqual(startMs)
    expect(barMs).toBeLessThan(endMs)
    const bar: OHLCVBar = {
      ts: new Date(barMs).toISOString(), open: 10, high: 11, low: 9, close: 10.5, volume: 100,
      is_adjusted: true, is_derived: false,
    }
    acquiredBar = bar
    historyAcquired = true
    const response = {
      request_id: body.request_id,
      status: 'partial',
      instrument_id: requestedId,
      symbol: 'TCNEW',
      timeframe: body.timeframe,
      adjusted: body.adjusted,
      requested_start: body.start,
      requested_end: body.end,
      coverage: {
        status: 'partial',
        bar_count: 1,
        covered_start: bar.ts,
        covered_end: bar.ts,
        missing_slices: [{ start: new Date(barMs + 60_000).toISOString(), end: body.end }],
      },
      bars: [bar],
      source_outcomes: [{ ...fixtureOutcome, status: 'used' }],
    } satisfies HistoryAcquisitionResponse
    await route.fulfill({ status: 200, json: response })
  })

  await page.goto('/')
  const search = page.getByRole('combobox', { name: 'Active symbol' })
  await expect(search).toBeVisible()
  await page.getByLabel('Linked timeframe').selectOption('M1')
  expect(discoveryRequests).toHaveLength(0)
  expect(instrumentRequests).toHaveLength(0)
  expect(historyRequests).toHaveLength(0)

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
  expect(historyRequests).toHaveLength(0)

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
      && url.pathname === `/api/v1/instruments/${fixtureInstrumentId}/history-acquisitions`
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
  expect(canonicalInstrumentLookups).toEqual([])
  expect(historyRequests).toHaveLength(1)
  expectBoundedM1Request(historyRequests[0]!)
  expect(instrumentRequests).toHaveLength(1)

  const chartWorkspace = page.getByRole('region', { name: 'Chart workspace' })
  await chartWorkspace.click()
  await expect(page.locator('.tool-window--active').getByRole('region', { name: 'Chart workspace' })).toBeVisible()

  await expect.poll(() => localBarReadbacks.some(readback => readback.afterAcquisition && readback.rows.length === 1)).toBe(true)
  expect(localBarReadbacks.filter(readback => readback.afterAcquisition).every(readback => readback.symbol === 'TCNEW' && readback.timeframe === 'M1')).toBe(true)
  expect(localBarReadbacks.some(readback => readback.afterAcquisition && readback.rows[0]?.ts === acquiredBar?.ts)).toBe(true)
  await expect(page.getByTestId('workstation-history-acquisition')).toHaveCount(0)
  const visibleChart = page.locator('.tool-window--active .chart-root')
  await expect(visibleChart).toHaveAttribute('aria-busy', 'false', { timeout: 10_000 })
  await expect(visibleChart.locator('.sr-only')).toContainText('M1 chart; 1 bars')
  await expect.poll(() => calendarRequests.length).toBeGreaterThan(0)
  expect(calendarRequests.every(symbol => symbol === 'TCNEW')).toBe(true)
  expect(historyRequests).toHaveLength(1)

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
  expect(historyRequests).toHaveLength(1)
  await expect(page.locator('.tool-window--active .chart-root')).toHaveAttribute('aria-busy', 'false')
  await browserDiagnostics.expectNoCriticalIssues()
})

test('held IWM issuer and constituent-history actions preserve snapshot lineage and current-analysis eligibility', async ({ page, loggedIn, browserDiagnostics }) => {
  await page.goto('about:blank')

  const identityRequests: InstrumentRequestBody[] = []
  const discoveryRequests: DiscoveryRequest[] = []
  const issuerRequests: IssuerRequest[] = []
  const historyRequests: Array<{ instrumentId: number; body: HistoryRequestBody }> = []
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

  await page.route('**/api/v1/instruments/*/history-acquisitions**', async route => {
    const body = route.request().postDataJSON() as HistoryRequestBody
    const requestedId = Number(new URL(route.request().url()).pathname.match(/\/instruments\/(\d+)\//)?.[1])
    expect(requestedId).toBe(amdInstrumentId)
    historyRequests.push({ instrumentId: requestedId, body })
    await route.fulfill({ status: 200, json: heldHistory(body, requestedId, 'AMD') })
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
      && url.pathname === `/api/v1/instruments/${amdInstrumentId}/history-acquisitions`
      && (response.request().postDataJSON() as HistoryRequestBody).timeframe === 'D1'
  })
  await page.locator('button.holding-row').filter({ hasText: 'AMD' }).click()
  await page.getByRole('button', { name: 'View history' }).click()
  await expect(page).toHaveURL(/\/legacy\/chart\/AMD(?:\?|$)/)
  expect((await initialChartCoverageReady).status()).toBe(200)
  const automaticD1History = await automaticD1HistoryReady
  expect(automaticD1History.status()).toBe(200)
  expect(await automaticD1History.json()).toMatchObject({ status: 'held', symbol: 'AMD', instrument_id: amdInstrumentId })
  expect(historyRequests).toHaveLength(1)
  expect(historyRequests[0]?.instrumentId).toBe(amdInstrumentId)
  expectBoundedD1Request(historyRequests[0]!.body)
  expect(identityRequests).toHaveLength(2)
  expect(identityRequests[1]).toMatchObject({ symbol: 'AMD' })
  await expect(page.getByRole('status').filter({ hasText: 'History for AMD is currently unavailable; saved chart data remains visible.' })).toBeVisible()
  const historyUrl = new URL(page.url())
  expect(historyUrl.pathname).toBe('/legacy/chart/AMD')
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
      && url.pathname === `/api/v1/instruments/${amdInstrumentId}/history-acquisitions`
      && (response.request().postDataJSON() as HistoryRequestBody).timeframe === 'M1'
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
  await expect(page.getByRole('status').filter({ hasText: 'The history request is held.' })).toBeVisible()
  const m1History = await m1HistoryReady
  expect(m1History.status()).toBe(200)
  expect(await m1History.json()).toMatchObject({ status: 'held', symbol: 'AMD', instrument_id: amdInstrumentId })
  expect(identityRequests).toHaveLength(identityBeforeExplicitM1 + 1)
  expect(identityRequests.at(-1)).toMatchObject({ symbol: 'AMD' })
  await expect(historicalContext).toBeVisible()
  await expect(chartCanvases).toHaveCount(canvasCountBefore)
  expect(identityRequests).toHaveLength(3)
  expect(identityRequests.map(request => request.symbol)).toEqual(['IWM', 'AMD', 'AMD'])
  expect(historyRequests).toHaveLength(2)
  expect(historyRequests.map(request => request.body.timeframe)).toEqual(['D1', 'M1'])
  expect(historyRequests.every(request => request.instrumentId === amdInstrumentId)).toBe(true)
  expect(new Set(historyRequests.map(request => request.body.request_id)).size).toBe(2)
  expectBoundedD1Request(historyRequests[0]!.body)
  expectBoundedM1Request(historyRequests[1]!.body)
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
  const historyRequests: Array<{ instrumentId: number; body: HistoryRequestBody }> = []
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
  await page.route('**/api/v1/instruments/*/history-acquisitions**', async route => {
    const body = route.request().postDataJSON() as HistoryRequestBody
    const requestedId = Number(new URL(route.request().url()).pathname.match(/\/instruments\/(\d+)\//)?.[1])
    expect(requestedId).toBe(amdInstrumentId)
    historyRequests.push({ instrumentId: requestedId, body })
    const startMs = Date.parse(body.start)
    const endMs = Date.parse(body.end)
    const intervalMs = body.timeframe === 'D1' ? 86_400_000 : 60_000
    const barMs = Math.ceil(startMs / intervalMs) * intervalMs
    expect(barMs).toBeGreaterThanOrEqual(startMs)
    expect(barMs).toBeLessThanOrEqual(endMs)
    acquiredFixtureBar = fixtureBarAt(new Date(barMs).toISOString())
    const missingSlices: Array<{ start: string; end: string }> = []
    if (startMs < barMs) missingSlices.push({ start: body.start, end: acquiredFixtureBar.ts })
    const afterBarMs = barMs + intervalMs
    if (afterBarMs < endMs) missingSlices.push({ start: new Date(afterBarMs).toISOString(), end: body.end })
    acquiredCoverage = {
      status: 'partial',
      covered_start: acquiredFixtureBar.ts,
      covered_end: acquiredFixtureBar.ts,
      bar_count: 1,
      missing_slices: missingSlices,
    }
    const response = {
      request_id: body.request_id,
      status: 'partial',
      instrument_id: amdInstrumentId,
      symbol: 'AMD',
      timeframe: body.timeframe,
      adjusted: body.adjusted,
      requested_start: body.start,
      requested_end: body.end,
      coverage: acquiredCoverage,
      bars: [acquiredFixtureBar],
      source_outcomes: [{ ...fixtureOutcome, capability: 'historical_ohlcv', operation: 'history', status: 'returned', result_count: 1 }],
    } satisfies HistoryAcquisitionResponse
    successfulHistoryResponseReceived = true
    await route.fulfill({ status: 200, json: response })
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
      && url.pathname === `/api/v1/instruments/${amdInstrumentId}/history-acquisitions`
      && (response.request().postDataJSON() as HistoryRequestBody).timeframe === 'D1'
  })
  await holdingButton.click()
  await page.getByRole('button', { name: 'View history' }).click()
  await expect(page).toHaveURL(/\/legacy\/chart\/AMD(?:\?|$)/)
  expect((await initialChartCoverageReady).status()).toBe(200)
  const historyUrl = new URL(page.url())
  expect(historyUrl.pathname).toBe('/legacy/chart/AMD')
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
  const automaticD1Result = await automaticD1History.json() as HistoryAcquisitionResponse
  expect(automaticD1Result).toMatchObject({ status: 'partial', symbol: 'AMD', instrument_id: amdInstrumentId, timeframe: 'D1' })
  expect(automaticD1Result.bars).toHaveLength(1)
  expect(Date.parse(automaticD1Result.bars[0]!.ts)).toBeGreaterThanOrEqual(Date.parse(historyRequests[0]!.body.start))
  expect(Date.parse(automaticD1Result.bars[0]!.ts)).toBeLessThanOrEqual(Date.parse(historyRequests[0]!.body.end))
  expect(historyRequests).toHaveLength(1)
  expect(historyRequests[0]?.instrumentId).toBe(amdInstrumentId)
  expectBoundedD1Request(historyRequests[0]!.body)
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
  expect(historyRequests.map(request => request.body.timeframe)).toEqual(['D1', 'M1'])
  expect(historyRequests.every(request => request.instrumentId === amdInstrumentId)).toBe(true)
  expectBoundedD1Request(historyRequests[0]!.body)
  expectBoundedM1Request(historyRequests[1]!.body)
  expect(acquiredFixtureBar).not.toBeNull()
  expect(Date.parse(acquiredFixtureBar!.ts)).toBeGreaterThanOrEqual(Date.parse(historyRequests[1]!.body.start))
  expect(Date.parse(acquiredFixtureBar!.ts)).toBeLessThanOrEqual(Date.parse(historyRequests[1]!.body.end))
  expect(identityRequests).toHaveLength(identityCountBeforeM1 + 1)
  expect(identityRequests.map(request => request.symbol)).toEqual(['OIH', 'AMD', 'AMD'])
  expect(identityRequests.at(-1)).toMatchObject({ symbol: 'AMD' })
  expect(new Set(historyRequests.map(request => request.body.request_id)).size).toBe(2)
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
  const historyRequests: Array<{ symbol: FixtureSymbol; body: HistoryRequestBody }> = []
  const issuerRequests: Array<{ symbol: FixtureSymbol; body: IssuerRequest }> = []
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
  const xhbAcquireStarted = deferred()
  const xhbAcquireGate = deferred()
  const oihAcquireStarted = deferred()
  const oihAcquireGate = deferred()
  const oihFailureStarted = deferred()
  const oihFailureGate = deferred()
  const igvAcquireStarted = deferred()
  const igvAcquireGate = deferred()
  const unresolvedDiscoveryStarted = deferred()
  const unresolvedDiscoveryGate = deferred()
  let oihAcquireCount = 0
  let delayedOihFailureUrl: string | null = null
  let igvSnapshotAvailable = false
  const capabilityReads: FixtureETF[] = []
  let unxqDiscoveryCount = 0
  const identityRequests: InstrumentRequestBody[] = []
  const locallySearchedSymbols = new Set<FixtureSymbol>()
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

  const profileFor = (symbol: FixtureETF): ETFProfile => ({
    id: instruments[symbol].id + 100,
    instrument_id: instruments[symbol].id,
    symbol,
    name: instruments[symbol].name,
    issuer: 'test-fixture',
    fund_family: 'controlled browser fixture',
    adapter_status: 'ready',
    latest_composition_date: '2026-11-02',
    latest_snapshot_id: symbol === 'IGV' && !igvSnapshotAvailable ? null : symbol === 'IGV' ? igvSnapshotId : instruments[symbol].id + 200,
    resolved_count: 0,
    unresolved_count: symbol === 'IGV' && igvSnapshotAvailable ? 3 : 0,
    holdings_capability: null,
  })
  const holdingsResponse = (symbol: FixtureETF, body: IssuerRequest, outcome: 'acquired' | 'unavailable'): ETFProfileAcquireResponse => ({
    request_id: body.request_id,
    instrument_id: instruments[symbol].id,
    symbol,
    outcome,
    refresh: body.refresh,
    refresh_attempted: true,
    refresh_succeeded: outcome === 'acquired',
    profile: outcome === 'acquired' ? profileFor(symbol) : null,
    provider_request_log_ids: [],
    source_provider: 'test-fixture',
    source_operation: 'controlled_browser_fixture',
    message: outcome === 'acquired'
      ? 'Controlled fixture response only; not issuer evidence.'
      : 'No holdings profile is available in this controlled fixture.',
  })

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
  await page.route('**/api/v1/instruments/*/history-acquisitions', async route => {
    const body = route.request().postDataJSON() as HistoryRequestBody
    const id = Number(new URL(route.request().url()).pathname.match(/\/instruments\/(\d+)\//)?.[1])
    const symbol = (Object.keys(instruments) as FixtureSymbol[]).find(key => instruments[key].id === id)
    if (!symbol) return route.continue()
    expect(body).toMatchObject({ timeframe: 'D1', adjusted: true })
    expect(body.request_id).toMatch(/^[0-9a-f-]{36}$/i)
    const start = Date.parse(body.start)
    const end = Date.parse(body.end)
    expect(end).toBeGreaterThan(start)
    expect(Math.ceil((end - start) / 86_400_000) + 1).toBeLessThanOrEqual(2000)
    historyRequests.push({ symbol, body })
    const bar: OHLCVBar = {
      ts: body.start,
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
    const response: HistoryAcquisitionResponse = {
      request_id: body.request_id,
      status: 'partial',
      instrument_id: id,
      symbol,
      timeframe: body.timeframe,
      adjusted: body.adjusted,
      requested_start: body.start,
      requested_end: body.end,
      coverage: {
        status: 'partial',
        covered_start: bar.ts,
        covered_end: bar.ts,
        bar_count: 1,
        missing_slices: [{ start: new Date(Date.parse(bar.ts) + 86_400_000).toISOString(), end: body.end }],
      },
      bars: [bar],
      source_outcomes: [{ ...fixtureOutcome, capability: 'historical_ohlcv', operation: 'history', status: 'returned', result_count: 1 }],
    }
    await route.fulfill({ status: 200, json: response })
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
  await page.route('**/api/v1/etf-holdings/*/acquire', async route => {
    const symbol = new URL(route.request().url()).pathname.split('/')[4] as FixtureSymbol
    if (!(symbol in instruments)) return route.continue()
    if (symbol === 'UNXQ') return route.continue()
    const body = route.request().postDataJSON() as IssuerRequest
    expect(body.refresh).toBe(true)
    expect(body.instrument_id).toBe(instruments[symbol].id)
    issuerRequests.push({ symbol, body })
    if (symbol === 'XHB') {
      xhbAcquireStarted.resolve()
      await xhbAcquireGate.promise
      await route.fulfill({ status: 200, json: holdingsResponse(symbol, body, 'unavailable') })
      return
    }
    if (symbol === 'OIH') {
      oihAcquireCount += 1
      if (oihAcquireCount === 1) {
        oihAcquireStarted.resolve()
        await oihAcquireGate.promise
        await route.fulfill({ status: 200, json: holdingsResponse(symbol, body, 'acquired') })
        return
      }
      delayedOihFailureUrl = route.request().url()
      oihFailureStarted.resolve()
      await oihFailureGate.promise
      await route.fulfill({ status: 503, json: { detail: 'Controlled fixture error; no source request was made.' } })
      return
    }
    if (symbol === 'IGV') {
      igvAcquireStarted.resolve()
      await igvAcquireGate.promise
      igvSnapshotAvailable = true
      await route.fulfill({ status: 200, json: holdingsResponse(symbol, body, 'acquired') })
      return
    }
    await route.fulfill({ status: 200, json: holdingsResponse(symbol, body, 'unavailable') })
  })

  try {
    await page.goto('/')
    const symbolSearch = page.getByRole('combobox', { name: 'Active symbol' })
    await expect(symbolSearch).toBeVisible()
    expect(historyRequests).toHaveLength(0)
    expect(issuerRequests).toHaveLength(0)
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

    const xhbHistoryResponseReady = page.waitForResponse(response => {
      const url = new URL(response.url())
      return response.request().method() === 'POST'
        && url.pathname === `/api/v1/instruments/${instruments.XHB.id}/history-acquisitions`
    })
    const xhbIssuerResponseReady = page.waitForResponse(response => {
      const url = new URL(response.url())
      return response.request().method() === 'POST' && url.pathname === '/api/v1/etf-holdings/XHB/acquire'
    })
    await chooseETF('XHB')
    const xhbHistoryResponse = await xhbHistoryResponseReady
    expect(xhbHistoryResponse.status()).toBe(200)
    await xhbAcquireStarted.promise
    expect(issuerRequests.map(request => request.symbol)).toContain('XHB')
    await expect.poll(() => localReadbacks.some(readback => readback.symbol === 'XHB' && readback.bars.length === 1)).toBe(true)
    expect(issuerRequests.find(request => request.symbol === 'XHB')?.body).toMatchObject({ refresh: true, instrument_id: instruments.XHB.id })
    expect(holdingsReads).toContain('XHB')
    expect(localReadbacks.find(readback => readback.symbol === 'XHB' && readback.bars.length === 1)?.timeframe).toBe('D1')

    xhbAcquireGate.resolve()
    expect((await xhbIssuerResponseReady).status()).toBe(200)
    await expect(page.locator('.workstation__selection-acquisition').filter({ hasText: 'Holdings for XHB are not available' })).toBeVisible()

    for (const symbol of ['SPY', 'RSP', 'QQQ'] as const) {
      const historyResponseReady = page.waitForResponse(response => {
        const url = new URL(response.url())
        return response.request().method() === 'POST'
          && url.pathname === `/api/v1/instruments/${instruments[symbol].id}/history-acquisitions`
      })
      const issuerResponseReady = page.waitForResponse(response => {
        const url = new URL(response.url())
        return response.request().method() === 'POST' && url.pathname === `/api/v1/etf-holdings/${symbol}/acquire`
      })
      await chooseETF(symbol)
      expect((await historyResponseReady).status()).toBe(200)
      expect((await issuerResponseReady).status()).toBe(200)
      await expect.poll(() => localReadbacks.some(readback => readback.symbol === symbol && readback.bars.length === 1)).toBe(true)
      await expect(page.locator('.workstation__selection-acquisition').filter({ hasText: `Holdings for ${symbol} are not available` })).toBeVisible()
    }

    const oihIssuerResponseReady = page.waitForResponse(response => {
      const url = new URL(response.url())
      return response.request().method() === 'POST' && url.pathname === '/api/v1/etf-holdings/OIH/acquire'
    })
    await chooseETF('OIH')
    await oihAcquireStarted.promise
    const oihReadsBeforeSwitch = holdingsReads.filter(symbol => symbol === 'OIH').length

    const igvIssuerResponseReady = page.waitForResponse(response => {
      const url = new URL(response.url())
      return response.request().method() === 'POST' && url.pathname === '/api/v1/etf-holdings/IGV/acquire'
    })
    await chooseETF('IGV')
    await igvAcquireStarted.promise
    await expect(page.locator('.workstation__selection-acquisition').filter({ hasText: 'Checking holdings for IGV' })).toBeVisible()
    await expect(page.locator('.workstation__selection-acquisition').filter({ hasText: 'Holdings for OIH' })).toHaveCount(0)
    expect(holdingsReads.at(-1)).toBe('IGV')
    igvAcquireGate.resolve()
    expect((await igvIssuerResponseReady).status()).toBe(200)
    await expect(page.locator('.workstation__selection-acquisition').filter({ hasText: 'Holdings for IGV are available from the selected ticker' })).toBeVisible()
    expect(industryReads.at(-1)).toBe('IGV')
    expect(holdingsReads.filter(symbol => symbol === 'IGV').length).toBeGreaterThan(0)
    const oihIndustryReadsBeforeLateResponse = industryReads.filter(symbol => symbol === 'OIH').length

    // The prior direct OIH selection resolves only after IGV is current. A late
    // success may not restore OIH holdings or replace IGV's channel message.
    oihAcquireGate.resolve()
    expect((await oihIssuerResponseReady).status()).toBe(200)
    await expect(symbolSearch).toHaveValue('IGV')
    await expect(page.locator('.workstation__selection-acquisition').filter({ hasText: 'Holdings for IGV are available from the selected ticker' })).toBeVisible()
    expect(holdingsReads.filter(symbol => symbol === 'OIH')).toHaveLength(oihReadsBeforeSwitch)
    expect(industryReads.filter(symbol => symbol === 'OIH')).toHaveLength(oihIndustryReadsBeforeLateResponse)

    // A locally misclassified Stock hint must not preserve the prior IGV
    // constituents after canonical identity confirms this selected ticker as ETV.
    const igvContextGroup = page.getByRole('group', { name: 'Constituents' })
    const igvContextWidget = igvContextGroup.getByRole('listbox', { name: 'Constituents symbols' })
    const priorIgvHolding = igvContextWidget.getByRole('option', { name: /UNXQ Unlisted Example Software Corp/ })
    await expect(igvContextGroup).toContainText('IGV')
    await expect(priorIgvHolding).toBeVisible()
    const bwetIdentityResponseReady = page.waitForResponse(response => {
      const url = new URL(response.url())
      return response.request().method() === 'POST' && url.pathname === '/api/v1/instruments/acquire'
        && (response.request().postDataJSON() as InstrumentRequestBody).symbol === 'BWET'
    })
    const bwetHistoryResponseReady = page.waitForResponse(response => {
      const url = new URL(response.url())
      return response.request().method() === 'POST'
        && url.pathname === `/api/v1/instruments/${instruments.BWET.id}/history-acquisitions`
    })
    const bwetIssuerResponseReady = page.waitForResponse(response => {
      const url = new URL(response.url())
      return response.request().method() === 'POST' && url.pathname === '/api/v1/etf-holdings/BWET/acquire'
    })
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
    expect((await bwetIssuerResponseReady).status()).toBe(200)
    expect(identityRequests.filter(request => request.symbol === 'BWET')).toHaveLength(1)
    expect(issuerRequests.filter(request => request.symbol === 'BWET').map(request => request.body)).toEqual([
      expect.objectContaining({ refresh: true, instrument_id: instruments.BWET.id }),
    ])
    expect(historyRequests.filter(request => request.symbol === 'BWET').map(request => request.body.timeframe)).toEqual(['D1'])
    expect(capabilityReads).toContain('BWET')
    await expect.poll(() => localReadbacks.some(readback => readback.symbol === 'BWET' && readback.bars.length === 1)).toBe(true)
    await expect(page.locator('.workstation__selection-acquisition').filter({ hasText: 'Holdings for BWET are not available' })).toBeVisible()
    await expect(igvContextGroup).toContainText('BWET')
    await expect(igvContextWidget).toBeVisible()
    await expect(priorIgvHolding).toHaveCount(0)

    const delayedOihFailureResponseReady = page.waitForResponse(response => {
      const url = new URL(response.url())
      return response.request().method() === 'POST' && url.pathname === '/api/v1/etf-holdings/OIH/acquire'
    })
    await chooseETF('OIH')
    await oihFailureStarted.promise
    const controlledOihFailure = issuerRequests.filter(request => request.symbol === 'OIH').at(-1)?.body
    expect(controlledOihFailure?.request_id).toMatch(/^[0-9a-f-]{36}$/i)
    expect(delayedOihFailureUrl).toBeTruthy()
    browserDiagnostics.allowExpectedControlledApiFault(
      delayedOihFailureUrl!,
      controlledOihFailure!.request_id,
      503,
    )
    const xhbAfterFailureSelectionReady = page.waitForResponse(response => {
      const url = new URL(response.url())
      return response.request().method() === 'POST' && url.pathname === '/api/v1/etf-holdings/XHB/acquire'
    })
    await chooseETF('XHB')
    expect((await xhbAfterFailureSelectionReady).status()).toBe(200)
    await expect(page.locator('.workstation__selection-acquisition').filter({ hasText: 'Holdings for XHB are not available' })).toBeVisible()
    oihFailureGate.resolve()
    igvAcquireGate.resolve()
    expect((await delayedOihFailureResponseReady).status()).toBe(503)
    await expect(page.locator('.workstation__selection-acquisition').filter({ hasText: 'Holdings for XHB are not available' })).toBeVisible()
    await expect(page.locator('.workstation__selection-acquisition--error')).toHaveCount(0)

    expect(issuerRequests.map(request => request.symbol)).toEqual(['XHB', 'SPY', 'RSP', 'QQQ', 'OIH', 'IGV', 'OIH', 'BWET', 'OIH', 'XHB'])
    expect(historyRequests.map(request => request.symbol)).toEqual(['XHB', 'SPY', 'RSP', 'QQQ', 'OIH', 'IGV', 'OIH', 'BWET', 'OIH', 'XHB'])
    expect(discoveryRequests).toHaveLength(0)
    expect(historyRequests.every(request => request.body.timeframe === 'D1' && request.body.adjusted)).toBe(true)
    const requestIds = historyRequests.map(request => request.body.request_id)
    expect(requestIds.every(requestId => /^[0-9a-f-]{36}$/i.test(requestId))).toBe(true)
    expect(new Set(requestIds).size).toBe(requestIds.length)
    const issuerRequestIds = issuerRequests.map(request => request.body.request_id)
    expect(issuerRequestIds.every(requestId => /^[0-9a-f-]{36}$/i.test(requestId))).toBe(true)
    expect(new Set(issuerRequestIds).size).toBe(issuerRequestIds.length)
    expect(calendarReads.every(symbol => symbol === 'SPY' || symbol in instruments)).toBe(true)

    // The acquired IGV snapshot is a real-shape controlled fixture with zero
    // canonical equities. Reported values remain visible before identity work.
    const igvIssuerCount = issuerRequests.filter(request => request.symbol === 'IGV').length
    expect(igvIssuerCount).toBe(1)
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
    expect(issuerRequests.filter(request => request.symbol === 'IGV')).toHaveLength(igvIssuerCount)
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
    // candidate is acquired once, the route retains snapshot/row lineage, and
    // chart history is then loaded for only that one selected equity.
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
        && url.pathname === `/api/v1/instruments/${instruments.UNXQ.id}/history-acquisitions`
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
    console.log(`[reported-holding-candidate-geometry] ${JSON.stringify(candidateGeometry)}`)
    expect(candidateGeometry.centerInsideToolBody).toBe(true)
    expect(candidateGeometry.fullyWithinToolBody).toBe(true)
    expect(candidateGeometry.fullyWithinSelectionPanel).toBe(true)
    expect(candidateGeometry.toolBodyScrollLeft).toBe(0)
    expect(candidateGeometry.toolBodyScrollWidth).toBe(candidateGeometry.toolBodyClientWidth)
    expect(candidateGeometry.centerHitCandidate).toBe(true)
    await candidate.click()
    expect((await identityResponseReady).status()).toBe(200)
    expect((await historyResponseReady).status()).toBe(200)
    await expect(page).toHaveURL(/\/legacy\/chart\/UNXQ\?/)
    const holdingChartUrl = new URL(page.url())
    expect(holdingChartUrl.searchParams.get('holding_snapshot_id')).toBe(String(igvSnapshot.id))
    expect(holdingChartUrl.searchParams.get('holding_composition_date')).toBe(igvSnapshot.composition_date)
    expect(holdingChartUrl.searchParams.get('holding_known_at')).toBe(igvSnapshot.known_at)
    expect(holdingChartUrl.searchParams.get('holding_provenance')).toBe(igvSnapshot.provenance)
    expect(holdingChartUrl.searchParams.get('holding_source_provider')).toBe(igvSnapshot.source_provider)
    expect(holdingChartUrl.searchParams.get('holding_instrument_id')).toBe(String(instruments.UNXQ.id))
    expect(holdingChartUrl.searchParams.get('holding_row_id')).toBe(String(unxqHolding.id))
    expect(holdingChartUrl.searchParams.get('holding_source_row_id')).toBe(unxqHolding.source_row_id)
    expect(holdingChartUrl.searchParams.get('holding_reported_symbol')).toBe(unxqHolding.reported_symbol)
    expect(holdingChartUrl.searchParams.get('holding_reported_name')).toBe(unxqHolding.reported_name)
    expect(holdingChartUrl.searchParams.get('holding_type')).toBe('equity')
    expect(identityRequests.filter(request => request.symbol === 'UNXQ')).toHaveLength(1)
    expect(identityRequests.find(request => request.symbol === 'UNXQ')?.provider_candidate).toMatchObject({ provider: 'test-fixture', symbol: 'UNXQ', exchange: 'TEST' })
    const unxqHistory = historyRequests.filter(request => request.symbol === 'UNXQ')
    expect(unxqHistory).toHaveLength(1)
    expectBoundedD1Request(unxqHistory[0]!.body)
    const loadedUnxqBar = bars.get('UNXQ')
    await expect.poll(() => localReadbacks.some(readback => readback.symbol === 'UNXQ' && readback.bars.length === 1)).toBe(true)
    expect(localReadbacks.find(readback => readback.symbol === 'UNXQ' && readback.bars.length === 1)?.bars[0]).toMatchObject({ ts: loadedUnxqBar?.ts, close: loadedUnxqBar?.close })
    await expect(page.locator('.historical-holding-context')).toContainText('UNXQ')
    await browserDiagnostics.expectNoCriticalIssues()
  } finally {
    xhbAcquireGate.resolve()
    oihAcquireGate.resolve()
    oihFailureGate.resolve()
    igvAcquireGate.resolve()
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
  await workstationResults.getByRole('option', { name: /AMD/ }).first().click()
  await expect(workstationSearch).toHaveValue('AMD')
  const workstationBars = await workstationBarsResponse
  expect(await workstationBars.json()).not.toHaveLength(0)

  await page.goto('/legacy/chart')
  const chartSearch = page.getByRole('combobox', { name: 'Symbol…' })
  const chartSearchActionCount = sourceActionRequests.length
  await chartSearch.fill('')
  const chartSearchResponse = waitForSearch('NVDA')
  await chartSearch.fill('NVDA')
  expect((await chartSearchResponse).ok()).toBe(true)
  const chartResults = page.getByRole('listbox', { name: 'Symbol search results' })
  await expect(chartResults.getByRole('option', { name: /NVDA/ }).first()).toBeVisible()
  expect(sourceActionRequests).toHaveLength(chartSearchActionCount)
  const chartBarsResponse = waitForBars('NVDA')
  await chartResults.getByRole('option', { name: /NVDA/ }).first().click()
  const chartBars = await chartBarsResponse
  expect(await chartBars.json()).not.toHaveLength(0)

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
  await page.getByRole('button', { name: 'View history' }).click()
  await page.waitForURL(url => url.pathname === '/legacy/chart/NVDA')
  const holdingChartUrl = new URL(page.url())
  expect(holdingChartUrl.searchParams.get('holding_snapshot_id')).toBe(String(spyPage.snapshot.id))
  expect(holdingChartUrl.searchParams.get('holding_composition_date')).toBe(spyPage.snapshot.composition_date)
  expect(holdingChartUrl.searchParams.get('holding_known_at')).toBe(spyPage.snapshot.known_at)
  expect(holdingChartUrl.searchParams.get('holding_provenance')).toBe(spyPage.snapshot.provenance)
  expect(holdingChartUrl.searchParams.get('holding_instrument_id')).toBe(String(reportedNvda!.constituent_instrument_id))
  expect(await (await chartBarsAfterDrilldown).json()).not.toHaveLength(0)
  await browserDiagnostics.expectNoCriticalIssues()
})
