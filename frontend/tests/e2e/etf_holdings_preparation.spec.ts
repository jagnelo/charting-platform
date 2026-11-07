import { test, expect } from './helpers'
import type { ETFHoldingsDate, ETFHoldingsPage, ETFProfile } from '../../src/types'
import type { DataEnsureRequest } from '../../src/lib/dataPreparation'

type EnsureStatus = 'waiting' | 'ready'
type EnsureRequest = DataEnsureRequest
type NormalizedEnsureRequest = {
  symbol: string
  datasets: NonNullable<EnsureRequest['datasets']>
  timeframe?: EnsureRequest['timeframe']
  adjusted?: boolean
}
const ETF_INSTRUMENT_IDS: Record<number, string> = { 701: 'FNEW', 702: 'RACE', 704: 'QQQ', 811: 'BWET' }
const ETF_INSTRUMENT_IDS_BY_SYMBOL: Record<string, number> = { FNEW: 701, RACE: 702, QQQ: 704, BWET: 811 }

function ensureRequestSymbol(request: EnsureRequest): string | null {
  if (request.target.kind !== 'instrument') return null
  if ('symbol' in request.target && typeof request.target.symbol === 'string') return request.target.symbol.toUpperCase()
  if ('instrument_id' in request.target && typeof request.target.instrument_id === 'number') {
    return ETF_INSTRUMENT_IDS[request.target.instrument_id] ?? null
  }
  return null
}

function normalizedEnsureRequest(request: EnsureRequest): NormalizedEnsureRequest | null {
  const symbol = ensureRequestSymbol(request)
  if (!symbol) return null
  return {
    symbol,
    datasets: request.datasets ?? [],
    ...(request.timeframe === undefined ? {} : { timeframe: request.timeframe }),
    ...(request.adjusted === undefined ? {} : { adjusted: request.adjusted }),
  }
}

function ensureResponse(request: EnsureRequest, symbol: string, status: EnsureStatus, requestId = `etf-${symbol.toLowerCase()}`) {
  const now = new Date().toISOString()
  return {
    request_id: requestId,
    status,
    created_at: now,
    updated_at: now,
    version: 1,
    target: request.target,
    dependencies: [{
      dependency_id: `holdings-${symbol.toLowerCase()}`,
      depends_on: [],
      instrument_id: ETF_INSTRUMENT_IDS_BY_SYMBOL[symbol] ?? null,
      symbol,
      dataset: 'holdings',
      status,
      requested_start: null,
      requested_end: null,
      covered_start: null,
      covered_end: null,
      reason_code: status === 'waiting' ? 'provider_quota_wait' : null,
      retry_at: status === 'waiting' ? new Date(Date.now() + 60_000).toISOString() : null,
      updated_at: now,
      covered_ranges: [],
    }],
    completed: status === 'ready' ? 1 : 0,
    total: 1,
    last_progress_at: now,
    has_pending_work: status === 'waiting',
  }
}

function profile(symbol: string, instrumentId: number, profileId: number, snapshotId: number): ETFProfile {
  return {
    id: profileId,
    instrument_id: instrumentId,
    symbol,
    name: `${symbol} Sector Fund`,
    issuer: 'Fixture Issuer',
    fund_family: 'Fixture Sector Funds',
    adapter_status: 'success',
    latest_composition_date: '2026-11-05',
    latest_snapshot_id: snapshotId,
    resolved_count: 1,
    unresolved_count: 0,
    holdings_capability: {
      availability: 'current',
      source_tier: 'issuer_native',
      identity_verified: true,
      usable_for_current_analysis: true,
      displayable_last_known: true,
      consecutive_failures: 0,
      reason: 'Controlled completed fixture.',
      symbol_audit: { tier: 0, outcome: 'not_run', evidence_state: 'fixture', next_action: '', evidence_refs: [] },
    },
  }
}

