import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiPost, loadWatchlistSources } = vi.hoisted(() => ({ apiPost: vi.fn(), loadWatchlistSources: vi.fn() }))
const sourceState = vi.hoisted(() => ({
  sources: [{ source_id: 'market-group:sp500', source_kind: 'index_membership', name: 'S&P 500', locked: true, can_follow: true, can_clone: true, can_edit_membership: false, member_count: 2, provenance: {} }],
  loading: false,
  error: '',
}))

vi.mock('@/lib/api', () => ({ api: { post: apiPost } }))
vi.mock('@/stores/watchlist', () => ({ useWatchlistStore: () => ({ watchlistSources: sourceState.sources, watchlistSourcesLoading: sourceState.loading, watchlistSourcesError: sourceState.error, loadWatchlistSources }) }))

import MarketMapTool from '@/components/workstation/MarketMapTool.vue'

const response = {
  source: sourceState.sources[0],
  group_by: 'sector_industry', period: '1D', period_start: '2026-08-06T00:00:00Z', period_end: '2026-08-07T00:00:00Z', timeframe: 'D1', adjustment: 'split_adjusted', area_metric: 'market_cap', color_metric: 'return', membership_version: 'market-group:sp500:current', calculation_version: 'market-map-v1', cache_key: 'cache', freshness: 'current', freshness_detail: { requested: 2, current: 2, stale: 0, other: 0 }, requested_count: 2, evaluated_count: 2, coverage: 1, warnings: [], exclusions: [], nodes: [{ node_id: 'root', level: 'root', label: 'All members', group_path: [], member_count: 2, covered_count: 2, area_total: 150, color_value: 0.1, coverage: 1, aggregation_method: 'area_weighted_mean', warnings: [] }, { node_id: 'group:Technology', parent_id: 'root', level: 'sector', label: 'Technology', group_path: ['Technology'], member_count: 2, covered_count: 2, area_total: 150, color_value: 0.1, coverage: 1, aggregation_method: 'area_weighted_mean', warnings: [] }],
  cells: [{ instrument_id: 1, symbol: 'NVDA', name: 'NVIDIA', sector: 'Technology', industry: 'Semiconductors', group_path: ['Technology', 'Semiconductors'], area_value: 100, color_value: 0.1, return_value: 0.1, observation_time: '2026-08-07T00:00:00Z', coverage: 1, warnings: [] }, { instrument_id: 2, symbol: 'MSFT', name: 'Microsoft', sector: 'Technology', industry: 'Software', group_path: ['Technology', 'Software'], area_value: 50, color_value: -0.02, return_value: -0.02, observation_time: '2026-08-07T00:00:00Z', coverage: 1, warnings: [] }],
}

describe('MarketMapTool', () => {
  beforeEach(() => {
    apiPost.mockReset()
    loadWatchlistSources.mockReset()
    apiPost.mockResolvedValue(response)
  })

  it('loads a locked source, renders tiles, persists controls, and publishes a selected symbol', async () => {
    const wrapper = mount(MarketMapTool)
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/analysis/market-map', expect.objectContaining({ source_id: 'market-group:sp500', group_by: 'sector_industry' }))
    expect(wrapper.text()).toContain('Locked source')
    expect(wrapper.text()).toContain('NVDA')
    expect(wrapper.findAll('.market-map-tool__tile')).toHaveLength(2)

    await wrapper.get('select[aria-label="Market Map grouping"]').setValue('sector')
    await flushPromises()
    expect(wrapper.emitted('configuration')?.at(-1)?.[0]).toEqual(expect.objectContaining({ group_by: 'sector' }))

    await wrapper.get('.market-map-tool__tile').trigger('click')
    expect(wrapper.emitted('select')).toEqual([['NVDA', 1]])
  })

  it('shows empty and failed map states without hiding the source controls', async () => {
    apiPost.mockRejectedValue(new Error('map unavailable'))
    const wrapper = mount(MarketMapTool)
    await flushPromises()
    expect(wrapper.find('[role="alert"]').text()).toContain('map unavailable')
    expect(wrapper.find('select[aria-label="Market Map universe"]').exists()).toBe(true)
  })
})
