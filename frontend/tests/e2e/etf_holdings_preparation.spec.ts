import { test, expect } from './helpers'
import type { ETFHoldingsDate, ETFHoldingsPage, ETFProfile } from '../../src/types'

type EnsureStatus = 'waiting' | 'ready'
type EnsureRequest = { target: { kind: 'instrument'; symbol: string }; datasets: ['holdings'] }

function ensureResponse(symbol: string, status: EnsureStatus, requestId = `etf-${symbol.toLowerCase()}`) {
  const now = new Date().toISOString()
  return {
    request_id: requestId,
    status,
    created_at: now,
    updated_at: now,
    version: 1,
    target: { kind: 'instrument', symbol },
    dependencies: [{
      dependency_id: `holdings-${symbol.toLowerCase()}`,
      depends_on: [],
      instrument_id: null,
      dataset: 'holdings',
      status,
      requested_start: null,
      requested_end: null,
      covered_start: null,
      covered_end: null,
      reason_code: status === 'waiting' ? 'provider_quota_wait' : null,
      retry_at: status === 'waiting' ? new Date(Date.now() + 60_000).toISOString() : null,
      updated_at: now,
    }],
    completed: status === 'ready' ? 1 : 0,
    total: 1,
    last_progress_at: now,
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
      type: 'ETF',
      instrument_id: query === 'FNEW' ? 701 : query === 'RACE' ? 702 : 703,
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
    const requested: EnsureRequest[] = []
    const legacyAcquireRequests: string[] = []
    page.on('request', request => {
      const path = new URL(request.url()).pathname
      if (/^\/api\/v1\/etf-holdings\/[^/]+\/acquire$/.test(path)) legacyAcquireRequests.push(path)
    })
    await installETFSearch(page)
    await page.route(url => new URL(url).pathname === '/api/v1/etf-holdings', async route => {
      const query = new URL(route.request().url()).searchParams.get('q')?.toUpperCase()
      await route.fulfill({ status: 200, json: query === 'FNEW' ? [selected] : [] })
    })
    await page.route('**/api/v1/data/ensure', async route => {
      expect(route.request().method()).toBe('POST')
      const body = route.request().postDataJSON() as EnsureRequest
      requested.push(body)
      await route.fulfill({ status: 200, json: ensureResponse('FNEW', 'ready') })
    })
    await page.route('**/api/v1/etf-holdings/FNEW/dates', route => route.fulfill({ status: 200, json: snapshotDates(901) }))
    await page.route('**/api/v1/etf-holdings/FNEW/holdings**', route => route.fulfill({ status: 200, json: fixtureHoldings('FNEW', 701, 71, 901) }))
    await page.route('**/api/v1/etf-holdings/FNEW/weight-evolution**', route => route.fulfill({
      status: 200,
      json: { etf_symbol: 'FNEW', etf_name: 'FNEW Sector Fund', snapshot_count: 1, series: [] },
    }))
    await page.route('**/api/v1/etf-holdings/FNEW/transitions**', route => route.fulfill({
      status: 200,
      json: { etf_symbol: 'FNEW', etf_name: 'FNEW Sector Fund', snapshot_count: 1, transition_count: 0, transitions: [] },
    }))

    await page.goto('/etf-holdings')
    await selectETF(page, 'FNEW')

    await expect(page.getByTestId('etf-preparation-status')).toHaveText('Requested data is ready.')
    await expect(page.locator('.holdings-table')).toContainText('FNEW1')
    await expect(page.getByTestId('etf-snapshot-lineage')).toContainText('controlled-fixture')
    await expect(page.getByTestId('etf-snapshot-known-at')).toHaveAttribute('datetime', '2026-11-06T10:15:00Z')
    await expect(page.getByTestId('etf-selected-snapshot-kind')).toHaveText('Latest stored snapshot')
    expect(requested).toEqual([{ target: { kind: 'instrument', symbol: 'FNEW' }, datasets: ['holdings'] }])
    expect(legacyAcquireRequests).toEqual([])
    await expect(page.getByRole('button', { name: 'Load latest holdings' })).toHaveCount(0)
    expect(loggedIn).toBeUndefined()
  })

  test('rapid fund switching keeps a waiting first preparation from replacing the second fund', async ({ page, loggedIn }) => {
    const second = profile('RACE', 702, 72, 902)
    const requests: EnsureRequest[] = []
    await installETFSearch(page)
    await page.route(url => new URL(url).pathname === '/api/v1/etf-holdings', async route => {
      const query = new URL(route.request().url()).searchParams.get('q')?.toUpperCase()
      await route.fulfill({ status: 200, json: query === 'RACE' ? [second] : [] })
    })
    await page.route('**/api/v1/data/ensure', async route => {
      const body = route.request().postDataJSON() as EnsureRequest
      requests.push(body)
      const status = body.target.symbol === 'RACE' ? 'ready' : 'waiting'
      await route.fulfill({ status: 200, json: ensureResponse(body.target.symbol, status) })
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
      { target: { kind: 'instrument', symbol: 'FNEW' }, datasets: ['holdings'] },
      { target: { kind: 'instrument', symbol: 'RACE' }, datasets: ['holdings'] },
    ])
    expect(loggedIn).toBeUndefined()
  })
})
