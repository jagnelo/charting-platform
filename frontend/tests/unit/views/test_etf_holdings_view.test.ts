import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ETFHoldingsView from '@/views/ETFHoldingsView.vue'
import { holdingDrilldownRouteQuery, type ETFHoldingDrilldownContext } from '@/lib/etfHoldingDrilldown'

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
    expect(routerPush).toHaveBeenCalledWith({
      path: '/legacy/chart/MSFT',
      query: {
        holding_snapshot_id: '55',
        holding_composition_date: '2026-06-07',
        holding_known_at: '2026-06-07T04:15:00Z',
        holding_provenance: 'issuer_current_holdings',
        holding_instrument_id: '200',
      },
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
    expect(routerPush).toHaveBeenCalledWith({
      path: '/legacy/chart/MSFT',
      query: {
        holding_snapshot_id: '55',
        holding_composition_date: '2026-06-07',
        holding_known_at: '2026-06-07T04:15:00Z',
        holding_provenance: 'issuer_current_holdings',
        holding_instrument_id: '200',
      },
    })
    expect(wrapper.find('.panel-meta').text()).toContain('Profile current eligibility: stale')
    expect(api.post).not.toHaveBeenCalled()
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
    searchBars[1]!.vm.$emit('select', 'UNXQ', {
      instrument_id: context.instrumentId,
      explicitlyResolved: true,
      identity_status: 'verified',
    })
    await nextTick()
    expect(routerPush).toHaveBeenCalledWith({
      path: '/legacy/chart/UNXQ',
      query: holdingDrilldownRouteQuery(context),
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
    expect(picker.props('resultTypes')).toEqual(['ETF', 'Fund'])
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
    expect(wrapper.text()).toContain('No stored snapshot is selected')
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
    })
    expect(wrapper.text()).toContain('No stored snapshot was returned')

    await wrapper.get('[data-testid="etf-request-issuer"]').trigger('click')
    await flushPromises()
    expect(api.post).toHaveBeenNthCalledWith(3, '/etf-holdings/IWM/acquire', {
      request_id: 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d',
      refresh: true,
    })
    expect(wrapper.text()).toContain('Issuer access is unavailable for this fund right now.')
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
        request_id: 'r', outcome: 'held', refresh: true, refresh_attempted: false, refresh_succeeded: false,
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
