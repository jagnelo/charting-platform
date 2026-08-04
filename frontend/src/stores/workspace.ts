import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '@/lib/api'
import { isEditorTarget as isWorkstationEditorTarget } from '@/lib/workstation/keyboard'
import { normaliseGoldenLayoutConfig } from '@/lib/workstation/layout'

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
  tool_type: 'chart' | 'watchlist' | 'notes' | 'alerts' | 'scan' | 'gauge' | 'study_lab' | 'relative_rotation' | 'breadth' | 'technical_summary' | 'coverage' | 'report' | 'code_library'
  title: string
  instance_prefix: string
  configuration?: Record<string, unknown>
}

export const OPENABLE_WORKSTATION_TOOLS: readonly OpenableToolDefinition[] = [
  { tool_type: 'chart', title: 'Chart', instance_prefix: 'chart', configuration: { symbol: 'SPY', timeframe: 'D1' } },
  { tool_type: 'watchlist', title: 'WatchList', instance_prefix: 'watchlist', configuration: { personal: true, watchlist_id: null } },
  { tool_type: 'notes', title: 'Notes', instance_prefix: 'notes', configuration: { scope: 'active-instrument' } },
  { tool_type: 'alerts', title: 'Alerts', instance_prefix: 'alerts', configuration: { scope: 'active-instrument' } },
  { tool_type: 'scan', title: 'EasyScan', instance_prefix: 'easy-scan', configuration: { scope: 'saved-conditions' } },
  { tool_type: 'gauge', title: 'Market Gauge', instance_prefix: 'market-gauge', configuration: { scope: 'saved-scans' } },
  { tool_type: 'study_lab', title: 'Study Lab', instance_prefix: 'study-lab', configuration: { symbol: 'SPY' } },
  { tool_type: 'relative_rotation', title: 'Relative Rotation', instance_prefix: 'relative-rotation', configuration: { group_key: 'sp500-sectors', benchmark: 'SPY', timeframe: 'D1', sampling: 1, lookback: 20, tail_length: 10, adjusted: true } },
  { tool_type: 'breadth', title: 'Market Breadth', instance_prefix: 'breadth', configuration: { group_key: 'sp500-sectors' } },
  { tool_type: 'technical_summary', title: 'Technical Summary', instance_prefix: 'technical-summary', configuration: {} },
  { tool_type: 'coverage', title: 'Coverage', instance_prefix: 'coverage', configuration: {} },
  { tool_type: 'report', title: 'Instrument Report', instance_prefix: 'report', configuration: {} },
  { tool_type: 'code_library', title: 'Python Library', instance_prefix: 'code-library', configuration: {} },
]

export interface LinkEvent {
  instrumentId?: number
  symbol: string
  /** Optional historical point selected by a linked research occurrence. */
  timestamp?: string
  timeframe?: string
  sourceWindowKey?: string
  group: LinkGroup
}

interface WorkspaceSnapshotEvent {
  type: 'workspace-snapshot'
  workspaceId: number
  revision: number
  sourceWindowId: string
}

type CrossWindowEvent = (LinkEvent & { type?: string }) | WorkspaceSnapshotEvent

function isWorkspaceSnapshotEvent(event: CrossWindowEvent): event is WorkspaceSnapshotEvent {
  return event.type === 'workspace-snapshot'
    && typeof (event as WorkspaceSnapshotEvent).workspaceId === 'number'
    && typeof (event as WorkspaceSnapshotEvent).revision === 'number'
    && typeof (event as WorkspaceSnapshotEvent).sourceWindowId === 'string'
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
  calendar_year_performance?: Record<string, { value: number | null; warning?: { code: string; message: string } | null }>
  relative_to_benchmark?: { value: number | null; warning?: { code: string; message: string } | null } | null
  relative_to_market?: { value: number | null; warning?: { code: string; message: string } | null } | null
  technical?: Record<string, { value: number | null; warning?: { code: string; message: string } | null }>
}

export interface GroupSnapshotState {
  group_key: string
  calculation_version?: string
  data_provenance?: string
  refreshed_at?: string
  membership_version?: number
  universe_provenance?: Record<string, unknown>
  coverage: number
  freshness?: 'current' | 'stale' | 'partial' | 'unavailable'
  freshness_detail?: Record<string, number>
  rows: GroupSnapshotRow[]
}

