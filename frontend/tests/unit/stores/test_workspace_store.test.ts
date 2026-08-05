import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGet, apiPost, apiPut } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: apiGet, post: apiPost, put: apiPut } }))

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(res => { resolve = res })
  return { promise, resolve }
}

import { OPENABLE_WORKSTATION_TOOLS, useWorkspaceStore, type OpenableToolDefinition } from '@/stores/workspace'

describe('workspace store layout tabs', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiPut.mockReset()
    apiPost.mockReset()
    apiGet.mockReset()
  })

  afterEach(() => vi.unstubAllGlobals())

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
      revision: 5,
      tabs: payload.tabs,
    }))

    store.scheduleSnapshot()
    await vi.waitFor(() => expect(apiPut).toHaveBeenCalledTimes(1), { timeout: 1_000 })
    store.workspace.tabs[0].windows[0].configuration = { expression: '=NVDA/XLK' }
    store.scheduleSnapshot()
    oldResponse.resolve({ ...store.workspace, revision: 5, tabs: [{ ...store.workspace.tabs[0], windows: [{ ...store.workspace.tabs[0].windows[0], configuration: { expression: '=SPY/RSP' } }] }] })

    await vi.waitFor(() => expect(apiPut).toHaveBeenCalledTimes(2), { timeout: 1_500 })
    expect(store.workspace.tabs[0].windows[0].configuration.expression).toBe('=NVDA/XLK')
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

  it('publishes an occurrence timestamp and clears it for ordinary symbol navigation', () => {
    const store = useWorkspaceStore()

    store.publishSymbol({ symbol: 'SPY', timestamp: '2026-01-02', group: 'blue' })
    expect(store.linkedSymbol).toBe('SPY')
    expect(store.linkedTimestamp).toBe('2026-01-02')

    store.publishSymbol({ symbol: 'XLK', group: 'blue' })
    expect(store.linkedSymbol).toBe('XLK')
    expect(store.linkedTimestamp).toBeNull()
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
    expect(store.workspace.settings.linked_timeframes).toEqual({ blue: 'W1', red: 'MN' })
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

    expect(store.updateToolTimeframe('grey-chart', 'MN')).toBe(true)
    expect(store.activeTab?.windows[0]?.configuration.timeframe).toBe('MN')
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
    const definition: OpenableToolDefinition = { tool_type: 'study_lab', title: 'Study Lab', instance_prefix: 'study-lab', configuration: { symbol: 'SPY' } }

    const opened = store.openTool(definition)

    expect(opened?.tool_type).toBe('study_lab')
    expect(store.activeTab?.windows).toHaveLength(1)
    expect((store.activeTab?.layout_config.root as { content: unknown[] }).content).toHaveLength(1)
    expect(store.activeTab?.active_window_key).toBe(opened?.instance_key)
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
    expect(OPENABLE_WORKSTATION_TOOLS.map(tool => tool.tool_type)).toEqual(expect.arrayContaining([
      'relative_rotation', 'breadth', 'technical_summary', 'coverage', 'report',
    ]))
  })

  it('preserves a local recovery workspace when snapshot revision is stale', async () => {
    const store = useWorkspaceStore()
    store.workspace = {
      id: 10, user_id: 3, name: 'Personal', is_default: false, position: 0, revision: 4, schema_version: 1, settings: { factory_id: 'us-top-down' },
      tabs: [{ id: 20, stable_key: 'personal', name: 'Personal', position: 0, active_window_key: null, layout_config: { root: { type: 'row', content: [] } }, windows: [] }],
    }
    const latest = { ...store.workspace, revision: 5, name: 'Remote Personal' }
    const recovery = { ...store.workspace, id: 11, name: 'Personal Recovery', is_default: false, settings: { recovery_of_workspace_id: 10, recovery_of_revision: 4 } }
    apiPut.mockRejectedValue(new Error('API PUT /workspaces/10/snapshot → 409: conflict'))
    apiGet.mockResolvedValue(latest)
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

  it('loads and caches verified industry-proxy rankings with the proxy evidence', async () => {
    const store = useWorkspaceStore()
    apiGet.mockImplementation((path: string) => {
      if (path.includes('/market-groups/etf/XLK/industries/Semiconductors/proxies')) {
        return Promise.resolve({ etf_symbol: 'XLK', industry: 'Semiconductors', candidate_symbols: ['SMH'], proxies: [{ symbol: 'SMH' }], exclusions: [] })
      }
      if (path.includes('/analysis/etf/XLK/industries/Semiconductors/proxies/snapshot')) {
        return Promise.resolve({ coverage: 1, rows: [{ symbol: 'SMH', name: 'Semiconductors', performance: { '1M': { value: 0.1 } }, technical: { rsi14: { value: 60 } }, relative_to_benchmark: { value: 1.2 }, relative_to_market: { value: 1.3 } }], exclusions: [] })
      }
      return Promise.resolve([])
    })

    await store.loadIndustryProxies('XLK', 'Semiconductors')
    await vi.waitFor(() => expect(store.industryProxySnapshots['XLK:Semiconductors']?.rows[0].symbol).toBe('SMH'))
    expect(apiGet).toHaveBeenCalledWith('/analysis/etf/XLK/industries/Semiconductors/proxies/snapshot')
  })
})