function fixtureSnapshot(symbol: string, instrumentId: number, profileId: number, snapshotId: number) {
  return {
    id: snapshotId,
    etf_profile_id: profileId,
    etf_instrument_id: instrumentId,
    etf_symbol: symbol,
    etf_name: `${symbol} Sector Fund`,
    composition_date: '2026-11-05',
    as_of_date: '2026-11-05',
    known_at: '2026-11-06T10:15:00Z',
    published_at: null,
    provenance: 'issuer_current_holdings',
    source_provider: 'controlled-fixture',
    source_url: 'https://fixture.invalid/holdings',
    source_identifier: `fixture:${symbol}:2026-11-05`,
    source_quality: 'issuer_current',
    completeness_status: 'complete',
    row_count: 1,
    resolved_count: 1,
    unresolved_count: 0,
    total_weight: '0.25000000',
    parser_version: 'fixture-v1',
    holdings: [],
  }
}

function fixtureHoldings(symbol: string, instrumentId: number, profileId: number, snapshotId: number): ETFHoldingsPage {
  return {
    snapshot: fixtureSnapshot(symbol, instrumentId, profileId, snapshotId),
    holdings: [{
      id: snapshotId * 10,
      snapshot_id: snapshotId,
      constituent_instrument_id: instrumentId + 1000,
      constituent_symbol: `${symbol}1`,
      constituent_name: `${symbol} Example Holding`,
      position: 1,
      reported_symbol: `${symbol}1`,
      reported_name: `${symbol} Example Holding`,
      weight: '0.25000000',
      currency: 'USD',
      country: 'US',
      exchange: 'XNYS',
      holding_type: 'equity',
      row_type: 'security',
      is_resolved: true,
    }],
    total: 1,
    limit: 100,
    offset: 0,
    has_next: false,
  }
}

function overlapFixture() {
  const sourceSnapshot = fixtureSnapshot('FNEW', 701, 71, 901)
  const peerSnapshot = { ...sourceSnapshot, id: 904, etf_instrument_id: 704, etf_profile_id: 74, etf_symbol: 'QQQ', etf_name: 'QQQ Sector Fund' }
  return {
    summary: {
      requested_symbols: ['FNEW', 'QQQ'],
      snapshot_date: '2026-11-05',
      point_in_time: true,
      etf_count: 2,
      pair_count: 1,
      missing: [],
      pairs: [{
        left_symbol: 'FNEW', right_symbol: 'QQQ', left_snapshot: sourceSnapshot, right_snapshot: peerSnapshot,
        left_count: 1, right_count: 1, shared_count: 1, left_unique_count: 0, right_unique_count: 0,
        jaccard_overlap: '1.00000000', shared_weight_left: '0.25000000',
        shared_weight_right: '0.25000000', overlap_weight_min: '0.25000000', top_shared: [],
      }],
    },
    matrix: {
      requested_symbols: ['FNEW', 'QQQ'], snapshot_date: '2026-11-05', point_in_time: true,
      metric: 'jaccard', etf_count: 2, symbols: ['FNEW', 'QQQ'], missing: [],
      highest_overlap_pairs: [], lowest_overlap_pairs: [],
      rows: ['FNEW', 'QQQ'].map(symbol => ({
        symbol, name: `${symbol} Sector Fund`, snapshot: symbol === 'FNEW' ? sourceSnapshot : peerSnapshot,
        average_overlap: '1.00000000', max_overlap: '1.00000000', min_overlap: '1.00000000',
        closest_peer: symbol === 'FNEW' ? 'QQQ' : 'FNEW', most_distinct_peer: null,
        cells: ['FNEW', 'QQQ'].map(column => ({
          row_symbol: symbol, column_symbol: column, value: '1.00000000',
          shared_count: symbol === column ? 0 : 1,
          jaccard_overlap: '1.00000000', overlap_weight_min: symbol === column ? null : '0.25000000',
        })),
      })),
    },
  }
}

function snapshotDates(snapshotId: number): ETFHoldingsDate[] {
  return [{
    snapshot_id: snapshotId,
    composition_date: '2026-11-05',
    as_of_date: '2026-11-05',
    known_at: '2026-11-06T10:15:00Z',
    provenance: 'issuer_current_holdings',
    source_provider: 'controlled-fixture',
    source_identifier: `fixture:${snapshotId}`,
    row_count: 1,
    resolved_count: 1,
    unresolved_count: 0,
    source_quality: 'issuer_current',
  }]
}