export interface BreadthState {
  group_key: string
  timeframe?: string
  adjustment?: string
  as_of?: string | null
  coverage: number
  coverage_detail?: Record<string, number>
  member_metrics?: Record<string, Record<string, number | null>>
  evaluated_count: number
  above_ma: Record<string, number | null>
  near_52w?: Record<string, number | null>
  new_highs?: Record<string, number | null>
  new_lows?: Record<string, number | null>
  trend?: Record<string, number | null>
  distance_from_ma?: Record<string, number | null>
  new_high_lookback?: number
  near_threshold?: number
  freshness?: 'current' | 'stale' | 'partial' | 'unavailable'
  freshness_detail?: Record<string, number>
}

export interface BreadthHistoryState {
  group_key: string
  timeframe?: string
  adjustment?: string
  points: Array<{ timestamp: string; above_ma: Record<string, number | null>; coverage: Record<string, number> }>
  freshness?: 'current' | 'stale' | 'partial' | 'unavailable'
  freshness_detail?: Record<string, number>
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
    performance: Record<string, { value: number | null; warning?: { code: string; message: string } | null }>
    technical: Record<string, { value: number | null; warning?: { code: string; message: string } | null }>
    relative_to_benchmark: { value: number | null; warning?: { code: string; message: string } | null } | null
    relative_to_market: { value: number | null; warning?: { code: string; message: string } | null } | null
  }>
  coverage: number
  exclusions: Array<{ code: string; message: string }>
  freshness?: 'current' | 'stale' | 'partial' | 'unavailable'
  freshness_detail?: Record<string, number>
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
  freshness?: 'current' | 'stale' | 'partial' | 'unavailable'
  freshness_detail?: Record<string, number>
}

const CHANNEL_NAME = 'charting-platform-workstation'
const LEADER_KEY = `${CHANNEL_NAME}-leader`
const LEADER_TIMEOUT_MS = 10_000
const LEADER_HEARTBEAT_MS = 4_000
const LINK_GROUPS: readonly LinkGroup[] = ['blue', 'red', 'green', 'purple', 'orange', 'cyan', 'pink', 'brown', 'yellow', 'grey']

function configuredLinkGroup(value: unknown, fallback: LinkGroup): LinkGroup {
  return typeof value === 'string' && (LINK_GROUPS as readonly string[]).includes(value)
    ? value as LinkGroup
    : fallback
}

/** Normalize the legacy monthly token without corrupting the valid one-minute token. */
function normalizeWorkstationTimeframe(value: string) {
  return value === 'MN1' ? 'MN' : value
}

