import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '@/lib/api'

export type LinkGroup = 'blue' | 'red' | 'green' | 'purple' | 'orange' | 'cyan' | 'pink' | 'brown' | 'yellow' | 'grey'

export interface WorkspaceWindowState {
  id: number
  instance_key: string
  tool_type: string
  title: string | null
  link_group: LinkGroup
  configuration: Record<string, unknown>
  style: Record<string, unknown>
  state_schema_version: number
  position: number
}

export interface WorkspaceTabState {
  id: number
  stable_key: string
  name: string
  position: number
  layout_config: Record<string, unknown>
  active_window_key: string | null
  windows: WorkspaceWindowState[]
}

export interface WorkspaceState {
  id: number
  user_id: number
  name: string
  is_default: boolean
  position: number
  revision: number
  schema_version: number
  settings: Record<string, unknown>
  tabs: WorkspaceTabState[]
}

/**
 * The browser-only tool registry deliberately contains only implemented, serializable
 * primary-workstation tools. It is not a substitute for a runtime component registry.
 */
export interface OpenableToolDefinition {
  tool_type: 'chart' | 'notes' | 'alerts' | 'scan' | 'gauge' | 'study_lab'
  title: string
  instance_prefix: string
  configuration?: Record<string, unknown>
}

export const OPENABLE_WORKSTATION_TOOLS: readonly OpenableToolDefinition[] = [
  { tool_type: 'chart', title: 'Chart', instance_prefix: 'chart', configuration: { symbol: 'SPY', timeframe: 'D1' } },
  { tool_type: 'notes', title: 'Notes', instance_prefix: 'notes', configuration: { scope: 'active-instrument' } },
  { tool_type: 'alerts', title: 'Alerts', instance_prefix: 'alerts', configuration: { scope: 'active-instrument' } },
  { tool_type: 'scan', title: 'EasyScan', instance_prefix: 'easy-scan', configuration: { scope: 'saved-conditions' } },
  { tool_type: 'gauge', title: 'Market Gauge', instance_prefix: 'market-gauge', configuration: { scope: 'saved-scans' } },
  { tool_type: 'study_lab', title: 'Study Lab', instance_prefix: 'study-lab', configuration: { symbol: 'SPY' } },
]

export interface LinkEvent {
  instrumentId?: number
  symbol: string
  /** Optional historical point selected by a linked research occurrence. */
  timestamp?: string
  sourceWindowKey?: string
  group: LinkGroup
}

export interface MarketGroupInstrument {
  id: number
  symbol: string
  name: string
  is_active: boolean
}

export interface MarketGroupMemberState {
  instrument_id: number
  relationship_type: string
  verification_state: string
  provenance: Record<string, unknown>
  instrument: MarketGroupInstrument
}

export interface MarketGroupState {
  id: number
  stable_key: string
  group_type: string
  name: string
  provenance: Record<string, unknown>
  members: MarketGroupMemberState[]
}

export interface GroupSnapshotRow {
  instrument_id: number
  symbol: string
  name: string
  performance: Record<string, { value: number | null; warning?: { code: string; message: string } | null }>
  relative_to_benchmark?: { value: number | null; warning?: { code: string; message: string } | null } | null
  technical?: Record<string, { value: number | null; warning?: { code: string; message: string } | null }>
}

export interface GroupSnapshotState {
  group_key: string
  coverage: number
  rows: GroupSnapshotRow[]
}

export interface BreadthState {
  group_key: string
  coverage: number
  evaluated_count: number
  above_ma: Record<string, number | null>
}

export interface BreadthHistoryState {
  group_key: string
  points: Array<{ timestamp: string; above_ma: Record<string, number | null>; coverage: Record<string, number> }>
}

export interface ETFHoldingState {
  constituent_instrument_id: number | null
  constituent_symbol: string | null
  constituent_name: string | null
  reported_symbol: string | null
  reported_name: string | null
  weight: number | null
  is_resolved: boolean
}

export interface ETFHoldingsPageState {
  snapshot: {
    etf_symbol: string
    composition_date: string
    known_at: string | null
    provenance: string
    source_provider: string
    completeness_status: string
  }
  holdings: ETFHoldingState[]
  total: number
}

export interface ETFConstituentSnapshotState extends GroupSnapshotState {
  etf_symbol: string
  composition_date: string
  known_at: string | null
  provenance: string
  source_provider: string
  completeness_status: string
}

