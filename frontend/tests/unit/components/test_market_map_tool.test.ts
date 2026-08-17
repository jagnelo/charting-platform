import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGet, apiPost, loadWatchlistSources, loadWatchlists, createWatchlist, addItem } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn(), loadWatchlistSources: vi.fn(), loadWatchlists: vi.fn(), createWatchlist: vi.fn(), addItem: vi.fn() }))
const sourceState = vi.hoisted(() => ({
  sources: [{ source_id: 'market-group:sp500', source_kind: 'index_membership', name: 'S&P 500', locked: true, can_follow: true, can_clone: true, can_edit_membership: false, member_count: 2, provenance: {} }],
  watchlists: [],
  loading: false,
  error: '',
}))

vi.mock('@/lib/api', () => ({ api: { get: apiGet, post: apiPost, delete: vi.fn() } }))
vi.mock('@/stores/watchlist', () => ({ useWatchlistStore: () => ({ watchlistSources: sourceState.sources, watchlistSourcesLoading: sourceState.loading, watchlistSourcesError: sourceState.error, watchlists: sourceState.watchlists, loadWatchlistSources, loadWatchlists, createWatchlist, addItem }) }))

import MarketMapTool from '@/components/workstation/MarketMapTool.vue'

const response = {
  source: sourceState.sources[0],
  group_by: 'sector_industry', period: '1D', period_start: '2026-08-06T00:00:00Z', period_end: '2026-08-07T00:00:00Z', timeframe: 'D1', adjustment: 'split_adjusted', area_metric: 'market_cap', color_metric: 'return', membership_version: 'market-group:sp500:current', calculation_version: 'market-map-v1', cache_key: 'cache', freshness: 'current', freshness_detail: { requested: 2, current: 2, stale: 0, other: 0 }, requested_count: 2, evaluated_count: 2, coverage: 1, warnings: [], exclusions: [], nodes: [{ node_id: 'root', level: 'root', label: 'All members', group_path: [], member_count: 2, covered_count: 2, area_total: 150, color_value: 0.1, coverage: 1, aggregation_method: 'area_weighted_mean', warnings: [] }, { node_id: 'group:Technology', parent_id: 'root', level: 'sector', label: 'Technology', group_path: ['Technology'], member_count: 2, covered_count: 2, area_total: 150, color_value: 0.1, coverage: 1, aggregation_method: 'area_weighted_mean', warnings: [] }],
  cache_hit: true, cached_at: '2026-08-07T15:30:00Z', cells: [{ instrument_id: 1, symbol: 'NVDA', name: 'NVIDIA', sector: 'Technology', industry: 'Semiconductors', group_path: ['Technology', 'Semiconductors'], area_value: 100, color_value: 0.1, return_value: 0.1, observation_time: '2026-08-07T00:00:00Z', coverage: 1, warnings: [] }, { instrument_id: 2, symbol: 'MSFT', name: 'Microsoft', sector: 'Technology', industry: 'Software', group_path: ['Technology', 'Software'], area_value: 50, color_value: -0.02, return_value: -0.02, observation_time: '2026-08-07T00:00:00Z', coverage: 1, warnings: [] }],
}

