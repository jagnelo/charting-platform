import { test, expect } from './helpers'
import type {
  ETFHolding,
  ETFHoldingsDate,
  ETFHoldingsPage,
  ETFHoldingsSnapshot,
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
type IssuerRequest = { request_id: string; refresh: boolean }
type InstrumentRequestBody = InstrumentAcquireRequest

const fixtureOutcome = {
  provider: 'test-fixture',
  capability: 'fixture_only',
  operation: 'deterministic_ui_test',
  status: 'used' as const,
}

function resolvedIdentity(request: InstrumentRequestBody, instrumentId: number): InstrumentAcquireResponse {
  return {
    request_id: request.request_id,
    status: 'resolved',
    instrument: {
      instrument_id: instrumentId,
      symbol: request.symbol,
      identity_status: 'resolved',
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

test('explicit chart discovery, identity selection, and bounded missing-history request', async ({ page, loggedIn, browserDiagnostics }) => {
  await page.goto('about:blank')

  const fixtureInstrumentId = 990010
  let canonicalInstrumentResolved = false
  const discoveryRequests: DiscoveryRequest[] = []
  const instrumentRequests: InstrumentRequestBody[] = []
  const historyRequests: HistoryRequestBody[] = []
  const canonicalSearchRequests: string[] = []

  // TCNEW is deliberately absent from the local canonical master in this
  // controlled browser case. Keep that local read deterministic; discovery and
  // acquisition remain explicit user actions below.
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

  await page.goto('/legacy/chart')
  const search = page.getByPlaceholder('Symbol…')
  await expect(search).toBeVisible()
  expect(discoveryRequests).toHaveLength(0)
  expect(instrumentRequests).toHaveLength(0)
  expect(historyRequests).toHaveLength(0)

  const canonicalSearch = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'GET'
      && url.pathname === '/api/v1/instruments/search'
      && url.searchParams.get('q')?.toUpperCase() === 'TCNEW'
  })
  await search.fill('')
  await search.pressSequentially('TCNEW', { delay: 25 })
  const canonicalResults = await canonicalSearch
  const matches = await canonicalResults.json() as Array<{ symbol: string; instrument_id?: number | null }>
  expect(matches).toHaveLength(0)
  expect(canonicalSearchRequests).toEqual(['TCNEW'])
  expect(discoveryRequests).toHaveLength(0)
  expect(instrumentRequests).toHaveLength(0)
  expect(historyRequests).toHaveLength(0)

  const discoveryResponseReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'POST' && url.pathname.replace(/\/+$/, '') === '/api/v1/instruments/discover'
  }, { timeout: 10_000 })
  await page.getByRole('button', { name: 'Search free sources for TCNEW' }).click()
  const discoveryResponse = await discoveryResponseReady
  expect(discoveryResponse.status()).toBe(200)
  expect(await discoveryResponse.json()).toMatchObject({ status: 'complete', candidates: [{ symbol: 'TCNEW', identity_status: 'unresolved' }] })
  expect(discoveryRequests).toHaveLength(1)
  const instrumentReadbackReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'GET'
      && url.pathname === '/api/v1/instruments/TCNEW'
  }, { timeout: 10_000 })
  await page.getByRole('button', { name: /Resolve TCNEW · TEST/ }).click()
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
  // the awaited response above proves the user flow reads that persisted record.
  await expect(page.getByTestId('history-load-missing')).toBeVisible()
  await expect(page.getByTestId('history-load-missing')).toBeEnabled()
  await expect(page.locator('.symbol-info .sym')).toHaveText('TCNEW')

  await page.locator('.tf-select').selectOption('M1')
  const loadHistory = page.getByTestId('history-load-missing')
  await expect(loadHistory).toBeEnabled()
  await loadHistory.click()
  await expect(page.getByRole('status').filter({ hasText: 'The history request is held.' })).toBeVisible()

  expect(instrumentRequests).toHaveLength(2)
  expect(instrumentRequests[1]).toMatchObject({ symbol: 'TCNEW' })
  expect(historyRequests).toHaveLength(1)
  expectBoundedM1Request(historyRequests[0]!)
  await expect(page.getByTestId('history-load-missing')).toBeEnabled()
  await browserDiagnostics.expectNoCriticalIssues()
})