export interface ETFIndustryCompositionState {
  etf_symbol: string
  composition_date: string
  known_at: string | null
  provenance: string
  source_provider: string
  completeness_status: string
  industries: Array<{ industry: string; constituent_count: number; resolved_count: number }>
  exclusions: string[]
}

export interface ETFIndustryConstituentsState {
  etf_symbol: string
  industry: string
  composition_date: string
  constituents: MarketGroupInstrument[]
  exclusions: string[]
}

export interface ETFIndustryProxyState {
  etf_symbol: string
  industry: string
  candidate_symbols: string[]
  proxies: Array<{
    symbol: string
    name: string
    composition_date: string
    known_at: string | null
    provenance: string
    source_provider: string
    matching_constituent_count: number
    classified_constituent_count: number
    classification_coverage: number
    source: string
    verification_state: string
  }>
  exclusions: string[]
}

export interface IndustryProxySnapshotState {
  rows: Array<{
    symbol: string
    name: string
    performance: Record<string, { value: number | null }>
    technical: Record<string, { value: number | null }>
    relative_to_benchmark: { value: number | null } | null
    relative_to_market: { value: number | null } | null
  }>
  coverage: number
  exclusions: Array<{ code: string; message: string }>
}

export interface TechnicalSnapshotState {
  symbol: string
  as_of: string | null
  last: number | null
  rsi14: number | null
  sma20: number | null
  sma50: number | null
  sma200: number | null
  position_52w: number | null
  volume_ratio_50: number | null
  warnings: Array<{ code: string; message: string }>
}

const CHANNEL_NAME = 'charting-platform-workstation'
const LEADER_KEY = `${CHANNEL_NAME}-leader`
const LEADER_TIMEOUT_MS = 10_000
const LEADER_HEARTBEAT_MS = 4_000

