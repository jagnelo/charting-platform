import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGet, apiPost, apiPut } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: apiGet, post: apiPost, put: apiPut } }))

import { useWorkspaceStore, type OpenableToolDefinition } from '@/stores/workspace'

describe('workspace store layout tabs', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiPut.mockReset()
    apiPost.mockReset()
    apiGet.mockReset()
  })

  afterEach(() => vi.unstubAllGlobals())

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

  it('persists a closed layout tool by removing only that serialized window', async () => {
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

    expect(store.activeTab?.windows.map(window => window.instance_key)).toEqual(['chart'])
    expect(store.activeTab?.active_window_key).toBe('chart')
    await new Promise(resolve => setTimeout(resolve, 400))
    expect(apiPut).toHaveBeenCalled()
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
