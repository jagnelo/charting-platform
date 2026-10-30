import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import ETFHoldingResolutionAction from '@/components/etf/ETFHoldingResolutionAction.vue'
import { api } from '@/lib/api'
import {
  createETFHoldingDrilldownContext,
  holdingDrilldownRouteQuery,
  isEligibleUnresolvedEquityHolding,
} from '@/lib/etfHoldingDrilldown'
import type { ETFHolding, ETFHoldingsSnapshot } from '@/types'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }))

const holding: ETFHolding = {
  id: 32,
  snapshot_id: 7,
  constituent_instrument_id: null,
  constituent_symbol: null,
  reported_symbol: 'UNXQ',
  reported_name: 'Unlisted Example Corp',
  source_row_id: 'issuer-row-32',
  position: 1,
  holding_type: 'equity',
  row_type: 'security',
  is_resolved: false,
  weight: '0.025',
}

const snapshot: ETFHoldingsSnapshot = {
  id: 7,
  etf_profile_id: 3,
  etf_instrument_id: 4,
  etf_symbol: 'OIH',
  etf_name: 'Oil Services ETF',
  composition_date: '2026-10-27',
  known_at: '2026-10-28T12:00:00Z',
  provenance: 'issuer_current_holdings',
  source_provider: 'vaneck_fixture',
  source_quality: 'issuer_current',
  completeness_status: 'complete',
  row_count: 1,
  resolved_count: 0,
  unresolved_count: 1,
  parser_version: 'fixture-v1',
  holdings: [holding],
}