export const useWorkspaceStore = defineStore('workspace', () => {
  const workspace = ref<WorkspaceState | null>(null)
  const activeTabKey = ref<string>('us-top-down')
  const linkedSymbol = ref('SPY')
  const linkedTimestamp = ref<string | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const isPersistenceLeader = ref(false)
  const marketGroups = ref<Record<string, MarketGroupState>>({})
  const groupSnapshots = ref<Record<string, GroupSnapshotState>>({})
  const breadth = ref<Record<string, BreadthState>>({})
  const breadthHistory = ref<Record<string, BreadthHistoryState>>({})
  const etfHoldings = ref<Record<string, ETFHoldingsPageState | null>>({})
  const etfConstituentSnapshots = ref<Record<string, ETFConstituentSnapshotState | null>>({})
  const etfIndustries = ref<Record<string, ETFIndustryCompositionState | null>>({})
  const industryConstituents = ref<Record<string, ETFIndustryConstituentsState | null>>({})
  const industryProxies = ref<Record<string, ETFIndustryProxyState | null>>({})
  const industryProxySnapshots = ref<Record<string, IndustryProxySnapshotState | null>>({})
  const technicals = ref<Record<string, TechnicalSnapshotState | null>>({})
  const constituentETF = ref<string | null>(null)
  const selectedIndustry = ref<string | null>(null)
  const selectedIndustryProxy = ref<string | null>(null)
  let persistedWorkspace: WorkspaceState | null = null
  let channel: BroadcastChannel | null = null
  let leaderTimer: ReturnType<typeof setInterval> | null = null
  let snapshotTimer: ReturnType<typeof setTimeout> | null = null
  const windowId = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `window-${Date.now()}-${Math.random().toString(36).slice(2)}`

  const activeTab = computed(() =>
    workspace.value?.tabs.find(tab => tab.stable_key === activeTabKey.value) ?? workspace.value?.tabs[0] ?? null,
  )

  function cloneSerializable<T>(value: T): T {
    return JSON.parse(JSON.stringify(value)) as T
  }

  function sameJson(left: unknown, right: unknown) {
    return JSON.stringify(left) === JSON.stringify(right)
  }

  function isEditorTarget(target: EventTarget | null) {
    return target instanceof HTMLInputElement
      || target instanceof HTMLTextAreaElement
      || target instanceof HTMLSelectElement
      || (target instanceof HTMLElement && target.isContentEditable)
  }

  function handleMessage(event: MessageEvent<LinkEvent & { type?: string }>) {
    if (event.data.type !== 'symbol' || event.data.group === 'grey') return
    linkedSymbol.value = event.data.symbol
    linkedTimestamp.value = event.data.timestamp ?? null
  }

  function refreshLeadership() {
    let current: { id: string; heartbeat: number } | null = null
    try {
      const raw = localStorage.getItem(LEADER_KEY)
      current = raw ? JSON.parse(raw) as { id: string; heartbeat: number } : null
    } catch {
      current = null
    }
    const now = Date.now()
    if (!current || current.id === windowId || now - current.heartbeat > LEADER_TIMEOUT_MS) {
      localStorage.setItem(LEADER_KEY, JSON.stringify({ id: windowId, heartbeat: now }))
      isPersistenceLeader.value = true
      return
    }
    isPersistenceLeader.value = false
  }

  function becomeLeader() {
    refreshLeadership()
    if (!leaderTimer) {
      leaderTimer = setInterval(() => {
        refreshLeadership()
      }, LEADER_HEARTBEAT_MS)
    }
  }

  function connect() {
    if (channel) return
    channel = new BroadcastChannel(CHANNEL_NAME)
    channel.addEventListener('message', handleMessage)
    window.addEventListener('storage', onStorage)
    becomeLeader()
  }

  function onStorage(event: StorageEvent) {
    if (event.key === LEADER_KEY) {
      refreshLeadership()
      return
    }
    if (event.key !== CHANNEL_NAME + ':symbol' || !event.newValue) return
    const message = JSON.parse(event.newValue) as LinkEvent
    if (message.group !== 'grey') {
      linkedSymbol.value = message.symbol
      linkedTimestamp.value = message.timestamp ?? null
    }
  }

  function disconnect() {
    channel?.close()
    channel = null
    window.removeEventListener('storage', onStorage)
    if (leaderTimer) clearInterval(leaderTimer)
    leaderTimer = null
    if (isPersistenceLeader.value) {
      try {
        const current = JSON.parse(localStorage.getItem(LEADER_KEY) ?? 'null') as { id?: string } | null
        if (current?.id === windowId) localStorage.removeItem(LEADER_KEY)
      } catch {
        localStorage.removeItem(LEADER_KEY)
      }
    }
    isPersistenceLeader.value = false
  }

  function publishSymbol(event: LinkEvent) {
    if (event.group === 'grey') return
    linkedSymbol.value = event.symbol
    linkedTimestamp.value = event.timestamp ?? null
    channel?.postMessage({ ...event, type: 'symbol' })
    localStorage.setItem(CHANNEL_NAME + ':symbol', JSON.stringify(event))
  }

  async function loadDefault() {
    loading.value = true
    error.value = null
    try {
      workspace.value = await api.get<WorkspaceState>('/workspaces/default')
      persistedWorkspace = cloneSerializable(workspace.value)
      activeTabKey.value = workspace.value.tabs[0]?.stable_key ?? 'us-top-down'
    } catch (cause: any) {
      error.value = cause?.message ?? 'Unable to load workstation'
    } finally {
      loading.value = false
    }
  }

  function snapshotPayload(current: WorkspaceState) {
    return {
      base_revision: current.revision,
      name: current.name,
      settings: current.settings,
      schema_version: current.schema_version,
      tabs: current.tabs.map(tab => ({
        stable_key: tab.stable_key,
        name: tab.name,
        position: tab.position,
        layout_config: tab.layout_config,
        active_window_key: tab.active_window_key,
        windows: tab.windows.map(window => ({
          instance_key: window.instance_key,
          tool_type: window.tool_type,
          title: window.title,
          link_group: window.link_group,
          configuration: window.configuration,
          style: window.style,
          state_schema_version: window.state_schema_version,
          position: window.position,
        })),
      })),
    }
  }

  async function preserveConflictRecovery(current: WorkspaceState) {
    const { factory_id: _factoryId, factory_version: _factoryVersion, ...settings } = current.settings
    return api.post<WorkspaceState>('/workspaces', {
      ...snapshotPayload(current),
      name: `${current.name} Recovery`,
      is_default: false,
      position: 0,
      settings: { ...settings, recovery_of_workspace_id: current.id, recovery_of_revision: current.revision },
    })
  }

  /**
   * Merge only independently changed window records. Dock structure, tab identity,
   * settings, names and active-window changes are intentionally treated as conflicts:
   * without a common structural editor they cannot be proven safe to combine.
   */
  function mergeDisjointWindowChanges(
    baseline: WorkspaceState | null,
    local: WorkspaceState,
    remote: WorkspaceState,
  ): WorkspaceState | null {
    if (!baseline
      || !sameJson(local.settings, baseline.settings)
      || !sameJson(remote.settings, baseline.settings)
      || local.name !== baseline.name
      || remote.name !== baseline.name
      || local.schema_version !== baseline.schema_version
      || remote.schema_version !== baseline.schema_version
      || local.tabs.length !== baseline.tabs.length
      || remote.tabs.length !== baseline.tabs.length) return null
    const merged = cloneSerializable(remote)
    for (const baseTab of baseline.tabs) {
      const localTab = local.tabs.find(tab => tab.stable_key === baseTab.stable_key)
      const remoteTab = remote.tabs.find(tab => tab.stable_key === baseTab.stable_key)
      const mergedTab = merged.tabs.find(tab => tab.stable_key === baseTab.stable_key)
      if (!localTab || !remoteTab || !mergedTab
        || localTab.name !== baseTab.name || remoteTab.name !== baseTab.name
        || localTab.position !== baseTab.position || remoteTab.position !== baseTab.position
        || localTab.active_window_key !== baseTab.active_window_key || remoteTab.active_window_key !== baseTab.active_window_key
        || !sameJson(localTab.layout_config, baseTab.layout_config) || !sameJson(remoteTab.layout_config, baseTab.layout_config)
        || localTab.windows.length !== baseTab.windows.length || remoteTab.windows.length !== baseTab.windows.length) return null
      for (const baseWindow of baseTab.windows) {
        const localWindow = localTab.windows.find(window => window.instance_key === baseWindow.instance_key)
        const remoteWindow = remoteTab.windows.find(window => window.instance_key === baseWindow.instance_key)
        const mergedWindow = mergedTab.windows.find(window => window.instance_key === baseWindow.instance_key)
        if (!localWindow || !remoteWindow || !mergedWindow) return null
        const localChanged = !sameJson(localWindow, baseWindow)
        const remoteChanged = !sameJson(remoteWindow, baseWindow)
        if (localChanged && remoteChanged && !sameJson(localWindow, remoteWindow)) return null
        if (localChanged) Object.assign(mergedWindow, cloneSerializable(localWindow))
      }
    }
    return merged
  }

  async function loadMarketGroup(stableKey: string) {
    try {
      const group = await api.get<MarketGroupState>(`/market-groups/${encodeURIComponent(stableKey)}`)
      marketGroups.value = { ...marketGroups.value, [stableKey]: group }
      return group
    } catch (cause: any) {
      error.value = cause?.message ?? `Unable to load ${stableKey}`
      return null
    }
  }

  async function loadGroupSnapshot(stableKey: string, benchmark?: string) {
    try {
      const snapshot = await api.get<GroupSnapshotState>(`/analysis/groups/${encodeURIComponent(stableKey)}/snapshot`, { benchmark })
      groupSnapshots.value = { ...groupSnapshots.value, [stableKey]: snapshot }
      return snapshot
    } catch (cause: any) {
      error.value = cause?.message ?? `Unable to calculate ${stableKey}`
      return null
    }
  }

  async function loadBreadth(stableKey: string) {
    try {
      const snapshot = await api.get<BreadthState>(`/analysis/groups/${encodeURIComponent(stableKey)}/breadth`)
      breadth.value = { ...breadth.value, [stableKey]: snapshot }
      return snapshot
    } catch (cause: any) {
      error.value = cause?.message ?? `Unable to calculate breadth for ${stableKey}`
      return null
    }
  }

  async function loadBreadthHistory(stableKey: string) {
    try {
      const history = await api.get<BreadthHistoryState>(`/analysis/groups/${encodeURIComponent(stableKey)}/breadth/history`, { limit: 500 })
      breadthHistory.value = { ...breadthHistory.value, [stableKey]: history }
      return history
    } catch (cause: any) {
      error.value = cause?.message ?? `Unable to calculate historical breadth for ${stableKey}`
      return null
    }
  }

  async function loadETFHoldings(symbol: string) {
    const normalized = symbol.trim().toUpperCase()
    if (!normalized) return null
    try {
      const page = await api.get<ETFHoldingsPageState>(`/etf-holdings/${encodeURIComponent(normalized)}/holdings`, {
        limit: 500,
        sort: 'weight',
        direction: 'desc',
        point_in_time: true,
      })
      etfHoldings.value = { ...etfHoldings.value, [normalized]: page }
      constituentETF.value = normalized
      selectedIndustry.value = null
      selectedIndustryProxy.value = null
      void loadETFConstituentSnapshot(normalized)
      return page
    } catch (cause: any) {
      if (cause?.status === 404) {
        etfHoldings.value = { ...etfHoldings.value, [normalized]: null }
        return null
      }
      error.value = cause?.message ?? `Unable to load ETF holdings for ${normalized}`
      return null
    }
  }

  async function loadETFConstituentSnapshot(symbol: string, benchmark?: string) {
    const normalized = symbol.trim().toUpperCase()
    if (!normalized) return null
    const comparison = (benchmark ?? normalized).trim().toUpperCase()
    try {
      const snapshot = await api.get<ETFConstituentSnapshotState>(
        `/analysis/etf/${encodeURIComponent(normalized)}/constituents/snapshot`,
        { benchmark: comparison },
      )
      etfConstituentSnapshots.value = { ...etfConstituentSnapshots.value, [normalized]: snapshot }
      return snapshot
    } catch (cause: any) {
      if (cause?.status === 404) {
        etfConstituentSnapshots.value = { ...etfConstituentSnapshots.value, [normalized]: null }
        return null
      }
      error.value = cause?.message ?? `Unable to calculate ${normalized} constituent strength`
      return null
    }
  }

  async function loadETFIndustries(symbol: string) {
    const normalized = symbol.trim().toUpperCase()
    if (!normalized) return null
    try {
      const composition = await api.get<ETFIndustryCompositionState>(`/market-groups/etf/${encodeURIComponent(normalized)}/industries`)
      etfIndustries.value = { ...etfIndustries.value, [normalized]: composition }
      return composition
    } catch (cause: any) {
      if (cause?.status === 404) {
        etfIndustries.value = { ...etfIndustries.value, [normalized]: null }
        return null
      }
      error.value = cause?.message ?? `Unable to load ETF industries for ${normalized}`
      return null
    }
  }

  async function selectIndustry(symbol: string, industry: string | null) {
    const normalized = symbol.trim().toUpperCase()
    selectedIndustry.value = industry
    if (!normalized || !industry) return null
    const key = `${normalized}:${industry}`
    selectedIndustryProxy.value = null
    try {
      const constituents = await api.get<ETFIndustryConstituentsState>(
        `/market-groups/etf/${encodeURIComponent(normalized)}/industries/${encodeURIComponent(industry)}`,
      )
      industryConstituents.value = { ...industryConstituents.value, [key]: constituents }
      void loadIndustryProxies(normalized, industry)
      return constituents
    } catch (cause: any) {
      error.value = cause?.message ?? `Unable to load ${industry} constituents`
      return null
    }
  }

  async function loadIndustryProxies(symbol: string, industry: string) {
    const normalized = symbol.trim().toUpperCase()
    const key = `${normalized}:${industry}`
    if (!normalized || !industry) return null
    try {
      const proxies = await api.get<ETFIndustryProxyState>(
        `/market-groups/etf/${encodeURIComponent(normalized)}/industries/${encodeURIComponent(industry)}/proxies`,
      )
      industryProxies.value = { ...industryProxies.value, [key]: proxies }
      void loadIndustryProxySnapshot(normalized, industry)
      return proxies
    } catch (cause: any) {
      error.value = cause?.message ?? `Unable to load ${industry} proxies`
      return null
    }
  }

  async function loadIndustryProxySnapshot(symbol: string, industry: string) {
    const normalized = symbol.trim().toUpperCase()
    const key = `${normalized}:${industry}`
    if (!normalized || !industry) return null
    try {
      const snapshot = await api.get<IndustryProxySnapshotState>(`/analysis/etf/${encodeURIComponent(normalized)}/industries/${encodeURIComponent(industry)}/proxies/snapshot`)
      industryProxySnapshots.value = { ...industryProxySnapshots.value, [key]: snapshot }
      return snapshot
    } catch (cause: any) {
      industryProxySnapshots.value = { ...industryProxySnapshots.value, [key]: null }
      error.value = cause?.message ?? `Unable to rank ${industry} proxies`
      return null
    }
  }

  function selectIndustryProxy(symbol: string | null) {
    selectedIndustryProxy.value = symbol?.trim().toUpperCase() || null
  }

  async function loadTechnical(symbol: string) {
    const normalized = symbol.trim().toUpperCase()
    if (!normalized) return null
    try {
      const snapshot = await api.get<TechnicalSnapshotState>(`/analysis/instruments/${encodeURIComponent(normalized)}/technical`)
      technicals.value = { ...technicals.value, [normalized]: snapshot }
      return snapshot
    } catch (cause: any) {
      if (cause?.status === 404) {
        technicals.value = { ...technicals.value, [normalized]: null }
        return null
      }
      error.value = cause?.message ?? `Unable to calculate technicals for ${normalized}`
      return null
    }
  }

  async function saveSnapshot() {
    if (!workspace.value) return
    const current = workspace.value
    try {
      workspace.value = await api.put<WorkspaceState>(`/workspaces/${current.id}/snapshot`, snapshotPayload(current))
      persistedWorkspace = cloneSerializable(workspace.value)
    } catch (cause: any) {
      if (String(cause?.message ?? '').includes(' 409:')) {
        try {
          const latest = await api.get<WorkspaceState>(`/workspaces/${current.id}`)
          const merged = mergeDisjointWindowChanges(persistedWorkspace, current, latest)
          if (merged) {
            const saved = await api.put<WorkspaceState>(`/workspaces/${latest.id}/snapshot`, snapshotPayload(merged))
            workspace.value = saved
            persistedWorkspace = cloneSerializable(saved)
            error.value = null
            return
          }
          const recovery = await preserveConflictRecovery(current)
          workspace.value = latest
          persistedWorkspace = cloneSerializable(latest)
          activeTabKey.value = latest.tabs[0]?.stable_key ?? 'us-top-down'
          error.value = `Workspace changed elsewhere. Your local changes were preserved as '${recovery.name}'.`
          return
        } catch (recoveryCause: any) {
          error.value = `Workspace changed elsewhere and recovery failed: ${recoveryCause?.message ?? 'unknown error'}`
          return
        }
      }
      error.value = cause?.message ?? 'Unable to save workspace snapshot'
    }
  }

  function scheduleSnapshot() {
    if (snapshotTimer) clearTimeout(snapshotTimer)
    snapshotTimer = setTimeout(() => { void saveSnapshot() }, 350)
  }

  function applyActiveLayout(layout: Record<string, unknown>, visibleToolKeys: string[]) {
    const tab = activeTab.value
    if (!tab) return
    tab.layout_config = layout
    if (visibleToolKeys.length) {
      const visible = new Set(visibleToolKeys)
      tab.windows = tab.windows.filter(window => visible.has(window.instance_key))
      if (!tab.windows.some(window => window.instance_key === tab.active_window_key)) {
        tab.active_window_key = tab.windows[0]?.instance_key ?? null
      }
    }
    scheduleSnapshot()
  }

  function openTool(definition: OpenableToolDefinition) {
    const tab = activeTab.value
    if (!tab) return null
    const instanceKey = `${definition.instance_prefix}-${Date.now().toString(36)}`
    const window: WorkspaceWindowState = {
      id: -Date.now(),
      instance_key: instanceKey,
      tool_type: definition.tool_type,
      title: definition.title,
      link_group: 'blue',
      configuration: { ...(definition.configuration ?? {}) },
      style: {},
      state_schema_version: 1,
      position: Math.max(-1, ...tab.windows.map(item => item.position)) + 1,
    }
    const component = {
      type: 'component',
      componentType: 'workstation-tool',
      title: window.title,
      componentState: {
        instance_key: window.instance_key,
        tool_type: window.tool_type,
        title: window.title,
      },
    }
    // Workspace layouts are intentionally JSON-only; this also unwraps Pinia's
    // reactive proxy before persistence or Golden Layout receives the config.
    const layout = JSON.parse(JSON.stringify(tab.layout_config)) as Record<string, unknown>
    const root = layout.root as Record<string, unknown> | undefined
    if (root && Array.isArray(root.content)) {
      root.content.push(component)
    } else if (root) {
      layout.root = { type: 'row', content: [root, component] }
    } else {
      layout.root = { type: 'row', content: [component] }
    }
    tab.windows = [...tab.windows, window]
    tab.layout_config = layout
    tab.active_window_key = instanceKey
    scheduleSnapshot()
    return window
  }

  /** Remove a tool through the same serializable state used by Golden Layout. */
  function closeTool(windowKey: string) {
    const tab = activeTab.value
    if (!tab || !tab.windows.some(window => window.instance_key === windowKey)) return false
    if (tab.windows.length === 1) {
      error.value = 'A workspace tab must retain at least one tool.'
      return false
    }
    tab.windows = tab.windows.filter(window => window.instance_key !== windowKey)
    if (tab.active_window_key === windowKey) tab.active_window_key = tab.windows[0]?.instance_key ?? null
    scheduleSnapshot()
    return true
  }

  function cloneActiveTab() {
    if (!workspace.value || !activeTab.value) return
    const source = activeTab.value
    const suffix = Date.now().toString(36)
    const remappedKeys = new Map(source.windows.map(window => [window.instance_key, `${window.instance_key}-${suffix}`]))
    const cloneLayout = (value: unknown): unknown => {
      if (Array.isArray(value)) return value.map(cloneLayout)
      if (!value || typeof value !== 'object') return value
      return Object.fromEntries(Object.entries(value as Record<string, unknown>).map(([key, child]) => [
        key,
        key === 'instance_key' && typeof child === 'string' ? (remappedKeys.get(child) ?? child) : cloneLayout(child),
      ]))
    }
    const copiedTab: WorkspaceTabState = {
      id: -Date.now(),
      stable_key: `layout-${suffix}`,
      name: `${source.name} Copy`,
      position: workspace.value.tabs.length,
      layout_config: cloneLayout(source.layout_config) as Record<string, unknown>,
      active_window_key: source.active_window_key ? (remappedKeys.get(source.active_window_key) ?? source.active_window_key) : null,
      windows: source.windows.map(window => ({
        ...window,
        id: -(Date.now() + window.position + 1),
        instance_key: remappedKeys.get(window.instance_key) ?? window.instance_key,
        configuration: cloneLayout(window.configuration) as Record<string, unknown>,
        style: cloneLayout(window.style) as Record<string, unknown>,
      })),
    }
    workspace.value = { ...workspace.value, tabs: [...workspace.value.tabs, copiedTab] }
    activeTabKey.value = copiedTab.stable_key
    scheduleSnapshot()
  }

  async function resetFactoryWorkspace() {
    if (!workspace.value || workspace.value.settings.factory_id !== 'us-top-down') return false
    try {
      const reset = await api.post<WorkspaceState>(`/workspaces/${workspace.value.id}/reset-factory`, {})
      workspace.value = reset
      persistedWorkspace = cloneSerializable(reset)
      activeTabKey.value = reset.tabs[0]?.stable_key ?? 'us-top-down'
      error.value = null
      return true
    } catch (cause: any) {
      error.value = cause?.message ?? 'Unable to reset factory workspace'
      return false
    }
  }

  return {
    workspace,
    activeTab,
    activeTabKey,
    linkedSymbol,
    linkedTimestamp,
    loading,
    error,
    isPersistenceLeader,
    marketGroups,
    groupSnapshots,
    breadth,
    breadthHistory,
    etfHoldings,
    etfConstituentSnapshots,
    etfIndustries,
    industryConstituents,
    industryProxies,
    industryProxySnapshots,
    technicals,
    constituentETF,
    selectedIndustry,
    selectedIndustryProxy,
    isEditorTarget,
    connect,
    disconnect,
    publishSymbol,
    loadDefault,
    loadMarketGroup,
    loadGroupSnapshot,
    loadBreadth,
    loadBreadthHistory,
    loadETFHoldings,
    loadETFConstituentSnapshot,
    loadETFIndustries,
    selectIndustry,
    loadIndustryProxies,
    loadIndustryProxySnapshot,
    selectIndustryProxy,
    loadTechnical,
    saveSnapshot,
    scheduleSnapshot,
    applyActiveLayout,
    openTool,
    closeTool,
    cloneActiveTab,
    resetFactoryWorkspace,
  }
})
