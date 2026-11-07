import { createPinia, setActivePinia } from 'pinia'
import { computed } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGet, apiPost, apiPut, apiPatch, apiDelete } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn(), apiPatch: vi.fn(), apiDelete: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: apiGet, post: apiPost, put: apiPut, patch: apiPatch, delete: apiDelete } }))

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(res => { resolve = res })
  return { promise, resolve }
}

import { useWorkspaceStore, workspaceToolRole, type OpenableToolDefinition } from '@/stores/workspace'

const canonicalCatalogueFixture: OpenableToolDefinition[] = [
  { key: 'chart', tool_type: 'chart', title: 'Chart', instance_prefix: 'chart', configuration: { symbol: 'SPY', timeframe: 'D1' } },
  { key: 'watchlist', tool_type: 'watchlist', title: 'WatchList', instance_prefix: 'watchlist', configuration: { personal: true, watchlist_id: null } },
  { key: 'benchmark-list', tool_type: 'watchlist', title: 'Benchmarks', instance_prefix: 'benchmark-list', configuration: { market_group: 'us-benchmarks' } },
  { key: 'sector-list', tool_type: 'watchlist', title: 'S&P 500 Sectors', instance_prefix: 'sector-list', configuration: { market_group: 'sp500-sectors' } },
  { key: 'industry-list', tool_type: 'watchlist', title: 'Industries', instance_prefix: 'industry-list', configuration: { market_group: 'selected-sector-industries' } },
  { key: 'constituent-list', tool_type: 'watchlist', title: 'Constituents', instance_prefix: 'constituent-list', configuration: { market_group: 'selected-industry-constituents' } },
  { key: 'ratio-chart', tool_type: 'chart', title: 'Relative Strength', instance_prefix: 'ratio-chart', configuration: { expression: '=SPY/RSP', timeframe: 'D1', auto_ratio: true } },
  { key: 'relative-rotation', tool_type: 'relative_rotation', title: 'Relative Rotation', instance_prefix: 'relative-rotation', configuration: { group_key: 'sp500-sectors', benchmark: 'SPY', timeframe: 'D1', sampling: 1, lookback: 20, tail_length: 10, adjusted: true } },
  { key: 'breadth', tool_type: 'breadth', title: 'Market Breadth', instance_prefix: 'breadth', configuration: { group_key: 'sp500-sectors' } },
  { key: 'technical-summary', tool_type: 'technical_summary', title: 'Technicals', instance_prefix: 'technical-summary', configuration: { scope: 'selected' } },
  { key: 'coverage', tool_type: 'coverage', title: 'Coverage', instance_prefix: 'coverage', configuration: { scope: 'selected' } },
  { key: 'report', tool_type: 'report', title: 'Instrument Report', instance_prefix: 'report', configuration: {} },
  { key: 'research-results', tool_type: 'research_results', title: 'Study Results', instance_prefix: 'research-results', configuration: {} },
]

