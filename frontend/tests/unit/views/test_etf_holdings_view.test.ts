import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ETFHoldingsView from '@/views/ETFHoldingsView.vue'
import {
  createETFHoldingDrilldownContext,
  holdingDrilldownRouteQuery,
  holdingDrilldownRouteState,
  type ETFHoldingDrilldownContext,
} from '@/lib/etfHoldingDrilldown'

const routerPush = vi.fn()

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPush }),
}))

vi.mock('@/components/common/SearchBar.vue', () => ({
  default: {
    name: 'SearchBar',
    props: ['modelValue', 'placeholder', 'resultTypes', 'allowExpressions', 'allowSourceDiscovery'],
    emits: ['select', 'update:modelValue'],
    template: `
      <div class="mock-search-bar">
        <input
          :value="modelValue"
          :placeholder="placeholder"
          @input="$emit('update:modelValue', $event.target.value)"
        />
        <button type="button" @click="$emit('select', modelValue || 'SPY')">Select</button>
      </div>
    `,
  },
}))

import { api } from '@/lib/api'

async function flushPromises() {
  await Promise.resolve()
  await Promise.resolve()
  await nextTick()
}

const profile = {
  id: 1,
  instrument_id: 10,
  symbol: 'SPY',
  name: 'SPDR S&P 500 ETF Trust',
  issuer: 'State Street',
  fund_family: 'SPDR',
  adapter_status: 'success',
  latest_composition_date: '2026-06-07',
  latest_snapshot_id: 55,
  resolved_count: 2,
  unresolved_count: 0,
  holdings_capability: {
    availability: 'current',
    source_tier: 'issuer_native',
    identity_verified: true,
    usable_for_current_analysis: true,
    displayable_last_known: true,
    consecutive_failures: 0,
    last_canary_at: '2026-09-05T10:00:00Z',
    last_canary_status: 'success',
    last_canary_latency_ms: 148.25,
    last_canary_recovered: true,
    circuit_state: 'closed',
    reason: 'A complete holdings snapshot passed the latest adapter check.',
  },
}

const overlapProfile = {
  id: 2,
  instrument_id: 11,
  symbol: 'QQQ',
  name: 'Invesco QQQ Trust',
  adapter_status: 'success',
  latest_composition_date: '2026-06-07',
  latest_snapshot_id: 77,
  resolved_count: 2,
  unresolved_count: 0,
  holdings_capability: {
    availability: 'current',
    source_tier: 'issuer_native',
    identity_verified: true,
    usable_for_current_analysis: true,
    displayable_last_known: true,
    consecutive_failures: 0,
    reason: 'A complete holdings snapshot passed the latest adapter check.',
  },
}

const dates = [
  {
    snapshot_id: 55,
    composition_date: '2026-06-07',
    as_of_date: '2026-06-07',
    known_at: '2026-06-07T04:00:00Z',
    provenance: 'issuer_current_holdings',
    source_provider: 'issuer-test',
    row_count: 2,
    resolved_count: 2,
    unresolved_count: 0,
    source_quality: 'issuer_current',
  },
  {
    snapshot_id: 54,
    composition_date: '2026-06-06',
    as_of_date: '2026-06-06',
    known_at: '2026-06-06T04:00:00Z',
    provenance: 'issuer_current_holdings',
    source_provider: 'issuer-test',
    row_count: 2,
    resolved_count: 2,
    unresolved_count: 0,
    source_quality: 'issuer_current',
  },
]

function holdingsPage(overrides: Record<string, unknown> = {}) {
  return {
    snapshot: {
      id: 55,
      etf_profile_id: 1,
      etf_instrument_id: 10,
      etf_symbol: 'SPY',
      etf_name: 'SPDR S&P 500 ETF Trust',
      composition_date: '2026-06-07',
      known_at: '2026-06-07T04:15:00Z',
      published_at: null,
      provenance: 'issuer_current_holdings',
      source_provider: 'issuer-test',
      source_identifier: 'issuer-test:SPY:2026-06-07',
      source_url: 'https://issuer.example.test/holdings/spy',
      source_quality: 'issuer_current',
      completeness_status: 'complete',
      row_count: 2,
      resolved_count: 2,
      unresolved_count: 0,
      total_weight: '0.12000000',
      parser_version: 'test-v1',
      holdings: [],
    },
    holdings: [
      {
        id: 100,
        snapshot_id: 55,
        constituent_instrument_id: 200,
        constituent_symbol: 'MSFT',
        constituent_name: 'Microsoft Corp',
        position: 1,
        reported_symbol: 'MSFT',
        reported_name: 'Microsoft Corp',
        cusip: '594918104',
        weight: '0.07000000',
        shares: '10',
        market_value: '4000',
        currency: 'USD',
        country: 'US',
        exchange: 'NASDAQ',
        holding_type: 'equity',
        row_type: 'security',
        is_resolved: true,
      },
    ],
    total: 2,
    limit: 100,
    offset: 0,
    has_next: true,
    ...overrides,
  }
}

function preparationResponse(symbol: string, status: 'ready' | 'unavailable' = 'ready') {
  const now = '2026-11-06T12:00:00Z'
  const instrumentIds: Record<string, number> = { EVOL: 991, SPY: 10, XLE: 30, XLF: 40 }
  return {
    request_id: `prepare-${symbol.toLowerCase()}`,
    status,
    created_at: now,
    updated_at: now,
    version: 1,
    target: { kind: 'instrument', symbol },
    dependencies: [{
      dependency_id: `dep-${symbol.toLowerCase()}`,
      depends_on: [],
      instrument_id: instrumentIds[symbol] ?? null,
      symbol,
      dataset: 'holdings',
      status,
      requested_start: null,
      requested_end: null,
      covered_start: null,
      covered_end: null,
      reason_code: status === 'unavailable' ? 'no_eligible_provider_data' : null,
      retry_at: null,
      updated_at: now,
      covered_ranges: [],
    }],
    completed: 1,
    total: 1,
    last_progress_at: now,
    has_pending_work: false,
  }
}

function diffPayload() {
  return {
    left_snapshot: {
      id: 54,
      etf_profile_id: 1,
      etf_instrument_id: 10,
      etf_symbol: 'SPY',
      etf_name: 'SPDR S&P 500 ETF Trust',
      composition_date: '2026-06-06',
      provenance: 'issuer_current_holdings',
      source_provider: 'issuer-test',
      source_quality: 'issuer_current',
      completeness_status: 'complete',
      row_count: 2,
      resolved_count: 2,
      unresolved_count: 0,
      total_weight: '0.12000000',
      parser_version: 'test-v1',
      holdings: [],
    },
    right_snapshot: {
      id: 55,
      etf_profile_id: 1,
      etf_instrument_id: 10,
      etf_symbol: 'SPY',
      etf_name: 'SPDR S&P 500 ETF Trust',
      composition_date: '2026-06-07',
      provenance: 'issuer_current_holdings',
      source_provider: 'issuer-test',
      source_quality: 'issuer_current',
      completeness_status: 'complete',
      row_count: 2,
      resolved_count: 2,
      unresolved_count: 0,
      total_weight: '0.12000000',
      parser_version: 'test-v1',
      holdings: [],
    },
    total_rows: 2,
    added: 1,
    removed: 0,
    changed: 1,
    unchanged: 0,
    summary: {
      gross_weight_churn: '0.02000000',
      total_added_weight: '0.02000000',
      total_removed_weight: '0',
      total_increased_weight: '0.02000000',
      total_decreased_weight: '0',
      largest_additions: [
        {
          key: 'NVDA',
          symbol: 'NVDA',
          name: 'NVIDIA Corp',
          status: 'added',
          weight_after: '0.02000000',
        },
      ],
      largest_removals: [],
      largest_reweights: [
        {
          key: 'MSFT',
          symbol: 'MSFT',
          name: 'Microsoft Corp',
          status: 'changed',
          weight_before: '0.05000000',
          weight_after: '0.07000000',
          weight_delta: '0.02000000',
        },
      ],
    },
    rows: [
      {
        key: 'NVDA',
        symbol: 'NVDA',
        name: 'NVIDIA Corp',
        status: 'added',
        weight_after: '0.02000000',
      },
      {
        key: 'MSFT',
        symbol: 'MSFT',
        name: 'Microsoft Corp',
        status: 'changed',
        weight_before: '0.05000000',
        weight_after: '0.07000000',
        weight_delta: '0.02000000',
      },
    ],
  }
}

function weightEvolutionPayload() {
  return {
    etf_symbol: 'SPY',
    etf_name: 'SPDR S&P 500 ETF Trust',
    snapshot_count: 2,
    from_date: '2026-06-06',
    to_date: '2026-06-07',
    series: [
      {
        key: 'MSFT',
        symbol: 'MSFT',
        name: 'Microsoft Corp',
        first_weight: '0.05000000',
        last_weight: '0.07000000',
        weight_delta: '0.02000000',
        min_weight: '0.05000000',
        max_weight: '0.07000000',
        observation_count: 2,
        points: [
          { snapshot_id: 54, composition_date: '2026-06-06', weight: '0.05000000' },
          { snapshot_id: 55, composition_date: '2026-06-07', weight: '0.07000000' },
        ],
      },
    ],
  }
}