test('main Workstation explicitly discovers an unknown ticker and loads its missing bars into the focused chart', async ({ page, loggedIn, browserDiagnostics }) => {
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

  await page.route('**/api/v1/instruments/search**', async route => {
    const url = new URL(route.request().url())
    if (route.request().method() !== 'GET' || url.searchParams.get('q')?.toUpperCase() !== 'TCNEW') {
      await route.continue()
      return
    }
    canonicalSearchRequests.push(url.searchParams.get('q') ?? '')
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
    const response = {
      request_id: body.request_id,
      status: 'complete',
      candidates: [{
        symbol: 'TCNEW', name: 'Unknown ticker (controlled test fixture)', exchange: 'TEST', type: 'Stock',
        provider: 'test-fixture', instrument_id: null, identity_status: 'unresolved',
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
    acquiredBar = {
      ts: new Date(barMs).toISOString(), open: 10, high: 11, low: 9, close: 10.5, volume: 100,
    } satisfies OHLCVBar
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
        covered_start: acquiredBar.ts,
        covered_end: acquiredBar.ts,
        missing_slices: [{ start: new Date(barMs + 60_000).toISOString(), end: body.end }],
      },
      bars: [acquiredBar],
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
  await search.click()
  await search.fill('')
  await search.pressSequentially('TCNEW', { delay: 25 })
  const canonicalSearch = await canonicalSearchReady
  expect(await canonicalSearch.json()).toEqual([])
  expect(canonicalSearchRequests).toEqual(['TCNEW'])
  expect(discoveryRequests).toHaveLength(0)
  expect(instrumentRequests).toHaveLength(0)
  expect(historyRequests).toHaveLength(0)

  const discoveryReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'POST' && url.pathname === '/api/v1/instruments/discover'
  }, { timeout: 10_000 })
  await page.getByRole('button', { name: 'Search free sources for TCNEW' }).click()
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
  await page.getByRole('button', { name: /Resolve TCNEW · TEST/ }).click()
  const candidateResolve = await candidateResolveReady
  expect(candidateResolve.status()).toBe(200)
  await expect(search).toHaveValue('TCNEW')
  await expect(page).toHaveURL(/\/$/)
  expect(instrumentRequests).toHaveLength(1)
  expect(instrumentRequests[0]).toMatchObject({
    symbol: 'TCNEW',
    provider_candidate: { provider: 'test-fixture', symbol: 'TCNEW', exchange: 'TEST' },
  })
  expect(canonicalInstrumentLookups).toContainEqual({ symbol: 'TCNEW', canonicalOnly: 'true' })
  expect(historyRequests).toHaveLength(0)

  const chartWorkspace = page.getByRole('region', { name: 'Chart workspace' })
  await chartWorkspace.click()
  await expect(page.locator('.tool-window--active').getByRole('region', { name: 'Chart workspace' })).toBeVisible()
  await expect(page.getByTestId('workstation-history-acquisition')).toBeVisible({ timeout: 15_000 })

  const historyReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'POST'
      && url.pathname === `/api/v1/instruments/${fixtureInstrumentId}/history-acquisitions`
  }, { timeout: 10_000 })
  await page.getByTestId('workstation-history-acquisition').getByTestId('history-load-missing').click()
  const historyResponse = await historyReady
  expect(historyResponse.status()).toBe(200)
  expect(historyRequests).toHaveLength(1)
  expectBoundedM1Request(historyRequests[0]!)
  expect(instrumentRequests).toHaveLength(2)
  expect(instrumentRequests[1]).toMatchObject({ symbol: 'TCNEW' })

  await expect.poll(() => localBarReadbacks.some(readback => readback.afterAcquisition && readback.rows.length === 1)).toBe(true)
  expect(localBarReadbacks.filter(readback => readback.afterAcquisition).every(readback => readback.symbol === 'TCNEW' && readback.timeframe === 'M1')).toBe(true)
  expect(localBarReadbacks.some(readback => readback.afterAcquisition && readback.rows[0]?.ts === acquiredBar?.ts)).toBe(true)
  await expect(page.getByTestId('workstation-history-acquisition')).toHaveCount(0)
  await expect(page.locator('.tool-window--active .chart-root')).toHaveAttribute('aria-busy', 'false', { timeout: 10_000 })
  expect(historyRequests).toHaveLength(1)
  await browserDiagnostics.expectNoCriticalIssues()
})