describe('workspace store layout tabs', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiPut.mockReset()
    apiPost.mockReset()
    apiGet.mockReset()
    apiPatch.mockReset()
    apiDelete.mockReset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.removeItem('charting-platform:workstation-tool-catalogue:v1')
  })

  it('loads and validates the authenticated server catalogue as the Add-tool source', async () => {
    apiGet.mockResolvedValueOnce({ version: 1, tools: canonicalCatalogueFixture })
    const store = useWorkspaceStore()

    const loaded = await store.loadToolCatalogue()

    expect(apiGet).toHaveBeenCalledWith('/workspaces/tool-catalogue')
    expect(loaded).toEqual(canonicalCatalogueFixture)
    expect(store.toolDefinition('constituent-list')?.configuration.market_group).toBe('selected-industry-constituents')
    expect(store.toolDefinition('ratio-chart')?.configuration.auto_ratio).toBe(true)
  })

  it('keeps the last verified catalogue when a later server response is malformed or unavailable', async () => {
    apiGet.mockResolvedValueOnce({ version: 1, tools: canonicalCatalogueFixture })
    const store = useWorkspaceStore()
    await store.loadToolCatalogue()

    apiGet.mockResolvedValueOnce({ version: 1, tools: [{ ...canonicalCatalogueFixture[0], key: '' }] })
    await store.loadToolCatalogue({ force: true })

    expect(store.toolCatalogue).toEqual(canonicalCatalogueFixture)
    expect(store.toolCatalogueError).toContain('temporarily unavailable')
  })

  it('hydrates the last validated catalogue cache before a failed server refresh', async () => {
    localStorage.setItem('charting-platform:workstation-tool-catalogue:v1', JSON.stringify({ version: 1, tools: canonicalCatalogueFixture }))
    apiGet.mockRejectedValueOnce(new Error('offline'))
    const store = useWorkspaceStore()

    expect(store.toolDefinition('ratio-chart')?.configuration.auto_ratio).toBe(true)
    await store.loadToolCatalogue()

    expect(store.toolCatalogue).toEqual(canonicalCatalogueFixture)
    expect(store.toolCatalogueError).toContain('temporarily unavailable')
  })

  it('deduplicates shared top-down refreshes and records the refresh time', async () => {
    apiGet.mockResolvedValue({})
    const store = useWorkspaceStore()

    const first = store.refreshMarketAnalysis()
    const second = store.refreshMarketAnalysis()
    await Promise.all([first, second])

    expect(apiGet).toHaveBeenCalledTimes(6)
    expect(apiGet).toHaveBeenCalledWith('/market-groups/us-benchmarks')
    expect(apiGet).toHaveBeenCalledWith('/market-groups/sp500-sectors')
    expect(apiGet).toHaveBeenCalledWith('/analysis/groups/us-benchmarks/snapshot', { benchmark: 'SPY' })
    expect(apiGet).toHaveBeenCalledWith('/analysis/groups/sp500-sectors/snapshot', { benchmark: 'SPY' })
    expect(apiGet).toHaveBeenCalledWith('/analysis/groups/sp500-sectors/breadth')
    expect(apiGet).toHaveBeenCalledWith('/analysis/groups/sp500-sectors/breadth/history', { limit: 500 })
    expect(store.marketAnalysisRefreshing).toBe(false)
    expect(store.marketAnalysisRefreshedAt).toEqual(expect.any(String))
  })

  it('joins active-panel reads to the shell refresh without cancelling its generation', async () => {
    const sharedResponse = deferred<unknown>()
    apiGet.mockReturnValue(sharedResponse.promise)
    const store = useWorkspaceStore()

    const shellRefresh = store.refreshMarketAnalysis()
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalledTimes(6))
    const panelReads = Promise.all([
      store.loadGroupSnapshot('sp500-sectors', 'SPY'),
      store.loadBreadth('sp500-sectors'),
      store.loadBreadthHistory('sp500-sectors'),
    ])

    expect(apiGet).toHaveBeenCalledTimes(6)
    sharedResponse.resolve({ group_key: 'sp500-sectors', rows: [], points: [], coverage: 1 })
    await Promise.all([shellRefresh, panelReads])

    expect(store.groupSnapshots['sp500-sectors']).toEqual(expect.objectContaining({ group_key: 'sp500-sectors' }))
    expect(store.breadth['sp500-sectors']).toEqual(expect.objectContaining({ group_key: 'sp500-sectors' }))
    expect(store.breadthHistory['sp500-sectors']).toEqual(expect.objectContaining({ group_key: 'sp500-sectors' }))
  })

  it('does not start queued market-analysis loaders while the document is hidden', async () => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
    const store = useWorkspaceStore()

    await store.refreshMarketAnalysis()
    await store.loadTechnical('SPY')
    await store.loadETFIndustries('XLK')

    expect(apiGet).not.toHaveBeenCalled()
    expect(store.marketAnalysisRefreshedAt).toBeNull()
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
  })

  it('publishes a leader-owned refresh event after a successful top-down refresh', async () => {
    const messages: unknown[] = []
    class FakeBroadcastChannel {
      addEventListener() {}
      close() {}
      postMessage(message: unknown) { messages.push(message) }
    }
    vi.stubGlobal('BroadcastChannel', FakeBroadcastChannel)
    apiGet.mockResolvedValue({})
    const store = useWorkspaceStore()
    store.connect()

    await store.refreshMarketAnalysis()

    expect(messages).toContainEqual(expect.objectContaining({
      type: 'market-analysis-refresh',
      refreshedAt: expect.any(String),
      sourceWindowId: expect.any(String),
    }))
    store.disconnect()
  })

  it('flushes a scheduled workspace snapshot immediately and avoids a second debounce write', async () => {
    const store = useWorkspaceStore()
    store.workspace = {
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{
        id: 20, stable_key: 'us-top-down', name: 'US Top Down', position: 0,
        active_window_key: 'relative-rotation',
        layout_config: { root: { type: 'stack', maximised: true, content: [] } },
        windows: [{ id: 30, instance_key: 'relative-rotation', tool_type: 'relative_rotation', title: 'Relative Rotation', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 0 }],
      }],
    }
    apiPut.mockResolvedValue({ ...store.workspace, revision: 5 })
    vi.useFakeTimers()
    store.scheduleSnapshot()

    const saved = await store.saveSnapshot()
    await vi.runAllTimersAsync()

    expect(saved).toBe(true)
    expect(apiPut).toHaveBeenCalledTimes(1)
    expect(apiPut.mock.calls[0][1].tabs[0].layout_config.root.maximised).toBe(true)
    vi.useRealTimers()
  })

  it('reports snapshot save progress, failure, and a confirmed retry', async () => {
    const store = useWorkspaceStore()
    store.workspace = {
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{
        id: 20, stable_key: 'us-top-down', name: 'US Top Down', position: 0,
        active_window_key: 'relative-rotation', layout_config: { root: { type: 'stack', maximised: true, content: [] } },
        windows: [{ id: 30, instance_key: 'relative-rotation', tool_type: 'relative_rotation', title: 'Relative Rotation', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 0 }],
      }],
    }
    store.scheduleSnapshot()
    expect(store.snapshotSaveStatus).toBe('saving')

    apiPut.mockRejectedValueOnce(new Error('API PUT /workspaces/10/snapshot → 503: unavailable'))
    expect(await store.saveSnapshot()).toBe(false)
    expect(store.snapshotSaveStatus).toBe('error')
    expect(store.snapshotSaveError).toContain('503')

    apiPut.mockResolvedValueOnce({ ...store.workspace, revision: 5 })
    expect(await store.saveSnapshot()).toBe(true)
    expect(store.snapshotSaveStatus).toBe('saved')
    expect(store.snapshotSaveError).toBeNull()
  })

  it('refreshes a follower from a leader refresh event without starting its own announcement', async () => {
    const messages: unknown[] = []
    let listener: ((event: MessageEvent) => void) | undefined
    class FakeBroadcastChannel {
      addEventListener(_type: string, callback: (event: MessageEvent) => void) { listener = callback }
      close() {}
      postMessage(message: unknown) { messages.push(message) }
    }
    vi.stubGlobal('BroadcastChannel', FakeBroadcastChannel)
    window.localStorage.setItem('charting-platform-workstation-leader', JSON.stringify({ id: 'another-window', heartbeat: Date.now() }))
    apiGet.mockResolvedValue({})
    const store = useWorkspaceStore()
    store.connect()

    listener?.({ data: { type: 'market-analysis-refresh', refreshedAt: '2026-08-05T15:00:00.000Z', sourceWindowId: 'another-window' } } as MessageEvent)
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalledTimes(6))
    await vi.waitFor(() => expect(store.marketAnalysisRefreshedAt).toEqual(expect.any(String)))

    expect(messages).toEqual([])
    store.disconnect()
    window.localStorage.removeItem('charting-platform-workstation-leader')
  })

  it('does not advance the successful-refresh timestamp when an input fails', async () => {
    apiGet.mockRejectedValue(new Error('temporary analysis outage'))
    const store = useWorkspaceStore()

    await store.refreshMarketAnalysis()

    expect(store.marketAnalysisRefreshing).toBe(false)
    expect(store.marketAnalysisRefreshedAt).toBeNull()
    expect(store.error).toContain('temporary analysis outage')
  })

  it('passes breadth timeframe and adjustment options through canonical analysis requests', async () => {
    apiGet.mockResolvedValue({})
    const store = useWorkspaceStore()

    await store.loadGroupSnapshot('sp500-sectors', 'SPY', { timeframe: 'W1', adjusted: false })
    await store.loadBreadth('sp500-sectors', { timeframe: 'W1', adjusted: false })
    await store.loadBreadthHistory('sp500-sectors', { timeframe: 'W1', adjusted: false })

    expect(apiGet).toHaveBeenCalledWith('/analysis/groups/sp500-sectors/snapshot', { benchmark: 'SPY', timeframe: 'W1', adjusted: false })
    expect(apiGet).toHaveBeenCalledWith('/analysis/groups/sp500-sectors/breadth', { timeframe: 'W1', adjusted: false })
    expect(apiGet).toHaveBeenCalledWith('/analysis/groups/sp500-sectors/breadth/history', { limit: 500, timeframe: 'W1', adjusted: false })
  })

  it('loads role-aware benchmark-family ratios with a stable cache key and lineage', async () => {
    apiGet.mockResolvedValue({
      family_key: 'sp500',
      official_index_symbol: 'SPX',
      ratios: [{ role: 'equal_weight', symbol: 'RSP', benchmark_role: 'cap_weight', benchmark: 'SPY', points: [] }],
      exclusions: [],
    })
    const store = useWorkspaceStore()

    const result = await store.loadBenchmarkFamilyRatios('sp500', 'equal_weight', 'SPY', { timeframe: 'W1', adjusted: false })

    expect(apiGet).toHaveBeenCalledWith('/analysis/benchmark-families/sp500/ratios', {
      role: 'equal_weight',
      market_benchmark: 'SPY',
      timeframe: 'W1',
      adjusted: false,
    })
    expect(result?.family_key).toBe('sp500')
    expect(store.benchmarkFamilyRatios['sp500:equal_weight:SPY:W1:raw']?.ratios[0]?.symbol).toBe('RSP')
    expect(store.benchmarkFamilyRatioErrors['sp500:equal_weight:SPY:W1:raw']).toBeNull()
  })

  it('loads an explicit all-leg benchmark-family ratio batch without changing the role cache identity', async () => {
    apiGet.mockResolvedValue({ family_key: 'sp500', official_index_symbol: 'SPX', ratios: [], exclusions: [] })
    const store = useWorkspaceStore()

    await store.loadBenchmarkFamilyRatios('sp500', 'equal_weight', 'SPY', {
      roles: ['cap_weight', 'equal_weight', 'value', 'growth'],
    })

    expect(apiGet).toHaveBeenCalledWith('/analysis/benchmark-families/sp500/ratios', {
      role: 'equal_weight',
      roles: 'cap_weight,equal_weight,value,growth',
      market_benchmark: 'SPY',
    })
    expect(store.benchmarkFamilyRatios['sp500:cap_weight,equal_weight,value,growth:SPY:D1:adj']).toBeTruthy()
  })

  it('keeps an as-of family ratio in a distinct cache entry', async () => {
    apiGet.mockResolvedValue({ family_key: 'sp500', official_index_symbol: 'SPX', ratios: [], exclusions: [] })
    const store = useWorkspaceStore()

    await store.loadBenchmarkFamilyRatios('sp500', 'equal_weight', 'SPY', {
      as_of: '2026-06-27T23:59:59Z',
    })

    expect(apiGet).toHaveBeenCalledWith('/analysis/benchmark-families/sp500/ratios', {
      role: 'equal_weight',
      market_benchmark: 'SPY',
      as_of: '2026-06-27T23:59:59Z',
    })
    expect(store.benchmarkFamilyRatios['sp500:equal_weight:SPY:D1:adj:2026-06-27T23:59:59Z']).toBeTruthy()
  })

  it('loads role-aware family technicals with an as-of cache identity', async () => {
    apiGet.mockResolvedValue({
      family_key: 'sp500',
      official_index_symbol: 'SPX',
      timeframe: 'D1',
      adjustment: 'split_adjusted',
      roles: [{ role: 'cap_weight', symbol: 'SPY', label: 'SPY', verification_state: 'verified', available: true, last: 600, rsi14: 55, sma20: 590, sma50: 580, sma200: 540, position_52w: 0.92, volume_ratio_50: 1.1, freshness: 'current', warnings: [] }],
      exclusions: [],
    })
    const store = useWorkspaceStore()

    const result = await store.loadBenchmarkFamilyTechnicals('sp500', {
      timeframe: 'W1',
      adjusted: false,
      as_of: '2026-06-27T23:59:59Z',
    })

    expect(apiGet).toHaveBeenCalledWith('/analysis/benchmark-families/sp500/technicals', {
      timeframe: 'W1',
      adjusted: false,
      as_of: '2026-06-27T23:59:59Z',
    })
    expect(result?.roles[0]?.symbol).toBe('SPY')
    expect(store.benchmarkFamilyTechnicals['sp500:W1:raw:2026-06-27T23:59:59Z']?.roles[0]?.rsi14).toBe(55)
  })

  it('loads side-by-side family participation with configurable near-high parameters', async () => {
    apiGet.mockResolvedValue({
      family_key: 'sp500',
      official_index_symbol: 'SPX',
      timeframe: 'D1',
      adjustment: 'split_adjusted',
      near_threshold: 0.02,
      new_high_lookback: 50,
      roles: [{ role: 'cap_weight', symbol: 'SPY', label: 'SPY', verification_state: 'verified', available: true, above_ma: { ma20: { percentage: 0.7, requested_count: 10, eligible_count: 10, excluded_count: 0, coverage: 1, exclusions: [] } }, near_52w_high: null, new_high: null, trend_up: null, relative_strength_to_cap: null, exclusions: [] }],
      exclusions: [],
    })
    const store = useWorkspaceStore()

    await store.loadBenchmarkFamilyBreadth('sp500', {
      near_threshold: 0.02,
      new_high_lookback: 50,
      as_of: '2026-06-27T23:59:59Z',
    })

    expect(apiGet).toHaveBeenCalledWith('/analysis/benchmark-families/sp500/breadth', {
      as_of: '2026-06-27T23:59:59Z',
      near_threshold: 0.02,
      new_high_lookback: 50,
    })
    expect(store.benchmarkFamilyBreadths['sp500:D1:adj:2026-06-27T23:59:59Z:0.02:50']?.roles[0]?.above_ma.ma20.percentage).toBe(0.7)
  })

  it('loads aligned historical participation for independent family roles', async () => {
    apiGet.mockResolvedValue({
      family_key: 'sp500',
      official_index_symbol: 'SPX',
      timeframe: 'W1',
      adjustment: 'raw',
      limit: 30,
      roles: [{ role: 'equal_weight', symbol: 'RSP', label: 'RSP', verification_state: 'verified', available: true, points: [{ timestamp: '2026-06-27T00:00:00Z', above_ma: { ma20: 0.8, ma50: null, ma200: null }, coverage: { ma20: 1, ma50: 0, ma200: 0 } }], exclusions: [] }],
      exclusions: [],
    })
    const store = useWorkspaceStore()

    const result = await store.loadBenchmarkFamilyBreadthHistory('sp500', {
      timeframe: 'W1',
      adjusted: false,
      as_of: '2026-06-27T23:59:59Z',
      limit: 30,
    })

    expect(apiGet).toHaveBeenCalledWith('/analysis/benchmark-families/sp500/breadth/history', {
      limit: 30,
      timeframe: 'W1',
      adjusted: false,
      as_of: '2026-06-27T23:59:59Z',
    })
    expect(result?.roles[0]?.points[0]?.above_ma.ma20).toBe(0.8)
    expect(store.benchmarkFamilyBreadthHistories['sp500:W1:raw:2026-06-27T23:59:59Z:30']?.roles[0]?.symbol).toBe('RSP')
  })

  it('loads family role ranking with an explicit period cache identity', async () => {
    apiGet.mockResolvedValue({
      family_key: 'sp500',
      official_index_symbol: 'SPX',
      benchmark: 'SPY',
      timeframe: 'D1',
      adjustment: 'split_adjusted',
      rank_period: '1M',
      roles: [{ role: 'equal_weight', symbol: 'RSP', label: 'RSP', verification_state: 'verified', available: true, rank: 1, performance: { '1M': 0.12 }, relative_performance: { '1M': 0.03 }, warnings: [] }],
      exclusions: [],
    })
    const store = useWorkspaceStore()

    const result = await store.loadBenchmarkFamilyRanking('sp500', { rank_period: '1M' })

    expect(apiGet).toHaveBeenCalledWith('/analysis/benchmark-families/sp500/ranking', { rank_period: '1M' })
    expect(result?.roles[0]?.rank).toBe(1)
    expect(store.benchmarkFamilyRankings['sp500:D1:adj:latest:1M']?.roles[0]?.performance['1M']).toBe(0.12)
  })

  it('loads family concentration with top-n and rank-period cache identity', async () => {
    apiGet.mockResolvedValue({
      family_key: 'sp500',
      official_index_symbol: 'SPX',
      timeframe: 'D1',
      adjustment: 'split_adjusted',
      rank_period: '1M',
      top_n: 5,
      roles: [{ role: 'cap_weight', symbol: 'SPY', label: 'SPY', verification_state: 'verified', available: true, weight_method: 'reported_holdings_weights', reported_weight_coverage: 1, top_n: 5, top_n_weight: 0.25, hhi: 0.1, effective_constituents: 10, eligible_count: 500, covered_count: 500, excluded_count: 0, coverage: 1, mean_return: 0.04, median_return: 0.04, dispersion: 0.02, members: [], warnings: [] }],
      exclusions: [],
    })
    const store = useWorkspaceStore()

    const result = await store.loadBenchmarkFamilyConcentration('sp500', { rank_period: '1M', top_n: 5 })

    expect(apiGet).toHaveBeenCalledWith('/analysis/benchmark-families/sp500/concentration', { rank_period: '1M', top_n: 5 })
    expect(result?.roles[0]?.top_n_weight).toBe(0.25)
    expect(store.benchmarkFamilyConcentrations['sp500:D1:adj:latest:1M:5']?.roles[0]?.hhi).toBe(0.1)
  })

  it('loads historical family concentration with bounded cache identity', async () => {
    apiGet.mockResolvedValue({
      family_key: 'sp500', official_index_symbol: 'SPX', timeframe: 'D1', adjustment: 'split_adjusted', rank_period: '1M', top_n: 10, limit: 50,
      roles: [{ role: 'cap_weight', symbol: 'SPY', label: 'SPY', verification_state: 'verified', available: true, points: [{ timestamp: '2026-01-02T00:00:00Z', snapshot_id: 1, composition_date: '2026-01-01', known_at: '2026-01-02T00:00:00Z', membership_version: 1, weight_method: 'reported_holdings_weights', reported_weight_coverage: 1, top_n_weight: 0.25, hhi: 0.1, effective_constituents: 10, eligible_count: 500, covered_count: 500, excluded_count: 0, coverage: 1, warnings: [] }], exclusions: [] }],
      exclusions: [],
    })
    const store = useWorkspaceStore()

    const result = await store.loadBenchmarkFamilyConcentrationHistory('sp500', { rank_period: '1M', limit: 50 })

    expect(apiGet).toHaveBeenCalledWith('/analysis/benchmark-families/sp500/concentration/history', { rank_period: '1M', top_n: 10, limit: 50 })
    expect(result?.roles[0]?.points[0]?.snapshot_id).toBe(1)
    expect(store.benchmarkFamilyConcentrationHistories['sp500:D1:adj:latest:1M:10:50']?.roles[0]?.points).toHaveLength(1)
  })

  it('loads cross-family ranking with a stable family-filter cache identity', async () => {
    apiGet.mockResolvedValue({
      timeframe: 'D1', adjustment: 'split_adjusted', rank_period: '1M', benchmark: 'SPY',
      rows: [{ family_key: 'sp500', family_name: 'S&P 500', official_index_symbol: 'SPX', symbol: 'SPY', label: 'SPY', available: true, rank: 1, performance: { '1M': 0.1 }, relative_performance: { '1M': 0 }, warnings: [] }], exclusions: [],
    })
    const store = useWorkspaceStore()

    const result = await store.loadCrossFamilyRanking({ families: ['sp500', 'sp400'], benchmark: 'SPY' })

    expect(apiGet).toHaveBeenCalledWith('/analysis/benchmark-families/ranking', {
      rank_period: '1M', families: 'sp400,sp500', benchmark: 'SPY',
    })
    expect(result?.rows[0]?.family_key).toBe('sp500')
    expect(store.crossFamilyRankings['D1:adj:latest:1M:sp400,sp500:SPY']?.rows[0]?.rank).toBe(1)
  })

  it('loads historical cross-family ranking with bounded cache identity', async () => {
    apiGet.mockResolvedValue({
      timeframe: 'D1', adjustment: 'split_adjusted', rank_period: '1M', limit: 50, benchmark: 'SPY',
      rows: [{ family_key: 'sp500', family_name: 'S&P 500', official_index_symbol: 'SPX', symbol: 'SPY', label: 'SPY', available: true, coverage: 1, points: [{ timestamp: '2026-01-02T00:00:00Z', rank: 1, performance: { '1M': 0.1 }, relative_performance: { '1M': 0 } }], warnings: [] }], exclusions: [],
    })
    const store = useWorkspaceStore()

    const result = await store.loadCrossFamilyRankingHistory({ families: ['sp500'], benchmark: 'SPY', limit: 50 })

    expect(apiGet).toHaveBeenCalledWith('/analysis/benchmark-families/ranking/history', {
      rank_period: '1M', limit: 50, families: 'sp500', benchmark: 'SPY',
    })
    expect(result?.rows[0]?.points[0]?.rank).toBe(1)
    expect(store.crossFamilyRankingHistories['D1:adj:latest:1M:sp500:SPY:50']?.limit).toBe(50)
  })

  it('loads a family overview with independent mapping readiness and stable lineage cache', async () => {
    apiGet.mockResolvedValue({
      family_key: 'sp500',
      name: 'S&P 500',
      official_index_symbol: 'SPX',
      mappings: [{ role: 'equal_weight', symbol: 'RSP', holdings_available: true }],
      rows: [],
      exclusions: [],
    })
    const store = useWorkspaceStore()

    const result = await store.loadBenchmarkFamilyOverview('sp500', { timeframe: 'W1', adjusted: false })

    expect(apiGet).toHaveBeenCalledWith('/analysis/benchmark-families/sp500/overview', {
      timeframe: 'W1',
      adjusted: false,
    })
    expect(result?.official_index_symbol).toBe('SPX')
    expect(store.benchmarkFamilyOverviews['sp500:W1:raw:latest']?.mappings[0]?.symbol).toBe('RSP')
    expect(store.benchmarkFamilyOverviewErrors['sp500:W1:raw:latest']).toBeNull()
  })

  it('loads dated family coverage without collapsing unavailable roles into the cap leg', async () => {
    apiGet.mockResolvedValue({
      family_key: 'sp500',
      name: 'S&P 500',
      official_index_symbol: 'SPX',
      coverage: 0.25,
      roles: [
        {
          role: 'cap_weight',
          symbol: 'SPY',
          status: 'available',
          snapshots: [{ snapshot_id: 1, composition_date: '2026-06-30' }],
          continuity_status: 'single_snapshot',
          member_bar_history: {
            status: 'partial',
            timeframes: [{ timeframe: 'D1', member_count: 2, covered_member_count: 2, analysis_ready_member_count: 1 }],
          },
        },
        { role: 'equal_weight', symbol: null, status: 'mapping_unavailable', snapshots: [] },
      ],
      exclusions: [],
    })
    const store = useWorkspaceStore()

    const result = await store.loadBenchmarkFamilyCoverage('sp500')

    expect(apiGet).toHaveBeenCalledWith('/analysis/benchmark-families/sp500/coverage', {})
    expect(result?.roles[0]?.snapshots[0]?.composition_date).toBe('2026-06-30')
    expect(result?.roles[0]?.continuity_status).toBe('single_snapshot')
    expect(result?.roles[0]?.member_bar_history?.timeframes[0]?.analysis_ready_member_count).toBe(1)
    expect(store.benchmarkFamilyCoverages['sp500:latest:256']?.coverage).toBe(0.25)
    expect(store.benchmarkFamilyCoverageErrors['sp500:latest:256']).toBeNull()
  })

  it('loads the provider-neutral all-family readiness matrix with explicit as-of bounds', async () => {
    apiGet.mockResolvedValue({
      as_of: '2026-08-01T00:00:00Z',
      snapshot_limit: 8,
      family_count: 8,
      ready_family_count: 0,
      role_count: 32,
      ready_role_count: 0,
      readiness_status: 'coverage_limited',
      universe_provenance: { provider_calls: false },
      provider_probe_evidence: [
        {
          provider: 'fixture',
          capability: 'price_history',
          classification: 'healthy',
          success: true,
          consecutive_failures: 0,
          recovered: false,
          observed_at: '2026-08-01T12:00:00Z',
        },
      ],
      families: [],
    })
    const store = useWorkspaceStore()

    const result = await store.loadBenchmarkFamilyReadiness({ as_of: '2026-08-01T00:00:00Z', limit: 8 })

    expect(apiGet).toHaveBeenCalledWith('/analysis/benchmark-families/readiness', {
      as_of: '2026-08-01T00:00:00Z',
      limit: 8,
    })
    expect(result?.readiness_status).toBe('coverage_limited')
    expect(result?.universe_provenance.provider_calls).toBe(false)
    expect(result?.provider_probe_evidence?.[0]?.provider).toBe('fixture')
    expect(result?.provider_probe_evidence?.[0]?.success).toBe(true)
    expect(store.benchmarkFamilyReadiness?.role_count).toBe(32)
    expect(store.benchmarkFamilyReadinessError).toBeNull()
  })

  it('loads role-specific family constituents without substituting a missing leg', async () => {
    apiGet.mockResolvedValue({
      group_key: 'benchmark-family:sp500:equal_weight',
      etf_symbol: 'RSP',
      source_provider: 'fixture',
      composition_date: '2026-06-27',
      rows: [{ instrument_id: 7, symbol: 'NVDA', name: 'NVIDIA', weight: 0.01 }],
      exclusions: [],
    })
    const store = useWorkspaceStore()

    const result = await store.loadBenchmarkFamilyConstituents('sp500', 'equal_weight', { market_benchmark: 'SPY' })

    expect(apiGet).toHaveBeenCalledWith('/analysis/benchmark-families/sp500/constituents', {
      role: 'equal_weight',
      market_benchmark: 'SPY',
    })
    expect(result?.etf_symbol).toBe('RSP')
    expect(store.benchmarkFamilyConstituents['sp500:equal_weight:D1:adj:latest:SPY']?.rows[0]?.symbol).toBe('NVDA')
  })

  it('hydrates a missing benchmark-family registry from explicit child groups', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/market-groups/us-benchmarks') return Promise.resolve({
        stable_key: 'us-benchmarks',
        provenance: { taxonomy_version: 'legacy-fixture' },
        members: [],
      })
      if (path === '/market-groups/us-benchmarks/children') return Promise.resolve([
        { stable_key: 'sp500', group_type: 'benchmark_family', name: 'S&P 500' },
      ])
      return Promise.resolve({})
    })
    const store = useWorkspaceStore()

    await store.loadMarketGroup('us-benchmarks')

    expect(apiGet).toHaveBeenCalledWith('/market-groups/us-benchmarks/children')
    expect(store.marketGroups['us-benchmarks']?.provenance.benchmark_families).toEqual([
      { logical_key: 'sp500', name: 'S&P 500' },
    ])
  })

  it('loads a selected benchmark family with its own cap proxy and timeframe', async () => {
    apiGet.mockImplementation((path: string) => path.includes('/snapshot')
      ? { group_key: 'sp400', rows: [], coverage: 0 }
      : path.includes('/overview')
        ? { family_key: 'sp400', mappings: [], rows: [] }
        : { stable_key: 'sp400', group_type: 'benchmark_family', members: [] })
    const store = useWorkspaceStore()

    await store.loadMarketGroup('sp400')
    await store.loadGroupSnapshot('sp400', 'MDY', { timeframe: 'W1' })
    await store.loadBenchmarkFamilyOverview('sp400', { timeframe: 'W1' })

    expect(apiGet).toHaveBeenCalledWith('/market-groups/sp400')
    expect(apiGet).toHaveBeenCalledWith('/analysis/groups/sp400/snapshot', { benchmark: 'MDY', timeframe: 'W1' })
    expect(apiGet).toHaveBeenCalledWith('/analysis/benchmark-families/sp400/overview', { timeframe: 'W1' })
    expect(store.marketGroups.sp400?.stable_key).toBe('sp400')
    expect(store.groupSnapshots.sp400).toEqual(expect.objectContaining({ group_key: 'sp400' }))
  })

  it('tracks breadth loading and errors independently for the workstation state surface', async () => {
    const pending = deferred<unknown>()
    apiGet.mockImplementation((path: string) => path.endsWith('/breadth') ? pending.promise : Promise.resolve({ points: [] }))
    const store = useWorkspaceStore()

    const request = store.loadBreadth('sp500-sectors')
    await vi.waitFor(() => expect(store.breadthLoading['sp500-sectors']).toBe(true))
    pending.resolve({ group_key: 'sp500-sectors', evaluated_count: 11 })
    await request

    expect(store.breadthLoading['sp500-sectors']).toBe(false)
    expect(store.breadthErrors['sp500-sectors']).toBeNull()

    apiGet.mockRejectedValueOnce(new Error('breadth provider unavailable'))
    await store.loadBreadth('sp500-sectors')
    expect(store.breadthLoading['sp500-sectors']).toBe(false)
    expect(store.breadthErrors['sp500-sectors']).toBe('breadth provider unavailable')
  })

  it('queues and polls an isolated numeric Python-series breadth target with lineage', async () => {
    apiPost.mockResolvedValue({
      run_id: 91,
      code_version_id: 17,
      status: 'queued',
      execution_mode: 'breadth_history',
      output_contract: 'series',
      series_target: { operator: 'gte', threshold: 0.02 },
      definition_hash: 'python-definition',
      universe: { kind: 'group', key: 'sp500-sectors', membership_version: 'm1' },
      condition: { code_version_id: 17, output_contract: 'series' },
      dataset_manifest: { timeframe: 'D1', adjustment: 'split_adjusted' },
      progress: {},
      diagnostics: [],
    })
    apiGet.mockResolvedValue({
      run_id: 91,
      code_version_id: 17,
      status: 'completed',
      execution_mode: 'breadth_history',
      output_contract: 'series',
      series_target: { operator: 'gte', threshold: 0.02 },
      definition_hash: 'python-definition',
      universe: { kind: 'group', key: 'sp500-sectors', membership_version: 'm1' },
      condition: { code_version_id: 17, output_contract: 'series' },
      dataset_manifest: { timeframe: 'D1', adjustment: 'split_adjusted' },
      current: { timestamp: '2026-08-17T00:00:00Z', requested_count: 2, eligible_count: 2, pass_count: 1, excluded_count: 0, percentage: 0.5, coverage: 1, members: [], exclusions: [] },
      points: [{ timestamp: '2026-08-16T00:00:00Z', requested_count: 2, eligible_count: 2, pass_count: 1, excluded_count: 0, percentage: 0.5, coverage: 1, members: [], exclusions: [] }],
      occurrences: [],
      progress: {},
      diagnostics: [],
    })
    const store = useWorkspaceStore()
    const request = {
      code_version_id: 17,
      universe: { kind: 'group', key: 'sp500-sectors', point_in_time: true },
      output_contract: 'series',
      series_target: { operator: 'gte', threshold: 0.02 },
      timeframe: 'D1',
      adjusted: true,
      history: true,
    }

    const result = await store.loadPythonBreadth(request, 'python-series-key')

    expect(apiPost).toHaveBeenCalledWith('/analysis/breadth/python', request)
    expect(apiGet).toHaveBeenCalledWith('/analysis/breadth/python/runs/91')
    expect(result?.status).toBe('completed')
    expect(store.pythonBreadth['python-series-key']?.current?.percentage).toBe(0.5)
    expect(store.pythonBreadth['python-series-key']?.series_target).toEqual({ operator: 'gte', threshold: 0.02 })
    expect(store.pythonBreadthLoading['python-series-key']).toBe(false)
    expect(store.pythonBreadthErrors['python-series-key']).toBeNull()
  })

  it('ignores late shared-analysis snapshots after a newer timeframe request', async () => {
    const staleSnapshot = deferred<unknown>()
    const staleBreadth = deferred<unknown>()
    const staleHistory = deferred<unknown>()
    apiGet.mockImplementation((path: string, params?: Record<string, unknown>) => {
      if (path === '/analysis/groups/sp500-sectors/snapshot' && params?.timeframe === 'D1') return staleSnapshot.promise
      if (path === '/analysis/groups/sp500-sectors/snapshot' && params?.timeframe === 'W1') return Promise.resolve({ group_key: 'sp500-sectors', timeframe: 'W1', rows: [] })
      if (path === '/analysis/groups/sp500-sectors/breadth' && params?.timeframe === 'D1') return staleBreadth.promise
      if (path === '/analysis/groups/sp500-sectors/breadth' && params?.timeframe === 'W1') return Promise.resolve({ group_key: 'sp500-sectors', timeframe: 'W1', evaluated_count: 11 })
      if (path === '/analysis/groups/sp500-sectors/breadth/history' && params?.timeframe === 'D1') return staleHistory.promise
      if (path === '/analysis/groups/sp500-sectors/breadth/history' && params?.timeframe === 'W1') return Promise.resolve({ group_key: 'sp500-sectors', timeframe: 'W1', points: [] })
      return Promise.resolve({})
    })
    const store = useWorkspaceStore()

    const oldSnapshot = store.loadGroupSnapshot('sp500-sectors', 'SPY', { timeframe: 'D1' })
    const oldBreadth = store.loadBreadth('sp500-sectors', { timeframe: 'D1' })
    const oldHistory = store.loadBreadthHistory('sp500-sectors', { timeframe: 'D1' })
    await Promise.all([
      store.loadGroupSnapshot('sp500-sectors', 'SPY', { timeframe: 'W1' }),
      store.loadBreadth('sp500-sectors', { timeframe: 'W1' }),
      store.loadBreadthHistory('sp500-sectors', { timeframe: 'W1' }),
    ])
    staleSnapshot.resolve({ group_key: 'sp500-sectors', timeframe: 'D1', rows: [{ symbol: 'stale' }] })
    staleBreadth.resolve({ group_key: 'sp500-sectors', timeframe: 'D1', evaluated_count: 1 })
    staleHistory.resolve({ group_key: 'sp500-sectors', timeframe: 'D1', points: [{ timestamp: 'stale' }] })
    await Promise.all([oldSnapshot, oldBreadth, oldHistory])

    expect(store.groupSnapshots['sp500-sectors']?.rows).toEqual([])
    expect(store.breadth['sp500-sectors']?.timeframe).toBe('W1')
    expect(store.breadthHistory['sp500-sectors']?.points).toEqual([])
  })

  it('keeps the active ETF drill-down when an older holdings response arrives late', async () => {
    const stale = deferred<unknown>()
    apiGet.mockImplementation((path: string) => {
      if (path === '/etf-holdings/SPY/holdings') return stale.promise
      if (path === '/etf-holdings/XLK/holdings') return Promise.resolve({
        snapshot: { etf_symbol: 'XLK', composition_date: '2026-08-01', known_at: null, provenance: 'test', source_provider: 'test', completeness_status: 'complete' },
        holdings: [],
        total: 0,
      })
      return Promise.resolve({})
    })
    const store = useWorkspaceStore()
    const oldRequest = store.loadETFHoldings('SPY')
    const currentRequest = store.loadETFHoldings('XLK')
    await currentRequest
    stale.resolve({ snapshot: { etf_symbol: 'SPY' }, holdings: [], total: 0 })
    await oldRequest

    expect(store.constituentETF).toBe('XLK')
    expect(store.etfHoldings.XLK?.snapshot.etf_symbol).toBe('XLK')
    expect(store.etfHoldings.SPY).toBeUndefined()
  })

  it('clears the prior holdings context synchronously and ignores its late response', async () => {
    const stale = deferred<unknown>()
    apiGet.mockImplementation((path: string) => {
      if (path === '/etf-holdings/OIH/holdings') return stale.promise
      if (path === '/etf-holdings/IGV/holdings') return Promise.reject(Object.assign(new Error('not found'), { status: 404 }))
      return Promise.resolve({})
    })
    const store = useWorkspaceStore()
    store.setConstituentETF('OIH')
    const oldRequest = store.loadETFHoldings('OIH')

    store.setConstituentETF(null)
    expect(store.constituentETF).toBeNull()
    expect(store.selectedIndustry).toBeNull()
    await store.loadETFHoldings('IGV')
    stale.resolve({ snapshot: { etf_symbol: 'OIH' }, holdings: [{ constituent_symbol: 'XLE' }], total: 1 })
    await oldRequest

    expect(store.constituentETF).toBeNull()
    expect(store.etfHoldings.IGV).toBeNull()
    expect(store.etfHoldings.OIH).toBeUndefined()
  })

  it('keeps the selected ETF identity while reporting an unavailable local holdings read', async () => {
    apiGet.mockRejectedValue(Object.assign(new Error('not found'), { status: 404 }))
    const store = useWorkspaceStore()
    store.setConstituentETF('OIH')

    await store.loadETFHoldings('OIH')

    expect(store.etfHoldings.OIH).toBeNull()
    expect(store.constituentETF).toBe('OIH')
    expect(store.selectedIndustry).toBeNull()
    expect(store.selectedIndustryProxy).toBeNull()
  })

  it('preserves a saved ETF snapshot when a later local holdings read returns not found', async () => {
    const saved = {
      snapshot: { id: 44, etf_symbol: 'OIH', composition_date: '2026-10-01', provenance: 'last-known' },
      holdings: [{ id: 45, reported_symbol: 'XLE', is_resolved: false }],
      total: 1,
    }
    apiGet.mockRejectedValue(Object.assign(new Error('not found'), { status: 404 }))
    const store = useWorkspaceStore()
    store.etfHoldings = { OIH: saved as any }
    store.setConstituentETF('OIH')

    await store.loadETFHoldings('OIH')

    expect(store.etfHoldings.OIH).toEqual(saved)
    expect(store.etfHoldings.OIH?.snapshot).toMatchObject({ id: 44, etf_symbol: 'OIH', provenance: 'last-known' })
  })

  it('does not clear a newer holdings context when an older symbol returns unavailable', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/etf-holdings/OIH/holdings') return Promise.reject(Object.assign(new Error('not found'), { status: 404 }))
      if (path === '/etf-holdings/IGV/holdings') return Promise.resolve({
        snapshot: { etf_symbol: 'IGV', composition_date: '2026-08-01', known_at: null, provenance: 'test', source_provider: 'test', completeness_status: 'complete' },
        holdings: [],
        total: 0,
      })
      return Promise.resolve({})
    })
    const store = useWorkspaceStore()
    store.setConstituentETF('OIH')
    const oldRequest = store.loadETFHoldings('OIH')
    store.setConstituentETF(null)
    store.setConstituentETF('IGV')
    const currentRequest = store.loadETFHoldings('IGV')
    await Promise.all([oldRequest, currentRequest])

    expect(store.constituentETF).toBe('IGV')
    expect(store.etfHoldings.OIH).toBeUndefined()
    expect(store.etfHoldings.IGV?.snapshot.etf_symbol).toBe('IGV')
  })

  it('does not let a late technical snapshot overwrite the newer symbol', async () => {
    const stale = deferred<unknown>()
    apiGet.mockImplementation((path: string) => {
      if (path === '/analysis/instruments/SPY/technical') return stale.promise
      if (path === '/analysis/instruments/XLK/technical') return Promise.resolve({ symbol: 'XLK', metrics: { rsi14: 61 } })
      return Promise.resolve({})
    })
    const store = useWorkspaceStore()

    const oldRequest = store.loadTechnical('SPY')
    await store.loadTechnical('XLK')
    stale.resolve({ symbol: 'SPY', metrics: { rsi14: 39 } })
    await oldRequest

    expect(store.technicals.XLK?.symbol).toBe('XLK')
    expect(store.technicals.SPY).toBeUndefined()
  })

  it('requests constituent strength against both the selected ETF and SPY', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/etf-holdings/XLK/holdings') return Promise.resolve({
        snapshot: { etf_symbol: 'XLK', composition_date: '2026-08-01', known_at: null, provenance: 'test', source_provider: 'test', completeness_status: 'complete' },
        holdings: [{ constituent_instrument_id: 7, constituent_symbol: 'NVDA', constituent_name: 'NVIDIA', is_resolved: true }],
        total: 1,
      })
      if (path === '/analysis/etf/XLK/constituents/snapshot') return Promise.resolve({
        benchmark: 'XLK', market_benchmark: 'SPY', coverage: 1,
        rows: [{ instrument_id: 7, symbol: 'NVDA', relative_to_benchmark: { value: 1.2 }, relative_to_market: { value: 1.5 } }],
      })
      return Promise.resolve({})
    })
    const store = useWorkspaceStore()

    await store.loadETFHoldings('XLK')
    await vi.waitFor(() => expect(store.etfConstituentSnapshots.XLK?.rows[0]?.relative_to_market?.value).toBe(1.5))
    expect(apiGet).toHaveBeenCalledWith('/analysis/etf/XLK/constituents/snapshot', { benchmark: 'XLK', market_benchmark: 'SPY' })
  })

  it('keeps expected stale-holdings analysis unavailable state scoped to its ETF context', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/analysis/etf/IGV/constituents/snapshot') {
        return Promise.reject(Object.assign(
          new Error('API GET /analysis/etf/IGV/constituents/snapshot → 409: {"code":"etf_holdings_not_current"}'),
          { status: 409 },
        ))
      }
      if (path === '/analysis/etf/USMV/constituents/snapshot') {
        return Promise.resolve({
          benchmark: 'USMV', market_benchmark: 'SPY', coverage: 1,
          rows: [{ instrument_id: 690, symbol: 'EXAMPLE', relative_to_benchmark: { value: 1.1 } }],
        })
      }
      return Promise.resolve({})
    })
    const store = useWorkspaceStore()
    store.setConstituentETF('IGV')

    await store.loadETFConstituentSnapshot('IGV')

    expect(store.etfConstituentSnapshots.IGV).toBeNull()
    expect(store.etfConstituentSnapshotErrors.IGV).toContain('IGV')
    expect(store.error).toBeNull()

    store.setConstituentETF('USMV')
    await store.loadETFConstituentSnapshot('USMV')

    expect(store.etfConstituentSnapshots.USMV?.rows[0]?.instrument_id).toBe(690)
    expect(store.etfConstituentSnapshotErrors.USMV).toBeNull()
    expect(store.etfConstituentSnapshotErrors.IGV).toContain('IGV')
    expect(store.error).toBeNull()
  })

  it('keeps non-capability analysis conflicts on the shared workspace error channel', async () => {
    apiGet.mockRejectedValueOnce(Object.assign(
      new Error('API GET /analysis/etf/IGV/constituents/snapshot → 409: {"code":"workspace_conflict"}'),
      { status: 409 },
    ))
    const store = useWorkspaceStore()

    await store.loadETFConstituentSnapshot('IGV')

    expect(store.etfConstituentSnapshotErrors.IGV).toBeNull()
    expect(store.error).toContain('workspace_conflict')
  })

  it('clones the active serializable layout with remapped tool identities and saves it', async () => {
    const store = useWorkspaceStore()
    store.workspace = {
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{
        id: 20, stable_key: 'us-top-down', name: 'US Top Down', position: 0, active_window_key: 'primary-chart',
        layout_config: { root: { componentState: { instance_key: 'primary-chart' } } },
        windows: [{ id: 30, instance_key: 'primary-chart', tool_type: 'chart', title: 'Chart', link_group: 'blue', configuration: { symbol: 'SPY' }, style: {}, state_schema_version: 1, position: 0 }],
      }],
    }
    apiPut.mockResolvedValue(store.workspace)

    store.cloneActiveTab()

    expect(store.workspace.tabs).toHaveLength(2)
    const clone = store.workspace.tabs[1]
    expect(clone.stable_key).not.toBe('us-top-down')
    expect(clone.windows[0].instance_key).not.toBe('primary-chart')
    expect((clone.layout_config.root as { componentState: { instance_key: string } }).componentState.instance_key).toBe(clone.windows[0].instance_key)
    expect(store.activeTabKey).toBe(clone.stable_key)

    await new Promise(resolve => setTimeout(resolve, 400))
    expect(apiPut).toHaveBeenCalledWith('/workspaces/10/snapshot', expect.objectContaining({ base_revision: 4, tabs: expect.any(Array) }))
  })

  it('preserves a benchmark universe role and selected family when cloning a legacy workspace tool', async () => {
    const store = useWorkspaceStore()
    store.workspace = {
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{
        id: 20, stable_key: 'us-top-down', name: 'US Top Down', position: 0, active_window_key: 'benchmark-list',
        layout_config: { root: { type: 'component', componentState: { instance_key: 'benchmark-list' } } },
        windows: [{ id: 30, instance_key: 'benchmark-list', tool_type: 'watchlist', title: 'Benchmarks', link_group: 'blue', configuration: { benchmark_family_key: 'sp500', benchmark_family_map_role: 'equal_weight' }, style: {}, state_schema_version: 1, position: 0 }],
      }],
    }

    store.cloneActiveTab()

    const clone = store.workspace.tabs[1].windows[0]
    expect(clone.instance_key).not.toBe('benchmark-list')
    expect(clone.configuration).toEqual(expect.objectContaining({
      workspace_role: 'benchmark-universe',
      benchmark_family_key: 'sp500',
      benchmark_family_map_role: 'equal_weight',
    }))
    expect(workspaceToolRole(clone)).toBe('benchmark-universe')
    expect(workspaceToolRole(store.workspace.tabs[0].windows[0])).toBe('benchmark-universe')
    expect(canonicalCatalogueFixture).toContainEqual(expect.objectContaining({
      key: 'benchmark-list', title: 'Benchmarks', tool_type: 'watchlist', configuration: { market_group: 'us-benchmarks' },
    }))
    await new Promise(resolve => setTimeout(resolve, 400))
    expect(apiPut).toHaveBeenCalledWith('/workspaces/10/snapshot', expect.objectContaining({
      tabs: expect.arrayContaining([expect.objectContaining({ windows: expect.arrayContaining([expect.objectContaining({ configuration: expect.objectContaining({ workspace_role: 'benchmark-universe', benchmark_family_key: 'sp500' }) })]) })]),
    }))
  })

  it('catalogues and preserves the semantic roles for factory list and ratio tools', async () => {
    const expected = [
      ['sector-list', 'sector-universe'],
      ['industry-list', 'industry-universe'],
      ['constituent-list', 'constituent-universe'],
      ['ratio-chart', 'relative-strength'],
    ] as const
    const store = useWorkspaceStore()
    store.toolCatalogue = canonicalCatalogueFixture
    const definitions = expected.map(([key]) => store.toolDefinition(key))
    expect(definitions.every(Boolean)).toBe(true)
    for (const [index, [, role]] of expected.entries()) {
      expect(workspaceToolRole({
        instance_key: definitions[index]!.instance_prefix,
        tool_type: definitions[index]!.tool_type,
        configuration: definitions[index]!.configuration ?? {},
      })).toBe(role)
    }

    store.workspace = {
      id: 10, user_id: 3, name: 'Role copy', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{
        id: 20, stable_key: 'roles', name: 'Roles', position: 0, active_window_key: 'sector-universe', layout_config: {},
        windows: expected.map(([key]) => {
          const definition = store.toolDefinition(key)!
          return {
            id: -1, instance_key: definition.instance_prefix, tool_type: definition.tool_type, title: definition.title,
            link_group: 'blue' as const, configuration: { ...(definition.configuration ?? {}) }, style: {}, state_schema_version: 1, position: 0,
          }
        }),
      }],
    }
    store.cloneActiveTab()
    const copiedRoles = store.workspace.tabs[1].windows.map(window => workspaceToolRole(window))
    expect(copiedRoles).toEqual(expected.map(([, role]) => role))
    // Let this test's debounced clone snapshot settle so it cannot bleed into
    // the next case's API mock call counts.
    await new Promise(resolve => setTimeout(resolve, 400))
  })

  it('does not let an older snapshot response replace a newer local tool edit', async () => {
    const oldResponse = deferred<any>()
    const store = useWorkspaceStore()
    store.workspace = {
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{
        id: 20, stable_key: 'us-top-down', name: 'US Top Down', position: 0, active_window_key: 'chart', layout_config: {},
        windows: [{ id: 30, instance_key: 'chart', tool_type: 'chart', title: 'Chart', link_group: 'blue', configuration: { expression: '=SPY/RSP' }, style: {}, state_schema_version: 1, position: 0 }],
      }],
    }
    apiPut.mockImplementationOnce(() => oldResponse.promise).mockImplementation(async (_path, payload) => ({
      ...store.workspace,
      revision: 6,
      tabs: payload.tabs,
    }))

    store.scheduleSnapshot()
    await vi.waitFor(() => expect(apiPut).toHaveBeenCalledTimes(1), { timeout: 1_000 })
    store.workspace.tabs[0].windows[0].configuration = { expression: '=NVDA/XLK' }
    store.scheduleSnapshot()
    await new Promise(resolve => setTimeout(resolve, 400))
    expect(apiPut).toHaveBeenCalledTimes(1)
    oldResponse.resolve({ ...store.workspace, revision: 5, tabs: [{ ...store.workspace.tabs[0], windows: [{ ...store.workspace.tabs[0].windows[0], configuration: { expression: '=SPY/RSP' } }] }] })

    await vi.waitFor(() => expect(apiPut).toHaveBeenCalledTimes(2), { timeout: 1_500 })
    expect(apiPut.mock.calls[1][1]).toEqual(expect.objectContaining({ base_revision: 5 }))
    expect(store.workspace.tabs[0].windows[0].configuration.expression).toBe('=NVDA/XLK')
    expect(store.workspace.revision).toBe(6)
  })

  it('flushes newer edits when their debounce expires during an earlier save', async () => {
    const response = deferred<any>()
    const store = useWorkspaceStore()
    const original = {
      id: 10, user_id: 3, name: 'Personal', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{ id: 20, stable_key: 'personal', name: 'Personal', position: 0, active_window_key: 'chart', layout_config: {}, windows: [
        { id: 30, instance_key: 'chart', tool_type: 'chart', title: 'Chart', link_group: 'blue', configuration: { symbol: 'SPY' }, style: {}, state_schema_version: 1, position: 0 },
      ] }],
    }
    store.workspace = structuredClone(original)
    apiPut.mockImplementationOnce(() => response.promise)
      .mockImplementation(async (_path, payload) => ({ ...original, ...payload, revision: 6 }))
    const saving = store.saveSnapshot()
    store.workspace.tabs[0].windows[0].configuration = { symbol: 'NVDA' }
    store.scheduleSnapshot()
    // Deliberately let the real 350ms debounce join the still-pending write.
    // No further mutation will arrive to rescue a dropped trailing save.
    await new Promise(resolve => setTimeout(resolve, 400))
    response.resolve({ ...original, revision: 5 })
    await saving

    await vi.waitFor(() => expect(apiPut).toHaveBeenCalledTimes(2), { timeout: 1_500 })
    expect(apiPut.mock.calls[1][1]).toEqual(expect.objectContaining({ base_revision: 5 }))
    expect(store.workspace.tabs[0].windows[0].configuration.symbol).toBe('NVDA')
    expect(store.workspace.revision).toBe(6)
  })

  it('does not replace a switched workspace with an earlier save acknowledgement', async () => {
    const response = deferred<any>()
    const store = useWorkspaceStore()
    const original = {
      id: 10, user_id: 3, name: 'First', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {}, tabs: [],
    }
    store.workspace = original
    apiPut.mockImplementationOnce(() => response.promise)
    const saving = store.saveSnapshot()
    store.workspace = { ...original, id: 11, name: 'Second', revision: 9 }

    response.resolve({ ...original, revision: 5 })
    await saving

    expect(store.workspace).toEqual(expect.objectContaining({ id: 11, name: 'Second', revision: 9 }))
    expect(apiPost).not.toHaveBeenCalled()
  })

  it('does not roll back an already newer revision when acknowledging a superseded save', async () => {
    const response = deferred<any>()
    const store = useWorkspaceStore()
    const original = {
      id: 10, user_id: 3, name: 'Personal', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {}, tabs: [],
    }
    store.workspace = { ...original }
    apiPut.mockImplementationOnce(() => response.promise)
      .mockImplementation(async (_path, payload) => ({ ...original, ...payload, revision: 8 }))
    const saving = store.saveSnapshot()
    store.workspace.revision = 7
    store.workspace.name = 'Newer local state'
    store.scheduleSnapshot()

    response.resolve({ ...original, revision: 5 })
    await saving

    expect(store.workspace.revision).toBe(7)
    expect(store.workspace.name).toBe('Newer local state')
    await vi.waitFor(() => expect(apiPut).toHaveBeenCalledTimes(2), { timeout: 1_500 })
    expect(apiPut.mock.calls[1][1]).toEqual(expect.objectContaining({ base_revision: 7, name: 'Newer local state' }))
  })

  it('acknowledges a conflict retry without replacing edits made during that retry', async () => {
    const retryResponse = deferred<any>()
    const store = useWorkspaceStore()
    const baseline = {
      id: 10, user_id: 3, name: 'Personal', is_default: false, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{ id: 20, stable_key: 'personal', name: 'Personal', position: 0, active_window_key: 'chart', layout_config: {}, windows: [
        { id: 30, instance_key: 'chart', tool_type: 'chart', title: 'Chart', link_group: 'blue', configuration: { symbol: 'SPY' }, style: {}, state_schema_version: 1, position: 0 },
      ] }],
    }
    const remote = structuredClone(baseline)
    remote.revision = 5
    apiGet.mockResolvedValueOnce(baseline).mockResolvedValueOnce(remote)
    await store.loadDefault()
    store.workspace!.tabs[0].windows[0].configuration = { symbol: 'QQQ' }
    apiPut.mockRejectedValueOnce(new Error('API PUT /workspaces/10/snapshot → 409: conflict'))
      .mockImplementationOnce(() => retryResponse.promise)
      .mockImplementation(async (_path, payload) => ({ ...baseline, ...payload, revision: 7 }))
    const saving = store.saveSnapshot()
    await vi.waitFor(() => expect(apiPut).toHaveBeenCalledTimes(2))
    store.workspace!.tabs[0].windows[0].configuration = { symbol: 'NVDA' }
    store.scheduleSnapshot()
    const accepted = structuredClone(remote)
    accepted.revision = 6
    accepted.tabs[0].windows[0].configuration = { symbol: 'QQQ' }
    retryResponse.resolve(accepted)
    await saving

    expect(store.workspace?.revision).toBe(6)
    expect(store.workspace?.tabs[0].windows[0].configuration.symbol).toBe('NVDA')
    await vi.waitFor(() => expect(apiPut).toHaveBeenCalledTimes(3), { timeout: 1_500 })
    expect(apiPut.mock.calls[2][1]).toEqual(expect.objectContaining({ base_revision: 6 }))
    expect(store.workspace?.revision).toBe(7)
    expect(apiPost).not.toHaveBeenCalled()
  })

  it('does not recover away a newly opened tool when an older snapshot conflicts', async () => {
    let rejectOld!: (error: Error) => void
    const store = useWorkspaceStore()
    store.workspace = {
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{
        id: 20, stable_key: 'us-top-down', name: 'US Top Down', position: 0, active_window_key: 'chart', layout_config: {},
        windows: [{ id: 30, instance_key: 'chart', tool_type: 'chart', title: 'Chart', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 0 }],
      }],
    }
    apiPut.mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectOld = reject }))
      .mockImplementation(async (_path, payload) => ({ ...store.workspace, revision: 5, tabs: payload.tabs }))

    store.scheduleSnapshot()
    await vi.waitFor(() => expect(apiPut).toHaveBeenCalledTimes(1), { timeout: 1_000 })
    const opened = store.openTool({ key: 'watchlist', tool_type: 'watchlist', title: 'WatchList', instance_prefix: 'watchlist', configuration: { personal: true } })
    rejectOld(new Error('API PUT /workspaces/10/snapshot → 409: conflict'))

    await vi.waitFor(() => expect(apiPut).toHaveBeenCalledTimes(2), { timeout: 1_500 })
    expect(apiPost).not.toHaveBeenCalled()
    expect(store.workspace?.tabs[0].windows.some(window => window.instance_key === opened?.instance_key)).toBe(true)
    expect(store.workspace?.tabs[0].active_window_key).toBe(opened?.instance_key)
  })

  it('keeps recovery semantics when a late local callback follows the mutation under test', async () => {
    const baseline = {
      id: 10, user_id: 3, name: 'Personal', is_default: false, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{ id: 20, stable_key: 'personal', name: 'Personal', position: 0, active_window_key: 'chart', layout_config: {}, windows: [
        { id: 30, instance_key: 'chart', tool_type: 'chart', title: 'Chart', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 0 },
      ] }],
    }
    apiGet.mockResolvedValueOnce(baseline)
    const store = useWorkspaceStore()
    await store.loadDefault()
    const opened = store.openTool({ key: 'notes', tool_type: 'notes', title: 'Notes', instance_prefix: 'notes', configuration: {} })
    expect(opened).toBeTruthy()

    let rejectOld!: (cause: Error) => void
    const oldResponse = new Promise<any>((_resolve, reject) => { rejectOld = reject })
    const latest = JSON.parse(JSON.stringify(baseline))
    latest.revision = 5
    latest.name = 'Remote Personal'
    const recovery = { ...store.workspace, id: 11, name: 'Personal Recovery', is_default: false, settings: { recovery_of_workspace_id: 10, recovery_of_revision: 4 } }
    apiPut.mockImplementationOnce(() => oldResponse)
    apiGet.mockResolvedValueOnce(latest)
    apiPost.mockResolvedValueOnce(recovery)

    const savePromise = store.saveSnapshot()
    await vi.waitFor(() => expect(apiPut).toHaveBeenCalledTimes(1), { timeout: 1_000 })
    // Simulate a late configuration/layout callback while the request is in
    // flight. The request already contained the locally opened Notes window,
    // so the conflict must still preserve that edit in a recovery copy.
    store.workspace!.tabs[0].windows[0].configuration = { symbol: 'SPY' }
    store.scheduleSnapshot()
    rejectOld(new Error('API PUT /workspaces/10/snapshot → 409: conflict'))

    await savePromise

    expect(apiGet).toHaveBeenCalledWith('/workspaces/10')
    expect(apiPost).toHaveBeenCalledWith('/workspaces', expect.objectContaining({ name: 'Personal Recovery', is_default: false }))
    expect(store.error).toContain('preserved as')
  })

  it('persists layout geometry without deleting tools from an observational key list', async () => {
    const store = useWorkspaceStore()
    store.workspace = {
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{
        id: 20, stable_key: 'us-top-down', name: 'US Top Down', position: 0, active_window_key: 'chart', layout_config: {},
        windows: [
          { id: 30, instance_key: 'chart', tool_type: 'chart', title: 'Chart', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 0 },
          { id: 31, instance_key: 'notes', tool_type: 'notes', title: 'Notes', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 1 },
        ],
      }],
    }
    apiPut.mockResolvedValue(store.workspace)

    store.applyActiveLayout({ root: { componentState: { instance_key: 'chart' } } }, ['chart'])

    expect(store.activeTab?.windows.map(window => window.instance_key)).toEqual(['chart', 'notes'])
    expect(store.activeTab?.active_window_key).toBe('chart')
    await new Promise(resolve => setTimeout(resolve, 400))
    expect(apiPut).toHaveBeenCalled()
  })

  it('manages personal layouts without mutating factory tool state', async () => {
    const store = useWorkspaceStore()
    store.workspace = {
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4, schema_version: 1, settings: { factory_id: 'us-top-down' },
      tabs: [
        { id: 20, stable_key: 'one', name: 'One', position: 0, active_window_key: 'chart', layout_config: {}, windows: [{ id: 30, instance_key: 'chart', tool_type: 'chart', title: 'Chart', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 0 }] },
        { id: 21, stable_key: 'two', name: 'Two', position: 1, active_window_key: 'chart-2', layout_config: {}, windows: [{ id: 31, instance_key: 'chart-2', tool_type: 'chart', title: 'Chart', link_group: 'red', configuration: {}, style: {}, state_schema_version: 1, position: 0 }] },
      ],
    }
    apiPut.mockResolvedValue(store.workspace)

    expect(store.renameTab('one', ' Morning   Scan ')).toBe(true)
    expect(store.workspace.tabs[0].name).toBe('Morning Scan')
    expect(store.reorderTabs('two', 'one')).toBe(true)
    expect(store.workspace.tabs.map(tab => tab.stable_key)).toEqual(['two', 'one'])
    expect(store.deleteTab('two')).toBe(true)
    expect(store.workspace.tabs).toHaveLength(1)
    expect(store.deleteTab('one')).toBe(false)
    expect(store.workspace.tabs).toHaveLength(1)

    const snapshot = JSON.parse(store.exportWorkspaceSnapshot()!)
    expect(snapshot.tabs).toHaveLength(1)
    expect(store.importWorkspaceSnapshot({ ...snapshot, tabs: [{ ...snapshot.tabs[0], stable_key: 'imported', name: ' Imported ' }] })).toBe(true)
    expect(store.activeTabKey).toBe('imported')
    expect(store.workspace.tabs[0].name).toBe('Imported')
    await new Promise(resolve => setTimeout(resolve, 400))
    expect(apiPut).toHaveBeenCalledWith('/workspaces/10/snapshot', expect.objectContaining({ tabs: expect.any(Array) }))
  })

  it('offers a same-workspace layout restore without reusing deleted server row IDs', async () => {
    const store = useWorkspaceStore()
    store.workspace = {
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [
        { id: 20, stable_key: 'one', name: 'One', position: 0, active_window_key: 'chart-one', layout_config: {}, windows: [{ id: 30, instance_key: 'chart-one', tool_type: 'chart', title: 'Chart', link_group: 'blue', configuration: { timeframe: 'D1' }, style: {}, state_schema_version: 1, position: 0 }] },
        { id: 21, stable_key: 'two', name: 'Two', position: 1, active_window_key: 'chart-two', layout_config: {}, windows: [{ id: 31, instance_key: 'chart-two', tool_type: 'chart', title: 'Chart', link_group: 'red', configuration: { timeframe: 'W1' }, style: {}, state_schema_version: 1, position: 0 }] },
      ],
    }
    apiPut.mockResolvedValue(store.workspace)

    const recovery = store.captureTabRecovery('two')!
    expect(store.deleteTab('two')).toBe(true)
    expect(store.workspace.tabs.map(tab => tab.stable_key)).toEqual(['one'])

    store.workspace = { ...store.workspace, id: 11 }
    expect(store.restoreDeletedTab(recovery)).toBe(false)
    expect(store.workspace.tabs.map(tab => tab.stable_key)).toEqual(['one'])
    store.workspace = { ...store.workspace, id: recovery.workspace_id }

    expect(store.restoreDeletedTab(recovery)).toBe(true)
    expect(store.workspace.tabs.map(tab => tab.stable_key)).toEqual(['one', 'two'])
    expect(store.activeTabKey).toBe('two')
    expect(store.workspace.tabs[1].id).toBeLessThan(0)
    expect(store.workspace.tabs[1].windows[0].id).toBeLessThan(0)
    expect(store.workspace.tabs[1].windows[0].configuration).toEqual({ timeframe: 'W1' })
    await new Promise(resolve => setTimeout(resolve, 400))
    expect(apiPut).toHaveBeenCalledWith('/workspaces/10/snapshot', expect.objectContaining({
      tabs: expect.arrayContaining([expect.objectContaining({ stable_key: 'two', windows: [expect.objectContaining({ instance_key: 'chart-two', configuration: { timeframe: 'W1' } })] })]),
    }))
  })

  it('flushes an explicit Undo after an older snapshot settles, preserving the restored name and position', async () => {
    const earlierWrite = deferred<any>()
    const store = useWorkspaceStore()
    const original = {
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [
        { id: 20, stable_key: 'one', name: 'One', position: 0, active_window_key: 'chart-one', layout_config: {}, windows: [{ id: 30, instance_key: 'chart-one', tool_type: 'chart', title: 'Chart', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 0 }] },
        { id: 21, stable_key: 'review', name: 'Review layout', position: 1, active_window_key: 'chart-review', layout_config: {}, windows: [{ id: 31, instance_key: 'chart-review', tool_type: 'chart', title: 'Chart', link_group: 'red', configuration: {}, style: {}, state_schema_version: 1, position: 0 }] },
      ],
    }
    store.workspace = structuredClone(original)
    const recovery = store.captureTabRecovery('review')!
    apiPut.mockImplementationOnce(() => earlierWrite.promise)
      .mockImplementation(async (_path, payload) => ({ ...payload, revision: 6 }))

    store.scheduleSnapshot()
    await vi.waitFor(() => expect(apiPut).toHaveBeenCalledTimes(1), { timeout: 1_000 })
    expect(store.deleteTab('review')).toBe(true)
    expect(store.restoreDeletedTab(recovery)).toBe(true)
    const undoSave = store.saveSnapshot()

    // Undo's explicit flush must wait for the earlier revision, then send the
    // current restored layout instead of treating the old clone/delete state
    // as the durable checkpoint.
    expect(apiPut).toHaveBeenCalledTimes(1)
    earlierWrite.resolve({ ...original, revision: 5 })
    await undoSave

    expect(apiPut).toHaveBeenCalledTimes(2)
    expect(apiPut.mock.calls[1][1]).toEqual(expect.objectContaining({
      base_revision: 5,
      tabs: expect.arrayContaining([expect.objectContaining({ stable_key: 'review', name: 'Review layout', position: 1 })]),
    }))
    expect(store.workspace?.tabs.map(tab => tab.stable_key)).toEqual(['one', 'review'])
  })

  it('rejects malformed or duplicate imported layouts', () => {
    const store = useWorkspaceStore()
    store.workspace = {
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{ id: 20, stable_key: 'one', name: 'One', position: 0, active_window_key: null, layout_config: {}, windows: [] }],
    }
    expect(store.importWorkspaceSnapshot({ tabs: [] })).toBe(false)
    expect(store.importWorkspaceSnapshot({ tabs: [{ stable_key: 'duplicate', name: 'A', windows: [] }, { stable_key: 'duplicate', name: 'B', windows: [] }] })).toBe(false)
    expect(store.workspace.tabs[0].stable_key).toBe('one')
  })

  it('closes a tool through serializable state but protects the final tool in a tab', () => {
    const store = useWorkspaceStore()
    store.workspace = {
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{
        id: 20, stable_key: 'us-top-down', name: 'US Top Down', position: 0, active_window_key: 'chart', layout_config: {},
        windows: [
          { id: 30, instance_key: 'chart', tool_type: 'chart', title: 'Chart', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 0 },
          { id: 31, instance_key: 'notes', tool_type: 'notes', title: 'Notes', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 1 },
        ],
      }],
    }

    expect(store.closeTool('chart')).toBe(true)
    expect(store.activeTab?.windows.map(window => window.instance_key)).toEqual(['notes'])
    expect(store.activeTab?.active_window_key).toBe('notes')
    expect(store.closeTool('notes')).toBe(false)
    expect(store.error).toContain('at least one tool')
  })

  it('persists a tool link-group change as serialized workspace state', async () => {
    const store = useWorkspaceStore()
    store.workspace = {
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{
        id: 20, stable_key: 'us-top-down', name: 'US Top Down', position: 0, active_window_key: 'chart', layout_config: {},
        windows: [{ id: 30, instance_key: 'chart', tool_type: 'chart', title: 'Chart', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 0 }],
      }],
    }
    apiPut.mockResolvedValue(store.workspace)

    expect(store.updateToolLinkGroup('chart', 'yellow')).toBe(true)
    expect(store.activeTab?.windows[0].link_group).toBe('yellow')
    expect(store.updateToolLinkGroup('missing', 'red')).toBe(false)

    await new Promise(resolve => setTimeout(resolve, 400))
    expect(apiPut).toHaveBeenCalledWith('/workspaces/10/snapshot', expect.objectContaining({
      tabs: [expect.objectContaining({ windows: [expect.objectContaining({ instance_key: 'chart', link_group: 'yellow' })] })],
    }))
  })

  it('captures the current symbol when moving a shared tool into grey isolation', () => {
    const store = useWorkspaceStore()
    store.workspace = {
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{
        id: 20, stable_key: 'us-top-down', name: 'US Top Down', position: 0, active_window_key: 'chart', layout_config: {},
        windows: [{ id: 30, instance_key: 'chart', tool_type: 'chart', title: 'Chart', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 0 }],
      }],
    }
    store.publishSymbol({ symbol: 'XLK', group: 'blue', sourceWindowKey: 'sector-list' })

    expect(store.updateToolLinkGroup('chart', 'grey')).toBe(true)
    expect(store.activeTab?.windows[0].configuration.symbol).toBe('XLK')
    expect(store.symbolForLinkGroup('grey', String(store.activeTab?.windows[0].configuration.symbol))).toBe('XLK')
  })

  it('persists Yellow wildcard symbol identity and captures it when the receiver becomes Grey', () => {
    const store = useWorkspaceStore()
    vi.spyOn(store, 'scheduleSnapshot').mockImplementation(() => {})
    store.workspace = {
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{
        id: 20, stable_key: 'us-top-down', name: 'US Top Down', position: 0, active_window_key: 'yellow-chart', layout_config: {},
        windows: [
          { id: 30, instance_key: 'red-list', tool_type: 'watchlist', title: 'Red list', link_group: 'red', configuration: { symbol: 'SPY' }, style: {}, state_schema_version: 1, position: 0 },
          { id: 31, instance_key: 'yellow-chart', tool_type: 'chart', title: 'Yellow chart', link_group: 'yellow', configuration: { symbol: 'SPY', instrument_id: 7 }, style: {}, state_schema_version: 1, position: 1 },
        ],
      }],
    }

    store.publishSymbol({ symbol: 'XLK', instrumentId: 42, group: 'red', sourceWindowKey: 'red-list' })

    expect(store.workspace?.settings.linked_symbols).toMatchObject({
      red: { symbol: 'XLK', instrument_id: 42 },
      yellow: { symbol: 'XLK', instrument_id: 42, source_group: 'red' },
    })
    expect(store.symbolForLinkGroup('yellow')).toBe('XLK')
    expect(store.updateToolLinkGroup('yellow-chart', 'grey', 'XLK')).toBe(true)
    expect(store.activeTab?.windows[1]).toMatchObject({
      link_group: 'grey',
      configuration: { symbol: 'XLK', instrument_id: 42 },
    })
  })

  it('publishes a selected row only to its owning link group and retains grey isolation', () => {
    const store = useWorkspaceStore()
    store.workspace = {
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{
        id: 20, stable_key: 'us-top-down', name: 'US Top Down', position: 0, active_window_key: 'blue-chart', layout_config: {},
        windows: [
          { id: 30, instance_key: 'blue-chart', tool_type: 'chart', title: 'Blue chart', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 0 },
          { id: 31, instance_key: 'red-list', tool_type: 'watchlist', title: 'Red list', link_group: 'red', configuration: {}, style: {}, state_schema_version: 1, position: 1 },
          { id: 32, instance_key: 'grey-chart', tool_type: 'chart', title: 'Grey chart', link_group: 'grey', configuration: { symbol: 'IWM' }, style: {}, state_schema_version: 1, position: 2 },
        ],
      }],
    }

    expect(store.selectToolSymbol('red-list', 'XLK', 42)).toBe(true)
    expect(store.linkedSymbol).toBe('SPY')
    expect(store.symbolForLinkGroup('red')).toBe('XLK')
    expect(store.symbolForLinkGroup('yellow')).toBe('XLK')
    expect(store.activeTab?.windows[1].configuration).toMatchObject({ symbol: 'XLK', instrument_id: 42 })

    expect(store.selectToolSymbol('grey-chart', 'XLE', 43)).toBe(true)
    expect(store.symbolForLinkGroup('grey', 'IWM')).toBe('IWM')
    expect(store.activeTab?.windows[2].configuration).toMatchObject({ symbol: 'XLE', instrument_id: 43 })
    expect(store.symbolForLinkGroup('grey', String(store.activeTab?.windows[2].configuration.symbol))).toBe('XLE')
    expect(store.symbolForLinkGroup('yellow')).toBe('XLK')
  })

  it('keeps canonical instrument identity on shared links and removes stale ids on ticker-only navigation', () => {
    const store = useWorkspaceStore()
    store.workspace = {
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{
        id: 20, stable_key: 'us-top-down', name: 'US Top Down', position: 0, active_window_key: 'chart', layout_config: {},
        windows: [{ id: 30, instance_key: 'chart', tool_type: 'chart', title: 'Chart', link_group: 'blue', configuration: { symbol: 'SPY' }, style: {}, state_schema_version: 1, position: 0 }],
      }],
    }

    store.publishSymbol({ symbol: 'XLK', instrumentId: 42, group: 'blue', sourceWindowKey: 'workstation' })
    expect(store.linkedSymbols.blue).toMatchObject({ symbol: 'XLK', instrumentId: 42 })
    expect(store.activeTab?.windows[0].configuration).toMatchObject({ symbol: 'XLK', instrument_id: 42 })

    store.publishSymbol({ symbol: 'XLE', group: 'blue', sourceWindowKey: 'workstation' })
    expect(store.linkedSymbols.blue).toMatchObject({ symbol: 'XLE' })
    expect(store.linkedSymbols.blue?.instrumentId).toBeUndefined()
    expect(store.activeTab?.windows[0].configuration).toMatchObject({ symbol: 'XLE' })
    expect(store.activeTab?.windows[0].configuration).not.toHaveProperty('instrument_id')
  })

  it('resets a factory workspace only through the backend factory-reset endpoint', async () => {
    const store = useWorkspaceStore()
    store.workspace = {
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4, schema_version: 1, settings: { factory_id: 'us-top-down' },
      tabs: [{ id: 20, stable_key: 'custom', name: 'Custom', position: 0, active_window_key: null, layout_config: {}, windows: [] }],
    }
    const reset = { ...store.workspace, revision: 5, tabs: [{ ...store.workspace.tabs[0], stable_key: 'us-top-down', name: 'US Top Down' }] }
    apiPost.mockResolvedValue(reset)

    await expect(store.resetFactoryWorkspace()).resolves.toBe(true)
    expect(apiPost).toHaveBeenCalledWith('/workspaces/10/reset-factory', {})
    expect(store.activeTabKey).toBe('us-top-down')
  })

  it('manages persisted workspaces through the workspace CRUD APIs', async () => {
    const base = {
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4,
      schema_version: 1, settings: {}, tabs: [],
    }
    const created = { ...base, id: 11, name: 'Research', is_default: false, position: 1 }
    apiPost.mockResolvedValueOnce(created).mockResolvedValueOnce({ ...created, id: 12, name: 'Research Copy', position: 2 })
    apiGet.mockResolvedValue([{ ...base }, { ...created }])
    apiPatch.mockResolvedValue({ ...created, name: 'Morning Scan', revision: 5 })
    apiDelete.mockResolvedValue(undefined)
    const store = useWorkspaceStore()
    store.workspace = base

    await expect(store.createWorkspace(' Research ')).resolves.toMatchObject({ name: 'Research' })
    await expect(store.cloneWorkspace()).resolves.toMatchObject({ name: 'Research Copy' })
    await expect(store.renameWorkspace(' Morning Scan ')).resolves.toMatchObject({ name: 'Morning Scan' })
    expect(apiPatch).toHaveBeenCalledWith('/workspaces/12', { name: 'Morning Scan' })
    store.workspace = { ...store.workspace!, is_default: false }
    apiGet.mockResolvedValue([{ ...base }])
    await expect(store.deleteCurrentWorkspace()).resolves.toBe(true)
    expect(apiDelete).toHaveBeenCalledWith('/workspaces/11')
  })

  it('reconciles cloned layout component identities and persists the repaired dock tree', async () => {
    const source = {
      id: 77, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 8,
      schema_version: 1, settings: { factory_id: 'us-top-down' },
      tabs: [{
        id: 90, stable_key: 'us-top-down', name: 'US Top Down', position: 0,
        active_window_key: 'benchmark-list',
        layout_config: { root: { type: 'stack', content: [
          { type: 'component', componentName: 'workstation-tool', title: 'Benchmarks', componentState: { instance_key: 'benchmark-list' } },
          { type: 'component', componentName: 'workstation-tool', title: 'Chart', componentState: { instance_key: 'chart-main' } },
        ] } },
        windows: [
          { id: 1, instance_key: 'benchmark-list', tool_type: 'watchlist', title: 'Benchmarks', link_group: 'blue', configuration: { market_group: 'us-benchmarks' }, style: {}, state_schema_version: 1, position: 0 },
          { id: 2, instance_key: 'chart-main', tool_type: 'chart', title: 'Chart', link_group: 'blue', configuration: { symbol: 'SPY' }, style: {}, state_schema_version: 1, position: 1 },
        ],
      }],
    }
    const cloned = {
      ...source,
      id: 78,
      name: 'US Top Down Copy',
      is_default: false,
      revision: 1,
      tabs: [{
        ...source.tabs[0],
        id: 91,
        windows: [
          { ...source.tabs[0].windows[0], id: 3, instance_key: 'benchmark-list-copy-1' },
          { ...source.tabs[0].windows[1], id: 4, instance_key: 'chart-copy-1' },
        ],
      }],
    }
    const saved = { ...cloned, revision: 2 }
    apiPost.mockResolvedValueOnce(cloned)
    apiGet.mockResolvedValueOnce([])
    apiPut.mockResolvedValueOnce(saved)
    const store = useWorkspaceStore()
    store.workspace = source

    const result = await store.cloneWorkspace()

    expect(result?.tabs[0]).toMatchObject({
      active_window_key: 'benchmark-list-copy-1',
      layout_config: { root: { content: [
        { componentState: { instance_key: 'benchmark-list-copy-1' } },
        { componentState: { instance_key: 'chart-copy-1' } },
      ] } },
    })
    await vi.waitFor(() => expect(apiPut).toHaveBeenCalledWith('/workspaces/78/snapshot', expect.objectContaining({
      tabs: [expect.objectContaining({
        active_window_key: 'benchmark-list-copy-1',
        layout_config: expect.objectContaining({ root: expect.objectContaining({ content: expect.arrayContaining([
          expect.objectContaining({ componentState: { instance_key: 'benchmark-list-copy-1' } }),
          expect.objectContaining({ componentState: { instance_key: 'chart-copy-1' } }),
        ]) }) }),
      })],
    })))
  })

  it('settles a stale layout snapshot before renaming the active workspace', async () => {
    const base = {
      id: 10, user_id: 3, name: 'New Workspace', is_default: false, position: 1, revision: 4,
      schema_version: 1, settings: {}, tabs: [],
    }
    const saved = { ...base, revision: 5 }
    const renamed = { ...base, name: 'Morning Review', revision: 6 }
    const pendingPut = deferred<typeof saved>()
    apiPut.mockReturnValueOnce(pendingPut.promise)
    apiPatch.mockResolvedValue(renamed)
    const store = useWorkspaceStore()
    store.workspace = base

    // A layout observer has already started an older snapshot write.
    const pendingSave = store.saveSnapshot()
    await vi.waitFor(() => expect(apiPut).toHaveBeenCalledWith('/workspaces/10/snapshot', expect.any(Object)))
    const rename = store.renameWorkspace(' Morning Review ')
    await Promise.resolve()
    expect(apiPatch).not.toHaveBeenCalled()

    pendingPut.resolve(saved)
    await pendingSave
    await expect(rename).resolves.toMatchObject({ name: 'Morning Review' })
    expect(apiPatch).toHaveBeenCalledWith('/workspaces/10', { name: 'Morning Review' })
  })

  it('publishes an occurrence timestamp and clears it for ordinary symbol navigation', () => {
    const store = useWorkspaceStore()

    store.publishSymbol({ symbol: 'SPY', timestamp: '2026-01-02', group: 'blue' })
    expect(store.linkedSymbol).toBe('SPY')
    expect(store.linkedTimestamp).toBe('2026-01-02')

    store.publishSymbol({ symbol: 'XLK', group: 'blue' })
    expect(store.linkedSymbol).toBe('XLK')
    expect(store.linkedTimestamp).toBeNull()

    store.publishTimestamp('2025-12-29T21:00:00Z', 'blue', 'chart-panel')
    expect(store.linkedTimestamp).toBe('2025-12-29T21:00:00Z')
  })

  it('keeps an explicit occurrence date ahead of stale chart cursors during symbol hydration', () => {
    const store = useWorkspaceStore()

    const firstToken = store.publishSymbol({ symbol: 'SPY', timestamp: '2026-06-27T00:00:00Z', group: 'blue', sourceWindowKey: 'workstation' })!
    store.publishTimestamp('2025-12-29T21:00:00Z', 'blue', 'chart-panel')

    expect(store.linkedTimestamp).toBe('2026-06-27T00:00:00Z')

    const sameDateToken = store.publishSymbol({ symbol: 'QQQ', timestamp: '2026-06-27T00:00:00Z', group: 'blue', sourceWindowKey: 'workstation' })!
    expect(sameDateToken).not.toBe(firstToken)
    store.clearExplicitLinkedTimestamp('2026-06-27T00:00:00Z', firstToken, 'blue')
    store.publishTimestamp('2025-12-29T21:00:00Z', 'blue', 'chart-panel')

    expect(store.linkedTimestamp).toBe('2026-06-27T00:00:00Z')

    const newerToken = store.publishSymbol({ symbol: 'SPY', timestamp: '2026-06-28T00:00:00Z', group: 'blue', sourceWindowKey: 'workstation' })!
    store.clearExplicitLinkedTimestamp('2026-06-27T00:00:00Z', sameDateToken, 'blue')
    store.publishTimestamp('2025-12-29T21:00:00Z', 'blue', 'chart-panel')

    expect(store.linkedTimestamp).toBe('2026-06-28T00:00:00Z')

    store.clearExplicitLinkedTimestamp('2026-06-28T00:00:00Z', newerToken, 'blue')
    store.publishTimestamp('2025-12-29T21:00:00Z', 'blue', 'chart-panel')

    expect(store.linkedTimestamp).toBe('2025-12-29T21:00:00Z')
  })

  it('publishes cursor timestamps only to their link group while yellow receives all groups', () => {
    const store = useWorkspaceStore()

    store.publishTimestamp('2026-07-30T14:00:00Z', 'red', 'red-chart')

    expect(store.timestampForLinkGroup('red')).toBe('2026-07-30T14:00:00Z')
    expect(store.timestampForLinkGroup('yellow')).toBe('2026-07-30T14:00:00Z')
    expect(store.timestampForLinkGroup('blue')).toBeNull()
    expect(store.timestampForLinkGroup('grey')).toBeNull()
  })

  it('publishes timeframes per link group while preserving grey isolation', () => {
    const store = useWorkspaceStore()
    store.workspace = {
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [],
    }

    store.publishTimeframe('W1', 'blue')
    expect(store.linkedTimeframe).toBe('W1')
    expect(store.workspace.settings.linked_timeframe).toBe('W1')
    expect(store.timeframeForLinkGroup('blue')).toBe('W1')

    store.publishTimeframe('MN', 'red')
    expect(store.linkedTimeframe).toBe('W1')
    expect(store.timeframeForLinkGroup('red')).toBe('MN')
    expect(store.timeframeForLinkGroup('yellow')).toBe('MN')
    expect(store.workspace.settings.linked_timeframes).toEqual({ blue: 'W1', red: 'MN', yellow: 'MN' })
    expect(store.timeframeForLinkGroup('grey', 'MN')).toBe('MN')
  })

  it('preserves one-minute links while normalizing only the legacy monthly token', () => {
    const store = useWorkspaceStore()
    store.workspace = {
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [],
    }

    store.publishTimeframe('M1', 'blue')
    expect(store.linkedTimeframe).toBe('M1')
    expect(store.workspace.settings.linked_timeframe).toBe('M1')

    store.publishTimeframe('MN1', 'red')
    expect(store.timeframeForLinkGroup('red')).toBe('MN')
  })

  it('keeps a grey chart timeframe local to the persisted tool', () => {
    const store = useWorkspaceStore()
    store.workspace = {
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{ id: 20, stable_key: 'us-top-down', name: 'US Top Down', position: 0, active_window_key: 'grey-chart', layout_config: {}, windows: [{
        id: 21, instance_key: 'grey-chart', tool_type: 'chart', title: 'Grey chart', link_group: 'grey', configuration: { timeframe: 'D1' }, style: {}, state_schema_version: 1, position: 0,
      }] }],
    }

    const visibleTimeframe = computed(() => store.timeframeForTool('grey-chart'))
    expect(visibleTimeframe.value).toBe('D1')
    expect(store.updateToolTimeframe('grey-chart', 'MN')).toBe(true)
    expect(store.activeTab?.windows[0]?.configuration.timeframe).toBe('MN')
    expect(visibleTimeframe.value).toBe('MN')
    expect(store.linkedTimeframe).toBe('D1')
    expect(store.timeframeForLinkGroup('grey', 'MN')).toBe('MN')
  })

  it('separates a chart timeframe link from its shared symbol link', () => {
    const store = useWorkspaceStore()
    store.workspace = {
      id: 10, user_id: 3, name: '4 Timeframe', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{ id: 20, stable_key: 'four-timeframe', name: '4 Timeframe', position: 0, active_window_key: 'daily', layout_config: {}, windows: [{
        id: 21, instance_key: 'daily', tool_type: 'chart', title: 'Daily', link_group: 'blue', configuration: { symbol: 'SPY', timeframe: 'D1', timeframe_link_group: 'green' }, style: {}, state_schema_version: 1, position: 0,
      }] }],
    }
    const chart = store.activeTab!.windows[0]!

    expect(store.symbolForLinkGroup(chart.link_group)).toBe('SPY')
    expect(store.timeframeLinkGroupForTool(chart)).toBe('green')
    expect(store.updateToolTimeframe('daily', 'W1')).toBe(true)
    expect(store.timeframeForLinkGroup('green')).toBe('W1')
    expect(store.timeframeForLinkGroup('blue')).toBe('D1')
    expect(store.updateToolTimeframeLinkGroup('daily', 'orange')).toBe(true)
    expect(store.timeframeLinkGroupForTool(chart)).toBe('orange')
  })

  it('opens an implemented tool with serializable state and adds it to the saved layout', () => {
    const store = useWorkspaceStore()
    store.workspace = {
      id: 10, user_id: 3, name: 'Personal', is_default: false, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{ id: 20, stable_key: 'personal', name: 'Personal', position: 0, active_window_key: null, layout_config: { root: { type: 'row', content: [] } }, windows: [] }],
    }
    const definition: OpenableToolDefinition = { key: 'study-lab', tool_type: 'study_lab', title: 'Study Lab', instance_prefix: 'study-lab', configuration: { symbol: 'SPY' } }

    const opened = store.openTool(definition)

    expect(opened?.tool_type).toBe('study_lab')
    expect(store.activeTab?.windows).toHaveLength(1)
    expect((store.activeTab?.layout_config.root as { content: unknown[] }).content).toHaveLength(1)
    expect(store.activeTab?.active_window_key).toBe(opened?.instance_key)
  })

  it('opens a tool with a canonical source override for cross-surface launches', () => {
    const store = useWorkspaceStore()
    store.workspace = {
      id: 10, user_id: 3, name: 'Personal', is_default: false, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{ id: 20, stable_key: 'personal', name: 'Personal', position: 0, active_window_key: null, layout_config: { root: { type: 'row', content: [] } }, windows: [] }],
    }

    const opened = store.openTool(
      { key: 'market-map', tool_type: 'market_map', title: 'Market Map', instance_prefix: 'market-map', configuration: { color_metric: 'return' } },
      { source_id: 'watchlist:42' },
    )

    expect(opened?.configuration).toEqual({ color_metric: 'return', source_id: 'watchlist:42' })
  })

  it('adds new tools to an existing Golden Layout stack instead of creating narrow root columns', () => {
    const store = useWorkspaceStore()
    store.workspace = {
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{
        id: 20, stable_key: 'us-top-down', name: 'US Top Down', position: 0, active_window_key: 'benchmark-list',
        layout_config: {
          root: { type: 'row', content: [
            { type: 'column', size: '22fr', content: [{ type: 'component', componentState: { instance_key: 'benchmark-list' } }] },
            { type: 'column', size: '78fr', content: [{ type: 'stack', content: [{ type: 'component', componentState: { instance_key: 'primary-chart' } }] }] },
          ] },
        },
        windows: [
          { id: 30, instance_key: 'benchmark-list', tool_type: 'watchlist', title: 'Benchmarks', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 0 },
          { id: 31, instance_key: 'primary-chart', tool_type: 'chart', title: 'Chart', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 1 },
        ],
      }],
    }
    const opened = store.openTool({ key: 'watchlist', tool_type: 'watchlist', title: 'WatchList', instance_prefix: 'watchlist', configuration: { personal: true } })
    const root = store.activeTab?.layout_config.root as { content: Array<Record<string, any>> }
    expect(root.content).toHaveLength(2)
    const stack = root.content[1].content[0] as { type: string; content: Array<Record<string, any>> }
    expect(stack.type).toBe('stack')
    expect(stack.content.at(-1)?.componentState.instance_key).toBe(opened?.instance_key)
  })

  it('persists active Golden Layout tab changes and rejects unknown window keys', () => {
    const store = useWorkspaceStore()
    store.workspace = {
      id: 10, user_id: 3, name: 'Personal', is_default: false, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{ id: 20, stable_key: 'personal', name: 'Personal', position: 0, active_window_key: 'chart', layout_config: {}, windows: [
        { id: 30, instance_key: 'chart', tool_type: 'chart', title: 'Chart', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 0 },
        { id: 31, instance_key: 'notes', tool_type: 'notes', title: 'Notes', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 1 },
      ] }],
    }

    expect(store.setActiveWindow('missing')).toBe(false)
    expect(store.setActiveWindow('notes')).toBe(true)
    expect(store.activeTab?.active_window_key).toBe('notes')
    expect(store.setActiveWindow('notes')).toBe(false)
  })

  it('persists pop-out geometry only when it actually changes', () => {
    const store = useWorkspaceStore()
    store.workspace = {
      id: 10, user_id: 3, name: 'Personal', is_default: false, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{ id: 20, stable_key: 'personal', name: 'Personal', position: 0, active_window_key: 'chart', layout_config: {}, windows: [{
        id: 30, instance_key: 'chart', tool_type: 'chart', title: 'Chart', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 0,
      }] }],
    }

    expect(store.updateToolStyle('chart', { popout: { left: 10, top: 20, width: 900, height: 600 } })).toBe(true)
    expect(store.updateToolStyle('chart', { popout: { left: 10, top: 20, width: 900, height: 600 } })).toBe(false)
    expect(store.activeTab?.windows[0]?.style).toEqual({ popout: { left: 10, top: 20, width: 900, height: 600 } })
  })

  it('exposes implemented analysis surfaces through the workstation tool registry', () => {
    expect(canonicalCatalogueFixture.map(tool => tool.tool_type)).toEqual(expect.arrayContaining([
      'relative_rotation', 'breadth', 'technical_summary', 'coverage', 'report', 'research_results',
    ]))
  })

  it('preserves local recovery when unrelated workspace settings conflict', async () => {
    const store = useWorkspaceStore()
    const baseline = {
      id: 10, user_id: 3, name: 'Personal', is_default: false, position: 0, revision: 4, schema_version: 1,
      settings: { factory_id: 'us-top-down', custom_layout: 'baseline' },
      tabs: [{ id: 20, stable_key: 'personal', name: 'Personal', position: 0, active_window_key: null, layout_config: { root: { type: 'row', content: [] } }, windows: [] }],
    }
    apiGet.mockResolvedValueOnce(baseline)
    await store.loadDefault()
    store.workspace!.settings.custom_layout = 'local'
    const latest = structuredClone(baseline)
    latest.revision = 5
    latest.settings.custom_layout = 'remote'
    const recovery = {
      ...store.workspace,
      id: 11,
      name: 'Personal Recovery',
      is_default: false,
      settings: { custom_layout: 'local', recovery_of_workspace_id: 10, recovery_of_revision: 4 },
    }
    apiPut.mockRejectedValue(new Error('API PUT /workspaces/10/snapshot → 409: conflict'))
    apiGet.mockResolvedValueOnce(latest)
    apiPost.mockResolvedValue(recovery)

    await store.saveSnapshot()

    expect(apiGet).toHaveBeenCalledWith('/workspaces/10')
    expect(apiPost).toHaveBeenCalledWith('/workspaces', expect.objectContaining({ name: 'Personal Recovery', is_default: false, settings: recovery.settings }))
    expect(store.workspace?.revision).toBe(5)
    expect(store.error).toContain('preserved as')
  })

  it('retries a snapshot when independent windows changed from the same persisted baseline', async () => {
    const store = useWorkspaceStore()
    const baseline = {
      id: 10, user_id: 3, name: 'Personal', is_default: false, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{ id: 20, stable_key: 'personal', name: 'Personal', position: 0, active_window_key: 'chart', layout_config: { root: { type: 'row', content: [] } }, windows: [
        { id: 30, instance_key: 'chart', tool_type: 'chart', title: 'Chart', link_group: 'blue', configuration: { symbol: 'SPY' }, style: {}, state_schema_version: 1, position: 0 },
        { id: 31, instance_key: 'notes', tool_type: 'notes', title: 'Notes', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 1 },
      ] }],
    }
    apiGet.mockResolvedValueOnce(baseline)
    await store.loadDefault()
    store.workspace!.tabs[0].windows[0].configuration = { symbol: 'QQQ' }
    const latest = structuredClone(baseline)
    latest.revision = 5
    latest.tabs[0].windows[1].configuration = { draft: 'remote note' }
    const saved = structuredClone(latest)
    saved.revision = 6
    apiPut.mockRejectedValueOnce(new Error('API PUT /workspaces/10/snapshot → 409: conflict')).mockResolvedValueOnce(saved)
    apiGet.mockResolvedValueOnce(latest)

    await store.saveSnapshot()

    expect(apiPost).not.toHaveBeenCalled()
    expect(apiPut).toHaveBeenCalledTimes(2)
    expect(apiPut.mock.calls[1][1]).toEqual(expect.objectContaining({ base_revision: 5 }))
    expect(store.workspace?.revision).toBe(6)
  })

  it('merges per-group link settings when a snapshot revision changes concurrently', async () => {
    const baseline = {
      id: 10, user_id: 3, name: 'Personal', is_default: false, position: 0, revision: 4, schema_version: 1,
      settings: {
        linked_timeframe: 'D1',
        linked_timeframes: { blue: 'D1', red: 'D1', yellow: 'D1' },
        linked_symbols: {
          blue: { symbol: 'SPY', instrument_id: 1 },
          red: { symbol: 'SPY', instrument_id: 1 },
          yellow: { symbol: 'SPY', instrument_id: 1, source_group: 'blue' },
        },
      },
      tabs: [{ id: 20, stable_key: 'personal', name: 'Personal', position: 0, active_window_key: 'chart', layout_config: {}, windows: [
        { id: 30, instance_key: 'chart', tool_type: 'chart', title: 'Chart', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 0 },
      ] }],
    }
    apiGet.mockResolvedValueOnce(baseline)
    const store = useWorkspaceStore()
    await store.loadDefault()
    store.workspace!.settings = {
      ...store.workspace!.settings,
      linked_timeframe: 'W1',
      linked_timeframes: { blue: 'W1', red: 'D1', yellow: 'W1' },
      linked_symbols: {
        blue: { symbol: 'QQQ', instrument_id: 42 },
        red: { symbol: 'SPY', instrument_id: 1 },
        yellow: { symbol: 'QQQ', instrument_id: 42, source_group: 'blue' },
      },
    }
    const remote = structuredClone(baseline)
    remote.revision = 5
    remote.settings.linked_timeframes.red = 'MN'
    remote.settings.linked_symbols.blue = { symbol: 'XLE', instrument_id: 14 }
    remote.settings.linked_symbols.red = { symbol: 'XLF', instrument_id: 15 }
    remote.settings.linked_symbols.yellow = { symbol: 'XLE', instrument_id: 14, source_group: 'blue' }
    apiPut.mockRejectedValueOnce(new Error('API PUT /workspaces/10/snapshot → 409: conflict'))
      .mockImplementationOnce(async (_path, payload) => ({ ...remote, revision: 6, settings: payload.settings, tabs: payload.tabs }))
    apiGet.mockResolvedValueOnce(remote)

    await store.saveSnapshot()

    expect(apiPost).not.toHaveBeenCalled()
    expect(apiPut).toHaveBeenCalledTimes(2)
    expect(apiPut.mock.calls[1][1]).toMatchObject({
      base_revision: 5,
      settings: {
        linked_timeframe: 'W1',
        linked_timeframes: { blue: 'W1', red: 'MN', yellow: 'W1' },
        linked_symbols: {
          blue: { symbol: 'QQQ', instrument_id: 42 },
          red: { symbol: 'XLF', instrument_id: 15 },
          yellow: { symbol: 'QQQ', instrument_id: 42, source_group: 'blue' },
        },
      },
    })
    expect(store.workspace?.revision).toBe(6)
  })

  it('keeps the local dock layout when concurrent Golden Layout snapshots race', async () => {
    const store = useWorkspaceStore()
    const baseline = {
      id: 10, user_id: 3, name: 'Personal', is_default: false, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{ id: 20, stable_key: 'personal', name: 'Personal', position: 0, active_window_key: 'chart', layout_config: { root: { type: 'row', content: [] } }, windows: [
        { id: 30, instance_key: 'chart', tool_type: 'chart', title: 'Chart', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 0 },
      ] }],
    }
    apiGet.mockResolvedValueOnce(baseline)
    await store.loadDefault()
    const localLayout = { root: { type: 'row', content: [{ type: 'stack', content: [] }] } }
    store.workspace!.tabs[0].layout_config = localLayout
    const remote = JSON.parse(JSON.stringify(baseline))
    remote.revision = 5
    remote.tabs[0].layout_config = { root: { type: 'column', content: [] } }
    const saved = JSON.parse(JSON.stringify(remote))
    saved.revision = 6
    apiPut.mockRejectedValueOnce(new Error('API PUT /workspaces/10/snapshot → 409: conflict')).mockResolvedValueOnce(saved)
    apiGet.mockResolvedValueOnce(remote)

    await store.saveSnapshot()

    expect(apiPost).not.toHaveBeenCalled()
    expect(apiPut).toHaveBeenCalledTimes(2)
    expect(apiPut.mock.calls[1][1]).toEqual(expect.objectContaining({
      base_revision: 5,
      tabs: [expect.objectContaining({ layout_config: localLayout })],
    }))
  })

  it('merges locally opened tools with a concurrent remote layout snapshot', async () => {
    const store = useWorkspaceStore()
    const baseline = {
      id: 10, user_id: 3, name: 'Personal', is_default: false, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{ id: 20, stable_key: 'personal', name: 'Personal', position: 0, active_window_key: 'chart', layout_config: { root: { type: 'row', content: [] } }, windows: [
        { id: 30, instance_key: 'chart', tool_type: 'chart', title: 'Chart', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 0 },
      ] }],
    }
    apiGet.mockResolvedValueOnce(baseline)
    await store.loadDefault()
    const opened = store.openTool({ tool_type: 'watchlist', title: 'WatchList', instance_prefix: 'watchlist', configuration: { personal: true } })
    expect(opened).toBeTruthy()
    const remote = JSON.parse(JSON.stringify(baseline))
    remote.revision = 5
    remote.tabs[0].layout_config = { root: { type: 'column', content: [] } }
    const saved = JSON.parse(JSON.stringify(remote))
    saved.revision = 6
    apiPut.mockRejectedValueOnce(new Error('API PUT /workspaces/10/snapshot → 409: conflict')).mockResolvedValueOnce(saved)
    apiGet.mockResolvedValueOnce(remote)

    await store.saveSnapshot()

    expect(apiPost).not.toHaveBeenCalled()
    expect(apiPut).toHaveBeenCalledTimes(2)
    expect(apiPut.mock.calls[1][1]).toEqual(expect.objectContaining({
      base_revision: 5,
      tabs: [expect.objectContaining({
        layout_config: baseline.tabs[0].layout_config,
        windows: expect.arrayContaining([expect.objectContaining({ instance_key: opened!.instance_key })]),
      })],
    }))
  })

  it('keeps an explicit local tool close when a stale remote snapshot still contains it', async () => {
    const baseline = {
      id: 10, user_id: 3, name: 'Personal', is_default: false, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{ id: 20, stable_key: 'personal', name: 'Personal', position: 0, active_window_key: 'map', layout_config: { root: { type: 'row', content: [] } }, windows: [
        { id: 30, instance_key: 'chart', tool_type: 'chart', title: 'Chart', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 0 },
        { id: 31, instance_key: 'map', tool_type: 'market_map', title: 'Market Map', link_group: 'blue', configuration: { source_id: 'benchmark-family:sp400:cap_weight' }, style: {}, state_schema_version: 1, position: 1 },
      ] }],
    }
    apiGet.mockResolvedValueOnce(JSON.parse(JSON.stringify(baseline)))
    const store = useWorkspaceStore()
    await store.loadDefault()
    expect(store.closeTool('map')).toBe(true)
    const remote = JSON.parse(JSON.stringify(baseline))
    remote.revision = 5
    remote.tabs[0].windows[0].configuration = { symbol: 'SPY' }
    const saved = JSON.parse(JSON.stringify(remote))
    saved.revision = 6
    saved.tabs[0].windows = saved.tabs[0].windows.filter((window: { instance_key: string }) => window.instance_key !== 'map')
    apiPut.mockRejectedValueOnce(new Error('API PUT /workspaces/10/snapshot → 409: conflict')).mockResolvedValueOnce(saved)
    apiGet.mockResolvedValueOnce(remote)

    await store.saveSnapshot()

    expect(apiPost).not.toHaveBeenCalled()
    expect(apiPut).toHaveBeenCalledTimes(2)
    expect(apiPut.mock.calls[1][1]).toEqual(expect.objectContaining({
      base_revision: 5,
      tabs: [expect.objectContaining({ windows: [expect.objectContaining({ instance_key: 'chart' })] })],
    }))
    expect(store.workspace?.tabs[0].windows.map(window => window.instance_key)).toEqual(['chart'])
  })

  it('merges a local reopen when the previously closed tool is also absent remotely', async () => {
    const baseline = {
      id: 10, user_id: 3, name: 'Personal', is_default: false, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{ id: 20, stable_key: 'personal', name: 'Personal', position: 0, active_window_key: 'map-old', layout_config: { root: { type: 'row', content: [] } }, windows: [
        { id: 30, instance_key: 'chart', tool_type: 'chart', title: 'Chart', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 0 },
        { id: 31, instance_key: 'map-old', tool_type: 'market_map', title: 'Market Map', link_group: 'blue', configuration: { source_id: 'benchmark-family:sp400:cap_weight' }, style: {}, state_schema_version: 1, position: 1 },
      ] }],
    }
    apiGet.mockResolvedValueOnce(JSON.parse(JSON.stringify(baseline)))
    const store = useWorkspaceStore()
    await store.loadDefault()
    expect(store.closeTool('map-old')).toBe(true)
    const reopened = store.openTool({ key: 'market-map', tool_type: 'market_map', title: 'Market Map', instance_prefix: 'market-map', configuration: { source_id: 'benchmark-family:sp600:cap_weight' } })
    expect(reopened).toBeTruthy()
    const remote = JSON.parse(JSON.stringify(baseline))
    remote.revision = 5
    remote.tabs[0].windows = remote.tabs[0].windows.filter((window: { instance_key: string }) => window.instance_key !== 'map-old')
    remote.tabs[0].active_window_key = 'chart'
    const saved = JSON.parse(JSON.stringify(remote))
    saved.revision = 6
    saved.tabs[0].windows.push(reopened)
    saved.tabs[0].active_window_key = reopened!.instance_key
    apiPut.mockRejectedValueOnce(new Error('API PUT /workspaces/10/snapshot → 409: conflict')).mockResolvedValueOnce(saved)
    apiGet.mockResolvedValueOnce(remote)

    await store.saveSnapshot()

    expect(apiPost).not.toHaveBeenCalled()
    expect(apiPut).toHaveBeenCalledTimes(2)
    expect(apiPut.mock.calls[1][1]).toEqual(expect.objectContaining({
      base_revision: 5,
      tabs: [expect.objectContaining({
        windows: expect.arrayContaining([expect.objectContaining({ instance_key: reopened!.instance_key })]),
      })],
    }))
    expect(store.workspace?.tabs[0].windows.map(window => window.instance_key)).toContain(reopened!.instance_key)
  })

  it('hydrates the persisted blue-link symbol before the workstation mounts', async () => {
    apiGet.mockResolvedValue({
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4, schema_version: 1,
      settings: {},
      tabs: [{
        id: 20, stable_key: 'us-top-down', name: 'US Top Down', position: 0, active_window_key: 'ratio-chart',
        layout_config: { root: { type: 'row', content: [] } },
        windows: [
          { id: 30, instance_key: 'chart', tool_type: 'chart', title: 'Chart', link_group: 'blue', configuration: { symbol: 'XLK', instrument_id: 77 }, style: {}, state_schema_version: 1, position: 0 },
          { id: 31, instance_key: 'ratio-chart', tool_type: 'ratio', title: 'Relative Strength', link_group: 'blue', configuration: { symbol: 'XLK', ratio_benchmarks: ['SPY', 'XLE'] }, style: {}, state_schema_version: 1, position: 1 },
        ],
      }],
    })
    const store = useWorkspaceStore()

    await store.loadDefault()

    expect(store.linkedSymbol).toBe('XLK')
    expect(store.symbolForLinkGroup('blue')).toBe('XLK')
    expect(store.linkedSymbols.blue).toMatchObject({ symbol: 'XLK', instrumentId: 77 })
  })

  it('restores group symbols, Yellow wildcard identity, and wildcard timeframe from workspace settings', async () => {
    apiGet.mockResolvedValue({
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4, schema_version: 1,
      settings: {
        linked_timeframe: 'D1',
        linked_timeframes: { blue: 'D1', red: 'W1', yellow: 'W1' },
        linked_symbols: {
          blue: { symbol: 'SPY', instrument_id: 1 },
          red: { symbol: 'XLK', instrument_id: 42 },
          yellow: { symbol: 'XLK', instrument_id: 42, source_group: 'red' },
        },
      },
      tabs: [{
        id: 20, stable_key: 'us-top-down', name: 'US Top Down', position: 0, active_window_key: 'blue-chart', layout_config: {},
        windows: [
          { id: 30, instance_key: 'blue-chart', tool_type: 'chart', title: 'Blue chart', link_group: 'blue', configuration: { symbol: 'SPY', instrument_id: 1 }, style: {}, state_schema_version: 1, position: 0 },
          { id: 31, instance_key: 'red-chart', tool_type: 'chart', title: 'Red chart', link_group: 'red', configuration: { symbol: 'XLF' }, style: {}, state_schema_version: 1, position: 1 },
          { id: 32, instance_key: 'yellow-chart', tool_type: 'chart', title: 'Yellow chart', link_group: 'yellow', configuration: { symbol: 'SPY' }, style: {}, state_schema_version: 1, position: 2 },
        ],
      }],
    })
    const store = useWorkspaceStore()

    await store.loadDefault()

    expect(store.symbolForLinkGroup('blue')).toBe('SPY')
    expect(store.symbolForLinkGroup('red')).toBe('XLK')
    expect(store.symbolForLinkGroup('yellow')).toBe('XLK')
    expect(store.linkedSymbols.red).toMatchObject({ symbol: 'XLK', instrumentId: 42 })
    expect(store.linkedSymbols.yellow).toMatchObject({ symbol: 'XLK', instrumentId: 42, group: 'red' })
    expect(store.timeframeForLinkGroup('blue')).toBe('D1')
    expect(store.timeframeForLinkGroup('red')).toBe('W1')
    expect(store.timeframeForLinkGroup('yellow')).toBe('W1')
  })

  it('releases leadership when its owning window disconnects', () => {
    class FakeBroadcastChannel {
      addEventListener() {}
      close() {}
      postMessage() {}
    }
    vi.stubGlobal('BroadcastChannel', FakeBroadcastChannel)
    const store = useWorkspaceStore()

    store.connect()
    expect(store.isPersistenceLeader).toBe(true)
    store.disconnect()

    expect(store.isPersistenceLeader).toBe(false)
    expect(localStorage.getItem('charting-platform-workstation-leader')).toBeNull()
  })

  it('keeps the cross-window bus alive when storage is blocked or malformed', () => {
    class FakeBroadcastChannel {
      addEventListener() {}
      close() {}
      postMessage() {}
    }
    vi.stubGlobal('BroadcastChannel', FakeBroadcastChannel)
    vi.stubGlobal('localStorage', {
      getItem() { throw new Error('storage blocked') },
      setItem() { throw new Error('storage blocked') },
      removeItem() { throw new Error('storage blocked') },
    })
    const store = useWorkspaceStore()

    expect(() => store.connect()).not.toThrow()
    expect(() => store.publishSymbol({ symbol: 'XLK', group: 'blue', sourceWindowKey: 'test' })).not.toThrow()
    expect(() => store.publishTimeframe('W1')).not.toThrow()
    expect(() => store.disconnect()).not.toThrow()
  })

  it('ignores malformed storage messages without changing shared selection', () => {
    class FakeBroadcastChannel {
      addEventListener() {}
      close() {}
      postMessage() {}
    }
    vi.stubGlobal('BroadcastChannel', FakeBroadcastChannel)
    const store = useWorkspaceStore()
    store.connect()

    window.dispatchEvent(new StorageEvent('storage', {
      key: 'charting-platform-workstation:symbol',
      newValue: '{not-json',
    }))

    expect(store.linkedSymbol).toBe('SPY')
    store.disconnect()
  })

  it('reloads a newer persisted workspace snapshot announced by another window', async () => {
    class FakeBroadcastChannel {
      addEventListener() {}
      close() {}
      postMessage() {}
    }
    vi.stubGlobal('BroadcastChannel', FakeBroadcastChannel)
    const store = useWorkspaceStore()
    const current = {
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{ id: 20, stable_key: 'us-top-down', name: 'US Top Down', position: 0, active_window_key: null, layout_config: {}, windows: [] }],
    }
    const latest = { ...current, revision: 5, name: 'US Top Down Updated' }
    store.workspace = current
    apiGet.mockResolvedValue(latest)
    store.connect()

    window.dispatchEvent(new StorageEvent('storage', {
      key: 'charting-platform-workstation:workspace-snapshot',
      newValue: JSON.stringify({ type: 'workspace-snapshot', workspaceId: 10, revision: 5, sourceWindowId: 'another-window' }),
    }))

    await vi.waitFor(() => expect(store.workspace?.revision).toBe(5))
    expect(store.workspace?.name).toBe('US Top Down Updated')
    expect(apiGet).toHaveBeenCalledWith('/workspaces/10')
    store.disconnect()
  })

  it('does not replace a locally dirty workspace from a remote snapshot before save', async () => {
    class FakeBroadcastChannel {
      addEventListener() {}
      close() {}
      postMessage() {}
    }
    vi.stubGlobal('BroadcastChannel', FakeBroadcastChannel)
    const store = useWorkspaceStore()
    const current = {
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{ id: 20, stable_key: 'us-top-down', name: 'US Top Down', position: 0, active_window_key: 'chart', layout_config: {}, windows: [{ id: 30, instance_key: 'chart', tool_type: 'chart', title: 'Chart', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 0 }] }],
    }
    store.workspace = current
    store.updateToolLinkGroup('chart', 'grey')
    apiGet.mockResolvedValue({ ...current, revision: 5, name: 'Remote update' })
    store.connect()

    window.dispatchEvent(new StorageEvent('storage', {
      key: 'charting-platform-workstation:workspace-snapshot',
      newValue: JSON.stringify({ type: 'workspace-snapshot', workspaceId: 10, revision: 5, sourceWindowId: 'another-window' }),
    }))

    await new Promise(resolve => setTimeout(resolve, 20))
    expect(store.workspace?.tabs[0].windows[0].link_group).toBe('grey')
    expect(store.workspace?.name).toBe('US Top Down')
    store.disconnect()
  })

  it('does not apply an in-flight remote snapshot after a local link edit begins', async () => {
    class FakeBroadcastChannel {
      addEventListener() {}
      close() {}
      postMessage() {}
    }
    vi.stubGlobal('BroadcastChannel', FakeBroadcastChannel)
    const store = useWorkspaceStore()
    const current = {
      id: 10, user_id: 3, name: 'US Top Down', is_default: true, position: 0, revision: 4, schema_version: 1, settings: {},
      tabs: [{ id: 20, stable_key: 'us-top-down', name: 'US Top Down', position: 0, active_window_key: 'chart', layout_config: {}, windows: [{ id: 30, instance_key: 'chart', tool_type: 'chart', title: 'Chart', link_group: 'blue', configuration: { symbol: 'SPY' }, style: {}, state_schema_version: 1, position: 0 }] }],
    }
    store.workspace = current
    let resolveRemote!: (value: typeof current) => void
    apiGet.mockImplementation(() => new Promise(resolve => { resolveRemote = resolve as typeof resolveRemote }))
    store.connect()
    window.dispatchEvent(new StorageEvent('storage', {
      key: 'charting-platform-workstation:workspace-snapshot',
      newValue: JSON.stringify({ type: 'workspace-snapshot', workspaceId: 10, revision: 5, sourceWindowId: 'another-window' }),
    }))
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalledWith('/workspaces/10'))

    store.updateToolLinkGroup('chart', 'grey', 'SPY')
    resolveRemote({ ...current, revision: 5, name: 'Remote update' })

    await new Promise(resolve => setTimeout(resolve, 20))
    expect(store.workspace?.tabs[0].windows[0].link_group).toBe('grey')
    expect(store.workspace?.name).toBe('US Top Down')
    store.disconnect()
  })

  it('loads and caches verified industry-proxy rankings with the proxy evidence', async () => {
    const store = useWorkspaceStore()
    apiGet.mockImplementation((path: string) => {
      if (path.includes('/market-groups/etf/XLK/industries/Semiconductors/proxies')) {
        return Promise.resolve({ etf_symbol: 'XLK', industry: 'Semiconductors', candidate_symbols: ['SMH'], proxies: [{ symbol: 'SMH' }], exclusions: [] })
      }
      if (path.includes('/analysis/etf/XLK/industries/Semiconductors/proxies/snapshot')) {
        return Promise.resolve({ coverage: 1, rows: [{ instrument_id: 91, symbol: 'SMH', name: 'Semiconductors', performance: { '1M': { value: 0.1 } }, technical: { rsi14: { value: 60 } }, relative_to_benchmark: { value: 1.2 }, relative_to_market: { value: 1.3 } }], exclusions: [] })
      }
      return Promise.resolve([])
    })

    await store.loadIndustryProxies('XLK', 'Semiconductors')
    await vi.waitFor(() => expect(store.industryProxySnapshots['XLK:Semiconductors']?.rows[0].symbol).toBe('SMH'))
    expect(apiGet).toHaveBeenCalledWith('/analysis/etf/XLK/industries/Semiconductors/proxies/snapshot')
  })

  it('loads and caches equal-weight industry rankings', async () => {
    const store = useWorkspaceStore()
    apiGet.mockImplementation((path: string) => {
      if (path === '/market-groups/etf/XLK/industries') {
        return Promise.resolve({ etf_symbol: 'XLK', industries: [{ industry: 'Semiconductors' }] })
      }
      if (path === '/analysis/etf/XLK/industries/snapshot') {
        return Promise.resolve({
          etf_symbol: 'XLK',
          market_benchmark: 'SPY',
          composition_date: '2024-06-02',
          known_at: null,
          coverage: 1,
          rows: [{ industry: 'Semiconductors', performance: { '1D': { value: 0.01 } } }],
          exclusions: [],
        })
      }
      return Promise.resolve([])
    })

    await store.loadETFIndustries('XLK')
    await vi.waitFor(() => expect(store.industrySnapshots.XLK?.rows[0].industry).toBe('Semiconductors'))
    expect(apiGet).toHaveBeenCalledWith('/analysis/etf/XLK/industries/snapshot', { market_benchmark: 'SPY' })
  })

  it('loads dated industry composition and analysis while retaining an honest empty-classification result', async () => {
    const store = useWorkspaceStore()
    apiGet.mockImplementation((path: string) => {
      if (path === '/market-groups/etf/XLB/industries') {
        return Promise.resolve({
          etf_symbol: 'XLB', composition_date: '2026-11-02', known_at: '2026-11-03T08:15:00Z',
          provenance: 'dated_holdings_snapshot', source_provider: 'controlled-source', completeness_status: 'complete',
          industries: [], exclusions: ['unclassified_constituent'], classification_systems: ['GICS'], classification_coverage: 0,
        })
      }
      if (path === '/analysis/etf/XLB/industries/snapshot') {
        return Promise.resolve({ etf_symbol: 'XLB', composition_date: '2026-11-02', rows: [], coverage: 0, exclusions: [] })
      }
      return Promise.resolve([])
    })

    const result = await store.loadETFIndustries('XLB')

    expect(apiGet).toHaveBeenCalledWith('/market-groups/etf/XLB/industries')
    expect(apiGet).toHaveBeenCalledWith('/analysis/etf/XLB/industries/snapshot', { market_benchmark: 'SPY' })
    expect(result?.industries).toEqual([])
    expect(result?.exclusions).toEqual(['unclassified_constituent'])
    expect(store.etfIndustryLoading.XLB).toBe(false)
    expect(store.etfIndustryErrors.XLB).toBeNull()
  })

  it('retains cached dated industry composition when a refresh has no current result', async () => {
    const store = useWorkspaceStore()
    const cached = {
      etf_symbol: 'XLB', composition_date: '2026-11-02', known_at: '2026-11-03T08:15:00Z',
      provenance: 'dated_holdings_snapshot', source_provider: 'controlled-source', completeness_status: 'complete',
      industries: [{ industry: 'Chemicals', constituent_count: 2, resolved_count: 2 }], exclusions: [],
    }
    store.etfIndustries = { XLB: cached as never }
    const missing = Object.assign(new Error('not found'), { status: 404 })
    apiGet.mockRejectedValueOnce(missing)

    await store.loadETFIndustries('XLB')

    expect(store.etfIndustries.XLB).toEqual(cached)
    expect(store.etfIndustryErrors.XLB).toContain('No dated holdings classification')
  })

  it('keeps an industry selection while ETF hydration completes after the click', async () => {
    const holdings = deferred<unknown>()
    apiGet.mockImplementation((path: string) => {
      if (path === '/etf-holdings/XLK/holdings') return holdings.promise
      if (path === '/market-groups/etf/XLK/industries/Semiconductors') {
        return Promise.resolve({ etf_symbol: 'XLK', industry: 'Semiconductors', constituents: [] })
      }
      if (path === '/market-groups/etf/XLK/industries/Semiconductors/proxies') {
        return Promise.resolve({ etf_symbol: 'XLK', industry: 'Semiconductors', proxies: [{ symbol: 'SOXX' }] })
      }
      if (path === '/analysis/etf/XLK/industries/Semiconductors/proxies/snapshot') {
        return Promise.resolve({ coverage: 1, rows: [{ symbol: 'SOXX' }], exclusions: [] })
      }
      return Promise.resolve({})
    })
    const store = useWorkspaceStore()
    const hydration = store.loadETFHoldings('XLK')
    await store.selectIndustry('XLK', 'Semiconductors')
    holdings.resolve({ snapshot: { etf_symbol: 'XLK' }, holdings: [], total: 0 })
    await hydration

    expect(store.constituentETF).toBe('XLK')
    expect(store.selectedIndustry).toBe('Semiconductors')
    await vi.waitFor(() => expect(store.industryProxies['XLK:Semiconductors']?.proxies[0]?.symbol).toBe('SOXX'))
  })
})
