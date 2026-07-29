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

export interface LinkEvent {
  instrumentId?: number
  symbol: string
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

export const useWorkspaceStore = defineStore('workspace', () => {
  const workspace = ref<WorkspaceState | null>(null)
  const activeTabKey = ref<string>('us-top-down')
  const linkedSymbol = ref('SPY')
  const loading = ref(false)
  const error = ref<string | null>(null)
  const isPersistenceLeader = ref(false)
  const marketGroups = ref<Record<string, MarketGroupState>>({})
  const groupSnapshots = ref<Record<string, GroupSnapshotState>>({})
  const breadth = ref<Record<string, BreadthState>>({})
  const etfHoldings = ref<Record<string, ETFHoldingsPageState | null>>({})
  const etfIndustries = ref<Record<string, ETFIndustryCompositionState | null>>({})
  const industryConstituents = ref<Record<string, ETFIndustryConstituentsState | null>>({})
  const technicals = ref<Record<string, TechnicalSnapshotState | null>>({})
  const constituentETF = ref<string | null>(null)
  const selectedIndustry = ref<string | null>(null)
  let channel: BroadcastChannel | null = null
  let leaderTimer: ReturnType<typeof setInterval> | null = null
  let snapshotTimer: ReturnType<typeof setTimeout> | null = null

  const activeTab = computed(() =>
    workspace.value?.tabs.find(tab => tab.stable_key === activeTabKey.value) ?? workspace.value?.tabs[0] ?? null,
  )

  function isEditorTarget(target: EventTarget | null) {
    return target instanceof HTMLInputElement
      || target instanceof HTMLTextAreaElement
      || target instanceof HTMLSelectElement
      || (target instanceof HTMLElement && target.isContentEditable)
  }

  function handleMessage(event: MessageEvent<LinkEvent & { type?: string }>) {
    if (event.data.type !== 'symbol' || event.data.group === 'grey') return
    linkedSymbol.value = event.data.symbol
  }

  function becomeLeader() {
    const key = 'charting-platform-workstation-leader'
    const current = Number(localStorage.getItem(key) ?? 0)
    const now = Date.now()
    if (!current || now - current > 10_000) {
      localStorage.setItem(key, String(now))
      isPersistenceLeader.value = true
    }
    if (!leaderTimer) {
      leaderTimer = setInterval(() => {
        if (isPersistenceLeader.value) localStorage.setItem(key, String(Date.now()))
      }, 4_000)
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
    if (event.key !== CHANNEL_NAME + ':symbol' || !event.newValue) return
    const message = JSON.parse(event.newValue) as LinkEvent
    if (message.group !== 'grey') linkedSymbol.value = message.symbol
  }

  function disconnect() {
    channel?.close()
    channel = null
    window.removeEventListener('storage', onStorage)
    if (leaderTimer) clearInterval(leaderTimer)
    leaderTimer = null
  }

  function publishSymbol(event: LinkEvent) {
    if (event.group === 'grey') return
    linkedSymbol.value = event.symbol
    channel?.postMessage({ ...event, type: 'symbol' })
    localStorage.setItem(CHANNEL_NAME + ':symbol', JSON.stringify(event))
  }

  async function loadDefault() {
    loading.value = true
    error.value = null
    try {
      workspace.value = await api.get<WorkspaceState>('/workspaces/default')
      activeTabKey.value = workspace.value.tabs[0]?.stable_key ?? 'us-top-down'
    } catch (cause: any) {
      error.value = cause?.message ?? 'Unable to load workstation'
    } finally {
      loading.value = false
    }
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
    try {
      const constituents = await api.get<ETFIndustryConstituentsState>(
        `/market-groups/etf/${encodeURIComponent(normalized)}/industries/${encodeURIComponent(industry)}`,
      )
      industryConstituents.value = { ...industryConstituents.value, [key]: constituents }
      return constituents
    } catch (cause: any) {
      error.value = cause?.message ?? `Unable to load ${industry} constituents`
      return null
    }
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
      workspace.value = await api.put<WorkspaceState>(`/workspaces/${current.id}/snapshot`, {
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
      })
    } catch (cause: any) {
      error.value = cause?.message ?? 'Unable to save workspace snapshot'
    }
  }

  function scheduleSnapshot() {
    if (snapshotTimer) clearTimeout(snapshotTimer)
    snapshotTimer = setTimeout(() => { void saveSnapshot() }, 350)
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

  return {
    workspace,
    activeTab,
    activeTabKey,
    linkedSymbol,
    loading,
    error,
    isPersistenceLeader,
    marketGroups,
    groupSnapshots,
    breadth,
    etfHoldings,
    etfIndustries,
    industryConstituents,
    technicals,
    constituentETF,
    selectedIndustry,
    isEditorTarget,
    connect,
    disconnect,
    publishSymbol,
    loadDefault,
    loadMarketGroup,
    loadGroupSnapshot,
    loadBreadth,
    loadETFHoldings,
    loadETFIndustries,
    selectIndustry,
    loadTechnical,
    saveSnapshot,
    scheduleSnapshot,
    cloneActiveTab,
  }
})