function transitionTimelinePayload() {
  return {
    etf_symbol: 'SPY',
    etf_name: 'SPDR S&P 500 ETF Trust',
    snapshot_count: 2,
    transition_count: 1,
    from_date: '2026-06-06',
    to_date: '2026-06-07',
    transitions: [
      {
        left_snapshot: diffPayload().left_snapshot,
        right_snapshot: diffPayload().right_snapshot,
        added: 1,
        removed: 0,
        changed: 1,
        unchanged: 0,
        gross_weight_churn: '0.02000000',
        total_added_weight: '0.02000000',
        total_removed_weight: '0',
        total_increased_weight: '0.02000000',
        total_decreased_weight: '0',
        largest_additions: diffPayload().summary.largest_additions,
        largest_removals: [],
        largest_reweights: diffPayload().summary.largest_reweights,
      },
    ],
  }
}

function overlapSummaryPayload() {
  return {
    requested_symbols: ['SPY', 'QQQ'],
    snapshot_date: '2026-06-07',
    point_in_time: true,
    etf_count: 2,
    pair_count: 1,
    missing: [],
    pairs: [
      {
        left_symbol: 'SPY',
        right_symbol: 'QQQ',
        left_snapshot: holdingsPage().snapshot,
        right_snapshot: {
          ...holdingsPage().snapshot,
          id: 77,
          etf_symbol: 'QQQ',
          etf_name: 'Invesco QQQ Trust',
        },
        left_count: 3,
        right_count: 3,
        shared_count: 2,
        left_unique_count: 1,
        right_unique_count: 1,
        jaccard_overlap: '0.50000000',
        shared_weight_left: '0.13000000',
        shared_weight_right: '0.21000000',
        overlap_weight_min: '0.13000000',
        top_shared: [
          {
            key: 'MSFT',
            symbol: 'MSFT',
            name: 'Microsoft Corp',
            weight_left: '0.07000000',
            weight_right: '0.09000000',
            min_weight: '0.07000000',
          },
        ],
      },
    ],
  }
}

function overlapMatrixPayload() {
  return {
    requested_symbols: ['SPY', 'QQQ'],
    snapshot_date: '2026-06-07',
    point_in_time: true,
    metric: 'jaccard',
    etf_count: 2,
    symbols: ['SPY', 'QQQ'],
    missing: [],
    highest_overlap_pairs: overlapSummaryPayload().pairs,
    lowest_overlap_pairs: overlapSummaryPayload().pairs,
    rows: [
      {
        symbol: 'SPY',
        name: 'SPDR S&P 500 ETF Trust',
        snapshot: holdingsPage().snapshot,
        average_overlap: '0.50000000',
        max_overlap: '0.50000000',
        min_overlap: '0.50000000',
        closest_peer: 'QQQ',
        most_distinct_peer: 'QQQ',
        cells: [
          {
            row_symbol: 'SPY',
            column_symbol: 'SPY',
            value: '1',
            shared_count: 0,
            jaccard_overlap: '1',
            overlap_weight_min: null,
          },
          {
            row_symbol: 'SPY',
            column_symbol: 'QQQ',
            value: '0.50000000',
            shared_count: 2,
            jaccard_overlap: '0.50000000',
            overlap_weight_min: '0.13000000',
          },
        ],
      },
      {
        symbol: 'QQQ',
        name: 'Invesco QQQ Trust',
        snapshot: {
          ...holdingsPage().snapshot,
          id: 77,
          etf_symbol: 'QQQ',
          etf_name: 'Invesco QQQ Trust',
        },
        average_overlap: '0.50000000',
        max_overlap: '0.50000000',
        min_overlap: '0.50000000',
        closest_peer: 'SPY',
        most_distinct_peer: 'SPY',
        cells: [
          {
            row_symbol: 'QQQ',
            column_symbol: 'SPY',
            value: '0.50000000',
            shared_count: 2,
            jaccard_overlap: '0.50000000',
            overlap_weight_min: '0.13000000',
          },
          {
            row_symbol: 'QQQ',
            column_symbol: 'QQQ',
            value: '1',
            shared_count: 0,
            jaccard_overlap: '1',
            overlap_weight_min: null,
          },
        ],
      },
    ],
  }
}