async function installETFSearch(page: import('@playwright/test').Page) {
  await page.route('**/api/v1/instruments/search**', async route => {
    const query = new URL(route.request().url()).searchParams.get('q')?.toUpperCase() ?? ''
    await route.fulfill({ status: 200, json: [{
      symbol: query,
      name: `${query} Sector Fund`,
      exchange: 'NYSE Arca',
      type: query === 'BWET' ? 'ETV' : 'ETF',
      instrument_id: query === 'FNEW' ? 701 : query === 'RACE' ? 702 : query === 'BWET' ? 811 : 703,
      identity_status: 'resolved',
    }] })
  })
}

async function selectETF(page: import('@playwright/test').Page, symbol: string) {
  const input = page.getByPlaceholder('Search ETF instrument')
  await input.fill(symbol)
  await page.getByRole('option', { name: new RegExp(`^${symbol}\\b`) }).click()
}

test.describe('ETF holdings preparation', () => {
  test('selecting an uncached ETF automatically requests holdings and displays the returned dated snapshot', async ({ page, loggedIn }) => {
    const selected = profile('FNEW', 701, 71, 901)
    const savedPeer = profile('QQQ', 704, 74, 904)
    const requested: NormalizedEnsureRequest[] = []
    const legacyAcquireRequests: string[] = []
    const holdingsQueries: Array<{ q: string | null; sort: string | null; direction: string | null }> = []
    const overlapRequests: Array<{ path: string; body: Record<string, unknown> }> = []
    page.on('request', request => {
      const path = new URL(request.url()).pathname
      if (/^\/api\/v1\/etf-holdings\/[^/]+\/acquire$/.test(path)) legacyAcquireRequests.push(path)
    })
    await installETFSearch(page)
    await page.route(url => new URL(url).pathname === '/api/v1/etf-holdings', async route => {
      const query = new URL(route.request().url()).searchParams.get('q')?.toUpperCase()
      await route.fulfill({ status: 200, json: query === 'FNEW' ? [selected] : !query ? [savedPeer] : [] })
    })
    await page.route('**/api/v1/data/ensure', async route => {
      const body = route.request().postDataJSON() as EnsureRequest
      const symbol = ensureRequestSymbol(body)
      if (!symbol || !body.datasets?.includes('holdings')) return route.continue()
      expect(route.request().method()).toBe('POST')
      if (body.datasets.length === 1 && body.datasets[0] === 'holdings') {
        requested.push(normalizedEnsureRequest(body)!)
      }
      await route.fulfill({ status: 200, json: ensureResponse(body, symbol, 'ready') })
    })
    await page.route('**/api/v1/etf-holdings/FNEW/dates', route => route.fulfill({ status: 200, json: snapshotDates(901) }))
    await page.route('**/api/v1/etf-holdings/FNEW/holdings**', async route => {
      const query = new URL(route.request().url()).searchParams
      holdingsQueries.push({ q: query.get('q'), sort: query.get('sort'), direction: query.get('direction') })
      await route.fulfill({ status: 200, json: fixtureHoldings('FNEW', 701, 71, 901) })
    })
    await page.route('**/api/v1/etf-holdings/FNEW/weight-evolution**', route => route.fulfill({
      status: 200,
      json: { etf_symbol: 'FNEW', etf_name: 'FNEW Sector Fund', snapshot_count: 1, series: [] },
    }))
    await page.route('**/api/v1/etf-holdings/FNEW/transitions**', route => route.fulfill({
      status: 200,
      json: { etf_symbol: 'FNEW', etf_name: 'FNEW Sector Fund', snapshot_count: 1, transition_count: 0, transitions: [] },
    }))
    await page.route('**/api/v1/etf-holdings/QQQ/dates', route => route.fulfill({ status: 200, json: snapshotDates(904) }))
    await page.route('**/api/v1/etf-holdings/QQQ/holdings**', route => route.fulfill({ status: 200, json: fixtureHoldings('QQQ', 704, 74, 904) }))
    await page.route('**/api/v1/etf-holdings/QQQ/weight-evolution**', route => route.fulfill({
      status: 200,
      json: { etf_symbol: 'QQQ', etf_name: 'QQQ Sector Fund', snapshot_count: 1, series: [] },
    }))
    await page.route('**/api/v1/etf-holdings/QQQ/transitions**', route => route.fulfill({
      status: 200,
      json: { etf_symbol: 'QQQ', etf_name: 'QQQ Sector Fund', snapshot_count: 1, transition_count: 0, transitions: [] },
    }))
    const overlap = overlapFixture()
    await page.route('**/api/v1/etf-holdings/overlap-summary', route => {
      overlapRequests.push({ path: new URL(route.request().url()).pathname, body: route.request().postDataJSON() as Record<string, unknown> })
      return route.fulfill({ status: 200, json: overlap.summary })
    })
    await page.route('**/api/v1/etf-holdings/overlap-matrix', route => {
      overlapRequests.push({ path: new URL(route.request().url()).pathname, body: route.request().postDataJSON() as Record<string, unknown> })
      return route.fulfill({ status: 200, json: overlap.matrix })
    })

    await page.goto('/etf-holdings')
    await expect(page.getByRole('heading', { name: 'QQQ' })).toBeVisible()
    await selectETF(page, 'FNEW')

    await expect(page.getByTestId('etf-preparation-status')).toHaveText('Requested data is ready.')
    await expect(page.locator('.holdings-table')).toContainText('FNEW1')
    await expect(page.getByTestId('etf-snapshot-lineage')).toContainText('controlled-fixture')
    await expect(page.getByTestId('etf-snapshot-source-identifier')).toHaveText('fixture:FNEW:2026-11-05')
    await expect(page.getByTestId('etf-snapshot-source-url')).toHaveText('https://fixture.invalid/holdings')
    await expect(page.getByTestId('etf-snapshot-known-at')).toHaveAttribute('datetime', '2026-11-06T10:15:00Z')
    await expect(page.getByTestId('etf-selected-snapshot-kind')).toHaveText('Latest stored snapshot')
    expect(requested).toEqual([{ symbol: 'FNEW', datasets: ['holdings'] }])
    expect(legacyAcquireRequests).toEqual([])
    await expect(page.getByRole('button', { name: 'Load latest holdings' })).toHaveCount(0)

    const filterRead = page.waitForResponse(response => {
      const url = new URL(response.url())
      return url.pathname === '/api/v1/etf-holdings/FNEW/holdings' && url.searchParams.get('q') === 'FNEW Example'
    })
    await page.getByPlaceholder('Symbol, name, CUSIP, ISIN').fill('FNEW Example')
    expect((await filterRead).ok()).toBeTruthy()
    await page.getByLabel('Sort').selectOption('symbol')
    await expect.poll(() => holdingsQueries.at(-1)?.sort).toBe('symbol')
    await page.getByLabel('Direction').selectOption('asc')
    await expect.poll(() => holdingsQueries.at(-1)?.direction).toBe('asc')
    await page.locator('button.holding-row').filter({ hasText: 'FNEW1' }).click()
    await expect(page.locator('.holding-detail h3')).toHaveText('FNEW1')
    await expect(page.locator('.holding-detail')).toContainText('FNEW Example Holding')
    await expect(page.getByRole('button', { name: 'View history' })).toBeEnabled()
    await page.getByRole('button', { name: 'Compare selected' }).click()
    await expect(page.locator('.overlap-matrix')).toContainText('FNEW')
    await expect(page.locator('.overlap-matrix')).toContainText('QQQ')
    expect(overlapRequests).toHaveLength(2)
    expect(overlapRequests.find(request => request.path.endsWith('/overlap-summary'))?.body).toMatchObject({
      etf_symbols: ['FNEW', 'QQQ'], snapshot_date: '2026-11-05', point_in_time: true,
    })
    expect(overlapRequests.find(request => request.path.endsWith('/overlap-matrix'))?.body).toMatchObject({
      etf_symbols: ['FNEW', 'QQQ'], snapshot_date: '2026-11-05', metric: 'jaccard',
    })
    expect(holdingsQueries).toContainEqual({ q: 'FNEW Example', sort: 'weight', direction: 'desc' })
    expect(holdingsQueries).toContainEqual({ q: 'FNEW Example', sort: 'symbol', direction: 'asc' })

    await page.getByRole('button', { name: 'View history' }).click()
    await expect(page).toHaveURL(/\/chart\/FNEW1\?.*holding_history_intent=selected/)
    const drilldownUrl = new URL(page.url())
    expect(drilldownUrl.searchParams.get('holding_snapshot_id')).toBe('901')
    expect(drilldownUrl.searchParams.get('holding_composition_date')).toBe('2026-11-05')
    expect(drilldownUrl.searchParams.get('holding_known_at')).toBe('2026-11-06T10:15:00Z')
    expect(drilldownUrl.searchParams.get('holding_provenance')).toBe('issuer_current_holdings')
    expect(drilldownUrl.searchParams.get('holding_source_provider')).toBe('controlled-fixture')
    expect(drilldownUrl.searchParams.get('holding_instrument_id')).toBe('1701')
    expect(drilldownUrl.searchParams.get('holding_row_id')).toBe('9010')
    expect(drilldownUrl.searchParams.get('holding_reported_symbol')).toBe('FNEW1')
    expect(drilldownUrl.searchParams.get('holding_type')).toBe('equity')
    expect(loggedIn).toBeUndefined()
  })

  test('rapid fund switching keeps a waiting first preparation from replacing the second fund', async ({ page, loggedIn }) => {
    const second = profile('RACE', 702, 72, 902)
    const requests: NormalizedEnsureRequest[] = []
    await installETFSearch(page)
    await page.route(url => new URL(url).pathname === '/api/v1/etf-holdings', async route => {
      const query = new URL(route.request().url()).searchParams.get('q')?.toUpperCase()
      await route.fulfill({ status: 200, json: query === 'RACE' ? [second] : [] })
    })
    await page.route('**/api/v1/data/ensure', async route => {
      const body = route.request().postDataJSON() as EnsureRequest
      const symbol = ensureRequestSymbol(body)
      if (!symbol || !body.datasets?.includes('holdings')) return route.continue()
      const status = symbol === 'RACE' ? 'ready' : 'waiting'
      if (body.datasets.length === 1 && body.datasets[0] === 'holdings') {
        requests.push(normalizedEnsureRequest(body)!)
      }
      await route.fulfill({ status: 200, json: ensureResponse(body, symbol, status) })
    })
    await page.route('**/api/v1/etf-holdings/RACE/dates', route => route.fulfill({ status: 200, json: snapshotDates(902) }))
    await page.route('**/api/v1/etf-holdings/RACE/holdings**', route => route.fulfill({ status: 200, json: fixtureHoldings('RACE', 702, 72, 902) }))
    await page.route('**/api/v1/etf-holdings/RACE/weight-evolution**', route => route.fulfill({
      status: 200,
      json: { etf_symbol: 'RACE', etf_name: 'RACE Sector Fund', snapshot_count: 1, series: [] },
    }))
    await page.route('**/api/v1/etf-holdings/RACE/transitions**', route => route.fulfill({
      status: 200,
      json: { etf_symbol: 'RACE', etf_name: 'RACE Sector Fund', snapshot_count: 1, transition_count: 0, transitions: [] },
    }))

    await page.goto('/etf-holdings')
    await selectETF(page, 'FNEW')
    await expect(page.getByTestId('etf-preparation-status')).toContainText('request capacity')
    await selectETF(page, 'RACE')

    await expect(page.getByRole('heading', { name: 'RACE' })).toBeVisible()
    await expect(page.locator('.holdings-table')).toContainText('RACE1')
    await expect(page.locator('.holdings-table')).not.toContainText('FNEW1')
    await expect(page.getByTestId('etf-preparation-status')).toHaveText('Requested data is ready.')
    expect(requests).toEqual([
      { symbol: 'FNEW', datasets: ['holdings'] },
      { symbol: 'RACE', datasets: ['holdings'] },
    ])
    expect(loggedIn).toBeUndefined()
  })

  test('BWET preparation keeps reported freight-futures and cash rows visible without charting them', async ({ page, loggedIn }) => {
    const bwetProfile = {
      ...profile('BWET', 811, 81, 911),
      name: 'Breakwave Tanker Shipping ETF',
      issuer: 'Amplify',
      fund_family: 'Amplify ETFs',
      resolved_count: 0,
      unresolved_count: 0,
    }
    const bwetSnapshot = {
      ...fixtureSnapshot('BWET', 811, 81, 911),
      etf_name: 'Breakwave Tanker Shipping ETF',
      composition_date: '2026-11-06',
      as_of_date: '2026-11-06',
      known_at: '2026-11-06T15:00:00Z',
      source_provider: 'amplify',
      source_identifier: 'amplify:bwet:account-1:2026-11-06',
      source_url: 'https://fixture.invalid/amplify/bwet',
      provenance: 'issuer_current_holdings',
      row_count: 2,
      resolved_count: 0,
      unresolved_count: 0,
      total_weight: '-0.07500000',
    }
    const rows: ETFHoldingsPage['holdings'] = [
      {
        id: 9111,
        snapshot_id: 911,
        constituent_instrument_id: null,
        constituent_symbol: null,
        constituent_name: null,
        position: 1,
        reported_symbol: 'C5TCM',
        reported_name: 'Freight futures exposure',
        weight: '-0.12500000',
        shares: '-3',
        market_value: '-125000',
        currency: 'USD',
        holding_type: 'future',
        row_type: 'derivative',
        is_resolved: false,
      },
      {
        id: 9112,
        snapshot_id: 911,
        constituent_instrument_id: null,
        constituent_symbol: null,
        constituent_name: null,
        position: 2,
        reported_symbol: 'USD',
        reported_name: 'Cash',
        weight: '0.05000000',
        shares: '50000',
        market_value: '50000',
        currency: 'USD',
        holding_type: 'cash',
        row_type: 'security',
        is_resolved: false,
      },
    ]
    const holdingsPage: ETFHoldingsPage = {
      snapshot: { ...bwetSnapshot, holdings: rows },
      holdings: rows,
      total: rows.length,
      limit: 100,
      offset: 0,
      has_next: false,
    }
    const ensureRequests: NormalizedEnsureRequest[] = []

    await installETFSearch(page)
    await page.route(url => new URL(url).pathname === '/api/v1/etf-holdings', async route => {
      const query = new URL(route.request().url()).searchParams.get('q')?.toUpperCase()
      await route.fulfill({ status: 200, json: query === 'BWET' ? [bwetProfile] : [] })
    })
    await page.route('**/api/v1/data/ensure', async route => {
      const body = route.request().postDataJSON() as EnsureRequest
      const symbol = ensureRequestSymbol(body)
      if (symbol !== 'BWET' || !body.datasets?.includes('holdings')) return route.continue()
      ensureRequests.push(normalizedEnsureRequest(body)!)
      await route.fulfill({ status: 200, json: ensureResponse(body, symbol, 'ready') })
    })
    await page.route('**/api/v1/etf-holdings/BWET/dates', route => route.fulfill({
      status: 200,
      json: [{
        snapshot_id: 911,
        composition_date: '2026-11-06',
        as_of_date: '2026-11-06',
        known_at: '2026-11-06T15:00:00Z',
        provenance: 'issuer_current_holdings',
        source_provider: 'amplify',
        source_identifier: 'amplify:bwet:account-1:2026-11-06',
        row_count: 2,
        resolved_count: 0,
        unresolved_count: 0,
        source_quality: 'issuer_current',
      }],
    }))
    await page.route('**/api/v1/etf-holdings/BWET/holdings**', route => route.fulfill({
      status: 200,
      json: holdingsPage,
    }))
    await page.route('**/api/v1/etf-holdings/BWET/weight-evolution', route => route.fulfill({
      status: 200,
      json: { etf_symbol: 'BWET', etf_name: 'Breakwave Tanker Shipping ETF', snapshot_count: 1, series: [] },
    }))
    await page.route('**/api/v1/etf-holdings/BWET/transitions', route => route.fulfill({
      status: 200,
      json: { etf_symbol: 'BWET', etf_name: 'Breakwave Tanker Shipping ETF', snapshot_count: 1, transition_count: 0, transitions: [] },
    }))

    await page.goto('/etf-holdings')
    await selectETF(page, 'BWET')
    await expect(page.getByTestId('etf-preparation-status')).toHaveText('Requested data is ready.')
    await expect(page.getByRole('heading', { name: 'BWET' })).toBeVisible()
    await expect(page.locator('.snapshot-date-line')).toContainText('Breakwave Tanker Shipping ETF')
    await expect(page.getByTestId('etf-snapshot-lineage')).toContainText('amplify')
    await expect(page.locator('.holdings-table')).toContainText('C5TCM')
    await expect(page.locator('.holdings-table')).toContainText('Freight futures exposure')
    await expect(page.locator('.holdings-table')).toContainText('USD')
    await expect(page.locator('.holdings-table')).toContainText('-12.50%')
    await expect(page.locator('.holdings-table')).toContainText('5.00%')

    await page.locator('button.holding-row').filter({ hasText: 'C5TCM' }).click()
    await expect(page.locator('.holding-detail h3')).toHaveText('C5TCM')
    await expect(page.locator('.holding-detail')).toContainText('reference')
    await expect(page.getByRole('button', { name: 'View history' })).toBeDisabled()
    expect(ensureRequests).toEqual([
      {
        symbol: 'BWET',
        datasets: ['identity', 'profile', 'history', 'holdings'],
        timeframe: 'D1',
        adjusted: true,
      },
      {
        symbol: 'BWET',
        datasets: ['identity', 'profile', 'history', 'holdings'],
        timeframe: 'D1',
        adjusted: true,
      },
      { symbol: 'BWET', datasets: ['holdings'] },
    ])
    await expect(page).toHaveURL(/\/etf-holdings$/)
    expect(loggedIn).toBeUndefined()
  })

  test('choosing an older snapshot shows that snapshot’s own date, known-at and source lineage', async ({ page, loggedIn }) => {
    const igvProfile = {
      ...profile('IGV', 820, 82, 912),
      name: 'iShares Expanded Tech Software Sector ETF',
      issuer: 'iShares',
      fund_family: 'iShares U.S. ETFs',
      latest_composition_date: '2026-11-05',
    }
    const dates: ETFHoldingsDate[] = [
      {
        snapshot_id: 912,
        composition_date: '2026-11-05',
        as_of_date: '2026-11-05',
        known_at: '2026-11-06T16:00:00Z',
        published_at: '2026-11-06T15:30:00Z',
        provenance: 'issuer_current_holdings',
        source_provider: 'ishares',
        source_identifier: 'ishares:239771:2026-11-05',
        row_count: 1,
        resolved_count: 1,
        unresolved_count: 0,
        source_quality: 'issuer_current',
      },
      {
        snapshot_id: 911,
        composition_date: '2026-10-15',
        as_of_date: '2026-10-15',
        known_at: '2026-10-16T09:20:00Z',
        published_at: '2026-10-16T08:00:00Z',
        provenance: 'issuer_historical_snapshot',
        source_provider: 'ishares',
        source_identifier: 'ishares:239771:2026-10-15',
        row_count: 1,
        resolved_count: 1,
        unresolved_count: 0,
        source_quality: 'issuer_historical',
      },
    ]
    const requests: Array<{ snapshotId: string | null; sort: string | null }> = []
    await page.route(url => new URL(url).pathname === '/api/v1/etf-holdings', async route => {
      await route.fulfill({ status: 200, json: [igvProfile] })
    })
    await page.route('**/api/v1/etf-holdings/IGV/dates', route => route.fulfill({ status: 200, json: dates }))
    await page.route('**/api/v1/etf-holdings/IGV/holdings**', async route => {
      const query = new URL(route.request().url()).searchParams
      const snapshotId = query.get('snapshot_id') ?? '912'
      requests.push({ snapshotId: query.get('snapshot_id'), sort: query.get('sort') })
      const historical = snapshotId === '911'
      const snapshotDate = historical ? dates[1] : dates[0]
      const base = fixtureHoldings('IGV', 820, 82, Number(snapshotId))
      const row = {
        ...base.holdings[0],
        id: Number(snapshotId) * 10,
        snapshot_id: Number(snapshotId),
        reported_symbol: historical ? 'ACME' : 'MSFT',
        constituent_symbol: historical ? 'ACME' : 'MSFT',
        reported_name: historical ? 'Historical Example Corp' : 'Current Example Corp',
        constituent_name: historical ? 'Historical Example Corp' : 'Current Example Corp',
      }
      await route.fulfill({
        status: 200,
        json: {
          ...base,
          snapshot: {
            ...base.snapshot,
            id: Number(snapshotId),
            composition_date: snapshotDate.composition_date,
            as_of_date: snapshotDate.as_of_date,
            known_at: snapshotDate.known_at,
            published_at: snapshotDate.published_at,
            provenance: snapshotDate.provenance,
            source_provider: snapshotDate.source_provider,
            source_identifier: snapshotDate.source_identifier,
            source_url: historical
              ? 'https://fixture.invalid/ishares/239771?date=2026-10-15'
              : 'https://fixture.invalid/ishares/239771?date=2026-11-05',
            source_quality: snapshotDate.source_quality,
            holdings: [row],
          },
          holdings: [row],
        },
      })
    })
    await page.route('**/api/v1/etf-holdings/IGV/weight-evolution', route => route.fulfill({
      status: 200,
      json: { etf_symbol: 'IGV', etf_name: igvProfile.name, snapshot_count: 2, series: [] },
    }))
    await page.route('**/api/v1/etf-holdings/IGV/transitions', route => route.fulfill({
      status: 200,
      json: { etf_symbol: 'IGV', etf_name: igvProfile.name, snapshot_count: 2, transition_count: 1, transitions: [] },
    }))

    await page.goto('/etf-holdings')
    await expect(page.getByRole('heading', { name: 'IGV' })).toBeVisible()
    await expect(page.getByTestId('etf-selected-snapshot-kind')).toHaveText('Latest stored snapshot')
    await expect(page.getByTestId('etf-snapshot-known-at')).toHaveAttribute('datetime', '2026-11-06T16:00:00Z')

    const historicalRequest = page.waitForResponse(response => {
      const url = new URL(response.url())
      return url.pathname === '/api/v1/etf-holdings/IGV/holdings'
        && url.searchParams.get('snapshot_id') === '911'
    })
    await page.getByLabel('Snapshot').selectOption('911')
    expect((await historicalRequest).ok()).toBeTruthy()
    await expect(page.getByTestId('etf-selected-snapshot-kind')).toHaveText('Historical snapshot')
    await expect(page.locator('.snapshot-date-line')).toContainText('2026-10-15')
    await expect(page.locator('.snapshot-date-line')).toContainText('Historical snapshot')
    await expect(page.getByTestId('etf-snapshot-known-at')).toHaveAttribute('datetime', '2026-10-16T09:20:00Z')
    await expect(page.getByTestId('etf-snapshot-published-at')).toHaveAttribute('datetime', '2026-10-16T08:00:00Z')
    await expect(page.getByTestId('etf-snapshot-lineage')).toContainText('ishares:239771:2026-10-15')
    await expect(page.getByTestId('etf-snapshot-source-url')).toHaveText('https://fixture.invalid/ishares/239771?date=2026-10-15')
    await expect(page.locator('.holdings-table')).toContainText('ACME')
    expect(requests.some(request => request.snapshotId === '911')).toBeTruthy()
    expect(loggedIn).toBeUndefined()
  })
})