export const useWorkspaceStore = defineStore('workspace', () => {
  const workspace = ref<WorkspaceState | null>(null)
  const activeTabKey = ref<string>('us-top-down')
  const linkedSymbol = ref('SPY')
  /**
   * Shared selection is keyed by link group. `linkedSymbol` remains the blue/default
   * shell symbol, while tools resolve their own group below. Grey tools never read
   * or publish shared state; yellow is the wildcard receiver.
   */
  const linkedSymbols = ref<Partial<Record<LinkGroup, LinkEvent>>>({
    blue: { symbol: 'SPY', group: 'blue', sourceWindowKey: 'workstation' },
  })
  const wildcardSymbol = ref<LinkEvent>({ symbol: 'SPY', group: 'blue', sourceWindowKey: 'workstation' })
  const linkedTimestamp = ref<string | null>(null)
  const linkedTimestamps = ref<Partial<Record<LinkGroup, string | null>>>({})
  const wildcardTimestamp = ref<string | null>(null)
  const linkedTimeframe = ref('D1')
  const linkedTimeframes = ref<Partial<Record<LinkGroup, string>>>({ blue: 'D1' })
  const wildcardTimeframe = ref('D1')
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
  const marketAnalysisRefreshing = ref(false)
  const marketAnalysisRefreshedAt = ref<string | null>(null)
  const constituentETF = ref<string | null>(null)
  const selectedIndustry = ref<string | null>(null)
  const selectedIndustryProxy = ref<string | null>(null)
  let persistedWorkspace: WorkspaceState | null = null
  let channel: BroadcastChannel | null = null
  let leaderTimer: ReturnType<typeof setInterval> | null = null
  let snapshotTimer: ReturnType<typeof setTimeout> | null = null
  let snapshotSavePromise: Promise<void> | null = null
  // A PUT may resolve after a newer local edit has already been made.  Never let
  // that older response replace the live reactive workspace with stale layout or
  // tool configuration.
  let snapshotGeneration = 0
  let marketRefreshPromise: Promise<void> | null = null
  const analysisGenerations = new Map<string, number>()
  const windowId = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `window-${Date.now()}-${Math.random().toString(36).slice(2)}`

  function beginAnalysisRequest(key: string) {
    const generation = (analysisGenerations.get(key) ?? 0) + 1
    analysisGenerations.set(key, generation)
    return generation
  }

  function isCurrentAnalysisRequest(key: string, generation: number) {
    return analysisGenerations.get(key) === generation
  }

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
    return isWorkstationEditorTarget(target)
  }

  function applySharedSymbol(event: LinkEvent) {
    if (event.group === 'grey') return
    linkedSymbols.value = { ...linkedSymbols.value, [event.group]: { ...event } }
    wildcardSymbol.value = { ...event }
    linkedTimestamps.value = { ...linkedTimestamps.value, [event.group]: event.timestamp ?? null }
    wildcardTimestamp.value = event.timestamp ?? null
    if (event.group === 'blue') {
      linkedSymbol.value = event.symbol
      linkedTimestamp.value = event.timestamp ?? null
    }
  }

  function applySharedTimestamp(event: LinkEvent) {
    if (event.group === 'grey' || !event.timestamp) return
    linkedTimestamps.value = { ...linkedTimestamps.value, [event.group]: event.timestamp }
    wildcardTimestamp.value = event.timestamp
    if (event.group === 'blue') linkedTimestamp.value = event.timestamp
  }

  function applySharedTimeframe(timeframe: string, group: LinkGroup) {
    if (group === 'grey') return
    timeframe = normalizeWorkstationTimeframe(timeframe)
    linkedTimeframes.value = { ...linkedTimeframes.value, [group]: timeframe }
    wildcardTimeframe.value = timeframe
    if (group === 'blue') linkedTimeframe.value = timeframe
  }

  async function reloadSharedWorkspace(event: WorkspaceSnapshotEvent) {
    const current = workspace.value
    if (!current || current.id !== event.workspaceId || current.revision >= event.revision || event.sourceWindowId === windowId) return
    try {
      const latest = await api.get<WorkspaceState>(`/workspaces/${event.workspaceId}`)
      if (latest.revision <= current.revision) return
      workspace.value = latest
      persistedWorkspace = cloneSerializable(latest)
      if (!latest.tabs.some(tab => tab.stable_key === activeTabKey.value)) {
        activeTabKey.value = latest.tabs[0]?.stable_key ?? 'us-top-down'
      }
      error.value = null
    } catch (cause: any) {
      error.value = cause?.message ?? 'Unable to synchronize the shared workspace'
    }
  }

  function announceWorkspaceSnapshot(saved: WorkspaceState) {
    const event: WorkspaceSnapshotEvent = {
      type: 'workspace-snapshot', workspaceId: saved.id, revision: saved.revision, sourceWindowId: windowId,
    }
    channel?.postMessage(event)
    try {
      localStorage.setItem(CHANNEL_NAME + ':workspace-snapshot', JSON.stringify(event))
    } catch {
      // BroadcastChannel remains the primary same-origin transport when storage is unavailable.
    }
  }

  function handleMessage(event: MessageEvent<CrossWindowEvent>) {
    if (isWorkspaceSnapshotEvent(event.data)) {
      void reloadSharedWorkspace(event.data)
      return
    }
    if (event.data.group === 'grey') return
    if (event.data.type === 'symbol') applySharedSymbol(event.data)
    if (event.data.type === 'cursor') applySharedTimestamp(event.data)
    if (event.data.type === 'timeframe' && event.data.timeframe) applySharedTimeframe(event.data.timeframe, event.data.group)
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
    if (!event.key || !event.newValue) return
    const message = JSON.parse(event.newValue) as CrossWindowEvent
    if (event.key === CHANNEL_NAME + ':workspace-snapshot' && isWorkspaceSnapshotEvent(message)) {
      void reloadSharedWorkspace(message)
      return
    }
    if (![CHANNEL_NAME + ':symbol', CHANNEL_NAME + ':timeframe', CHANNEL_NAME + ':cursor'].includes(event.key)) return
    const linkMessage = message as LinkEvent & { type?: string }
    if (linkMessage.group !== 'grey') {
      if (event.key === CHANNEL_NAME + ':symbol') {
        applySharedSymbol(linkMessage)
      }
      if (event.key === CHANNEL_NAME + ':cursor') applySharedTimestamp(linkMessage)
      if (event.key === CHANNEL_NAME + ':timeframe' && linkMessage.timeframe) applySharedTimeframe(linkMessage.timeframe, linkMessage.group)
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
    applySharedSymbol(event)
    channel?.postMessage({ ...event, type: 'symbol' })
    localStorage.setItem(CHANNEL_NAME + ':symbol', JSON.stringify(event))
  }

  function symbolForLinkGroup(group: LinkGroup, isolatedSymbol?: string | null) {
    if (group === 'grey') return isolatedSymbol?.trim().toUpperCase() || 'SPY'
    if (group === 'yellow') return wildcardSymbol.value.symbol
    return linkedSymbols.value[group]?.symbol ?? (isolatedSymbol?.trim().toUpperCase() || 'SPY')
  }

  function timestampForLinkGroup(group: LinkGroup) {
    if (group === 'grey') return null
    if (group === 'yellow') return wildcardTimestamp.value
    return linkedTimestamps.value[group] ?? null
  }

  function timeframeForLinkGroup(group: LinkGroup, isolatedTimeframe?: string | null) {
    if (group === 'grey') return normalizeWorkstationTimeframe(isolatedTimeframe ?? 'D1')
    if (group === 'yellow') return wildcardTimeframe.value
    return linkedTimeframes.value[group] ?? normalizeWorkstationTimeframe(isolatedTimeframe ?? 'D1')
  }

  function timeframeLinkGroupForTool(tool: WorkspaceWindowState) {
    return configuredLinkGroup(tool.configuration.timeframe_link_group, tool.link_group)
  }

  function publishTimestamp(timestamp: string, group: LinkGroup = 'blue', sourceWindowKey = 'workstation') {
    if (group === 'grey' || !timestamp) return
    const event: LinkEvent & { type: 'cursor' } = {
      symbol: symbolForLinkGroup(group), timestamp, group, sourceWindowKey, type: 'cursor',
    }
    applySharedTimestamp(event)
    channel?.postMessage(event)
    try {
      localStorage.setItem(CHANNEL_NAME + ':cursor', JSON.stringify(event))
    } catch {
      // BroadcastChannel remains the primary same-origin transport when storage is unavailable.
    }
  }

  function publishTimeframe(timeframe: string, group: LinkGroup = 'blue', sourceWindowKey = 'workstation') {
    if (group === 'grey') return
    timeframe = normalizeWorkstationTimeframe(timeframe)
    applySharedTimeframe(timeframe, group)
    if (workspace.value) {
      const existing = workspace.value.settings.linked_timeframes
      const linked_timeframes = {
        ...(existing && typeof existing === 'object' && !Array.isArray(existing) ? existing as Record<string, string> : {}),
        [group]: timeframe,
      }
      workspace.value.settings = {
        ...workspace.value.settings,
        ...(group === 'blue' ? { linked_timeframe: timeframe } : {}),
        linked_timeframes,
      }
      scheduleSnapshot()
    }
    const event: LinkEvent & { type: 'timeframe' } = { symbol: linkedSymbol.value, timeframe, group, sourceWindowKey, type: 'timeframe' }
    channel?.postMessage(event)
    localStorage.setItem(CHANNEL_NAME + ':timeframe', JSON.stringify(event))
  }

  async function loadDefault() {
    loading.value = true
    error.value = null
    try {
      workspace.value = await api.get<WorkspaceState>('/workspaces/default')
      persistedWorkspace = cloneSerializable(workspace.value)
      activeTabKey.value = workspace.value.tabs[0]?.stable_key ?? 'us-top-down'
      const savedTimeframe = workspace.value.settings.linked_timeframe
      linkedTimeframe.value = typeof savedTimeframe === 'string' ? normalizeWorkstationTimeframe(savedTimeframe) : 'D1'
      const savedTimeframes = workspace.value.settings.linked_timeframes
      linkedTimeframes.value = {
        blue: linkedTimeframe.value,
        ...(savedTimeframes && typeof savedTimeframes === 'object' && !Array.isArray(savedTimeframes)
          ? Object.fromEntries(Object.entries(savedTimeframes).map(([group, timeframe]) => [group, typeof timeframe === 'string' ? normalizeWorkstationTimeframe(timeframe) : timeframe])) as Partial<Record<LinkGroup, string>>
          : {}),
      }
      wildcardTimeframe.value = linkedTimeframes.value.blue ?? 'D1'
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
    const requestKey = `top-down:market-group:${stableKey}`
    const generation = beginAnalysisRequest(requestKey)
    try {
      const group = await api.get<MarketGroupState>(`/market-groups/${encodeURIComponent(stableKey)}`)
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      marketGroups.value = { ...marketGroups.value, [stableKey]: group }
      return group
    } catch (cause: any) {
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      error.value = cause?.message ?? `Unable to load ${stableKey}`
      return null
    }
  }

  async function loadGroupSnapshot(stableKey: string, benchmark?: string, options: { timeframe?: string; adjusted?: boolean; as_of?: string; new_high_lookback?: number; near_threshold?: number } = {}) {
    const requestKey = `top-down:group-snapshot:${stableKey}`
    const generation = beginAnalysisRequest(requestKey)
    try {
      const params = {
        ...(benchmark ? { benchmark } : {}),
        ...(options.timeframe ? { timeframe: options.timeframe } : {}),
        ...(typeof options.adjusted === 'boolean' ? { adjusted: options.adjusted } : {}),
        ...(options.as_of ? { as_of: options.as_of } : {}),
      }
      const snapshot = await api.get<GroupSnapshotState>(`/analysis/groups/${encodeURIComponent(stableKey)}/snapshot`, params)
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      groupSnapshots.value = { ...groupSnapshots.value, [stableKey]: snapshot }
      return snapshot
    } catch (cause: any) {
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      error.value = cause?.message ?? `Unable to calculate ${stableKey}`
      return null
    }
  }

  async function loadBreadth(stableKey: string, options: { timeframe?: string; adjusted?: boolean; as_of?: string; new_high_lookback?: number; near_threshold?: number } = {}) {
    const requestKey = `top-down:breadth:${stableKey}`
    const generation = beginAnalysisRequest(requestKey)
    try {
      const params = {
        ...(options.timeframe ? { timeframe: options.timeframe } : {}),
        ...(typeof options.adjusted === 'boolean' ? { adjusted: options.adjusted } : {}),
        ...(options.as_of ? { as_of: options.as_of } : {}),
        ...(options.new_high_lookback ? { new_high_lookback: options.new_high_lookback } : {}),
        ...(options.near_threshold ? { near_threshold: options.near_threshold } : {}),
      }
      const snapshot = Object.keys(params).length
        ? await api.get<BreadthState>(`/analysis/groups/${encodeURIComponent(stableKey)}/breadth`, params)
        : await api.get<BreadthState>(`/analysis/groups/${encodeURIComponent(stableKey)}/breadth`)
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      breadth.value = { ...breadth.value, [stableKey]: snapshot }
      return snapshot
    } catch (cause: any) {
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      error.value = cause?.message ?? `Unable to calculate breadth for ${stableKey}`
      return null
    }
  }

  async function loadBreadthHistory(stableKey: string, options: { timeframe?: string; adjusted?: boolean; as_of?: string; new_high_lookback?: number; near_threshold?: number } = {}) {
    const requestKey = `top-down:breadth-history:${stableKey}`
    const generation = beginAnalysisRequest(requestKey)
    try {
      const params = {
        limit: 500,
        ...(options.timeframe ? { timeframe: options.timeframe } : {}),
        ...(typeof options.adjusted === 'boolean' ? { adjusted: options.adjusted } : {}),
        ...(options.as_of ? { as_of: options.as_of } : {}),
        ...(options.new_high_lookback ? { new_high_lookback: options.new_high_lookback } : {}),
        ...(options.near_threshold ? { near_threshold: options.near_threshold } : {}),
      }
      const history = await api.get<BreadthHistoryState>(`/analysis/groups/${encodeURIComponent(stableKey)}/breadth/history`, params)
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      breadthHistory.value = { ...breadthHistory.value, [stableKey]: history }
      return history
    } catch (cause: any) {
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      error.value = cause?.message ?? `Unable to calculate historical breadth for ${stableKey}`
      return null
    }
  }

  /**
   * Refresh the shared US top-down inputs in one deduplicated batch. The shell and
   * pop-outs call this method instead of fanning out one request per watchlist cell.
   * A second caller joins the existing refresh, which keeps linked windows from
   * producing duplicate analysis requests.
   */
  async function refreshMarketAnalysis() {
    if (marketRefreshPromise) return marketRefreshPromise
    marketAnalysisRefreshing.value = true
    marketRefreshPromise = Promise.all([
      loadMarketGroup('us-benchmarks'),
      loadMarketGroup('sp500-sectors'),
      loadGroupSnapshot('us-benchmarks', 'SPY'),
      loadGroupSnapshot('sp500-sectors', 'SPY'),
      loadBreadth('sp500-sectors'),
      loadBreadthHistory('sp500-sectors'),
    ]).then(results => {
      // The individual loaders retain their error state and return null. Do not
      // advance the last-successful timestamp when any shared input failed.
      if (results.every(result => result !== null)) {
        marketAnalysisRefreshedAt.value = new Date().toISOString()
      }
    }).finally(() => {
      marketAnalysisRefreshing.value = false
      marketRefreshPromise = null
    })
    return marketRefreshPromise
  }

  async function loadETFHoldings(symbol: string) {
    const normalized = symbol.trim().toUpperCase()
    if (!normalized) return null
    const requestKey = 'top-down:holdings'
    const generation = beginAnalysisRequest(requestKey)
    try {
      const page = await api.get<ETFHoldingsPageState>(`/etf-holdings/${encodeURIComponent(normalized)}/holdings`, {
        limit: 500,
        sort: 'weight',
        direction: 'desc',
        point_in_time: true,
      })
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      etfHoldings.value = { ...etfHoldings.value, [normalized]: page }
      const sameETF = constituentETF.value === normalized
      constituentETF.value = normalized
      // Repeated concurrent hydration for the same ETF is expected (initial
      // shell load, linked-symbol watcher, and an explicit selection can all
      // request it). It must not erase an industry/proxy selection the user has
      // already made while those duplicate responses are arriving.
      if (!sameETF) {
        selectedIndustry.value = null
        selectedIndustryProxy.value = null
      }
      void loadETFConstituentSnapshot(normalized)
      return page
    } catch (cause: any) {
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
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
    const requestKey = 'top-down:constituent-snapshot'
    const generation = beginAnalysisRequest(requestKey)
    try {
      const snapshot = await api.get<ETFConstituentSnapshotState>(
        `/analysis/etf/${encodeURIComponent(normalized)}/constituents/snapshot`,
        { benchmark: comparison, market_benchmark: 'SPY' },
      )
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      etfConstituentSnapshots.value = { ...etfConstituentSnapshots.value, [normalized]: snapshot }
      return snapshot
    } catch (cause: any) {
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
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
    const requestKey = 'top-down:industries'
    const generation = beginAnalysisRequest(requestKey)
    try {
      const composition = await api.get<ETFIndustryCompositionState>(`/market-groups/etf/${encodeURIComponent(normalized)}/industries`)
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      etfIndustries.value = { ...etfIndustries.value, [normalized]: composition }
      return composition
    } catch (cause: any) {
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
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
    const requestKey = 'top-down:industry'
    const generation = beginAnalysisRequest(requestKey)
    selectedIndustryProxy.value = null
    try {
      const constituents = await api.get<ETFIndustryConstituentsState>(
        `/market-groups/etf/${encodeURIComponent(normalized)}/industries/${encodeURIComponent(industry)}`,
      )
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      industryConstituents.value = { ...industryConstituents.value, [key]: constituents }
      void loadIndustryProxies(normalized, industry)
      return constituents
    } catch (cause: any) {
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      error.value = cause?.message ?? `Unable to load ${industry} constituents`
      return null
    }
  }

  async function loadIndustryProxies(symbol: string, industry: string) {
    const normalized = symbol.trim().toUpperCase()
    const key = `${normalized}:${industry}`
    if (!normalized || !industry) return null
    const requestKey = 'top-down:industry-proxies'
    const generation = beginAnalysisRequest(requestKey)
    try {
      const proxies = await api.get<ETFIndustryProxyState>(
        `/market-groups/etf/${encodeURIComponent(normalized)}/industries/${encodeURIComponent(industry)}/proxies`,
      )
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      industryProxies.value = { ...industryProxies.value, [key]: proxies }
      void loadIndustryProxySnapshot(normalized, industry)
      return proxies
    } catch (cause: any) {
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      error.value = cause?.message ?? `Unable to load ${industry} proxies`
      return null
    }
  }

  async function loadIndustryProxySnapshot(symbol: string, industry: string) {
    const normalized = symbol.trim().toUpperCase()
    const key = `${normalized}:${industry}`
    if (!normalized || !industry) return null
    const requestKey = 'top-down:industry-proxy-snapshot'
    const generation = beginAnalysisRequest(requestKey)
    try {
      const snapshot = await api.get<IndustryProxySnapshotState>(`/analysis/etf/${encodeURIComponent(normalized)}/industries/${encodeURIComponent(industry)}/proxies/snapshot`)
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      industryProxySnapshots.value = { ...industryProxySnapshots.value, [key]: snapshot }
      return snapshot
    } catch (cause: any) {
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
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
    const requestKey = 'top-down:technical'
    const generation = beginAnalysisRequest(requestKey)
    try {
      const snapshot = await api.get<TechnicalSnapshotState>(`/analysis/instruments/${encodeURIComponent(normalized)}/technical`)
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      technicals.value = { ...technicals.value, [normalized]: snapshot }
      return snapshot
    } catch (cause: any) {
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      if (cause?.status === 404) {
        technicals.value = { ...technicals.value, [normalized]: null }
        return null
      }
      error.value = cause?.message ?? `Unable to calculate technicals for ${normalized}`
      return null
    }
  }

  async function saveSnapshot() {
    if (snapshotSavePromise) {
      const waitingGeneration = snapshotGeneration
      await snapshotSavePromise
      if (workspace.value && snapshotGeneration !== waitingGeneration) return saveSnapshot()
      return
    }
    if (!workspace.value) return
    const current = workspace.value
    const generation = snapshotGeneration
    const persist = (async () => {
      try {
        const saved = await api.put<WorkspaceState>(`/workspaces/${current.id}/snapshot`, snapshotPayload(current))
        if (generation !== snapshotGeneration) return
        workspace.value = saved
        persistedWorkspace = cloneSerializable(workspace.value)
        announceWorkspaceSnapshot(workspace.value)
      } catch (cause: any) {
        if (String(cause?.message ?? '').includes(' 409:')) {
          try {
            const latest = await api.get<WorkspaceState>(`/workspaces/${current.id}`)
            const merged = mergeDisjointWindowChanges(persistedWorkspace, current, latest)
            if (merged) {
              const saved = await api.put<WorkspaceState>(`/workspaces/${latest.id}/snapshot`, snapshotPayload(merged))
              if (generation !== snapshotGeneration) return
              workspace.value = saved
              persistedWorkspace = cloneSerializable(saved)
              announceWorkspaceSnapshot(saved)
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
    })()
    snapshotSavePromise = persist
    try {
      await persist
    } finally {
      if (snapshotSavePromise === persist) snapshotSavePromise = null
    }
  }

  function scheduleSnapshot() {
    if (snapshotTimer) clearTimeout(snapshotTimer)
    snapshotGeneration += 1
    snapshotTimer = setTimeout(() => { void saveSnapshot() }, 350)
  }

  function applyActiveLayout(layout: Record<string, unknown>, visibleToolKeys: string[]) {
    const tab = activeTab.value
    if (!tab) return
    tab.layout_config = normaliseGoldenLayoutConfig(layout)
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
    const layout = normaliseGoldenLayoutConfig(
      JSON.parse(JSON.stringify(tab.layout_config)) as Record<string, unknown>,
    )
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

  /**
   * Link membership is workspace state, not transient component state. This keeps a
   * docked tool and any browser pop-out on the same persisted link contract after a
   * reload or recovery.
   */
  function updateToolLinkGroup(windowKey: string, group: LinkGroup) {
    const tab = activeTab.value
    const tool = tab?.windows.find(window => window.instance_key === windowKey)
    if (!tool || tool.link_group === group) return false
    tool.link_group = group
    scheduleSnapshot()
    return true
  }

  /**
   * A chart timeframe belongs to its link group.  Grey is deliberately local to the
   * persisted tool; every other group publishes through the same cross-window link
   * bus used for symbols and cursors.  Keeping the local value also makes a tool's
   * first render deterministic before that group has received an event.
   */
  function updateToolTimeframe(windowKey: string, timeframe: string) {
    const tool = activeTab.value?.windows.find(window => window.instance_key === windowKey)
    if (!tool || tool.tool_type !== 'chart' || !timeframe) return false
    timeframe = normalizeWorkstationTimeframe(timeframe)
    tool.configuration = { ...tool.configuration, timeframe }
    const linkGroup = timeframeLinkGroupForTool(tool)
    if (linkGroup === 'grey') {
      scheduleSnapshot()
      return true
    }
    publishTimeframe(timeframe, linkGroup, windowKey)
    return true
  }

  function updateToolTimeframeLinkGroup(windowKey: string, group: LinkGroup) {
    const tool = activeTab.value?.windows.find(window => window.instance_key === windowKey)
    if (!tool || tool.tool_type !== 'chart' || timeframeLinkGroupForTool(tool) === group) return false
    tool.configuration = { ...tool.configuration, timeframe_link_group: group }
    scheduleSnapshot()
    return true
  }

  /**
   * A list row is selected by canonical identity and published only to its owning
   * link group. Persisting the symbol gives grey/isolated windows a durable local
   * selection and provides a safe fallback before a group receives its first event.
   */
  function selectToolSymbol(windowKey: string, symbol: string, instrumentId?: number | null) {
    const tool = activeTab.value?.windows.find(window => window.instance_key === windowKey)
    const normalized = symbol.trim().toUpperCase()
    if (!tool || !normalized) return false
    tool.configuration = {
      ...tool.configuration,
      symbol: normalized,
      ...(typeof instrumentId === 'number' ? { instrument_id: instrumentId } : {}),
    }
    if (tool.link_group !== 'grey') {
      publishSymbol({
        symbol: normalized,
        ...(typeof instrumentId === 'number' ? { instrumentId } : {}),
        group: tool.link_group,
        sourceWindowKey: windowKey,
      })
    }
    scheduleSnapshot()
    return true
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

  function renameTab(stableKey: string, name: string) {
    const tab = workspace.value?.tabs.find(item => item.stable_key === stableKey)
    const normalized = name.trim().replace(/\s+/g, ' ')
    if (!tab || !normalized) return false
    if (tab.name === normalized) return true
    tab.name = normalized.slice(0, 80)
    scheduleSnapshot()
    return true
  }

  function reorderTabs(fromStableKey: string, toStableKey: string) {
    if (!workspace.value || fromStableKey === toStableKey) return false
    const tabs = [...workspace.value.tabs]
    const from = tabs.findIndex(tab => tab.stable_key === fromStableKey)
    const to = tabs.findIndex(tab => tab.stable_key === toStableKey)
    if (from < 0 || to < 0) return false
    const [moved] = tabs.splice(from, 1)
    tabs.splice(to, 0, moved)
    workspace.value.tabs = tabs.map((tab, position) => ({ ...tab, position }))
    scheduleSnapshot()
    return true
  }

  function deleteTab(stableKey: string) {
    if (!workspace.value || workspace.value.tabs.length <= 1) {
      error.value = 'A workspace must retain at least one layout.'
      return false
    }
    const index = workspace.value.tabs.findIndex(tab => tab.stable_key === stableKey)
    if (index < 0) return false
    const remaining = workspace.value.tabs.filter(tab => tab.stable_key !== stableKey)
      .map((tab, position) => ({ ...tab, position }))
    workspace.value.tabs = remaining
    if (activeTabKey.value === stableKey) activeTabKey.value = remaining[Math.max(0, index - 1)]?.stable_key ?? remaining[0].stable_key
    scheduleSnapshot()
    return true
  }

  function exportWorkspaceSnapshot() {
    if (!workspace.value) return null
    return JSON.stringify({
      schema_version: workspace.value.schema_version,
      name: workspace.value.name,
      settings: workspace.value.settings,
      tabs: workspace.value.tabs,
    }, null, 2)
  }

  function importWorkspaceSnapshot(raw: unknown) {
    if (!workspace.value || !raw || typeof raw !== 'object') return false
    const payload = raw as Record<string, unknown>
    if (!Array.isArray(payload.tabs) || !payload.tabs.length) {
      error.value = 'The workspace file contains no layouts.'
      return false
    }
    const tabs = payload.tabs.filter(tab => {
      if (!tab || typeof tab !== 'object') return false
      const candidate = tab as Record<string, unknown>
      return typeof candidate.stable_key === 'string' && typeof candidate.name === 'string' && Array.isArray(candidate.windows)
    }).map((tab, position) => {
      const candidate = tab as Record<string, unknown>
      return {
        ...candidate,
        position,
        name: String(candidate.name).trim().replace(/\s+/g, ' ').slice(0, 80) || `Layout ${position + 1}`,
      }
    }) as WorkspaceTabState[]
    if (!tabs.length) {
      error.value = 'The workspace file contains no valid layouts.'
      return false
    }
    const keys = new Set<string>()
    if (tabs.some(tab => keys.has(tab.stable_key) || (keys.add(tab.stable_key), false))) {
      error.value = 'The workspace file contains duplicate layout IDs.'
      return false
    }
    workspace.value = {
      ...workspace.value,
      tabs,
      settings: payload.settings && typeof payload.settings === 'object' ? payload.settings as Record<string, unknown> : workspace.value.settings,
      schema_version: Number.isInteger(payload.schema_version) ? Number(payload.schema_version) : workspace.value.schema_version,
    }
    activeTabKey.value = tabs[0].stable_key
    error.value = null
    scheduleSnapshot()
    return true
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
    linkedSymbols,
    linkedTimestamp,
    linkedTimestamps,
    linkedTimeframe,
    linkedTimeframes,
    loading,
    error,
    isPersistenceLeader,
    marketGroups,
    groupSnapshots,
    marketAnalysisRefreshing,
    marketAnalysisRefreshedAt,
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
    publishTimestamp,
    symbolForLinkGroup,
    timestampForLinkGroup,
    timeframeForLinkGroup,
    timeframeLinkGroupForTool,
    publishTimeframe,
    loadDefault,
    loadMarketGroup,
    loadGroupSnapshot,
    loadBreadth,
    loadBreadthHistory,
    refreshMarketAnalysis,
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
    updateToolLinkGroup,
    updateToolTimeframe,
    updateToolTimeframeLinkGroup,
    selectToolSymbol,
    closeTool,
    cloneActiveTab,
    renameTab,
    reorderTabs,
    deleteTab,
    exportWorkspaceSnapshot,
    importWorkspaceSnapshot,
    resetFactoryWorkspace,
  }
})