describe('ETFHoldingResolutionAction', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
    vi.stubGlobal('crypto', { randomUUID: () => 'c1de14e1-d595-4e68-a7aa-0ae10cb8fe20' })
  })

  it('does nothing until the row action and source discovery are explicitly clicked, then emits exact resolved identity with holding lineage', async () => {
    vi.mocked(api.post)
      .mockResolvedValueOnce({
        request_id: 'c1de14e1-d595-4e68-a7aa-0ae10cb8fe20',
        status: 'complete',
        candidates: [{ symbol: 'UNXQ', name: 'Unlisted Example Corp', exchange: 'XNYS', type: 'Equity', provider: 'free-source', instrument_id: null, identity_status: 'unresolved' }],
        source_outcomes: [],
      })
      .mockResolvedValueOnce({
        request_id: 'c1de14e1-d595-4e68-a7aa-0ae10cb8fe20',
        status: 'resolved',
        instrument: { instrument_id: 987654, symbol: 'UNXQ', identity_status: 'verified' },
        source_outcomes: [],
      })

    const wrapper = mount(ETFHoldingResolutionAction, {
      props: { holding, snapshot, available: true },
      global: { stubs: { RouterLink: true } },
    })

    expect(api.get).not.toHaveBeenCalled()
    expect(api.post).not.toHaveBeenCalled()
    await wrapper.get('button').trigger('click')
    expect(wrapper.get('input').element.value).toBe('UNXQ')
    expect(wrapper.get('input').attributes('readonly')).toBeDefined()
    expect(api.get).not.toHaveBeenCalled()
    expect(api.post).not.toHaveBeenCalled()

    await wrapper.get('button').trigger('click')
    expect(api.post).toHaveBeenNthCalledWith(1, '/instruments/discover', {
      query: 'UNXQ', types: ['Equity', 'Stock'], limit: 10, request_id: 'c1de14e1-d595-4e68-a7aa-0ae10cb8fe20',
    })
    await vi.waitFor(() => expect(wrapper.find('.search-source-candidate').exists()).toBe(true))
    await wrapper.get('.search-source-candidate').trigger('click')
    expect(api.post).toHaveBeenNthCalledWith(2, '/instruments/acquire', {
      symbol: 'UNXQ',
      provider_candidate: { provider: 'free-source', symbol: 'UNXQ', exchange: 'XNYS' },
      request_id: 'c1de14e1-d595-4e68-a7aa-0ae10cb8fe20',
    })
    expect(wrapper.emitted('resolved')?.[0]).toMatchObject([
      'UNXQ',
      {
        instrumentId: 987654,
        canonicalSymbol: 'UNXQ',
        snapshotId: 7,
        compositionDate: '2026-10-27',
        knownAt: '2026-10-28T12:00:00Z',
        provenance: 'issuer_current_holdings',
        sourceProvider: 'vaneck_fixture',
        holdingRowId: 32,
        sourceRowId: 'issuer-row-32',
        reportedSymbol: 'UNXQ',
        reportedName: 'Unlisted Example Corp',
      },
    ])
    expect(holding.is_resolved).toBe(false)
    expect(holding.constituent_instrument_id).toBeNull()

    const context = createETFHoldingDrilldownContext(snapshot, holding, 987654, 'UNXQ')
    expect(holdingDrilldownRouteQuery(context)).toMatchObject({
      holding_snapshot_id: '7',
      holding_composition_date: '2026-10-27',
      holding_known_at: '2026-10-28T12:00:00Z',
      holding_provenance: 'issuer_current_holdings',
      holding_source_provider: 'vaneck_fixture',
      holding_row_id: '32',
      holding_source_row_id: 'issuer-row-32',
      holding_reported_symbol: 'UNXQ',
      holding_reported_name: 'Unlisted Example Corp',
    })
  })

  it('keeps held, conflict, no-match, and non-exact identity results nonpositive', async () => {
    vi.mocked(api.post)
      .mockResolvedValueOnce({ status: 'held', candidates: [], source_outcomes: [] })
      .mockResolvedValueOnce({ status: 'complete', candidates: [{ symbol: 'UNXQ', name: 'Example', exchange: 'X', type: 'Equity', provider: 'free-source', instrument_id: null, identity_status: 'unresolved' }], source_outcomes: [] })
      .mockResolvedValueOnce({ status: 'identity_conflict', instrument: null, source_outcomes: [] })

    const wrapper = mount(ETFHoldingResolutionAction, {
      props: { holding, snapshot, available: true },
      global: { stubs: { RouterLink: true } },
    })
    await wrapper.get('button').trigger('click')
    await wrapper.get('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('held'))
    await wrapper.get('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.find('.search-source-candidate').exists()).toBe(true))
    await wrapper.get('.search-source-candidate').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Identity conflict'))
    expect(wrapper.emitted('resolved')).toBeUndefined()
  })

  it.each([
    ['no match', { status: 'no_match', candidates: [], source_outcomes: [] }, 'No source candidates matched'],
    ['unavailable', { status: 'unavailable', candidates: [], source_outcomes: [] }, 'unavailable'],
  ])('keeps %s discovery nonpositive', async (_label, response, expectedMessage) => {
    vi.mocked(api.post).mockResolvedValueOnce(response)
    const wrapper = mount(ETFHoldingResolutionAction, {
      props: { holding, snapshot, available: true },
      global: { stubs: { RouterLink: true } },
    })
    await wrapper.get('button').trigger('click')
    await wrapper.get('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text().toLowerCase()).toContain(expectedMessage.toLowerCase()))
    expect(wrapper.emitted('resolved')).toBeUndefined()
  })

  it('keeps discovery transport errors visible and never emits a chart handoff', async () => {
    vi.mocked(api.post).mockRejectedValueOnce(new Error('fixture transport failure'))
    const wrapper = mount(ETFHoldingResolutionAction, {
      props: { holding, snapshot, available: true },
      global: { stubs: { RouterLink: true } },
    })
    await wrapper.get('button').trigger('click')
    await wrapper.get('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Free source discovery failed'))
    expect(wrapper.emitted('resolved')).toBeUndefined()
  })

  it.each([
    ['cash row', { ...holding, row_type: 'cash', holding_type: 'cash' }],
    ['reference row', { ...holding, row_type: 'reference' }],
    ['synthetic symbol', { ...holding, reported_symbol: 'HOLDING-UNXQ' }],
    ['synthetic metadata', { ...holding, extra_data: { is_synthetic: true } }],
    ['missing symbol', { ...holding, reported_symbol: null }],
    ['already resolved', { ...holding, is_resolved: true, constituent_instrument_id: 987654 }],
    ['inconsistent unresolved ID', { ...holding, constituent_instrument_id: 987654 }],
  ])('does not expose a row action for %s', (_label, row) => {
    const wrapper = mount(ETFHoldingResolutionAction, {
      props: { holding: row as ETFHolding, snapshot, available: true },
    })
    expect(wrapper.find('button').exists()).toBe(false)
    expect(api.post).not.toHaveBeenCalled()
  })

  it('holds eligible rows when current analysis capability is unavailable', () => {
    const wrapper = mount(ETFHoldingResolutionAction, {
      props: { holding, snapshot, available: false },
    })
    expect(wrapper.find('button').exists()).toBe(false)
    expect(api.post).not.toHaveBeenCalled()
  })

  it('checks row eligibility independently of a reported ticker being a canonical identity', () => {
    expect(isEligibleUnresolvedEquityHolding(holding)).toBe(true)
    expect(isEligibleUnresolvedEquityHolding({ ...holding, reported_symbol: 'HOLDING-32' })).toBe(false)
  })
})