describe('MarketMapTool', () => {
  beforeEach(() => {
    apiPost.mockReset()
    apiGet.mockReset()
    loadWatchlistSources.mockReset()
    loadWatchlists.mockReset()
    createWatchlist.mockReset()
    addItem.mockReset()
    sourceState.watchlists = []
    apiPost.mockResolvedValue(response)
    apiGet.mockResolvedValue([])
  })

  it('loads a locked source, renders tiles, persists controls, and publishes a selected symbol', async () => {
    const wrapper = mount(MarketMapTool)
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/analysis/market-map', expect.objectContaining({ source_id: 'market-group:sp500', group_by: 'sector_industry' }))
    expect(wrapper.text()).toContain('Locked source')
    expect(wrapper.text()).toContain('Cached result')
    expect(wrapper.text()).toContain('Combined 100%')
    expect(wrapper.text()).toContain('Colour 100%')
    expect(wrapper.text()).toContain('Area 100%')
    expect(wrapper.text()).toContain('NVDA')
    expect(wrapper.text()).not.toContain('Choose a managed index/ETF universe')
    expect(wrapper.findAll('.market-map-tool__tile')).toHaveLength(2)

    await wrapper.get('select[aria-label="Market Map grouping"]').setValue('sector')
    await flushPromises()
    expect(wrapper.emitted('configuration')?.at(-1)?.[0]).toEqual(expect.objectContaining({ group_by: 'sector' }))

    await wrapper.get('.market-map-tool__tile').trigger('click')
    expect(wrapper.emitted('select')).toEqual([['NVDA', 1]])
    await wrapper.get('.market-map-tool__tile').trigger('mouseenter')
    expect(wrapper.find('.market-map-tool__hover').text()).toContain('NVDA')
    await wrapper.findAll('.market-map-tool__tile')[1].trigger('click', { shiftKey: true })
    expect(wrapper.findAll('.market-map-tool__tile--selected')).toHaveLength(2)
    expect(wrapper.emitted('select')).toEqual([['NVDA', 1], ['MSFT', 2]])

    await wrapper.get('select[aria-label="Market Map sort order"]').setValue('symbol_asc')
    expect(wrapper.emitted('configuration')?.at(-1)?.[0]).toEqual(expect.objectContaining({ sort_by: 'symbol_asc' }))
  })

  it('shows empty and failed map states without hiding the source controls', async () => {
    apiPost.mockRejectedValue(new Error('map unavailable'))
    const wrapper = mount(MarketMapTool)
    await flushPromises()
    expect(wrapper.find('[role="alert"]').text()).toContain('map unavailable')
    expect(wrapper.find('select[aria-label="Market Map universe"]').exists()).toBe(true)
  })

  it('drills hierarchy and controls the map viewport without changing the source', async () => {
    const wrapper = mount(MarketMapTool)
    await flushPromises()

    await wrapper.find('.market-map-tool__nodes button').trigger('click')
    expect(wrapper.find('.market-map-tool__breadcrumbs').text()).toContain('Technology')
    expect(wrapper.find('.market-map-tool__tiles').exists()).toBe(true)

    await wrapper.get('[aria-label="Zoom in Market Map"]').trigger('click')
    expect(wrapper.find('[aria-live="polite"]').text()).toBe('125%')
    await wrapper.get('[aria-label="Reset Market Map viewport"]').trigger('click')
    expect(wrapper.find('[aria-live="polite"]').text()).toBe('100%')
    expect(apiPost.mock.calls.length).toBeGreaterThan(0)
  })

  it('publishes an additive selection into a new personal watchlist', async () => {
    createWatchlist.mockResolvedValue({ id: 9, name: 'XLK leaders', is_managed: false, is_locked: false, items: [] })
    addItem.mockResolvedValue({ id: 90, instrument_id: 1 })
    const wrapper = mount(MarketMapTool)
    await flushPromises()

    await wrapper.get('.market-map-tool__tile').trigger('click')
    await wrapper.get('.market-map-tool__tile:nth-child(2)').trigger('click', { shiftKey: true })
    await wrapper.get('[aria-label="Market Map new watchlist name"]').setValue('XLK leaders')
    const saveButton = wrapper.findAll('button').find(button => button.text() === 'Save selection')
    expect(saveButton).toBeDefined()
    await saveButton!.trigger('click')
    await flushPromises()

    expect(createWatchlist).toHaveBeenCalledWith('XLK leaders')
    expect(addItem).toHaveBeenCalledWith(9, 1)
    expect(addItem).toHaveBeenCalledWith(9, 2)
    expect(wrapper.find('[role="status"]').text()).toContain('2 selected members saved')
  })

  it('publishes the canonical source and selected members into breadth and Study Lab', async () => {
    const wrapper = mount(MarketMapTool)
    await flushPromises()

    await wrapper.get('.market-map-tool__tile').trigger('click')
    await wrapper.get('[aria-label="Open source in Market Breadth"]').trigger('click')
    await wrapper.get('[aria-label="Open source in Study Lab"]').trigger('click')

    expect(wrapper.emitted('publishAnalysis')).toEqual([
      [{ target: 'breadth', sourceId: 'market-group:sp500', selectedIds: [1], selectedSymbols: ['NVDA'] }],
      [{ target: 'study_lab', sourceId: 'market-group:sp500', selectedIds: [1], selectedSymbols: ['NVDA'] }],
    ])
  })

  it('saves and reopens a named snapshot without changing the source contract', async () => {
    const snapshot = { id: 12, name: 'Morning leaders', source_id: 'market-group:sp500', membership_version: 'v1', cache_key: 'a'.repeat(64), snapshot_hash: 'b'.repeat(64), created_at: '2026-08-07T15:30:00Z', updated_at: '2026-08-07T15:30:00Z', map: response }
    apiPost.mockReset()
    apiPost.mockImplementation((path: string) => Promise.resolve(path === '/analysis/market-map' ? response : snapshot))
    apiGet.mockImplementation((path: string) => Promise.resolve(path.includes('/snapshots/12') ? snapshot : []))
    const wrapper = mount(MarketMapTool)
    await flushPromises()

    await wrapper.get('[aria-label="Market Map snapshot name"]').setValue('Morning leaders')
    const saveSnapshotButton = wrapper.findAll('button').find(button => button.text() === 'Save snapshot')
    expect(saveSnapshotButton).toBeDefined()
    await saveSnapshotButton!.trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/analysis/market-map/snapshots', { name: 'Morning leaders', cache_key: response.cache_key })
    expect(wrapper.text()).toContain('Snapshot · Morning leaders')
    expect(wrapper.get('[aria-label="Market Map snapshot"]').element.value).toBe('12')
  })

  it('authors a breadth condition and sends it as the map colour definition', async () => {
    apiPost.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/analysis/market-map') return Promise.resolve({ ...response, color_metric: body?.color_metric, condition: body?.condition })
      return Promise.resolve([])
    })
    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'market-group:sp500' } } })
    await flushPromises()

    await wrapper.get('select[aria-label="Market Map colour metric"]').setValue('breadth')
    await wrapper.get('input[aria-label="Market Map breadth moving average period"]').setValue('3')
    await wrapper.get('.market-map-tool__run').trigger('click')
    await flushPromises()

    const request = apiPost.mock.calls.map(call => call[1]).find(body => body?.color_metric === 'breadth')
    expect(request).toEqual(expect.objectContaining({
      color_metric: 'breadth',
      condition: { kind: 'above_moving_average', params: { period: 3, average: 'sma', comparator: 'above' } },
    }))
  })

  it('runs a completed isolated Python output before colouring the map', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/code/assets') return Promise.resolve([{ kind: 'condition', name: 'Momentum score', versions: [{ id: 17, version_number: 2, output_contract: 'series' }] }])
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/analysis/breadth/python') return Promise.resolve({ run_id: 42 })
      if (path === '/analysis/market-map') return Promise.resolve({ ...response, color_metric: body?.color_metric, python_run_id: body?.python_run_id })
      return Promise.resolve([])
    })
    apiGet.mockImplementation((path: string) => {
      if (path === '/code/assets') return Promise.resolve([{ kind: 'condition', name: 'Momentum score', versions: [{ id: 17, version_number: 2, output_contract: 'series' }] }])
      if (path === '/analysis/breadth/python/runs/42') return Promise.resolve({ status: 'completed' })
      return Promise.resolve([])
    })
    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'market-group:sp500', color_metric: 'python', python_code_version_id: 17 } } })
    await flushPromises()
    await wrapper.get('.market-map-tool__run').trigger('click')
    await flushPromises()
    const request = apiPost.mock.calls.map(call => call[1]).find(body => body?.color_metric === 'python')
    expect(request).toEqual(expect.objectContaining({ color_metric: 'python', python_run_id: 42 }))

    await wrapper.get('select[aria-label="Market Map colour metric"]').setValue('return')
    await wrapper.get('select[aria-label="Market Map area metric"]').setValue('python')
    await wrapper.get('.market-map-tool__run').trigger('click')
    await flushPromises()
    const areaRequest = apiPost.mock.calls.map(call => call[1]).find(body => body?.area_metric === 'python')
    expect(areaRequest).toEqual(expect.objectContaining({ area_metric: 'python', python_run_id: 42 }))
  })

  it('authors a provider numeric area field and persists its selection', async () => {
    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'market-group:sp500' } } })
    await flushPromises()

    await wrapper.get('select[aria-label="Market Map area metric"]').setValue('field')
    await wrapper.get('select[aria-label="Market Map provider numeric area field"]').setValue('beta')
    await wrapper.get('.market-map-tool__run').trigger('click')
    await flushPromises()

    const request = apiPost.mock.calls.map(call => call[1]).find(body => body?.area_metric === 'field')
    expect(request).toEqual(expect.objectContaining({ area_metric: 'field', area_field: 'beta' }))
    expect(wrapper.emitted('configuration')?.at(-1)?.[0]).toEqual(expect.objectContaining({ area_metric: 'field', area_field: 'beta' }))
  })

  it('authors an event predicate for Market Map breadth colouring', async () => {
    apiPost.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/analysis/market-map') return Promise.resolve({ ...response, color_metric: body?.color_metric, condition: body?.condition })
      return Promise.resolve([])
    })
    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'market-group:sp500' } } })
    await flushPromises()

    await wrapper.get('select[aria-label="Market Map colour metric"]').setValue('breadth')
    await wrapper.get('select[aria-label="Market Map breadth condition"]').setValue('event')
    await wrapper.get('select[aria-label="Market Map breadth event type"]').setValue('dividend')
    await wrapper.get('input[aria-label="Market Map breadth event lookback"]').setValue('5')
    await wrapper.get('.market-map-tool__run').trigger('click')
    await flushPromises()

    const request = apiPost.mock.calls.map(call => call[1]).find(body => body?.color_metric === 'breadth' && body?.condition?.kind === 'event')
    expect(request).toEqual(expect.objectContaining({
      condition: { kind: 'event', params: { event_type: 'dividend', lookback_days: 5, include_estimates: false } },
    }))
  })

  it('uses a canonical reference source for relative-return map colouring', async () => {
    sourceState.sources.push({ source_id: 'watchlist:reference', source_kind: 'personal', name: 'Reference group', locked: false, can_follow: true, can_clone: true, can_edit_membership: true, member_count: 2, provenance: {} })
    apiPost.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/analysis/market-map') return Promise.resolve({ ...response, color_metric: body?.color_metric, reference_source_id: body?.reference_source_id, reference_source: sourceState.sources[1], reference_series_method: 'derived_equal_weight_return_index' })
      return Promise.resolve([])
    })
    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'market-group:sp500', color_metric: 'relative_return', reference_source_id: 'watchlist:reference' } } })
    await flushPromises()
    await wrapper.get('[aria-label="Market Map reference universe"]').setValue('watchlist:reference')
    await wrapper.get('.market-map-tool__run').trigger('click')
    await flushPromises()

    const request = apiPost.mock.calls.map(call => call[1]).find(body => body?.color_metric === 'relative_return')
    expect(request).toEqual(expect.objectContaining({ reference_source_id: 'watchlist:reference', reference_symbol: null }))
  })
})
