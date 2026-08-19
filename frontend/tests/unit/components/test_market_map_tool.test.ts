import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGet, apiPost, loadWatchlistSources, loadWatchlists, resolveWatchlistSource, createWatchlist, addItem, loadUserSettings, toggleFollowedSource, togglePinnedSource, invalidateQueries } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn(), loadWatchlistSources: vi.fn(), loadWatchlists: vi.fn(), resolveWatchlistSource: vi.fn(), createWatchlist: vi.fn(), addItem: vi.fn(), loadUserSettings: vi.fn(), toggleFollowedSource: vi.fn(), togglePinnedSource: vi.fn(), invalidateQueries: vi.fn() }))
const sourceState = vi.hoisted(() => ({
  sources: [{ source_id: 'market-group:sp500', source_kind: 'index_membership', name: 'S&P 500', locked: true, can_follow: true, can_clone: true, can_edit_membership: false, member_count: 2, provenance: {} }],
  watchlists: [],
  loading: false,
  error: '',
}))

vi.mock('@/lib/api', () => ({ api: { get: apiGet, post: apiPost, delete: vi.fn() } }))
vi.mock('@tanstack/vue-query', () => ({ useQueryClient: () => ({ invalidateQueries }) }))
vi.mock('@/stores/watchlist', () => ({ useWatchlistStore: () => ({ watchlistSources: sourceState.sources, watchlistSourcesLoading: sourceState.loading, watchlistSourcesError: sourceState.error, watchlists: sourceState.watchlists, loadWatchlistSources, loadWatchlists, resolveWatchlistSource, createWatchlist, addItem }) }))
vi.mock('@/stores/userSettings', () => ({ useUserSettingsStore: () => ({ followedSourceIds: [], pinnedSourceIds: [], loadSettings: loadUserSettings, toggleFollowedSource, togglePinnedSource }) }))

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
    resolveWatchlistSource.mockReset()
    createWatchlist.mockReset()
    addItem.mockReset()
    loadUserSettings.mockReset()
    toggleFollowedSource.mockReset()
    togglePinnedSource.mockReset()
    invalidateQueries.mockReset()
    sourceState.watchlists = []
    apiPost.mockResolvedValue(response)
    apiGet.mockResolvedValue([])
  })

  it('persists follow and pin preferences without changing locked source membership', async () => {
    const wrapper = mount(MarketMapTool)
    await flushPromises()

    expect(loadUserSettings).toHaveBeenCalled()
    await wrapper.get('[aria-label="Follow S&P 500"]').trigger('click')
    await wrapper.get('[aria-label="Pin S&P 500"]').trigger('click')

    expect(toggleFollowedSource).toHaveBeenCalledWith('market-group:sp500')
    expect(togglePinnedSource).toHaveBeenCalledWith('market-group:sp500')
    expect(wrapper.text()).toContain('Locked source')
    expect(wrapper.find('[aria-label="Market Map universe"]').element.value).toBe('market-group:sp500')
  })

  it('persists a selected subset as a durable locked explicit source with parent lineage', async () => {
    apiPost.mockImplementation((path: string) => path === '/watchlists/sources/explicit'
      ? Promise.resolve({
          ...sourceState.sources[0],
          source_id: 'explicit-list:selection-test',
          source_kind: 'explicit',
          name: 'Saved technology leaders',
          locked: true,
          member_count: 1,
        })
      : Promise.resolve(response))
    const wrapper = mount(MarketMapTool)
    await flushPromises()

    await wrapper.get('.market-map-tool__tile').trigger('click')
    await wrapper.get('[aria-label="Market Map locked source name"]').setValue('Saved technology leaders')
    await wrapper.get('[aria-label="Save selected members as locked source"]').trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/watchlists/sources/explicit', {
      name: 'Saved technology leaders',
      instrument_ids: [1],
      parent_source_id: 'market-group:sp500',
      parent_membership_version: 'market-group:sp500:current',
    })
    expect(loadWatchlistSources).toHaveBeenCalled()
    expect(wrapper.text()).toContain('saved as locked source Saved technology leaders')
  })

  it('clones the complete canonical locked source with membership provenance', async () => {
    resolveWatchlistSource.mockResolvedValue({
      source: { ...sourceState.sources[0], composition_date: '2026-08-07', membership_version: 'sp500:2026-08-07' },
      members: [
        { instrument_id: 1, position: 0, relationship_type: 'constituent', effective_at: '2026-08-07T00:00:00Z', known_at: '2026-08-07T00:00:00Z' },
        { instrument_id: 2, position: 1, relationship_type: 'constituent', effective_at: '2026-08-07T00:00:00Z', known_at: '2026-08-07T00:00:00Z' },
      ],
      exclusions: [],
    })
    createWatchlist.mockResolvedValue({ id: 11, name: 'S&P 500 snapshot 2026-08-07', is_managed: false, is_locked: false, items: [] })
    addItem.mockResolvedValue({ id: 110, instrument_id: 1 })
    const wrapper = mount(MarketMapTool)
    await flushPromises()

    await wrapper.get('[aria-label="Clone S&P 500 snapshot"]').trigger('click')
    await flushPromises()

    expect(resolveWatchlistSource).toHaveBeenCalledWith('market-group:sp500', null)
    expect(createWatchlist).toHaveBeenCalledWith(
      'S&P 500 snapshot 2026-08-07',
      expect.stringContaining('membership_version=sp500:2026-08-07'),
    )
    expect(addItem).toHaveBeenCalledWith(11, 1)
    expect(addItem).toHaveBeenCalledWith(11, 2)
    expect(wrapper.get('[aria-label="Market Map source preferences"] [role="status"]').text()).toContain('2/2 members cloned')
  })

  it('keeps failed clone members retryable without hiding the partial copy', async () => {
    resolveWatchlistSource.mockResolvedValue({
      source: { ...sourceState.sources[0], membership_version: 'sp500:retry' },
      members: [
        { instrument_id: 1, position: 0, relationship_type: 'constituent' },
        { instrument_id: 2, position: 1, relationship_type: 'constituent' },
      ],
      exclusions: [],
    })
    createWatchlist.mockResolvedValue({ id: 12, name: 'S&P 500 snapshot retry', is_managed: false, is_locked: false, items: [] })
    addItem.mockResolvedValueOnce({ id: 121, instrument_id: 1 }).mockResolvedValueOnce(null)
    const wrapper = mount(MarketMapTool)
    await flushPromises()

    await wrapper.get('[aria-label="Clone S&P 500 snapshot"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[aria-label="Market Map source preferences"] [role="status"]').text()).toContain('1/2 members cloned')
    expect(wrapper.get('[aria-label="Retry failed source clone members"]')).toBeTruthy()

    addItem.mockResolvedValueOnce({ id: 122, instrument_id: 2 })
    await wrapper.get('[aria-label="Retry failed source clone members"]').trigger('click')
    await flushPromises()

    expect(addItem).toHaveBeenCalledTimes(3)
    expect(wrapper.get('[aria-label="Market Map source preferences"] [role="status"]').text()).toContain('2/2 members cloned')
    expect(wrapper.find('[aria-label="Retry failed source clone members"]').exists()).toBe(false)
  })

  it('groups index, ETF, and editable sources while using one locked-source map contract', async () => {
    const previousSources = sourceState.sources
    sourceState.sources = [
      ...previousSources,
      {
        ...previousSources[0],
        source_id: 'benchmark-family:sp500:cap_weight',
        source_kind: 'index_membership',
        name: 'S&P 500 — Cap weight constituents',
        member_count: 500,
        provenance: { availability: 'available', membership_semantics: 'etf_proxy_holdings' },
      },
      {
        ...previousSources[0],
        source_id: 'etf-holdings:SPY',
        source_kind: 'etf_holdings',
        name: 'SPY holdings',
        member_count: 500,
        provenance: { availability: 'available', membership_semantics: 'etf_proxy_holdings' },
      },
      {
        ...previousSources[0],
        source_id: 'watchlist:7',
        source_kind: 'personal',
        name: 'My candidates',
        locked: false,
        member_count: 12,
        provenance: { availability: 'available' },
      },
    ]
    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'benchmark-family:sp500:cap_weight' } } })
    await flushPromises()

    const universe = wrapper.get('[aria-label="Market Map universe"]')
    expect(universe.find('optgroup[label="Index and managed universes"] option[value="benchmark-family:sp500:cap_weight"]').exists()).toBe(true)
    expect(universe.find('optgroup[label="ETF holdings"] option[value="etf-holdings:SPY"]').exists()).toBe(true)
    expect(universe.find('optgroup[label="Personal watchlists"] option[value="watchlist:7"]').exists()).toBe(true)
    expect(wrapper.find('.market-map-tool__source-kind').text()).toContain('Index and managed universes · 500 members')
    expect(apiPost).toHaveBeenCalledWith('/analysis/market-map', expect.objectContaining({ source_id: 'benchmark-family:sp500:cap_weight' }))
    expect(wrapper.text()).toContain('Locked source')

    wrapper.unmount()
    sourceState.sources = previousSources
  })

  it('explicitly bootstraps an arbitrary ETF into the locked source catalog', async () => {
    const previousSources = sourceState.sources
    const pendingEtf = {
      ...previousSources[0],
      source_id: 'etf-holdings:QQQ',
      source_kind: 'etf_holdings' as const,
      name: 'QQQ holdings',
      member_count: 0,
      provenance: { availability: 'profile_not_loaded' },
    }
    sourceState.sources = [...previousSources, pendingEtf]
    apiPost.mockImplementation((path: string) => path === '/etf-holdings/QQQ/bootstrap'
      ? Promise.resolve({ profile: { symbol: 'QQQ' }, latest_snapshot: null, refresh_succeeded: false, message: 'No local holdings snapshot yet.' })
      : Promise.resolve(response))

    const wrapper = mount(MarketMapTool)
    await flushPromises()
    await wrapper.get('[aria-label="ETF universe symbol"]').setValue('qqq')
    await wrapper.get('[aria-label="Load ETF constituent universe"]').trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/etf-holdings/QQQ/bootstrap', {})
    expect(wrapper.get('[aria-label="Market Map universe"]').element.value).toBe('etf-holdings:QQQ')
    expect(wrapper.find('[aria-label="Add ETF constituent universe"] [role="status"]').text()).toContain('membership is pending hydration')

    wrapper.unmount()
    sourceState.sources = previousSources
  })

  it('rejects malformed ETF symbols before any bootstrap request', async () => {
    const wrapper = mount(MarketMapTool)
    await flushPromises()

    await wrapper.get('[aria-label="ETF universe symbol"]').setValue('not a ticker')
    await wrapper.get('[aria-label="Load ETF constituent universe"]').trigger('click')
    await flushPromises()

    expect(apiPost.mock.calls.some(([path]) => String(path).includes('/etf-holdings/'))).toBe(false)
    expect(wrapper.get('[aria-label="Add ETF constituent universe"] [role="alert"]').text()).toContain('canonical ETF symbol')
  })

  it('shows source history readiness and queues an explicit refresh without changing membership', async () => {
    const historyStatus = {
      source_id: 'market-group:sp500',
      source_kind: 'index_membership',
      name: 'S&P 500',
      locked: true,
      membership_version: 'v1',
      max_instruments: 5000,
      available_instrument_count: 2,
      selected_instrument_count: 2,
      limited: false,
      excluded_count: 0,
      overall_status: 'partial',
      timeframes: [{ timeframe: 'D1', member_count: 2, covered_member_count: 1, coverage_percent: 50, bar_count: 3, in_progress_count: 0, complete_count: 1, failed_count: 0, pending_count: 1 }],
    }
    const historyRun = { id: 42, source_ids: ['market-group:sp500'], timeframes: ['D1'], max_instruments: 5000, available_instrument_count: 2, selected_instrument_count: 2, queued_count: 1, already_queued_count: 1, status: 'running', cancel_requested: false, progress: { complete: 1, in_progress: 1 }, created_at: '2026-08-19T00:00:00Z', updated_at: '2026-08-19T00:00:00Z' }
    apiGet.mockImplementation((path: string) => path.includes('/history-status/') ? Promise.resolve(historyStatus) : path.includes('/history-refresh-runs/') ? Promise.resolve(historyRun) : Promise.resolve([]))
    apiPost.mockImplementation((path: string) => {
      if (path === '/analysis/market-map') return Promise.resolve(response)
      if (path === '/watchlists/sources/history-refresh') return Promise.resolve({ run_id: 42, source_ids: ['market-group:sp500'], timeframes: ['D1'], max_instruments: 5000, available_instrument_count: 2, selected_instrument_count: 2, limited: false, queued: 1, already_queued: 1, queue_unavailable: false })
      return Promise.resolve({ ...historyRun, status: 'canceled', cancel_requested: true, progress: { ...historyRun.progress, status: 'canceled' } })
    })

    const wrapper = mount(MarketMapTool)
    await flushPromises()

    expect(wrapper.find('[aria-label="Market Map history readiness"]').text()).toContain('partial')
    expect(wrapper.find('[aria-label="Market Map history readiness"]').text()).toContain('1/2 D1 members covered')
    await wrapper.get('[aria-label="Refresh Market Map history"]').trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/watchlists/sources/history-refresh', {
      source_ids: ['market-group:sp500'],
      timeframes: ['D1'],
      max_instruments: 5000,
    })
    expect(wrapper.find('[aria-label="Market Map history readiness"]').text()).toContain('2 history jobs queued')
    expect(wrapper.find('[aria-label="Market Map history readiness"]').text()).toContain('Run 42 · running · 1/2')
    await wrapper.get('[aria-label="Cancel Market Map history refresh"]').trigger('click')
    await flushPromises()
    expect(apiPost).toHaveBeenCalledWith('/watchlists/history-refresh-runs/42/cancel', {})
    expect(wrapper.find('[aria-label="Market Map history readiness"]').text()).toContain('History refresh canceled')
    expect(wrapper.text()).toContain('Locked source')
  })

  it('keeps unmapped family legs unavailable but lets mapped pending sources remain followable', async () => {
    const previousSources = sourceState.sources
    const pendingSource = {
      ...previousSources[0],
      source_id: 'benchmark-family:sp500:value-pending',
      source_kind: 'index_membership' as const,
      name: 'S&P 500 — Value pending',
      member_count: 0,
      provenance: { availability: 'holdings_snapshot_not_loaded' },
    }
    sourceState.sources = [
      ...previousSources,
      pendingSource,
      {
        ...previousSources[0],
        source_id: 'benchmark-family:sp500:value',
        source_kind: 'index_membership',
        name: 'S&P 500 — Value',
        provenance: { availability: 'unavailable' },
      },
    ]
    apiPost.mockResolvedValue({
      ...response,
      source: pendingSource,
      requested_count: 0,
      evaluated_count: 0,
      coverage: 0,
      color_coverage: 0,
      area_coverage: 0,
      nodes: [],
      cells: [],
    })
    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: pendingSource.source_id } } })
    await flushPromises()

    const pendingOption = wrapper.find(`option[value="${pendingSource.source_id}"]`)
    expect(pendingOption.attributes('disabled')).toBeUndefined()
    expect(pendingOption.text()).toContain('Pending membership')
    expect(wrapper.find('[aria-label="Market Map source preferences"] [role="status"]').text()).toContain('remains followable')
    await wrapper.get(`[aria-label="Follow ${pendingSource.name}"]`).trigger('click')
    expect(toggleFollowedSource).toHaveBeenCalledWith(pendingSource.source_id)

    const option = wrapper.find('option[value="benchmark-family:sp500:value"]')
    expect(option.attributes('disabled')).toBeDefined()
    expect(option.text()).toContain('Unavailable')

    wrapper.unmount()
    sourceState.sources = previousSources
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

    await wrapper.get('select[aria-label="Market Map timeframe"]').setValue('W1')
    await flushPromises()
    expect(wrapper.emitted('configuration')?.at(-1)?.[0]).toEqual(expect.objectContaining({ timeframe: 'W1' }))
    await wrapper.get('.market-map-tool__run').trigger('click')
    await flushPromises()
    expect(apiPost).toHaveBeenLastCalledWith('/analysis/market-map', expect.objectContaining({ timeframe: 'W1' }))

    await wrapper.get('.market-map-tool__tile').trigger('click')
    expect(wrapper.emitted('select')).toEqual([['NVDA', 1]])
    await wrapper.get('.market-map-tool__tile').trigger('mouseenter')
    expect(wrapper.find('.market-map-tool__hover').text()).toContain('NVDA')
    await wrapper.findAll('.market-map-tool__tile')[1].trigger('click', { shiftKey: true })
    expect(wrapper.findAll('.market-map-tool__tile--selected')).toHaveLength(2)
    expect(wrapper.emitted('select')).toEqual([['NVDA', 1], ['MSFT', 2]])
    await wrapper.get('[aria-label="Open selected members in chart"]').trigger('click')
    expect(wrapper.emitted('select')).toEqual([['NVDA', 1], ['MSFT', 2], ['NVDA', 1]])
    await wrapper.get('[aria-label="Compare selected members in chart"]').trigger('click')
    expect(wrapper.emitted('compare')).toEqual([[['NVDA', 'MSFT']]])
    await wrapper.get('[aria-label="Open selected members in relative strength"]').trigger('click')
    expect(wrapper.emitted('ratio')).toEqual([[['NVDA', 'MSFT']]])

    await wrapper.get('select[aria-label="Market Map sort order"]').setValue('symbol_asc')
    expect(wrapper.emitted('configuration')?.at(-1)?.[0]).toEqual(expect.objectContaining({ sort_by: 'symbol_asc' }))
  })

  it('switches a 10,000-member arbitrary universe to one canvas without proportional tile DOM', async () => {
    const largeResponse = {
      ...response,
      requested_count: 10000,
      evaluated_count: 10000,
      freshness_detail: { requested: 10000, current: 10000, stale: 0, other: 0 },
      cells: Array.from({ length: 10000 }, (_, index) => ({
        ...response.cells[0],
        instrument_id: index + 1,
        symbol: `SYM${index + 1}`,
        name: `Synthetic ${index + 1}`,
        group_path: ['Technology'],
        area_value: 1,
        color_value: index % 2 === 0 ? 0.01 : -0.01,
      })),
    }
    apiPost.mockResolvedValue(largeResponse)
    const context = {
      setTransform: vi.fn(),
      clearRect: vi.fn(),
      fillRect: vi.fn(),
      strokeRect: vi.fn(),
      fillText: vi.fn(),
      fillStyle: '',
      strokeStyle: '',
      lineWidth: 1,
      font: '',
      textAlign: 'center',
      textBaseline: 'middle',
    }
    const canvasContext = vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(context as unknown as CanvasRenderingContext2D)
    const previousAnimationFrame = window.requestAnimationFrame
    const previousCancelAnimationFrame = window.cancelAnimationFrame
    const animationFrames: FrameRequestCallback[] = []
    Object.defineProperty(window, 'requestAnimationFrame', { configurable: true, value: (callback: FrameRequestCallback) => { animationFrames.push(callback); return animationFrames.length } })
    Object.defineProperty(window, 'cancelAnimationFrame', { configurable: true, value: vi.fn() })

    const wrapper = mount(MarketMapTool)
    await flushPromises()
    await wrapper.vm.$nextTick()
    window.dispatchEvent(new Event('resize'))
    for (const callback of animationFrames.splice(0)) callback(0)

    expect(wrapper.find('canvas.market-map-tool__canvas-map').exists()).toBe(true)
    expect(wrapper.find('canvas.market-map-tool__canvas-map').attributes('aria-label')).toBe('10000 Market Map members')
    expect(wrapper.findAll('.market-map-tool__tile')).toHaveLength(0)
    expect(wrapper.find('.market-map-tool__canvas-hint').text()).toContain('canvas rendering')
    expect(context.fillRect).toHaveBeenCalled()
    expect(Math.max(...context.strokeRect.mock.invocationCallOrder)).toBeGreaterThan(Math.max(...context.fillRect.mock.invocationCallOrder))

    const previousSetPointerCapture = HTMLElement.prototype.setPointerCapture
    const previousHasPointerCapture = HTMLElement.prototype.hasPointerCapture
    const previousReleasePointerCapture = HTMLElement.prototype.releasePointerCapture
    Object.defineProperty(HTMLElement.prototype, 'setPointerCapture', { configurable: true, value: vi.fn() })
    Object.defineProperty(HTMLElement.prototype, 'hasPointerCapture', { configurable: true, value: vi.fn(() => true) })
    Object.defineProperty(HTMLElement.prototype, 'releasePointerCapture', { configurable: true, value: vi.fn() })
    vi.spyOn(HTMLCanvasElement.prototype, 'getBoundingClientRect').mockReturnValue({ left: 0, top: 0, width: 100, height: 100, right: 100, bottom: 100, x: 0, y: 0, toJSON: () => ({}) } as DOMRect)
    await wrapper.get('[aria-label="Zoom in Market Map"]').trigger('click')
    const viewport = wrapper.get('.market-map-tool__tiles')
    await viewport.trigger('pointerdown', { pointerId: 1, clientX: 1, clientY: 1 })
    await viewport.trigger('pointermove', { pointerId: 1, clientX: 20, clientY: 20 })
    await viewport.trigger('pointerup', { pointerId: 1, clientX: 20, clientY: 20 })
    await wrapper.get('canvas.market-map-tool__canvas-map').trigger('click', { clientX: 0, clientY: 0 })
    expect(wrapper.emitted('select')).toBeUndefined()
    await wrapper.get('[aria-label="Find Large Market Map member"]').setValue('SYM1501')
    await wrapper.get('[aria-label="Find Large Market Map member"]').trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('select')).toEqual([['SYM1501', 1501]])

    wrapper.unmount()
    canvasContext.mockRestore()
    vi.restoreAllMocks()
    Object.defineProperty(HTMLElement.prototype, 'setPointerCapture', { configurable: true, value: previousSetPointerCapture })
    Object.defineProperty(HTMLElement.prototype, 'hasPointerCapture', { configurable: true, value: previousHasPointerCapture })
    Object.defineProperty(HTMLElement.prototype, 'releasePointerCapture', { configurable: true, value: previousReleasePointerCapture })
    Object.defineProperty(window, 'requestAnimationFrame', { configurable: true, value: previousAnimationFrame })
    Object.defineProperty(window, 'cancelAnimationFrame', { configurable: true, value: previousCancelAnimationFrame })
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
    await wrapper.get('[aria-label="Open selected members in Market Breadth"]').trigger('click')
    await wrapper.get('[aria-label="Open selected members in Study Lab"]').trigger('click')

    expect(wrapper.emitted('publishAnalysis')).toEqual([
      [{ target: 'breadth', sourceId: 'market-group:sp500', selectedIds: [1], selectedSymbols: ['NVDA'], scope: 'selection' }],
      [{ target: 'study_lab', sourceId: 'market-group:sp500', selectedIds: [1], selectedSymbols: ['NVDA'], scope: 'selection' }],
    ])
  })

  it('opens the full canonical source without requiring a tile selection', async () => {
    const wrapper = mount(MarketMapTool)
    await flushPromises()

    await wrapper.get('[aria-label="Open full source in Market Breadth"]').trigger('click')
    await wrapper.get('[aria-label="Open full source in Study Lab"]').trigger('click')

    expect(wrapper.emitted('publishAnalysis')).toEqual([
      [{ target: 'breadth', sourceId: 'market-group:sp500', selectedIds: [], selectedSymbols: [], scope: 'full' }],
      [{ target: 'study_lab', sourceId: 'market-group:sp500', selectedIds: [], selectedSymbols: [], scope: 'full' }],
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

  it('exports the current source-agnostic map cells as CSV', async () => {
    const createObjectURL = vi.fn(() => 'blob:market-map')
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', { ...URL, createObjectURL, revokeObjectURL })
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const wrapper = mount(MarketMapTool)
    await flushPromises()

    const exportButton = wrapper.findAll('button').find(button => button.text() === 'Export CSV')
    expect(exportButton).toBeDefined()
    await exportButton!.trigger('click')

    expect(createObjectURL).toHaveBeenCalledOnce()
    expect(anchorClick).toHaveBeenCalledOnce()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:market-map')
    anchorClick.mockRestore()
    vi.unstubAllGlobals()
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

  it('saves the current breadth condition as an immutable Study Lab definition', async () => {
    apiPost.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/analysis/market-map') return Promise.resolve(response)
      if (path === '/code/assets') return Promise.resolve({ versions: [{ id: 91 }] })
      return Promise.resolve(body ?? {})
    })
    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'market-group:sp500' } } })
    await flushPromises()

    await wrapper.get('select[aria-label="Market Map colour metric"]').setValue('breadth')
    await wrapper.get('[aria-label="Market Map breadth definition name"]').setValue('SPY within one percent of highs')
    await wrapper.get('[aria-label="Save as Study Lab definition"]').trigger('click')
    await flushPromises()

    const request = apiPost.mock.calls.find(call => call[0] === '/code/assets')?.[1] as Record<string, any>
    expect(request).toEqual(expect.objectContaining({ kind: 'study', name: 'SPY within one percent of highs' }))
    expect(request.initial_version.output_contract).toBe('study')
    expect(request.initial_version.source).toContain('research.breadth_condition')
    expect(request.initial_version.default_parameters).toEqual(expect.objectContaining({ source_id: 'market-group:sp500' }))
    expect(wrapper.text()).toContain('Saved immutable Study Lab definition.')
    expect(invalidateQueries).toHaveBeenCalled()
  })

  it('supports the reusable nested breadth condition editor for heatmap colours', async () => {
    apiPost.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/analysis/market-map') return Promise.resolve({ ...response, color_metric: body?.color_metric, condition: body?.condition })
      return Promise.resolve([])
    })
    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'market-group:sp500' } } })
    await flushPromises()

    await wrapper.get('select[aria-label="Market Map colour metric"]').setValue('breadth')
    await wrapper.get('input[aria-label="Use advanced Market Map breadth condition editor"]').setValue(true)
    await wrapper.get('select[aria-label="Breadth condition type 1"]').setValue('within_52_week_high')
    await wrapper.get('select[aria-label="Breadth 52-week direction 1"]').setValue('low')
    await wrapper.get('.market-map-tool__run').trigger('click')
    await flushPromises()

    const request = apiPost.mock.calls.map(call => call[1]).find(body => body?.color_metric === 'breadth')
    expect(request).toEqual(expect.objectContaining({
      color_metric: 'breadth',
      condition: { kind: 'within_52_week_high', params: { direction: 'low', threshold: 0.01, lookback: 252 } },
    }))
  })

  it('authors a cross-sectional percentile breadth colour target', async () => {
    apiPost.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/analysis/market-map') return Promise.resolve({ ...response, color_metric: body?.color_metric, condition: body?.condition })
      return Promise.resolve([])
    })
    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'market-group:sp500' } } })
    await flushPromises()

    await wrapper.get('select[aria-label="Market Map colour metric"]').setValue('breadth')
    await wrapper.get('input[aria-label="Use advanced Market Map breadth condition editor"]').setValue(true)
    await wrapper.get('select[aria-label="Breadth condition type 1"]').setValue('percentile')
    await wrapper.get('select[aria-label="Breadth percentile scope 1"]').setValue('cross_sectional')
    await wrapper.get('select[aria-label="Breadth percentile field 1"]').setValue('return')
    await wrapper.get('input[aria-label="Breadth percentile target 1"]').setValue('0.8')
    await wrapper.get('.market-map-tool__run').trigger('click')
    await flushPromises()

    const request = apiPost.mock.calls.map(call => call[1]).find(body => body?.color_metric === 'breadth' && body?.condition?.kind === 'percentile')
    expect(request).toEqual(expect.objectContaining({
      color_metric: 'breadth',
      condition: { kind: 'percentile', target_scope: 'cross_sectional', params: { field: 'return', period: 252, operator: 'gte', percentile: 0.8 } },
    }))
  })

  it('serializes a mixed member and cross-sectional breadth tree for the heatmap', async () => {
    apiPost.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/analysis/market-map') return Promise.resolve({ ...response, color_metric: body?.color_metric, condition: body?.condition })
      return Promise.resolve([])
    })
    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'market-group:sp500' } } })
    await flushPromises()

    await wrapper.get('select[aria-label="Market Map colour metric"]').setValue('breadth')
    await wrapper.get('input[aria-label="Use advanced Market Map breadth condition editor"]').setValue(true)
    await wrapper.get('select[aria-label="Breadth condition type 1"]').setValue('percentile')
    await wrapper.get('select[aria-label="Breadth percentile scope 1"]').setValue('cross_sectional')
    await wrapper.get('button.breadth-condition-tree__wrap').trigger('click')
    await wrapper.get('.breadth-condition-tree__footer button').trigger('click')
    await wrapper.get('select[aria-label="Breadth condition type 1.2"]').setValue('comparison')
    await wrapper.get('.market-map-tool__run').trigger('click')
    await flushPromises()

    const request = apiPost.mock.calls.map(call => call[1]).find(body => body?.color_metric === 'breadth' && body?.condition?.kind === 'all')
    expect(request?.condition).toEqual({
      kind: 'all',
      params: {
        conditions: [
          { kind: 'percentile', target_scope: 'cross_sectional', params: { field: 'close', period: 252, operator: 'gte', percentile: 0.8 } },
          { kind: 'comparison', params: { field: 'close', operator: 'gte', threshold: 0 } },
        ],
      },
    })
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

  it('uses the same Python breadth source contract for derived and explicit watchlists', async () => {
    const previousSources = sourceState.sources
    sourceState.sources = [{ ...previousSources[0], source_id: 'combo:tech-leaders', source_kind: 'combo', name: 'Tech leaders', locked: true }]
    apiGet.mockImplementation((path: string) => {
      if (path === '/code/assets') return Promise.resolve([{ kind: 'condition', name: 'Momentum score', versions: [{ id: 17, version_number: 1, output_contract: 'boolean' }] }])
      if (path === '/analysis/breadth/python/runs/42') return Promise.resolve({ status: 'completed' })
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/analysis/breadth/python') return Promise.resolve({ run_id: 42 })
      if (path === '/analysis/market-map') return Promise.resolve({ ...response, source: { ...response.source, source_id: body?.source_id }, color_metric: body?.color_metric, python_run_id: body?.python_run_id })
      return Promise.resolve([])
    })
    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'combo:tech-leaders', color_metric: 'python', python_code_version_id: 17 } } })
    await flushPromises()
    await wrapper.get('.market-map-tool__run').trigger('click')
    await flushPromises()
    const request = apiPost.mock.calls.find(call => call[0] === '/analysis/breadth/python')?.[1]
    expect(request).toEqual(expect.objectContaining({ universe: { kind: 'watchlist', key: 'combo:tech-leaders', point_in_time: true } }))
    wrapper.unmount()
    sourceState.sources = previousSources
  })

  it('uses the same Python breadth source contract for benchmark-family legs', async () => {
    const previousSources = sourceState.sources
    sourceState.sources = [{
      ...previousSources[0],
      source_id: 'benchmark-family:sp500:cap_weight',
      source_kind: 'index_membership',
      name: 'S&P 500 — Cap weight',
      locked: true,
    }]
    apiGet.mockImplementation((path: string) => {
      if (path === '/code/assets') return Promise.resolve([{ kind: 'condition', name: 'Momentum score', versions: [{ id: 17, version_number: 1, output_contract: 'boolean' }] }])
      if (path === '/analysis/breadth/python/runs/42') return Promise.resolve({ status: 'completed' })
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/analysis/breadth/python') return Promise.resolve({ run_id: 42 })
      if (path === '/analysis/market-map') return Promise.resolve({ ...response, source: { ...response.source, source_id: body?.source_id }, color_metric: body?.color_metric, python_run_id: body?.python_run_id })
      return Promise.resolve([])
    })
    const wrapper = mount(MarketMapTool, { props: { configuration: { source_id: 'benchmark-family:sp500:cap_weight', color_metric: 'python', python_code_version_id: 17 } } })
    await flushPromises()
    await wrapper.get('.market-map-tool__run').trigger('click')
    await flushPromises()
    const request = apiPost.mock.calls.find(call => call[0] === '/analysis/breadth/python')?.[1]
    expect(request).toEqual(expect.objectContaining({
      universe: { kind: 'watchlist', key: 'benchmark-family:sp500:cap_weight', point_in_time: true },
    }))
    wrapper.unmount()
    sourceState.sources = previousSources
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

  it('sends an arbitrary completed-session custom period for any watchlist source', async () => {
    const wrapper = mount(MarketMapTool, {
      props: {
        configuration: {
          source_id: 'market-group:sp500',
          period: 'CUSTOM',
          start_date: '2026-01-05',
          end_date: '2026-02-06',
        },
      },
    })
    await flushPromises()

    const request = apiPost.mock.calls.map(call => call[1]).find(body => body?.period === 'CUSTOM')
    expect(request).toEqual(expect.objectContaining({
      period: 'CUSTOM',
      start: '2026-01-05',
      end: '2026-02-06T23:59:59Z',
    }))
    await wrapper.get('[aria-label="Market Map custom start date"]').setValue('2026-01-06')
    expect(wrapper.emitted('configuration')?.at(-1)?.[0]).toEqual(expect.objectContaining({
      period: 'CUSTOM',
      start_date: '2026-01-06',
      end_date: '2026-02-06',
    }))
  })

  it('resolves explicit symbols to canonical IDs before building an ephemeral map source', async () => {
    apiGet.mockImplementation((path: string) => {
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/instruments/resolve-canonical') {
        expect(body).toEqual({ symbols: ['NVDA', 'MSFT'] })
        return Promise.resolve({ resolved: [{ symbol: 'NVDA', instrument_id: 1 }, { symbol: 'MSFT', instrument_id: 2 }], missing: [] })
      }
      return Promise.resolve(response)
    })
    const wrapper = mount(MarketMapTool, { props: { configuration: { explicit_symbols: 'NVDA, MSFT' } } })
    await flushPromises()

    const request = apiPost.mock.calls.map(call => call[1]).find(body => body?.source_id?.startsWith('explicit:'))
    expect(request).toEqual(expect.objectContaining({ source_id: 'explicit:1,2' }))
    expect(wrapper.emitted('configuration')?.at(-1)?.[0]).toEqual(expect.objectContaining({
      explicit_symbols: 'NVDA, MSFT',
      source_id: 'explicit:1,2',
    }))
  })

  it('saves the complete explicit canonical selection as a personal watchlist', async () => {
    const explicitResponse = {
      ...response,
      source: { ...response.source, source_id: 'explicit:1,2', source_kind: 'explicit', name: 'Explicit symbols (2)', can_follow: false, can_clone: false, provenance: { instrument_ids: [1, 2] } },
    }
    apiPost.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/instruments/resolve-canonical') return Promise.resolve({ resolved: [{ symbol: 'NVDA', instrument_id: 1 }, { symbol: 'MSFT', instrument_id: 2 }], missing: [] })
      if (path === '/analysis/market-map') return Promise.resolve(explicitResponse)
      return Promise.resolve(response)
    })
    createWatchlist.mockResolvedValue({ id: 12, name: 'My explicit set', is_managed: false, is_locked: false, items: [] })
    addItem.mockResolvedValue({ id: 120, instrument_id: 1 })
    const wrapper = mount(MarketMapTool, { props: { configuration: { explicit_symbols: 'NVDA, MSFT' } } })
    await flushPromises()

    await wrapper.get('[aria-label="Explicit source watchlist name"]').setValue('My explicit set')
    await wrapper.findAll('button').find(button => button.text() === 'Save as watchlist')!.trigger('click')
    await flushPromises()

    expect(createWatchlist).toHaveBeenCalledWith('My explicit set')
    expect(addItem).toHaveBeenCalledWith(12, 1)
    expect(addItem).toHaveBeenCalledWith(12, 2)
    expect(wrapper.find('[role="status"]').text()).toContain('2 canonical members saved as My explicit set')
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