test('held IWM issuer and constituent-history actions preserve snapshot lineage and current-analysis eligibility', async ({ page, loggedIn, browserDiagnostics }) => {
  await page.goto('about:blank')

  const identityRequests: InstrumentRequestBody[] = []
  const discoveryRequests: DiscoveryRequest[] = []
  const issuerRequests: IssuerRequest[] = []
  const historyRequests: HistoryRequestBody[] = []
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
    await route.fulfill({ status: 200, json: resolvedIdentity(body, instrumentId) })
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
      outcome: 'held',
      refresh: body.refresh,
      refresh_attempted: true,
      refresh_succeeded: false,
      profile: selectedProfile,
      capability: selectedProfile.holdings_capability,
      provider_request_log_ids: [],
      message: 'Deterministic test-fixture hold; the stored snapshot remains available.',
    } satisfies ETFProfileAcquireResponse
    await route.fulfill({ status: 200, json: response })
  })

  await page.route('**/api/v1/coverage/instruments/AMD/ohlcv*', async route => {
    await route.fulfill({ status: 200, json: missingCoverage(new URL(route.request().url())) })
  })

  await page.route('**/api/v1/instruments/*/history-acquisitions**', async route => {
    const body = route.request().postDataJSON() as HistoryRequestBody
    historyRequests.push(body)
    const requestedId = Number(new URL(route.request().url()).pathname.match(/\/instruments\/(\d+)\//)?.[1])
    expect(requestedId).toBe(amdInstrumentId)
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
  await page.locator('.profile-card').filter({ hasText: 'IWM' }).first().click()
  const originalPage = await (await holdingsReady).json() as ETFHoldingsPage
  const amdRow = originalPage.holdings.find(row => (row.constituent_symbol || row.reported_symbol) === 'AMD' && row.is_resolved)
  amdInstrumentId = Number(amdRow?.constituent_instrument_id ?? 0)
  expect(amdInstrumentId, 'history identity uses the actual selected constituent ID').toBeGreaterThan(0)

  const lineage = page.getByTestId('etf-snapshot-lineage')
  await expect(lineage).toBeVisible()
  const originalLineage = await lineage.innerText()
  const snapshotPanel = page.locator('.holdings-main > .workspace-panel').filter({ has: lineage })
  const originalEligibility = await snapshotPanel.locator('.panel-title-row > .panel-meta').innerText()
  const compositionLine = await page.locator('.snapshot-date-line').innerText()
  const compositionDate = compositionLine.match(/Composition (\d{4}-\d{2}-\d{2})/)?.[1]
  const knownAt = await page.getByTestId('etf-snapshot-known-at').getAttribute('datetime')
  expect(compositionDate).toBeTruthy()
  expect(knownAt).toBeTruthy()
  const rowLocator = page.locator('.holdings-table .holding-row:not(.holding-row--head)')
  const originalRowCount = await rowLocator.count()
  expect(originalRowCount).toBeGreaterThan(0)

  const iwmIdentityResponseReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'POST'
      && url.pathname.replace(/\/+$/, '') === '/api/v1/instruments/acquire'
  }, { timeout: 10_000 })
  await page.getByTestId('etf-request-issuer').click()
  const iwmIdentityResponse = await iwmIdentityResponseReady
  expect(iwmIdentityResponse.status()).toBe(200)
  expect(await iwmIdentityResponse.json()).toMatchObject({ status: 'resolved', instrument: { symbol: 'IWM', identity_status: 'resolved' } })
  await expect(page.getByRole('status').filter({ hasText: 'Issuer refresh did not complete.' })).toBeVisible()
  expect(identityRequests).toHaveLength(1)
  expect(identityRequests[0]).toMatchObject({ symbol: 'IWM' })
  expect(issuerRequests).toHaveLength(1)
  expect(issuerRequests[0]).toMatchObject({ refresh: true })
  expect(await lineage.innerText()).toBe(originalLineage)
  expect(await snapshotPanel.locator('.panel-title-row > .panel-meta').innerText()).toBe(originalEligibility)
  await expect(page.getByTestId('etf-snapshot-known-at')).toHaveAttribute('datetime', String(knownAt))
  await expect(rowLocator).toHaveCount(originalRowCount)

  const initialChartCoverageReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'GET'
      && url.pathname === '/api/v1/instruments/AMD/data-coverage'
  })
  await page.locator('.holding-row').filter({ hasText: 'AMD' }).first().click()
  await page.getByRole('button', { name: 'View history' }).click()
  await expect(page).toHaveURL(/\/legacy\/chart\/AMD(?:\?|$)/)
  expect((await initialChartCoverageReady).status()).toBe(200)
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
  await page.getByTestId('history-load-missing').click()
  await expect(page.getByRole('status').filter({ hasText: 'The history request is held.' })).toBeVisible()
  await expect(historicalContext).toBeVisible()
  await expect(chartCanvases).toHaveCount(canvasCountBefore)
  expect(identityRequests).toHaveLength(2)
  expect(identityRequests[1]).toMatchObject({ symbol: 'AMD' })
  expect(historyRequests).toHaveLength(1)
  expectBoundedM1Request(historyRequests[0]!)
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
  const historyRequests: HistoryRequestBody[] = []
  let amdInstrumentId = 0
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
    const id = symbol === 'OIH' ? fixtureInstrumentId : symbol === 'AMD' ? amdInstrumentId : 0
    expect(id, `identity fixture must use the local canonical ${symbol} ID`).toBeGreaterThan(0)
    await route.fulfill({ status: 200, json: resolvedIdentity(body, id) })
  })

  await page.route('**/api/v1/etf-holdings/OIH/acquire**', async route => {
    const body = route.request().postDataJSON() as IssuerRequest
    issuerRequests.push(body)
    const response = {
      request_id: body.request_id,
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
    historyRequests.push(body)
    const requestedId = Number(new URL(route.request().url()).pathname.match(/\/instruments\/(\d+)\//)?.[1])
    expect(requestedId).toBe(amdInstrumentId)
    const startMs = Date.parse(body.start)
    const endMs = Date.parse(body.end)
    const barMs = Math.ceil(startMs / 60_000) * 60_000
    expect(barMs).toBeGreaterThanOrEqual(startMs)
    expect(barMs).toBeLessThanOrEqual(endMs)
    acquiredFixtureBar = fixtureBarAt(new Date(barMs).toISOString())
    const missingSlices: Array<{ start: string; end: string }> = []
    if (startMs < barMs) missingSlices.push({ start: body.start, end: acquiredFixtureBar.ts })
    const afterBarMs = barMs + 60_000
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

  const discoveryResponseReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'POST'
      && url.pathname.replace(/\/+$/, '') === '/api/v1/instruments/discover'
  }, { timeout: 10_000 })
  await page.getByRole('button', { name: 'Search free sources for OIH' }).click()
  const discoveryResponse = await discoveryResponseReady
  expect(discoveryResponse.status()).toBe(200)
  expect(await discoveryResponse.json()).toMatchObject({ status: 'complete', candidates: [{ symbol: 'OIH', identity_status: 'unresolved' }] })
  expect(discoveryRequests).toHaveLength(1)
  await page.getByRole('button', { name: /Resolve OIH · TEST/ }).click()
  expect(fixtureProfile.instrument_id).toBe(fixtureInstrumentId)
  expect(fixtureSnapshot.etf_instrument_id).toBe(fixtureInstrumentId)
  expect(fixtureHolding.constituent_instrument_id).toBe(amdInstrumentId)
  expect(discoveryRequests).toHaveLength(1)
  expect(identityRequests).toHaveLength(1)
  expect(identityRequests[0]).toMatchObject({
    symbol: 'OIH',
    provider_candidate: { provider: 'test-fixture', symbol: 'OIH', exchange: 'TEST' },
  })
  expect(identityRequests[0]?.request_id).toMatch(/^[0-9a-f-]{36}$/i)

  await expect(page.getByText('No stored snapshot is selected.')).toBeVisible()
  expect(issuerRequests).toHaveLength(0)
  const requestAcquisition = page.getByTestId('etf-request-issuer')
  await requestAcquisition.click()
  await expect(page.getByRole('status').filter({ hasText: 'Issuer holdings request completed. Snapshot dates and current-analysis capability remain separate.' })).toBeVisible()
  expect(issuerRequests).toHaveLength(1)
  expect(issuerRequests[0]).toMatchObject({ refresh: true })
  expect(issuerRequests[0]?.request_id).toMatch(/^[0-9a-f-]{36}$/i)
  await expect(page.getByTestId('etf-snapshot-lineage')).toBeVisible()
  await expect(page.getByTestId('etf-snapshot-known-at')).toHaveAttribute('datetime', fixtureSnapshot.known_at!)
  await expect(page.getByText('Current holdings are not verified.')).toBeVisible()
  await expect(page.locator('.holding-row').filter({ hasText: 'AMD' }).first()).toBeVisible()

  const initialChartCoverageReady = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'GET'
      && url.pathname === '/api/v1/instruments/AMD/data-coverage'
  })
  await page.locator('.holding-row').filter({ hasText: 'AMD' }).first().click()
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
  await page.getByTestId('history-load-missing').click()
  await expect(page.getByRole('status').filter({ hasText: /^Some history loaded;/ })).toBeVisible()
  const localReadback = await localReadbackReady
  const readbackBars = await localReadback.json() as OHLCVBar[]
  expect(historyRequests).toHaveLength(1)
  expectBoundedM1Request(historyRequests[0]!)
  expect(acquiredFixtureBar).not.toBeNull()
  expect(Date.parse(acquiredFixtureBar!.ts)).toBeGreaterThanOrEqual(Date.parse(historyRequests[0]!.start))
  expect(Date.parse(acquiredFixtureBar!.ts)).toBeLessThanOrEqual(Date.parse(historyRequests[0]!.end))
  expect(identityRequests).toHaveLength(2)
  expect(identityRequests[1]).toMatchObject({ symbol: 'AMD' })
  expect(historyRequests[0]).toBeDefined()
  expect(successfulHistoryResponseReceived).toBe(true)
  expect(localReadbackCount).toBeGreaterThan(0)
  expect(readbackBars).toHaveLength(1)
  expect(readbackBars[0]).toMatchObject({ ts: acquiredFixtureBar!.ts, close: acquiredFixtureBar!.close })
  await expect(historicalContext).toBeVisible()
  await browserDiagnostics.expectNoCriticalIssues()
})