describe('ETFHoldingsView', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
    vi.mocked(api.post).mockReset()
    routerPush.mockReset()
  })

  it('loads ETF profiles, browses a paged holdings result, and opens a constituent chart', async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce([profile, overlapProfile])
      .mockResolvedValueOnce(dates)
      .mockResolvedValueOnce(holdingsPage())
      .mockResolvedValueOnce(diffPayload())
      .mockResolvedValueOnce(weightEvolutionPayload())
      .mockResolvedValueOnce(transitionTimelinePayload())
      .mockResolvedValueOnce(holdingsPage({
        holdings: [],
        offset: 100,
        has_next: false,
      }))
    vi.mocked(api.post)
      .mockResolvedValueOnce(overlapSummaryPayload())
      .mockResolvedValueOnce(overlapMatrixPayload())
      .mockResolvedValueOnce(overlapMatrixPayload())

    const wrapper = mount(ETFHoldingsView)
    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('MSFT')
    })

    expect(api.get).toHaveBeenNthCalledWith(1, '/etf-holdings', { q: undefined })
    expect(api.get).toHaveBeenNthCalledWith(2, '/etf-holdings/SPY/dates')
    expect(api.get).toHaveBeenNthCalledWith(3, '/etf-holdings/SPY/holdings', {
      snapshot_id: '55',
      q: undefined,
      sort: 'weight',
      direction: 'desc',
      limit: 100,
      offset: 0,
    })
    expect(wrapper.get('[data-testid="etf-selected-snapshot-kind"]').text()).toBe('Latest stored snapshot')
    expect(wrapper.get('[data-testid="etf-snapshot-lineage"]').text()).toContain('issuer current holdings')
    expect(wrapper.get('[data-testid="etf-snapshot-source-provider"]').text()).toBe('issuer-test')
    expect(wrapper.get('[data-testid="etf-snapshot-source-identifier"]').text())
      .toBe('issuer-test:SPY:2026-06-07')
    expect(wrapper.get('[data-testid="etf-snapshot-source-url"]').text())
      .toBe('https://issuer.example.test/holdings/spy')
    expect(wrapper.get('[data-testid="etf-snapshot-known-at"]').attributes('datetime'))
      .toBe('2026-06-07T04:15:00Z')
    expect(wrapper.get('[data-testid="etf-snapshot-lineage"]').text()).toContain('Source-reported publication')
    expect(wrapper.get('[data-testid="etf-snapshot-lineage"]').text()).toContain('Not established')
    expect(wrapper.find('.panel-meta').text()).toContain('Profile current eligibility: current')
    expect(api.get).toHaveBeenNthCalledWith(4, '/etf-holdings/SPY/diff', {
      left_snapshot_id: '54',
      right_snapshot_id: '55',
    })
    expect(api.get).toHaveBeenNthCalledWith(5, '/etf-holdings/SPY/weight-evolution', {
      limit: 8,
    })
    expect(api.get).toHaveBeenNthCalledWith(6, '/etf-holdings/SPY/transitions', {
      limit: 8,
    })
    expect(wrapper.text()).toContain('Snapshot changes')
    expect(wrapper.text()).toContain('1 added')
    expect(wrapper.text()).toContain('1 changed')
    expect(wrapper.text()).toContain('Gross churn')
    expect(wrapper.text()).not.toContain('Same-date parser correction audit')
    expect(wrapper.text()).toContain('2.00%')
    expect(wrapper.text()).toContain('Largest additions')
    expect(wrapper.text()).toContain('Largest reweights')
    expect(wrapper.text()).toContain('Weight evolution')
    expect(wrapper.text()).toContain('2 snapshots')
    expect(wrapper.text()).toContain('1 mover')
    expect(wrapper.text()).toContain('Turnover timeline')
    expect(wrapper.text()).toContain('1 transitions')
    expect(wrapper.text()).toContain('2.00% churn')
    expect(wrapper.text()).toContain('ETF overlap')
    expect(wrapper.text()).toContain('QQQ')
    expect(wrapper.text()).toContain('NVDA')
    expect(wrapper.text()).toContain('+2.00%')
    expect(wrapper.text()).toContain('USD 4,000')
    expect(wrapper.text()).toContain('NASDAQ · US')
    expect(wrapper.get('[data-testid="etf-view-capability-health"]').text()).toContain('Canary success')
    expect(wrapper.text()).toContain('148.25 ms')
    expect(wrapper.text()).toContain('Failures 0')
    expect(wrapper.text()).toContain('Recovered')
    expect(wrapper.text()).toContain('Circuit closed')

    await wrapper.find('.detail-title button').trigger('click')
    const selectedContext = createETFHoldingDrilldownContext(
      holdingsPage().snapshot,
      holdingsPage().holdings[0]!,
      200,
      'MSFT',
    )
    expect(routerPush).toHaveBeenCalledWith({
      path: '/chart/MSFT',
      query: { ...holdingDrilldownRouteQuery(selectedContext), holding_history_intent: 'selected' },
      state: holdingDrilldownRouteState(selectedContext),
    })

    await wrapper.find('.research-action').trigger('click')
    await flushPromises()

    expect(api.post).toHaveBeenCalledWith('/etf-holdings/overlap-summary', {
      etf_symbols: ['SPY', 'QQQ'],
      snapshot_date: '2026-06-07',
      point_in_time: true,
      top_n: 5,
    })
    expect(api.post).toHaveBeenCalledWith('/etf-holdings/overlap-matrix', {
      etf_symbols: ['SPY', 'QQQ'],
      snapshot_date: '2026-06-07',
      point_in_time: true,
      top_n: 5,
      metric: 'jaccard',
    })
    expect(wrapper.text()).toContain('Overlap matrix')
    expect(wrapper.text()).toContain('2 ETFs · Jaccard overlap')
    expect(wrapper.text()).toContain('closest QQQ')
    expect(wrapper.text()).toContain('50.0% overlap')
    expect(wrapper.text()).toContain('2 shared')
    expect(wrapper.text()).toContain('13.00% min weight')

    await wrapper.find('.research-action--ghost').trigger('click')
    await flushPromises()

    expect(api.post).toHaveBeenCalledWith('/etf-holdings/overlap-matrix', {
      etf_symbols: ['SPY'],
      snapshot_date: '2026-06-07',
      point_in_time: true,
      top_n: 5,
      metric: 'jaccard',
      issuer: 'State Street',
      fund_family: 'SPDR',
      q: undefined,
      limit: 25,
    })

    await wrapper.find('.pager button:last-child').trigger('click')
    await flushPromises()

    expect(api.get).toHaveBeenLastCalledWith('/etf-holdings/SPY/holdings', {
      q: undefined,
      snapshot_id: '55',
      sort: 'weight',
      direction: 'desc',
      limit: 100,
      offset: 100,
    })
    expect(wrapper.text()).toContain('ETF Holdings')
    expect(wrapper.text()).toContain('No holdings match the current filters.')
  })

  it('applies the visible row search, sort field, and direction to the selected snapshot request', async () => {
    vi.mocked(api.get).mockImplementation(async (path: string) => {
      if (path === '/etf-holdings') return [profile] as never
      if (path === '/etf-holdings/SPY/dates') return dates as never
      if (path === '/etf-holdings/SPY/holdings') return holdingsPage() as never
      if (path === '/etf-holdings/SPY/diff') return diffPayload() as never
      if (path === '/etf-holdings/SPY/weight-evolution') return weightEvolutionPayload() as never
      if (path === '/etf-holdings/SPY/transitions') return transitionTimelinePayload() as never
      return [] as never
    })

    const wrapper = mount(ETFHoldingsView)
    await vi.waitFor(() => expect(wrapper.text()).toContain('MSFT'))
    const expectedQuery = {
      snapshot_id: '55',
      q: undefined,
      sort: 'weight',
      direction: 'desc',
      limit: 100,
      offset: 0,
    }

    await wrapper.get('input[placeholder="Symbol, name, CUSIP, ISIN"]').setValue('Microsoft')
    await vi.waitFor(() => expect(api.get).toHaveBeenLastCalledWith(
      '/etf-holdings/SPY/holdings', { ...expectedQuery, q: 'Microsoft' },
    ))

    const sortControls = wrapper.findAll('.toolbar select')
    await sortControls[0]!.setValue('symbol')
    await vi.waitFor(() => expect(api.get).toHaveBeenLastCalledWith(
      '/etf-holdings/SPY/holdings', { ...expectedQuery, q: 'Microsoft', sort: 'symbol' },
    ))
    await sortControls[1]!.setValue('asc')
    await vi.waitFor(() => expect(api.get).toHaveBeenLastCalledWith(
      '/etf-holdings/SPY/holdings', { ...expectedQuery, q: 'Microsoft', sort: 'symbol', direction: 'asc' },
    ))
  })

  it('automatically prepares an uncached selected ETF and loads only its returned holdings', async () => {
    const xleProfile = {
      ...profile,
      id: 3,
      instrument_id: 30,
      symbol: 'XLE',
      name: 'Energy Select Sector SPDR Fund',
      latest_snapshot_id: 95,
      latest_composition_date: '2026-11-05',
      holdings_capability: { ...profile.holdings_capability, availability: 'current', identity_verified: true, usable_for_current_analysis: true },
    }
    const xleSnapshot = {
      ...holdingsPage().snapshot,
      id: 95,
      etf_profile_id: 3,
      etf_instrument_id: 30,
      etf_symbol: 'XLE',
      etf_name: xleProfile.name,
      composition_date: '2026-11-05',
      known_at: '2026-11-06T09:00:00Z',
    }
    const xlePage = holdingsPage({
      snapshot: xleSnapshot,
      holdings: [{ ...holdingsPage().holdings[0], id: 301, snapshot_id: 95, reported_symbol: 'XOM', constituent_symbol: 'XOM' }],
      total: 1,
      has_next: false,
    })
    vi.mocked(api.get)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([xleProfile])
      .mockResolvedValueOnce([{ ...dates[0], snapshot_id: 95, composition_date: '2026-11-05' }])
      .mockResolvedValueOnce(xlePage)
      .mockResolvedValueOnce(weightEvolutionPayload())
      .mockResolvedValueOnce(transitionTimelinePayload())
    vi.mocked(api.post).mockResolvedValueOnce(preparationResponse('XLE') as never)

    const wrapper = mount(ETFHoldingsView)
    const search = wrapper.find('.mock-search-bar input')
    await search.setValue('XLE')
    await wrapper.find('.mock-search-bar button').trigger('click')

    await vi.waitFor(() => expect(wrapper.text()).toContain('XOM'))
    expect(api.post).toHaveBeenCalledWith('/data/ensure', {
      target: { kind: 'instrument', symbol: 'XLE' },
      datasets: ['holdings'],
    }, expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(api.get).toHaveBeenCalledWith('/etf-holdings', { q: 'XLE' })
    expect(wrapper.get('[data-testid="etf-snapshot-known-at"]').attributes('datetime')).toBe('2026-11-06T09:00:00Z')
    expect(wrapper.get('[data-testid="etf-snapshot-lineage"]').text()).toContain('issuer current holdings')
    expect(wrapper.get('[data-testid="etf-preparation-status"]').text()).toBe('Requested data is ready.')
    expect(wrapper.get('.holdings-table').text()).not.toContain('MSFT')
    await wrapper.unmount()
  })

  it('aborts the selected holdings observer and ignores a late response after unmount', async () => {
    let resolvePreparation!: (response: unknown) => void
    vi.mocked(api.get).mockResolvedValue([])
    vi.mocked(api.post).mockImplementation((path) => {
      if (path !== '/data/ensure') return Promise.reject(new Error(`Unexpected request: ${path}`)) as never
      return new Promise(resolve => { resolvePreparation = resolve }) as never
    })

    const wrapper = mount(ETFHoldingsView)
    await vi.waitFor(() => expect(api.get).toHaveBeenCalledWith('/etf-holdings', { q: undefined }))
    await wrapper.findComponent({ name: 'SearchBar' }).vm.$emit('select', 'OIH', {
      symbol: 'OIH', name: 'Oil Services ETF', exchange: 'NYSE Arca', type: 'ETF',
    })
    await vi.waitFor(() => expect(api.post).toHaveBeenCalledWith('/data/ensure', {
      target: { kind: 'instrument', symbol: 'OIH' }, datasets: ['holdings'],
    }, expect.objectContaining({ signal: expect.any(AbortSignal) })))
    expect(api.get).toHaveBeenCalledWith('/etf-holdings', { q: 'OIH' })
    const exactProfileLookupCount = vi.mocked(api.get).mock.calls.filter(([path, params]) =>
      path === '/etf-holdings' && (params as { q?: string } | undefined)?.q === 'OIH',
    ).length
    const ensureSignal = vi.mocked(api.post).mock.calls[0]?.[2]?.signal
    expect(ensureSignal?.aborted).toBe(false)

    await wrapper.unmount()
    expect(ensureSignal?.aborted).toBe(true)

    // A shared request may complete after this view has detached. It must not
    // trigger a profile refresh or write a late selection into the disposed view.
    resolvePreparation(preparationResponse('OIH'))
    await flushPromises()
    expect(vi.mocked(api.get).mock.calls.filter(([path, params]) =>
      path === '/etf-holdings' && (params as { q?: string } | undefined)?.q === 'OIH',
    )).toHaveLength(exactProfileLookupCount)
  })

  it('keeps rapid selected-fund preparations isolated when the user switches tickers', async () => {
    let releaseFirst!: (value: unknown) => void
    vi.mocked(api.post).mockImplementation((path, body) => {
      const request = body as { target?: { symbol?: string } }
      if (request.target?.symbol === 'XLE') return new Promise(resolve => { releaseFirst = resolve }) as never
      return Promise.resolve(preparationResponse('XLF')) as never
    })
    vi.mocked(api.get)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([{ ...profile, id: 4, instrument_id: 40, symbol: 'XLF', name: 'Financial Select Sector SPDR Fund', latest_snapshot_id: null }])
      .mockResolvedValueOnce([])

    const wrapper = mount(ETFHoldingsView)
    const search = wrapper.find('.mock-search-bar input')
    await search.setValue('XLE')
    await wrapper.find('.mock-search-bar button').trigger('click')
    await vi.waitFor(() => expect(api.post).toHaveBeenCalledTimes(1))
    const firstSignal = vi.mocked(api.post).mock.calls[0]?.[2]?.signal

    await search.setValue('XLF')
    await wrapper.find('.mock-search-bar button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Financial Select Sector SPDR Fund'))
    expect(api.post).toHaveBeenCalledTimes(2)
    expect(firstSignal?.aborted).toBe(true)
    expect(api.get).toHaveBeenCalledWith('/etf-holdings', { q: 'XLF' })
    expect(vi.mocked(api.get).mock.calls.filter(([path, params]) =>
      path === '/etf-holdings' && (params as { q?: string } | undefined)?.q === 'XLE',
    )).toHaveLength(1)
    expect(wrapper.get('[data-testid="etf-preparation-status"]').text()).toBe('Requested data is ready.')

    releaseFirst(preparationResponse('XLE'))
    await flushPromises()
    expect(vi.mocked(api.get).mock.calls.filter(([path, params]) =>
      path === '/etf-holdings' && (params as { q?: string } | undefined)?.q === 'XLE',
    )).toHaveLength(1)
    expect(wrapper.get('.panel-title-row h2').text()).toBe('XLF')
    await wrapper.unmount()
  })

  it('opens resolved constituent history without promoting stale parent eligibility', async () => {
    const staleProfile = {
      ...profile,
      holdings_capability: {
        ...profile.holdings_capability,
        availability: 'stale',
        usable_for_current_analysis: false,
        reason: 'The stored snapshot is displayable but not current-analysis eligible.',
      },
    }
    vi.mocked(api.get)
      .mockResolvedValueOnce([staleProfile])
      .mockResolvedValueOnce(dates)
      .mockResolvedValueOnce(holdingsPage())
      .mockResolvedValueOnce(diffPayload())
      .mockResolvedValueOnce(weightEvolutionPayload())
      .mockResolvedValueOnce(transitionTimelinePayload())

    const wrapper = mount(ETFHoldingsView)
    await vi.waitFor(() => expect(wrapper.text()).toContain('MSFT'))
    expect(wrapper.find('.panel-meta').text()).toContain('Profile current eligibility: stale')
    expect(wrapper.text()).toContain('not current-analysis eligible')

    const historyButton = wrapper.find('.detail-title button')
    expect(historyButton.text()).toBe('View history')
    expect(historyButton.attributes('disabled')).toBeUndefined()
    await historyButton.trigger('click')
    const selectedContext = createETFHoldingDrilldownContext(
      holdingsPage().snapshot,
      holdingsPage().holdings[0]!,
      200,
      'MSFT',
    )
    expect(routerPush).toHaveBeenCalledWith({
      path: '/chart/MSFT',
      query: { ...holdingDrilldownRouteQuery(selectedContext), holding_history_intent: 'selected' },
      state: holdingDrilldownRouteState(selectedContext),
    })
    expect(wrapper.find('.panel-meta').text()).toContain('Profile current eligibility: stale')
    expect(api.post).not.toHaveBeenCalled()
  })

  it('does not route an old page row while a newly selected snapshot is still loading', async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce([profile])
      .mockResolvedValueOnce(dates)
      .mockResolvedValueOnce(holdingsPage())
      .mockResolvedValueOnce(diffPayload())
      .mockResolvedValueOnce(weightEvolutionPayload())
      .mockResolvedValueOnce(transitionTimelinePayload())

    const wrapper = mount(ETFHoldingsView)
    await vi.waitFor(() => expect(wrapper.text()).toContain('MSFT'))

    let releasePage!: (value: unknown) => void
    const pendingPage = new Promise(resolve => { releasePage = resolve })
    vi.mocked(api.get).mockImplementationOnce(() => pendingPage as Promise<never>)
    const snapshotPicker = wrapper.findAll('.toolbar select').at(-1)!
    await snapshotPicker.setValue('54')
    await vi.waitFor(() => expect(api.get).toHaveBeenCalledWith('/etf-holdings/SPY/holdings', expect.objectContaining({ snapshot_id: '54' })))
    vi.mocked(api.get).mockResolvedValueOnce(diffPayload())

    await wrapper.find('.detail-title button').trigger('click')
    expect(routerPush).not.toHaveBeenCalled()

    const previousPage = holdingsPage()
    releasePage({
      ...previousPage,
      snapshot: { ...previousPage.snapshot, id: 54, composition_date: '2026-06-06' },
      holdings: previousPage.holdings.map(holding => ({ ...holding, snapshot_id: 54 })),
    })
    await flushPromises()
    expect(routerPush).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('does not offer a history route for an unresolved holding row', async () => {
    const unresolvedPage = holdingsPage({
      holdings: [{
        ...holdingsPage().holdings[0],
        constituent_instrument_id: null,
        constituent_symbol: null,
        is_resolved: false,
      }],
      total: 1,
      has_next: false,
    })
    vi.mocked(api.get)
      .mockResolvedValueOnce([profile])
      .mockResolvedValueOnce(dates)
      .mockResolvedValueOnce(unresolvedPage)
      .mockResolvedValueOnce(diffPayload())
      .mockResolvedValueOnce(weightEvolutionPayload())
      .mockResolvedValueOnce(transitionTimelinePayload())

    const wrapper = mount(ETFHoldingsView)
    await vi.waitFor(() => expect(wrapper.text()).toContain('MSFT'))
    const historyButton = wrapper.find('.detail-title button')
    expect(historyButton.text()).toBe('View history')
    expect(historyButton.attributes('disabled')).toBeDefined()
    await historyButton.trigger('click')
    expect(routerPush).not.toHaveBeenCalled()
  })

  it('offers row-originated discovery for an eligible unresolved reported equity without mutating the snapshot', async () => {
    const unresolvedPage = holdingsPage({
      holdings: [{
        ...holdingsPage().holdings[0],
        constituent_instrument_id: null,
        constituent_symbol: null,
        reported_symbol: 'UNXQ',
        reported_name: 'Uncached Example Equity',
        source_row_id: 'issuer-row-100',
        is_resolved: false,
      }],
      total: 1,
      has_next: false,
    })
    vi.mocked(api.get)
      .mockResolvedValueOnce([profile])
      .mockResolvedValueOnce(dates)
      .mockResolvedValueOnce(unresolvedPage)
      .mockResolvedValueOnce(diffPayload())
      .mockResolvedValueOnce(weightEvolutionPayload())
      .mockResolvedValueOnce(transitionTimelinePayload())

    const wrapper = mount(ETFHoldingsView)
    await vi.waitFor(() => expect(wrapper.text()).toContain('UNXQ'))
    const rowAction = wrapper.findAll('button').find(button => button.text().includes('Resolve reported holding UNXQ'))
    expect(rowAction).toBeDefined()
    await rowAction!.trigger('click')
    expect(wrapper.findAll('.mock-search-bar input')[1]!.element.value).toBe('UNXQ')
    expect(api.post).not.toHaveBeenCalled()
    const context: ETFHoldingDrilldownContext = {
      etfSymbol: 'SPY',
      instrumentId: 987654,
      canonicalSymbol: 'UNXQ',
      snapshotId: 55,
      compositionDate: '2026-06-07',
      knownAt: '2026-06-07T04:15:00Z',
      provenance: 'issuer_current_holdings',
      sourceProvider: 'issuer-test',
      holdingRowId: 100,
      sourceRowId: 'issuer-row-100',
      reportedSymbol: 'UNXQ',
      reportedName: 'Uncached Example Equity',
      holdingType: 'equity',
    }
    const searchBars = wrapper.findAllComponents({ name: 'SearchBar' })
    const confirmedIdentity = {
      request_id: 'confirmed-unxq',
      status: 'resolved' as const,
      instrument: { instrument_id: context.instrumentId, symbol: 'UNXQ', identity_status: 'verified' },
      source_outcomes: [],
    }
    searchBars[1]!.vm.$emit('select', 'UNXQ', {
      instrument_id: context.instrumentId,
      explicitlyResolved: true,
      identity_status: 'verified',
    }, confirmedIdentity)
    await nextTick()
    expect(routerPush).toHaveBeenCalledWith({
      path: '/chart/UNXQ',
      query: { ...holdingDrilldownRouteQuery(context), holding_history_intent: 'selected' },
      state: holdingDrilldownRouteState(context, confirmedIdentity),
    })
    expect(unresolvedPage.holdings[0]?.is_resolved).toBe(false)
    expect(unresolvedPage.holdings[0]?.constituent_instrument_id).toBeNull()
  })

  it('does not offer unresolved-row discovery when current-analysis capability is held', async () => {
    const heldProfile = {
      ...profile,
      holdings_capability: {
        ...profile.holdings_capability,
        availability: 'held',
        usable_for_current_analysis: false,
      },
    }
    const unresolvedPage = holdingsPage({
      holdings: [{
        ...holdingsPage().holdings[0],
        constituent_instrument_id: null,
        constituent_symbol: null,
        reported_symbol: 'UNXQ',
        is_resolved: false,
      }],
      total: 1,
      has_next: false,
    })
    vi.mocked(api.get)
      .mockResolvedValueOnce([heldProfile])
      .mockResolvedValueOnce(dates)
      .mockResolvedValueOnce(unresolvedPage)
      .mockResolvedValueOnce(diffPayload())
      .mockResolvedValueOnce(weightEvolutionPayload())
      .mockResolvedValueOnce(transitionTimelinePayload())

    const wrapper = mount(ETFHoldingsView)
    await vi.waitFor(() => expect(wrapper.text()).toContain('UNXQ'))
    expect(wrapper.text()).not.toContain('Resolve reported holding')
    expect(api.post).not.toHaveBeenCalled()
  })

  it('labels same-date parser-version differences as audit data while preserving raw rows and metrics', async () => {
    const sameDate = '2026-06-07'
    const parserCorrection = diffPayload()
    parserCorrection.left_snapshot = {
      ...parserCorrection.left_snapshot,
      composition_date: sameDate,
      parser_version: 'issuer-html-v1',
      known_at: '2026-06-07T03:00:00Z',
    }
    parserCorrection.right_snapshot = {
      ...parserCorrection.right_snapshot,
      composition_date: sameDate,
      parser_version: 'issuer-html-v2',
      known_at: '2026-06-07T04:15:00Z',
    }

    const correctionEvolution = weightEvolutionPayload()
    correctionEvolution.from_date = sameDate
    correctionEvolution.to_date = sameDate
    correctionEvolution.series[0].points = [
      { ...correctionEvolution.series[0].points[0], composition_date: sameDate, parser_version: 'issuer-html-v1' },
      { ...correctionEvolution.series[0].points[1], composition_date: sameDate, parser_version: 'issuer-html-v2' },
    ]
    const correctionTimeline = transitionTimelinePayload()
    correctionTimeline.from_date = sameDate
    correctionTimeline.to_date = sameDate
    correctionTimeline.transitions[0].left_snapshot = parserCorrection.left_snapshot
    correctionTimeline.transitions[0].right_snapshot = parserCorrection.right_snapshot

    vi.mocked(api.get)
      .mockResolvedValueOnce([profile, overlapProfile])
      .mockResolvedValueOnce([
        { ...dates[0], composition_date: sameDate, parser_version: 'issuer-html-v2', known_at: '2026-06-07T04:15:00Z' },
        { ...dates[1], snapshot_id: 54, composition_date: sameDate, parser_version: 'issuer-html-v1', known_at: '2026-06-07T03:00:00Z' },
      ])
      .mockResolvedValueOnce(holdingsPage({ total: 1946 }))
      .mockResolvedValueOnce(parserCorrection)
      .mockResolvedValueOnce(correctionEvolution)
      .mockResolvedValueOnce(correctionTimeline)
    vi.mocked(api.post)
      .mockResolvedValueOnce(overlapSummaryPayload())
      .mockResolvedValueOnce(overlapMatrixPayload())
      .mockResolvedValueOnce(overlapMatrixPayload())

    const wrapper = mount(ETFHoldingsView)
    await vi.waitFor(() => {
      expect(wrapper.get('[data-testid="etf-parser-correction-audit"]').exists()).toBe(true)
    })

    const audit = wrapper.get('[data-testid="etf-parser-correction-audit"]')
    expect(audit.text()).toContain('Same-date parser correction audit')
    expect(audit.text()).toContain('issuer-html-v1 and issuer-html-v2')
    expect(audit.text()).toContain('not fund activity or turnover')
    expect(audit.findAll('time').map((time) => time.attributes('datetime')))
      .toEqual(['2026-06-07T03:00:00Z', '2026-06-07T04:15:00Z'])
    expect(wrapper.text()).toContain('1946 rows')
    expect(wrapper.text()).toContain('Raw gross weight change · audit')
    expect(wrapper.text()).toContain('2.00%')
    expect(wrapper.text()).toContain('Raw diff status · audit')
    expect(wrapper.text()).toContain('raw added')
    expect(wrapper.text()).toContain('Raw parser row delta')
    expect(wrapper.get('[data-testid="etf-parser-correction-evolution-audit"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('Gross churn')
    expect(wrapper.text()).not.toContain('2.00% churn')
    expect(wrapper.get('[data-testid="etf-parser-correction-transition"]').text())
      .toContain('Same-date parser correction audit')
  })

  it('labels an explicitly selected older snapshot as historical and shows its own lineage', async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce([profile])
      .mockResolvedValueOnce(dates)
      .mockResolvedValueOnce(holdingsPage())
      .mockResolvedValueOnce(diffPayload())
      .mockResolvedValueOnce(weightEvolutionPayload())
      .mockResolvedValueOnce(transitionTimelinePayload())
      .mockResolvedValueOnce(holdingsPage({
        snapshot: {
          ...holdingsPage().snapshot,
          id: 54,
          composition_date: '2026-06-06',
          known_at: '2026-06-07T04:15:00Z',
          published_at: null,
          provenance: 'manual_import',
          source_provider: 'manual_csv',
          source_quality: 'historical_unverified',
        },
      }))
      .mockResolvedValueOnce(diffPayload())

    const wrapper = mount(ETFHoldingsView)
    await vi.waitFor(() => {
      expect(wrapper.get('[data-testid="etf-selected-snapshot-kind"]').text()).toBe('Latest stored snapshot')
    })

    const snapshotPicker = wrapper.findAll('label')
      .find(label => label.text().includes('Snapshot'))
      ?.find('select')
    expect(snapshotPicker).toBeTruthy()
    await snapshotPicker!.setValue('54')

    await vi.waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/etf-holdings/SPY/holdings', {
        snapshot_id: '54',
        q: undefined,
        sort: 'weight',
        direction: 'desc',
        limit: 100,
        offset: 0,
      })
      expect(wrapper.get('[data-testid="etf-selected-snapshot-kind"]').text()).toBe('Historical snapshot')
    })
    expect(wrapper.get('[data-testid="etf-snapshot-lineage"]').text()).toContain('manual import')
    expect(wrapper.find('.panel-meta').text()).toContain('manual_csv')
    expect(wrapper.get('[data-testid="etf-snapshot-known-at"]').attributes('datetime'))
      .toBe('2026-06-07T04:15:00Z')
    expect(wrapper.get('[data-testid="etf-snapshot-lineage"]').text()).toContain('Not established')
    expect(wrapper.find('.panel-meta').text()).toContain('Profile current eligibility: current')
  })

  it('resets the selected snapshot when switching ETF profiles', async () => {
    const copxProfile = {
      ...profile,
      id: 2,
      instrument_id: 20,
      symbol: 'COPX',
      name: 'Global X Copper Miners ETF',
      latest_snapshot_id: 2,
      latest_composition_date: '2026-06-07',
      resolved_count: 45,
      unresolved_count: 1,
    }
    const iwmProfile = {
      ...profile,
      id: 3,
      instrument_id: 30,
      symbol: 'IWM',
      name: 'iShares Russell 2000 ETF',
      issuer: 'iShares',
      latest_snapshot_id: 3,
      latest_composition_date: '2026-06-05',
      resolved_count: 1910,
      unresolved_count: 3,
    }
    const copxDates = [{ ...dates[0], snapshot_id: 2, composition_date: '2026-06-07' }]
    const iwmDates = [{ ...dates[0], snapshot_id: 3, composition_date: '2026-06-05' }]

    vi.mocked(api.get)
      .mockResolvedValueOnce([copxProfile, iwmProfile])
      .mockResolvedValueOnce(copxDates)
      .mockResolvedValueOnce(holdingsPage({
        snapshot: {
          ...holdingsPage().snapshot,
          id: 2,
          etf_profile_id: 2,
          etf_instrument_id: 20,
          etf_symbol: 'COPX',
          etf_name: 'Global X Copper Miners ETF',
          composition_date: '2026-06-07',
        },
      }))
      .mockResolvedValueOnce(weightEvolutionPayload())
      .mockResolvedValueOnce(transitionTimelinePayload())
      .mockResolvedValueOnce(profile.holdings_capability)
      .mockResolvedValueOnce(iwmDates)
      .mockResolvedValueOnce(holdingsPage({
        snapshot: {
          ...holdingsPage().snapshot,
          id: 3,
          etf_profile_id: 3,
          etf_instrument_id: 30,
          etf_symbol: 'IWM',
          etf_name: 'iShares Russell 2000 ETF',
          composition_date: '2026-06-05',
          row_count: 1913,
          resolved_count: 1910,
          unresolved_count: 3,
        },
        total: 1913,
      }))
      .mockResolvedValueOnce(weightEvolutionPayload())
      .mockResolvedValueOnce(transitionTimelinePayload())

    const wrapper = mount(ETFHoldingsView)
    await vi.waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/etf-holdings/COPX/holdings', {
        snapshot_id: '2',
        q: undefined,
        sort: 'weight',
        direction: 'desc',
        limit: 100,
        offset: 0,
      })
    })

    const iwmCard = wrapper.findAll('button.profile-card').find(button => button.text().includes('IWM'))
    expect(iwmCard).toBeTruthy()
    await iwmCard!.trigger('click')

    await vi.waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/etf-holdings/IWM/holdings', {
        snapshot_id: '3',
        q: undefined,
        sort: 'weight',
        direction: 'desc',
        limit: 100,
        offset: 0,
      })
    })
    expect(api.get).not.toHaveBeenCalledWith('/etf-holdings/IWM/holdings', expect.objectContaining({
      snapshot_id: '2',
    }))
  })

  it('uses the shared instrument picker to select a stored ETF profile', async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce([profile, overlapProfile])
      .mockResolvedValueOnce(dates)
      .mockResolvedValueOnce(holdingsPage())
      .mockResolvedValueOnce(diffPayload())
      .mockResolvedValueOnce(weightEvolutionPayload())
      .mockResolvedValueOnce(transitionTimelinePayload())
      .mockResolvedValueOnce(overlapProfile.holdings_capability)
      .mockResolvedValueOnce(dates)
      .mockResolvedValueOnce(holdingsPage({
        snapshot: {
          ...holdingsPage().snapshot,
          etf_profile_id: 2,
          etf_instrument_id: 11,
          etf_symbol: 'QQQ',
          etf_name: 'Invesco QQQ Trust',
        },
      }))
      .mockResolvedValueOnce(diffPayload())
      .mockResolvedValueOnce(weightEvolutionPayload())
      .mockResolvedValueOnce(transitionTimelinePayload())
    const wrapper = mount(ETFHoldingsView)
    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('MSFT')
    })

    const picker = wrapper.findComponent({ name: 'SearchBar' })
    expect(picker.exists()).toBe(true)
    expect(picker.props('placeholder')).toBe('Search ETF instrument')
    expect(picker.props('resultTypes')).toEqual(['ETF', 'Fund', 'ETV', 'Exchange Traded Vehicle'])
    expect(picker.props('allowExpressions')).toBe(false)

    await picker.vm.$emit('update:modelValue', 'QQQ')
    await picker.vm.$emit('select', 'QQQ', {
      symbol: 'QQQ',
      name: 'Invesco QQQ Trust',
      exchange: 'NASDAQ',
      type: 'ETF',
    })
    await flushPromises()

    expect(api.post).not.toHaveBeenCalled()
    expect(api.get).toHaveBeenCalledWith('/etf-holdings', { q: undefined })
    await vi.waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/etf-holdings/QQQ/dates')
    })
    expect(wrapper.text()).toContain('QQQ')
    expect(wrapper.text()).toContain('SPY')
    expect(wrapper.findAll('button.profile-card')).toHaveLength(2)
    wrapper.unmount()
  })

  it('selects an existing fund before unrelated startup profiles finish and preserves it through unavailable preparation', async () => {
    const diaProfile = { ...profile, id: 16, instrument_id: 160, symbol: 'DIA', name: 'SPDR Dow Jones Industrial Average ETF Trust' }
    const xlbCapability = {
      ...profile.holdings_capability,
      availability: 'stale',
      usable_for_current_analysis: false,
      reason: 'The retained XLB snapshot is not current for analysis.',
    }
    const xlbProfile = {
      ...profile,
      id: 17,
      instrument_id: 701,
      symbol: 'XLB',
      name: 'State Street Materials Select Sector SPDR ETF',
      latest_snapshot_id: 16,
      latest_composition_date: '2026-01-02',
      holdings_capability: xlbCapability,
    }
    const xlbDate = {
      ...dates[0],
      snapshot_id: 16,
      composition_date: '2026-01-02',
      as_of_date: '2026-01-02',
      known_at: '2026-01-03T00:00:00Z',
      provenance: 'controlled_fixture',
      source_provider: 'e2e_reference',
      source_quality: 'controlled_fixture',
    }
    const xlbPage = holdingsPage({
      snapshot: {
        ...holdingsPage().snapshot,
        id: 16,
        etf_profile_id: xlbProfile.id,
        etf_instrument_id: xlbProfile.instrument_id,
        etf_symbol: xlbProfile.symbol,
        etf_name: xlbProfile.name,
        composition_date: xlbDate.composition_date,
        known_at: xlbDate.known_at,
        provenance: 'controlled_fixture',
        source_provider: 'e2e_reference',
        source_quality: 'controlled_fixture',
        source_identifier: 'e2e:XLB:2026-01-02',
        source_url: 'https://issuer.example.test/holdings/xlb',
      },
      holdings: [{
        ...holdingsPage().holdings[0],
        id: 7010,
        snapshot_id: 16,
        constituent_symbol: 'LIN',
        constituent_name: 'Linde plc',
        reported_symbol: 'LIN',
        reported_name: 'Linde plc',
      }],
      total: 1,
      has_next: false,
    })

    let startupProfilesResolved = false
    let finishStartupProfiles!: (value: unknown) => void
    const startupProfiles = new Promise<unknown>(resolve => { finishStartupProfiles = resolve })
    void startupProfiles.then(() => { startupProfilesResolved = true })
    vi.mocked(api.get).mockImplementation((path, params) => {
      if (path === '/etf-holdings' && (params as { q?: string } | undefined)?.q === undefined) {
        return startupProfiles as never
      }
      if (path === '/etf-holdings' && (params as { q?: string } | undefined)?.q === 'XLB') {
        return Promise.resolve([xlbProfile]) as never
      }
      if (path === '/etf-holdings/XLB/dates') return Promise.resolve([xlbDate]) as never
      if (path === '/etf-holdings/XLB/holdings') return Promise.resolve(xlbPage) as never
      if (path === '/etf-holdings/XLB/capability') return Promise.resolve(xlbCapability) as never
      if (path === '/etf-holdings/XLB/weight-evolution') return Promise.resolve(weightEvolutionPayload()) as never
      if (path === '/etf-holdings/XLB/transitions') return Promise.resolve(transitionTimelinePayload()) as never
      return Promise.resolve([]) as never
    })
    let finishPreparation!: (response: unknown) => void
    vi.mocked(api.post).mockImplementation(() => new Promise(resolve => { finishPreparation = resolve }) as never)

    const wrapper = mount(ETFHoldingsView)
    const picker = wrapper.findComponent({ name: 'SearchBar' })
    await picker.vm.$emit('select', 'XLB', {
      symbol: 'XLB',
      name: xlbProfile.name,
      exchange: 'NYSE Arca',
      type: 'ETF',
    })

    await vi.waitFor(() => expect(api.get).toHaveBeenCalledWith('/etf-holdings', { q: 'XLB' }))
    await vi.waitFor(() => expect(wrapper.get('.panel-title-row h2').text()).toBe('XLB'))
    await vi.waitFor(() => expect(api.get).toHaveBeenCalledWith('/etf-holdings/XLB/holdings', expect.objectContaining({ snapshot_id: '16' })))
    await vi.waitFor(() => expect(api.post).toHaveBeenCalledWith('/data/ensure', {
      target: { kind: 'instrument', symbol: 'XLB' }, datasets: ['holdings'],
    }, expect.objectContaining({ signal: expect.any(AbortSignal) })))
    const exactProfileLookupIndex = vi.mocked(api.get).mock.calls.findIndex(([path, params]) =>
      path === '/etf-holdings' && (params as { q?: string } | undefined)?.q === 'XLB',
    )
    expect(exactProfileLookupIndex).toBeGreaterThanOrEqual(0)
    expect(vi.mocked(api.get).mock.invocationCallOrder[exactProfileLookupIndex])
      .toBeLessThan(vi.mocked(api.post).mock.invocationCallOrder[0]!)
    expect(startupProfilesResolved).toBe(false)
    expect(wrapper.get('[data-testid="etf-preparation-status"]').text()).toContain('Preparing XLB holdings.')
    expect(wrapper.get('.panel-title-row h2').text()).toBe('XLB')
    expect(wrapper.get('.holdings-table').text()).toContain('LIN')
    finishStartupProfiles([diaProfile])
    await vi.waitFor(() => expect(startupProfilesResolved).toBe(true))
    await flushPromises()
    expect(wrapper.get('.panel-title-row h2').text()).toBe('XLB')
    expect(wrapper.findAll('button.profile-card').some(card => card.text().includes('XLB'))).toBe(true)
    finishPreparation(preparationResponse('XLB', 'unavailable'))
    await vi.waitFor(() => expect(wrapper.get('[data-testid="etf-preparation-status"]').text()).toContain('No reviewed data source can provide this request.'))

    expect(wrapper.get('.panel-title-row h2').text()).toBe('XLB')
    expect(wrapper.get('.holdings-table').text()).toContain('LIN')
    expect(api.get).not.toHaveBeenCalledWith('/etf-holdings/DIA/holdings', expect.anything())
    expect(wrapper.get('[data-testid="etf-snapshot-source-identifier"]').text()).toBe('e2e:XLB:2026-01-02')
    wrapper.unmount()
  })

  it('discovers and deliberately selects a confirmed Exchange Traded Vehicle without admitting ETNs', async () => {
    vi.mocked(api.get).mockImplementation(async (path: string) => {
      if (path === '/etf-holdings') return []
      return []
    })
    vi.mocked(api.post).mockResolvedValueOnce(preparationResponse('EVOL', 'unavailable') as never)

    const wrapper = mount(ETFHoldingsView)
    const picker = wrapper.findComponent({ name: 'SearchBar' })
    expect(picker.props('resultTypes')).toEqual(['ETF', 'Fund', 'ETV', 'Exchange Traded Vehicle'])
    expect(picker.props('resultTypes')).not.toContain('ETN')

    await picker.vm.$emit('select', 'EVOL', {
      symbol: 'EVOL',
      name: 'Example Exchange Traded Vehicle',
      exchange: 'XNYS',
      type: 'Exchange Traded Vehicle',
      instrument_id: 991,
      identity_status: 'resolved',
      explicitlyResolved: true,
    })
    await vi.waitFor(() => expect(api.post).toHaveBeenCalledWith('/data/ensure', {
      target: { kind: 'instrument', instrument_id: 991 }, datasets: ['holdings'],
    }, expect.objectContaining({ signal: expect.any(AbortSignal) })))
    expect(api.post).not.toHaveBeenCalledWith('/instruments/acquire', expect.anything())
    await vi.waitFor(() => expect(wrapper.get('[data-testid="etf-preparation-status"]').text()).toContain('No reviewed data source can provide this request.'))
    expect(wrapper.text()).toContain('EVOL')
    wrapper.unmount()
  })

  it('reuses a producer-qualified current cache on deliberate profile selection', async () => {
    vi.mocked(api.get).mockImplementation(async (path: string) => {
      if (path === '/etf-holdings') return [profile]
      if (path === '/etf-holdings/SPY/capability') return profile.holdings_capability
      if (path === '/etf-holdings/SPY/dates') return dates
      if (path === '/etf-holdings/SPY/holdings') return holdingsPage()
      if (path === '/etf-holdings/SPY/diff') return diffPayload()
      if (path === '/etf-holdings/SPY/weight-evolution') return weightEvolutionPayload()
      if (path === '/etf-holdings/SPY/transitions') return transitionTimelinePayload()
      return []
    })
    const wrapper = mount(ETFHoldingsView)
    await vi.waitFor(() => expect(wrapper.text()).toContain('MSFT'))
    expect(api.get).not.toHaveBeenCalledWith('/etf-holdings/SPY/capability')
    expect(api.post).not.toHaveBeenCalled()

    await wrapper.get('button.profile-card').trigger('click')
    await vi.waitFor(() => expect(api.get).toHaveBeenCalledWith('/etf-holdings/SPY/capability'))
    await vi.waitFor(() => expect(wrapper.text()).toContain('MSFT'))
    expect(api.post).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="etf-snapshot-known-at"]').attributes('datetime'))
      .toBe('2026-06-07T04:15:00Z')
    wrapper.unmount()
  })

  it('checks once when an explicitly selected stored fund has no snapshot despite a current capability summary', async () => {
    const noSnapshotProfile = {
      ...profile,
      latest_composition_date: null,
      latest_snapshot_id: null,
      resolved_count: 0,
      unresolved_count: 0,
    }
    vi.mocked(api.get).mockImplementation(async (path: string) => {
      if (path === '/etf-holdings') return [noSnapshotProfile]
      if (path === '/etf-holdings/SPY/dates') return []
      if (path === '/etf-holdings/SPY/capability') return profile.holdings_capability
      return []
    })
    vi.mocked(api.post).mockResolvedValueOnce(preparationResponse('SPY', 'unavailable') as never)

    const wrapper = mount(ETFHoldingsView)
    await vi.waitFor(() => expect(wrapper.get('.profile-card').text()).toContain('SPY'))
    expect(api.post).not.toHaveBeenCalled()
    await wrapper.get('.profile-card').trigger('click')
    await vi.waitFor(() => expect(api.post).toHaveBeenCalledWith('/data/ensure', {
      target: { kind: 'instrument', symbol: 'SPY' }, datasets: ['holdings'],
    }, expect.objectContaining({ signal: expect.any(AbortSignal) })))
    await vi.waitFor(() => expect(wrapper.get('[data-testid="etf-preparation-status"]').text()).toContain('No reviewed data source can provide this request.'))
    expect(api.post).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('keeps a stale dated holdings cache visible while automatic preparation is pending and unavailable', async () => {
    const staleProfile = {
      ...profile,
      holdings_capability: {
        ...profile.holdings_capability,
        availability: 'stale',
        usable_for_current_analysis: false,
        reason: 'The saved snapshot is retained but requires a current check.',
      },
    }
    vi.mocked(api.get).mockImplementation(async (path: string) => {
      if (path === '/etf-holdings') return [staleProfile]
      if (path === '/etf-holdings/SPY/capability') return staleProfile.holdings_capability
      if (path === '/etf-holdings/SPY/dates') return dates
      if (path === '/etf-holdings/SPY/holdings') return holdingsPage()
      if (path === '/etf-holdings/SPY/diff') return diffPayload()
      if (path === '/etf-holdings/SPY/weight-evolution') return weightEvolutionPayload()
      if (path === '/etf-holdings/SPY/transitions') return transitionTimelinePayload()
      return []
    })
    let finishPreparation!: (value: unknown) => void
    vi.mocked(api.post).mockImplementation(() => new Promise(resolve => { finishPreparation = resolve }) as never)

    const wrapper = mount(ETFHoldingsView)
    await vi.waitFor(() => expect(wrapper.text()).toContain('MSFT'))
    const originalKnownAt = wrapper.get('[data-testid="etf-snapshot-known-at"]').attributes('datetime')
    await wrapper.get('button.profile-card').trigger('click')
    await vi.waitFor(() => expect(api.post).toHaveBeenCalledWith('/data/ensure', {
      target: { kind: 'instrument', symbol: 'SPY' }, datasets: ['holdings'],
    }, expect.objectContaining({ signal: expect.any(AbortSignal) })))
    expect(wrapper.get('[data-testid="etf-preparation-status"]').text()).toContain('Preparing SPY holdings.')
    expect(wrapper.get('.holdings-table').text()).toContain('MSFT')
    expect(wrapper.get('[data-testid="etf-snapshot-known-at"]').attributes('datetime')).toBe(originalKnownAt)
    expect(wrapper.get('.panel-meta').text()).toContain('Profile current eligibility: stale')
    expect(wrapper.get('[data-testid="etf-check-stored"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="etf-request-issuer"]').attributes('disabled')).toBeDefined()

    finishPreparation(preparationResponse('SPY', 'unavailable'))
    await vi.waitFor(() => expect(wrapper.get('[data-testid="etf-preparation-status"]').text()).toContain('No reviewed data source can provide this request.'))
    expect(api.post).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('MSFT')
    expect(wrapper.get('[data-testid="etf-snapshot-known-at"]').attributes('datetime')).toBe(originalKnownAt)
    expect(wrapper.find('.panel-meta').text()).toContain('Profile current eligibility: stale')
    wrapper.unmount()
  })

  it('resolves a newly selected fund and starts one generic holdings check', async () => {
    vi.mocked(api.get).mockImplementation(async (path: string) => {
      if (path === '/etf-holdings') return [profile]
      if (path === '/etf-holdings/SPY/dates') return dates
      if (path === '/etf-holdings/SPY/holdings') return holdingsPage()
      if (path === '/etf-holdings/SPY/diff') return diffPayload()
      if (path === '/etf-holdings/SPY/weight-evolution') return weightEvolutionPayload()
      if (path === '/etf-holdings/SPY/transitions') return transitionTimelinePayload()
      return []
    })
    vi.mocked(api.post).mockResolvedValueOnce(preparationResponse('OIH', 'unavailable') as never)
    const wrapper = mount(ETFHoldingsView)
    await vi.waitFor(() => expect(wrapper.text()).toContain('MSFT'))
    await wrapper.findComponent({ name: 'SearchBar' }).vm.$emit('select', 'OIH', {
      symbol: 'OIH', name: 'Oil Services ETF', exchange: 'NYSE Arca', type: 'ETF',
    })
    await vi.waitFor(() => expect(api.post).toHaveBeenCalledWith('/data/ensure', {
      target: { kind: 'instrument', symbol: 'OIH' }, datasets: ['holdings'],
    }, expect.objectContaining({ signal: expect.any(AbortSignal) })))
    await vi.waitFor(() => expect(wrapper.get('[data-testid="etf-preparation-status"]').text()).toContain('No reviewed data source can provide this request.'))
    expect(api.post).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.holdings-browser').exists()).toBe(false)
    wrapper.unmount()
  })

  it('does not let a late failed refresh for one selected fund alter the next fund', async () => {
    const qqqDates = dates.map((date, index) => ({ ...date, snapshot_id: 77 - index }))
    let resolveSpyPreparation: ((value: unknown) => void) | undefined
    vi.mocked(api.get).mockImplementation(async (path: string) => {
      if (path === '/etf-holdings') return [profile, overlapProfile]
      if (path === '/etf-holdings/SPY/capability') return { ...profile.holdings_capability, availability: 'stale', usable_for_current_analysis: false }
      if (path === '/etf-holdings/QQQ/capability') return overlapProfile.holdings_capability
      if (path === '/etf-holdings/SPY/dates') return dates
      if (path === '/etf-holdings/QQQ/dates') return qqqDates
      if (path === '/etf-holdings/SPY/holdings') return holdingsPage()
      if (path === '/etf-holdings/QQQ/holdings') return holdingsPage({
        snapshot: { ...holdingsPage().snapshot, id: 77, etf_instrument_id: 11, etf_symbol: 'QQQ', etf_name: 'Invesco QQQ Trust' },
      })
      if (path.endsWith('/diff')) return diffPayload()
      if (path.endsWith('/weight-evolution')) return weightEvolutionPayload()
      if (path.endsWith('/transitions')) return transitionTimelinePayload()
      return []
    })
    vi.mocked(api.post).mockImplementation((path, body) => {
      if (path !== '/data/ensure' || (body as { target?: { symbol?: string } }).target?.symbol !== 'SPY') {
        return Promise.reject(new Error(`Unexpected request: ${path}`)) as never
      }
      return new Promise(resolve => { resolveSpyPreparation = resolve }) as never
    })

    const wrapper = mount(ETFHoldingsView)
    await vi.waitFor(() => expect(wrapper.text()).toContain('MSFT'))
    await wrapper.findAll('button.profile-card').find(button => button.text().includes('SPY'))!.trigger('click')
    await vi.waitFor(() => expect(api.post).toHaveBeenCalledWith('/data/ensure', {
      target: { kind: 'instrument', symbol: 'SPY' }, datasets: ['holdings'],
    }, expect.objectContaining({ signal: expect.any(AbortSignal) })))
    const stalePreparationSignal = vi.mocked(api.post).mock.calls[0]?.[2]?.signal
    await wrapper.findAll('button.profile-card').find(button => button.text().includes('QQQ'))!.trigger('click')
    await vi.waitFor(() => expect(wrapper.get('.panel-title-row h2').text()).toBe('QQQ'))
    expect(stalePreparationSignal?.aborted).toBe(true)
    resolveSpyPreparation?.(preparationResponse('SPY', 'unavailable'))
    await flushPromises()

    expect(wrapper.get('.panel-title-row h2').text()).toBe('QQQ')
    expect(wrapper.get('.snapshot-date-line').text()).toContain('Invesco QQQ Trust')
    expect(wrapper.text()).not.toContain('late SPY response failed')
    expect(wrapper.text()).not.toContain('temporarily unavailable')
    wrapper.unmount()
  })

  it('resolves identity inside one selected-fund action and keeps stored-only distinct from issuer refresh', async () => {
    const profileWithoutSnapshot = {
      ...profile,
      id: 3,
      instrument_id: 12,
      symbol: 'IWM',
      name: 'iShares Russell 2000 ETF',
      latest_composition_date: null,
      latest_snapshot_id: null,
      resolved_count: 0,
      unresolved_count: 0,
    }
    vi.mocked(api.get)
      .mockResolvedValueOnce([profileWithoutSnapshot])
      .mockResolvedValueOnce([])
    vi.stubGlobal('crypto', { randomUUID: () => 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d' })
    vi.mocked(api.post)
      .mockResolvedValueOnce({
        request_id: 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d',
        status: 'resolved',
        instrument: { instrument_id: 12, symbol: 'IWM', identity_status: 'verified' },
        source_outcomes: [],
      })
      .mockResolvedValueOnce({
        request_id: 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d',
        instrument_id: 12,
        symbol: 'IWM',
        outcome: 'no_data',
        refresh: false,
        refresh_attempted: false,
        refresh_succeeded: false,
        profile: profileWithoutSnapshot,
        snapshot: null,
        capability: profileWithoutSnapshot.holdings_capability,
        source_provider: null,
        source_operation: null,
        provider_request_log_ids: [],
      })
      .mockResolvedValueOnce({
        request_id: 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d',
        instrument_id: 12,
        symbol: 'IWM',
        outcome: 'held',
        refresh: true,
        refresh_attempted: false,
        refresh_succeeded: false,
        profile: profileWithoutSnapshot,
        snapshot: null,
        capability: profileWithoutSnapshot.holdings_capability,
        source_provider: null,
        source_operation: null,
        provider_request_log_ids: [],
        message: 'Issuer access is unavailable for this fund right now.',
      })

    const wrapper = mount(ETFHoldingsView)
    await vi.waitFor(() => expect(wrapper.text()).toContain('IWM'))
    expect(api.post).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('No saved snapshot is available yet')
    expect(wrapper.get('[data-testid="etf-check-stored"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('[data-testid="etf-request-issuer"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.find('[data-testid="etf-resolve-identity"]').exists()).toBe(false)

    await wrapper.get('[data-testid="etf-check-stored"]').trigger('click')
    await flushPromises()
    expect(api.post).toHaveBeenNthCalledWith(1, '/instruments/acquire', {
      symbol: 'IWM', request_id: 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d',
    })
    expect(api.post).toHaveBeenNthCalledWith(2, '/etf-holdings/IWM/acquire', {
      request_id: 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d',
      refresh: false,
      instrument_id: 12,
    })
    expect(wrapper.text()).toContain('No stored snapshot was returned')

    await wrapper.get('[data-testid="etf-request-issuer"]').trigger('click')
    await flushPromises()
    expect(api.post).toHaveBeenNthCalledWith(3, '/etf-holdings/IWM/acquire', {
      request_id: 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d',
      refresh: true,
      instrument_id: 12,
    })
    expect(wrapper.text()).toContain('Issuer access is unavailable for this fund right now.')
    wrapper.unmount()
  })

  it('preserves a typed unavailable result when no ETF profile was returned', async () => {
    const unresolvedProfile = {
      ...profile,
      id: 3,
      instrument_id: 12,
      symbol: 'IWM',
      name: 'iShares Russell 2000 ETF',
      latest_composition_date: null,
      latest_snapshot_id: null,
      resolved_count: 0,
      unresolved_count: 0,
    }
    vi.mocked(api.get).mockResolvedValueOnce([unresolvedProfile]).mockResolvedValueOnce([])
    vi.stubGlobal('crypto', { randomUUID: () => 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d' })
    vi.mocked(api.post)
      .mockResolvedValueOnce({
        request_id: 'identity', status: 'resolved',
        instrument: { instrument_id: 12, symbol: 'IWM', identity_status: 'resolved' }, source_outcomes: [],
      })
      .mockResolvedValueOnce({
        request_id: 'holdings', instrument_id: 12, symbol: 'IWM', outcome: 'unavailable',
        refresh: true, refresh_attempted: false, refresh_succeeded: false,
        profile: null, snapshot: null, capability: null, provider_request_log_ids: [],
        message: 'Issuer profile is not available for this selected fund.',
      })

    const wrapper = mount(ETFHoldingsView)
    await vi.waitFor(() => expect(wrapper.text()).toContain('IWM'))
    await wrapper.get('[data-testid="etf-request-issuer"]').trigger('click')
    await flushPromises()

    expect(api.post).toHaveBeenNthCalledWith(2, '/etf-holdings/IWM/acquire', expect.objectContaining({
      refresh: true,
      instrument_id: 12,
    }))
    expect(wrapper.text()).toContain('Issuer profile is not available for this selected fund.')
    expect(wrapper.text()).not.toContain('Issuer refresh did not complete')
    expect(wrapper.text()).not.toContain('undefined')
    wrapper.unmount()
  })

  it('does not display a returned profile bound to a different selected ETF', async () => {
    const selectedProfile = {
      ...profile,
      id: 3,
      instrument_id: 12,
      symbol: 'IWM',
      name: 'iShares Russell 2000 ETF',
      latest_composition_date: null,
      latest_snapshot_id: null,
      resolved_count: 0,
      unresolved_count: 0,
    }
    vi.mocked(api.get).mockResolvedValueOnce([selectedProfile]).mockResolvedValueOnce([])
    vi.stubGlobal('crypto', { randomUUID: () => 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d' })
    vi.mocked(api.post)
      .mockResolvedValueOnce({
        request_id: 'r',
        status: 'resolved',
        instrument: { instrument_id: 12, symbol: 'IWM', identity_status: 'resolved' },
        source_outcomes: [],
      })
      .mockResolvedValueOnce({
        request_id: 'r',
        instrument_id: 12,
        symbol: 'IWM',
        outcome: 'cached',
        refresh: false,
        refresh_attempted: false,
        refresh_succeeded: false,
        profile,
        snapshot: null,
        capability: profile.holdings_capability,
        source_provider: null,
        source_operation: null,
        provider_request_log_ids: [],
      })

    const wrapper = mount(ETFHoldingsView)
    await vi.waitFor(() => expect(wrapper.text()).toContain('IWM'))
    await wrapper.get('[data-testid="etf-request-issuer"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('The holdings profile did not match IWM')
    expect(wrapper.text()).not.toContain('SPY')
    expect(api.get).not.toHaveBeenCalledWith('/etf-holdings/SPY/holdings', expect.anything())
    wrapper.unmount()
  })

  it('stops after a denied identity in the selected-fund action', async () => {
    const profileWithoutSnapshot = {
      ...profile,
      id: 3,
      symbol: 'IWM',
      name: 'iShares Russell 2000 ETF',
      latest_composition_date: null,
      latest_snapshot_id: null,
      resolved_count: 0,
      unresolved_count: 0,
    }
    vi.mocked(api.get).mockResolvedValueOnce([profileWithoutSnapshot]).mockResolvedValueOnce([])
    vi.stubGlobal('crypto', { randomUUID: () => 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d' })
    vi.mocked(api.post).mockResolvedValueOnce({
      request_id: 'r', status: 'identity_conflict', instrument: null, source_outcomes: [],
    })
    const wrapper = mount(ETFHoldingsView)
    await vi.waitFor(() => expect(wrapper.text()).toContain('IWM'))

    await wrapper.get('[data-testid="etf-request-issuer"]').trigger('click')
    await flushPromises()

    expect(api.post).toHaveBeenCalledTimes(1)
    expect(api.post).toHaveBeenCalledWith('/instruments/acquire', {
      symbol: 'IWM', request_id: 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d',
    })
    expect(wrapper.text()).toContain('identity for IWM conflicts')
    expect(wrapper.text()).toContain('no holdings request was sent')
    expect(wrapper.text()).not.toContain('canonical instrument')
    wrapper.unmount()
  })

  it('keeps the cached snapshot visible when an explicit issuer refresh is held', async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce([profile])
      .mockResolvedValueOnce(dates)
      .mockResolvedValueOnce(holdingsPage())
      .mockResolvedValueOnce(diffPayload())
      .mockResolvedValueOnce(weightEvolutionPayload())
      .mockResolvedValueOnce(transitionTimelinePayload())
    vi.stubGlobal('crypto', { randomUUID: () => 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d' })
    vi.mocked(api.post)
      .mockResolvedValueOnce({
        request_id: 'r', status: 'resolved',
        instrument: { instrument_id: 10, symbol: 'SPY', identity_status: 'verified' }, source_outcomes: [],
      })
      .mockResolvedValueOnce({
        request_id: 'r', instrument_id: 10, symbol: 'SPY', outcome: 'held', refresh: true, refresh_attempted: false, refresh_succeeded: false,
        profile, snapshot: null, capability: profile.holdings_capability, provider_request_log_ids: [],
        message: 'Issuer refresh is paused; stored data remains readable.',
      })
    const wrapper = mount(ETFHoldingsView)
    await vi.waitFor(() => expect(wrapper.text()).toContain('MSFT'))
    const cachedKnownAt = wrapper.get('[data-testid="etf-snapshot-known-at"]').attributes('datetime')

    await wrapper.get('[data-testid="etf-request-issuer"]').trigger('click')
    await flushPromises()

    expect(api.post).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('MSFT')
    expect(wrapper.get('[data-testid="etf-snapshot-known-at"]').attributes('datetime')).toBe(cachedKnownAt)
    expect(wrapper.text()).toContain('Issuer refresh is paused; stored data remains readable.')
    wrapper.unmount()
  })

})
