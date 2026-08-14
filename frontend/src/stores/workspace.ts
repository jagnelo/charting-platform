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

export interface WorkspaceSummary {
  id: number
  name: string
  is_default: boolean
  position: number
  revision: number
}

/**
 * The browser-only tool registry deliberately contains only implemented, serializable
 * primary-workstation tools. It is not a substitute for a runtime component registry.
 */
export interface OpenableToolDefinition {
  tool_type: 'chart' | 'watchlist' | 'notes' | 'alerts' | 'scan' | 'gauge' | 'study_lab' | 'research_results' | 'relative_rotation' | 'breadth' | 'technical_summary' | 'coverage' | 'report' | 'code_library'
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
  { tool_type: 'research_results', title: 'Study Results', instance_prefix: 'research-results', configuration: {} },
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

interface MarketAnalysisRefreshEvent {
  type: 'market-analysis-refresh'
  refreshedAt: string
  sourceWindowId: string
}

type CrossWindowEvent = (LinkEvent & { type?: string }) | WorkspaceSnapshotEvent | MarketAnalysisRefreshEvent

function isWorkspaceSnapshotEvent(event: CrossWindowEvent): event is WorkspaceSnapshotEvent {
  return event.type === 'workspace-snapshot'
    && typeof (event as WorkspaceSnapshotEvent).workspaceId === 'number'
    && typeof (event as WorkspaceSnapshotEvent).revision === 'number'
    && typeof (event as WorkspaceSnapshotEvent).sourceWindowId === 'string'
}

function isMarketAnalysisRefreshEvent(event: CrossWindowEvent): event is MarketAnalysisRefreshEvent {
  return event.type === 'market-analysis-refresh'
    && typeof (event as MarketAnalysisRefreshEvent).refreshedAt === 'string'
    && typeof (event as MarketAnalysisRefreshEvent).sourceWindowId === 'string'
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
  freshness?: 'current' | 'delayed' | 'stale' | 'partial' | 'coverage_limited' | 'coverage-limited' | 'unavailable'
  freshness_detail?: Record<string, number>
  rows: GroupSnapshotRow[]
}

export interface BenchmarkFamilyRatioState {
  family_key: string
  role: 'cap_weight' | 'equal_weight' | 'value' | 'growth'
  symbol: string
  benchmark_role: 'cap_weight' | 'market'
  benchmark: string
  timeframe: string
  adjustment: string
  as_of?: string | null
  points: Array<{ timestamp: string; value: number }>
  coverage: number
  warnings: Array<{ code: string; message: string }>
}

export interface BenchmarkFamilyRatiosState {
  family_key: string
  official_index_symbol: string
  timeframe: string
  adjustment: string
  as_of?: string | null
  membership_version?: number
  universe_provenance?: Record<string, unknown>
  ratios: BenchmarkFamilyRatioState[]
  exclusions: Array<{ code: string; message: string }>
  freshness?: string
  freshness_detail?: Record<string, number>
}

export interface BenchmarkFamilyTechnicalRoleState {
  role: 'cap_weight' | 'equal_weight' | 'value' | 'growth'
  symbol: string | null
  label: string
  verification_state: string
  available: boolean
  as_of?: string | null
  last: number | null
  rsi14: number | null
  sma20: number | null
  sma50: number | null
  sma200: number | null
  position_52w: number | null
  volume_ratio_50: number | null
  freshness: string
  warnings: Array<{ code: string; message: string }>
}

export interface BenchmarkFamilyTechnicalsState {
  family_key: string
  official_index_symbol: string
  timeframe: string
  adjustment: string
  as_of?: string | null
  membership_version?: number
  universe_provenance?: Record<string, unknown>
  roles: BenchmarkFamilyTechnicalRoleState[]
  exclusions: Array<{ code: string; message: string }>
  freshness?: string
  freshness_detail?: Record<string, number>
}

export interface BenchmarkFamilyBreadthMetricState {
  percentage: number | null
  requested_count: number
  eligible_count: number
  excluded_count: number
  coverage: number
  exclusions: Array<{ code: string; message: string; instrument_id?: number | null }>
}

export interface BenchmarkFamilyBreadthRoleState {
  role: 'cap_weight' | 'equal_weight' | 'value' | 'growth'
  symbol: string | null
  label: string
  verification_state: string
  available: boolean
  membership_version?: number | null
  universe_provenance?: Record<string, unknown>
  above_ma: Record<string, BenchmarkFamilyBreadthMetricState>
  near_52w_high?: BenchmarkFamilyBreadthMetricState | null
  new_high?: BenchmarkFamilyBreadthMetricState | null
  trend_up?: BenchmarkFamilyBreadthMetricState | null
  relative_strength_to_cap?: BenchmarkFamilyBreadthMetricState | null
  exclusions: Array<{ code: string; message: string; instrument_id?: number | null }>
}

export interface BenchmarkFamilyBreadthState {
  family_key: string
  official_index_symbol: string
  timeframe: string
  adjustment: string
  as_of?: string | null
  near_threshold: number
  new_high_lookback: number
  membership_version?: number
  universe_provenance?: Record<string, unknown>
  roles: BenchmarkFamilyBreadthRoleState[]
  exclusions: Array<{ code: string; message: string; instrument_id?: number | null }>
  freshness?: string
  freshness_detail?: Record<string, number>
}

export interface BenchmarkFamilyBreadthHistoryState {
  family_key: string
  official_index_symbol: string
  timeframe: string
  adjustment: string
  as_of?: string | null
  limit: number
  roles: Array<{
    role: BenchmarkFamilyBreadthRoleState['role']
    symbol?: string | null
    label: string
    verification_state: string
    available: boolean
    membership_version?: number | null
    universe_provenance?: Record<string, unknown>
    points: BreadthHistoryState['points']
    exclusions: Array<{ code: string; message: string; instrument_id?: number | null }>
  }>
  exclusions: Array<{ code: string; message: string; instrument_id?: number | null }>
  freshness?: string
  freshness_detail?: Record<string, number>
}

export interface BenchmarkFamilyRankingState {
  family_key: string
  official_index_symbol: string
  benchmark?: string | null
  timeframe: string
  adjustment: string
  as_of?: string | null
  rank_period: string
  roles: Array<{
    role: BenchmarkFamilyBreadthRoleState['role']
    symbol?: string | null
    label: string
    verification_state: string
    available: boolean
    rank?: number | null
    performance: Record<string, number | null>
    relative_performance: Record<string, number | null>
    warnings: Array<{ code: string; message: string; instrument_id?: number | null }>
  }>
  exclusions: Array<{ code: string; message: string; instrument_id?: number | null }>
  freshness?: string
  freshness_detail?: Record<string, number>
}

export interface BenchmarkFamilyConcentrationState {
  family_key: string
  official_index_symbol: string
  timeframe: string
  adjustment: string
  as_of?: string | null
  rank_period: string
  top_n: number
  roles: Array<{
    role: BenchmarkFamilyMappingState['role']
    symbol?: string | null
    label: string
    verification_state: string
    available: boolean
    membership_version?: number | null
    composition_date?: string | null
    known_at?: string | null
    weight_method: string
    reported_weight_coverage?: number | null
    top_n: number
    top_n_weight?: number | null
    hhi?: number | null
    effective_constituents?: number | null
    eligible_count: number
    covered_count: number
    excluded_count: number
    coverage: number
    mean_return?: number | null
    median_return?: number | null
    dispersion?: number | null
    p10_return?: number | null
    p25_return?: number | null
    p75_return?: number | null
    p90_return?: number | null
    positive_percentage?: number | null
    negative_percentage?: number | null
    members: Array<{
      instrument_id: number
      symbol: string
      name: string
      position: number
      weight?: number | null
      performance?: number | null
      covered: boolean
    }>
    warnings: Array<{ code: string; message: string }>
  }>
  exclusions: Array<{ code: string; message: string }>
  freshness?: string
  freshness_detail?: Record<string, number>
}

export interface CrossFamilyRankingState {
  timeframe: string
  adjustment: string
  as_of?: string | null
  benchmark?: string | null
  rank_period: string
  rows: Array<{
    family_key: string
    family_name: string
    official_index_symbol: string
    symbol?: string | null
    label: string
    available: boolean
    rank?: number | null
    performance: Record<string, number | null>
    relative_performance: Record<string, number | null>
    warnings: Array<{ code: string; message: string; instrument_id?: number | null }>
  }>
  exclusions: Array<{ code: string; message: string; instrument_id?: number | null }>
  freshness?: string
  freshness_detail?: Record<string, number>
}

export interface CrossFamilyRankingHistoryState {
  timeframe: string
  adjustment: string
  as_of?: string | null
  benchmark?: string | null
  rank_period: string
  limit: number
  rows: Array<{
    family_key: string
    family_name: string
    official_index_symbol: string
    symbol?: string | null
    label: string
    available: boolean
    coverage: number
    points: Array<{
      timestamp: string
      rank?: number | null
      performance: Record<string, number | null>
      relative_performance: Record<string, number | null>
    }>
    warnings: Array<{ code: string; message: string; instrument_id?: number | null }>
  }>
  exclusions: Array<{ code: string; message: string; instrument_id?: number | null }>
  freshness?: string
  freshness_detail?: Record<string, number>
}

export interface BenchmarkFamilyMappingState {
  role: 'cap_weight' | 'equal_weight' | 'value' | 'growth'
  symbol: string | null
  label: string
  verification_state: string
  source_url?: string | null
  instrument_id?: number | null
  available: boolean
  holdings_snapshot_id?: number | null
  holdings_available: boolean
  holdings_composition_date?: string | null
  holdings_known_at?: string | null
  holdings_source_provider?: string | null
  holdings_completeness_status?: string | null
  holdings_row_count?: number | null
  holdings_resolved_count?: number | null
  holdings_unresolved_count?: number | null
  holdings_total_weight?: number | null
}

export interface BenchmarkFamilyOverviewState {
  family_key: string
  name: string
  official_index_symbol: string
  official_index_name: string
  timeframe: string
  adjustment: string
  as_of?: string | null
  membership_version: number
  universe_provenance: Record<string, unknown>
  coverage: number
  exclusions: Array<{ code: string; message: string }>
  mappings: BenchmarkFamilyMappingState[]
  derived_equal_weight: Record<string, unknown>
  rows: GroupSnapshotRow[]
  freshness?: string
  freshness_detail?: Record<string, number>
}

export interface BenchmarkFamilyCoverageSnapshotState {
  snapshot_id: number
  composition_date: string
  as_of_date?: string | null
  known_at?: string | null
  provenance: string
  source_provider: string
  source_quality: string
  completeness_status: string
  row_count: number
  resolved_count: number
  unresolved_count: number
}

export interface BenchmarkFamilyCoverageRoleState {
  role: BenchmarkFamilyMappingState['role']
  symbol?: string | null
  label: string
  verification_state: string
  instrument_id?: number | null
  available: boolean
  status: string
  snapshots: BenchmarkFamilyCoverageSnapshotState[]
}

export interface BenchmarkFamilyCoverageState {
  family_key: string
  name: string
  official_index_symbol: string
  official_index_name: string
  as_of?: string | null
  membership_version: number
  universe_provenance: Record<string, unknown>
  coverage: number
  roles: BenchmarkFamilyCoverageRoleState[]
  exclusions: Array<{ code: string; message: string; instrument_id?: number | null }>
  freshness?: string
  freshness_detail?: Record<string, number>
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
  freshness?: 'current' | 'delayed' | 'stale' | 'partial' | 'coverage_limited' | 'coverage-limited' | 'unavailable'
  freshness_detail?: Record<string, number>
}

export interface BreadthHistoryState {
  group_key: string
  timeframe?: string
  adjustment?: string
  points: Array<{ timestamp: string; above_ma: Record<string, number | null>; coverage: Record<string, number> }>
  freshness?: 'current' | 'delayed' | 'stale' | 'partial' | 'coverage_limited' | 'coverage-limited' | 'unavailable'
  freshness_detail?: Record<string, number>
}

export interface GenericBreadthState {
  definition_version: number
  definition_hash: string
  universe: Record<string, unknown>
  condition: Record<string, unknown>
  timeframe: string
  adjustment: string
  as_of?: string | null
  requested_count: number
  eligible_count: number
  pass_count: number
  excluded_count: number
  percentage: number | null
  coverage: number
  members: Array<{
    instrument_id: number
    symbol: string
    name: string
    value: boolean | null
    metric: number | null
    observation_time?: string | null
    warning?: { code: string; message: string } | null
  }>
  exclusions: Array<{ code: string; message: string; instrument_id?: number | null }>
  freshness?: string
  freshness_detail?: Record<string, number>
}

export interface GenericBreadthHistoryState {
  definition_version: number
  definition_hash: string
  universe: Record<string, unknown>
  condition: Record<string, unknown>
  timeframe: string
  adjustment: string
  as_of?: string | null
  points: Array<{
    timestamp: string
    requested_count: number
    eligible_count: number
    pass_count: number
    excluded_count: number
    percentage: number | null
    coverage: number
    members: GenericBreadthState['members']
    exclusions: Array<{ code: string; message: string; instrument_id?: number | null }>
  }>
  exclusions: Array<{ code: string; message: string; instrument_id?: number | null }>
  freshness?: string
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

export interface BenchmarkFamilyConstituentRowState extends GroupSnapshotRow {
  position?: number
  weight?: number | null
  shares?: number | null
  market_value?: number | null
  holding_type?: string
  row_type?: string
  resolution_confidence?: number | null
}

export interface BenchmarkFamilyConstituentsState extends ETFConstituentSnapshotState {
  group_key: string
  rows: BenchmarkFamilyConstituentRowState[]
  universe_provenance?: Record<string, unknown>
}

export interface ETFIndustryCompositionState {
  etf_symbol: string
  composition_date: string
  known_at: string | null
  provenance: string
  source_provider: string
  completeness_status: string
  industries: Array<{
    industry: string
    constituent_count: number
    resolved_count: number
    classification_systems?: string[]
  }>
  exclusions: string[]
  classification_systems?: string[]
  classification_coverage?: number
}

export interface ETFIndustryConstituentsState {
  etf_symbol: string
  industry: string
  composition_date: string
  known_at: string | null
  provenance: string
  source_provider: string
  constituents: MarketGroupInstrument[]
  exclusions: string[]
  classification_systems?: string[]
  classification_coverage?: number
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

export interface IndustrySnapshotState {
  etf_symbol: string
  market_benchmark: string
  timeframe?: string
  composition_date: string
  known_at: string | null
  membership_version?: number
  universe_provenance?: Record<string, unknown>
  coverage: number
  rows: Array<{
    industry: string
    constituent_count: number
    resolved_count: number
    coverage: number
    last: { value: number | null; observation_time?: string | null; warning?: { code: string; message: string } | null }
    performance: Record<string, { value: number | null; observation_time?: string | null; warning?: { code: string; message: string } | null }>
    relative_to_benchmark?: { value: number | null; warning?: { code: string; message: string } | null } | null
    relative_to_market?: { value: number | null; warning?: { code: string; message: string } | null } | null
    technical?: Record<string, { value: number | null; warning?: { code: string; message: string } | null }>
    warnings?: Array<{ code: string; message: string }>
  }>
  exclusions: Array<{ code: string; message: string }>
  freshness?: 'current' | 'delayed' | 'stale' | 'partial' | 'coverage_limited' | 'coverage-limited' | 'unavailable'
  freshness_detail?: Record<string, number>
}

export interface IndustryProxySnapshotState {
  rows: Array<{
    instrument_id: number
    symbol: string
    name: string
    performance: Record<string, { value: number | null; warning?: { code: string; message: string } | null }>
    technical: Record<string, { value: number | null; warning?: { code: string; message: string } | null }>
    relative_to_benchmark: { value: number | null; warning?: { code: string; message: string } | null } | null
    relative_to_market: { value: number | null; warning?: { code: string; message: string } | null } | null
  }>
  coverage: number
  exclusions: Array<{ code: string; message: string }>
  freshness?: 'current' | 'delayed' | 'stale' | 'partial' | 'coverage_limited' | 'coverage-limited' | 'unavailable'
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
  freshness?: 'current' | 'delayed' | 'stale' | 'partial' | 'coverage_limited' | 'coverage-limited' | 'unavailable'
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

function safeStorageGet(key: string) {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function safeStorageSet(key: string, value: string) {
  try {
    localStorage.setItem(key, value)
  } catch {
    // BroadcastChannel remains the primary same-origin transport when storage
    // is unavailable or blocked by the browser's privacy policy.
  }
}

function safeStorageRemove(key: string) {
  try {
    localStorage.removeItem(key)
  } catch {
    // Storage cleanup is best effort; leadership heartbeats still expire.
  }
}

/** Normalize the legacy monthly token without corrupting the valid one-minute token. */
function normalizeWorkstationTimeframe(value: string) {
  return value === 'MN1' ? 'MN' : value
}

export const useWorkspaceStore = defineStore('workspace', () => {
  const workspace = ref<WorkspaceState | null>(null)
  const workspaces = ref<WorkspaceSummary[]>([])
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
  // Last symbol explicitly published by this window. Cross-window storage
  // events can arrive out of order around a reset; this local value is the
  // authoritative displayed-symbol fallback when a tool is isolated.
  const locallyPublishedSymbols = ref<Partial<Record<LinkGroup, string>>>({ blue: 'SPY' })
  // Shell-level selections are the user's canonical active-symbol intent. A
  // late chart/pop-out publication must not overwrite this before Grey
  // isolation captures the currently selected symbol.
  const latestWorkstationSymbol = ref('SPY')
  const latestWorkstationInstrumentId = ref<number | null>(null)
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
  const marketGroupErrors = ref<Record<string, string | null>>({})
  const groupSnapshotErrors = ref<Record<string, string | null>>({})
  const benchmarkFamilyRatios = ref<Record<string, BenchmarkFamilyRatiosState | null>>({})
  const benchmarkFamilyRatioErrors = ref<Record<string, string | null>>({})
  const benchmarkFamilyTechnicals = ref<Record<string, BenchmarkFamilyTechnicalsState | null>>({})
  const benchmarkFamilyTechnicalErrors = ref<Record<string, string | null>>({})
  const benchmarkFamilyBreadths = ref<Record<string, BenchmarkFamilyBreadthState | null>>({})
  const benchmarkFamilyBreadthErrors = ref<Record<string, string | null>>({})
  const benchmarkFamilyBreadthHistories = ref<Record<string, BenchmarkFamilyBreadthHistoryState | null>>({})
  const benchmarkFamilyBreadthHistoryErrors = ref<Record<string, string | null>>({})
  const benchmarkFamilyRankings = ref<Record<string, BenchmarkFamilyRankingState | null>>({})
  const benchmarkFamilyRankingErrors = ref<Record<string, string | null>>({})
  const benchmarkFamilyConcentrations = ref<Record<string, BenchmarkFamilyConcentrationState | null>>({})
  const benchmarkFamilyConcentrationErrors = ref<Record<string, string | null>>({})
  const crossFamilyRankings = ref<Record<string, CrossFamilyRankingState | null>>({})
  const crossFamilyRankingErrors = ref<Record<string, string | null>>({})
  const crossFamilyRankingHistories = ref<Record<string, CrossFamilyRankingHistoryState | null>>({})
  const crossFamilyRankingHistoryErrors = ref<Record<string, string | null>>({})
  const benchmarkFamilyOverviews = ref<Record<string, BenchmarkFamilyOverviewState | null>>({})
  const benchmarkFamilyOverviewErrors = ref<Record<string, string | null>>({})
  const benchmarkFamilyCoverages = ref<Record<string, BenchmarkFamilyCoverageState | null>>({})
  const benchmarkFamilyCoverageErrors = ref<Record<string, string | null>>({})
  const benchmarkFamilyConstituents = ref<Record<string, BenchmarkFamilyConstituentsState | null>>({})
  const benchmarkFamilyConstituentErrors = ref<Record<string, string | null>>({})
  const breadth = ref<Record<string, BreadthState>>({})
  const breadthHistory = ref<Record<string, BreadthHistoryState>>({})
  const breadthLoading = ref<Record<string, boolean>>({})
  const breadthHistoryLoading = ref<Record<string, boolean>>({})
  const breadthErrors = ref<Record<string, string | null>>({})
  const breadthHistoryErrors = ref<Record<string, string | null>>({})
  const genericBreadth = ref<Record<string, GenericBreadthState>>({})
  const genericBreadthLoading = ref<Record<string, boolean>>({})
  const genericBreadthErrors = ref<Record<string, string | null>>({})
  const genericBreadthHistory = ref<Record<string, GenericBreadthHistoryState>>({})
  const genericBreadthHistoryLoading = ref<Record<string, boolean>>({})
  const genericBreadthHistoryErrors = ref<Record<string, string | null>>({})
  const etfHoldings = ref<Record<string, ETFHoldingsPageState | null>>({})
  const etfConstituentSnapshots = ref<Record<string, ETFConstituentSnapshotState | null>>({})
  const etfIndustries = ref<Record<string, ETFIndustryCompositionState | null>>({})
  const industryConstituents = ref<Record<string, ETFIndustryConstituentsState | null>>({})
  const industryProxies = ref<Record<string, ETFIndustryProxyState | null>>({})
  const industryProxySnapshots = ref<Record<string, IndustryProxySnapshotState | null>>({})
  const industrySnapshots = ref<Record<string, IndustrySnapshotState | null>>({})
  const industrySnapshotErrors = ref<Record<string, string | null>>({})
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
  let lastLocalWorkspaceMutationAt = 0
  const recentLinkGroupOverrides = new Map<string, { group: LinkGroup; symbol: string; at: number }>()
  const recentActiveWindowOverrides = new Map<string, { windowKey: string; at: number }>()
  // A PUT may resolve after a newer local edit has already been made.  Never let
  // that older response replace the live reactive workspace with stale layout or
  // tool configuration.
  let snapshotGeneration = 0
  let marketRefreshPromise: Promise<void> | null = null
  const analysisGenerations = new Map<string, number>()
  const windowId = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `window-${Date.now()}-${Math.random().toString(36).slice(2)}`

  // Visibility is checked at the request boundary as well as by Vue Query's
  // interval coordinator. This closes the small race where a queued loader
  // resumes after a tab becomes hidden and would otherwise start a new market
  // analysis request despite the polling surface being suspended.
  function documentIsVisible() {
    return typeof document === 'undefined' || document.visibilityState !== 'hidden'
  }

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
    // A remote event can have been queued before a local edit and arrive after
    // the debounce/save completes. Keep a short revisioned-write settling
    // window so that stale snapshots cannot undo the user's latest control
    // selection; the next explicit event/read still reconciles normally.
    if (Date.now() - lastLocalWorkspaceMutationAt < 750) return
    // A local edit is already queued or being persisted. Applying a remote
    // snapshot first would silently discard that edit and make the subsequent
    // save appear to have originated from a stale tool. Let the revisioned save
    // path merge or create its documented recovery copy instead.
    if (snapshotTimer || snapshotSavePromise) return
    try {
      const latest = await api.get<WorkspaceState>(`/workspaces/${event.workspaceId}`)
      // The read may have started before a local control change queued a
      // snapshot. Re-check after the await so an older remote response cannot
      // restore the previous link group over the user's current selection.
      if (snapshotTimer || snapshotSavePromise || workspace.value?.revision !== current.revision) return
      if (latest.revision <= current.revision) return
      const now = Date.now()
      for (const [windowKey, override] of recentLinkGroupOverrides) {
        if (now - override.at >= 5000) {
          recentLinkGroupOverrides.delete(windowKey)
          continue
        }
        const remoteTool = latest.tabs.flatMap(tab => tab.windows).find(window => window.instance_key === windowKey)
        if (!remoteTool) continue
        remoteTool.link_group = override.group
        remoteTool.configuration = { ...remoteTool.configuration, symbol: override.symbol }
      }
      for (const [tabKey, override] of recentActiveWindowOverrides) {
        if (now - override.at >= 10_000) {
          recentActiveWindowOverrides.delete(tabKey)
          continue
        }
        const remoteTab = latest.tabs.find(tab => tab.stable_key === tabKey)
        if (remoteTab?.windows.some(window => window.instance_key === override.windowKey)) {
          remoteTab.active_window_key = override.windowKey
        }
      }
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
      safeStorageSet(CHANNEL_NAME + ':workspace-snapshot', JSON.stringify(event))
    } catch {
      // JSON serialization of the serializable event should not fail, but a
      // failed announcement must never break a successful workspace save.
    }
  }

  function announceMarketAnalysisRefresh(refreshedAt: string) {
    const event: MarketAnalysisRefreshEvent = {
      type: 'market-analysis-refresh', refreshedAt, sourceWindowId: windowId,
    }
    channel?.postMessage(event)
    safeStorageSet(CHANNEL_NAME + ':market-analysis-refresh', JSON.stringify(event))
  }

  function handleMessage(event: MessageEvent<CrossWindowEvent>) {
    if (isWorkspaceSnapshotEvent(event.data)) {
      void reloadSharedWorkspace(event.data)
      return
    }
    if (isMarketAnalysisRefreshEvent(event.data)) {
      if (!isPersistenceLeader.value && event.data.sourceWindowId !== windowId && event.data.refreshedAt !== marketAnalysisRefreshedAt.value) {
        void refreshMarketAnalysis()
      }
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
      const raw = safeStorageGet(LEADER_KEY)
      current = raw ? JSON.parse(raw) as { id: string; heartbeat: number } : null
    } catch {
      current = null
    }
    const now = Date.now()
    if (!current || current.id === windowId || now - current.heartbeat > LEADER_TIMEOUT_MS) {
      safeStorageSet(LEADER_KEY, JSON.stringify({ id: windowId, heartbeat: now }))
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
    let message: CrossWindowEvent
    try {
      message = JSON.parse(event.newValue) as CrossWindowEvent
    } catch {
      // Another same-origin app or a partially written storage value must not
      // take down the workstation's cross-window coordinator.
      return
    }
    if (event.key === CHANNEL_NAME + ':workspace-snapshot' && isWorkspaceSnapshotEvent(message)) {
      void reloadSharedWorkspace(message)
      return
    }
    if (event.key === CHANNEL_NAME + ':market-analysis-refresh' && isMarketAnalysisRefreshEvent(message)) {
      if (!isPersistenceLeader.value && message.sourceWindowId !== windowId && message.refreshedAt !== marketAnalysisRefreshedAt.value) {
        void refreshMarketAnalysis()
      }
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
        const current = JSON.parse(safeStorageGet(LEADER_KEY) ?? 'null') as { id?: string } | null
        if (current?.id === windowId) safeStorageRemove(LEADER_KEY)
      } catch {
        safeStorageRemove(LEADER_KEY)
      }
    }
    isPersistenceLeader.value = false
  }

  function publishSymbol(event: LinkEvent) {
    if (event.group === 'grey') return
    if (event.sourceWindowKey === 'workstation') {
      latestWorkstationSymbol.value = event.symbol
      latestWorkstationInstrumentId.value = typeof event.instrumentId === 'number' ? event.instrumentId : null
    }
    locallyPublishedSymbols.value = { ...locallyPublishedSymbols.value, [event.group]: event.symbol }
    applySharedSymbol(event)
    // Keep each concrete linked tool's serializable fallback current as the
    // shared symbol changes. This is important when a tool is moved to Grey:
    // the isolation boundary must capture the symbol the user was actually
    // viewing, not the factory symbol that happened to be persisted earlier.
    if (workspace.value) {
      let changed = false
      for (const tab of workspace.value.tabs) {
        for (const tool of tab.windows) {
          if (tool.link_group !== event.group) continue
          const hasMatchingSymbol = tool.configuration.symbol === event.symbol
          const hasMatchingInstrument = typeof event.instrumentId === 'number'
            ? tool.configuration.instrument_id === event.instrumentId
            : !('instrument_id' in tool.configuration)
          if (hasMatchingSymbol && hasMatchingInstrument) continue
          const configuration: Record<string, unknown> & { symbol: string } = {
            ...tool.configuration,
            symbol: event.symbol,
          }
          if (typeof event.instrumentId === 'number') configuration.instrument_id = event.instrumentId
          else delete configuration.instrument_id
          tool.configuration = configuration
          changed = true
        }
      }
      if (changed) scheduleSnapshot()
    }
    channel?.postMessage({ ...event, type: 'symbol' })
    safeStorageSet(CHANNEL_NAME + ':symbol', JSON.stringify(event))
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
    safeStorageSet(CHANNEL_NAME + ':timeframe', JSON.stringify(event))
  }

  async function loadDefault() {
    loading.value = true
    error.value = null
    try {
      workspace.value = await api.get<WorkspaceState>('/workspaces/default')
      workspaces.value = [{
        id: workspace.value.id,
        name: workspace.value.name,
        is_default: workspace.value.is_default,
        position: workspace.value.position,
        revision: workspace.value.revision,
      }]
      persistedWorkspace = cloneSerializable(workspace.value)
      activeTabKey.value = workspace.value.tabs[0]?.stable_key ?? 'us-top-down'
      // Persisted tool configuration is the durable source of the active
      // symbol. Hydrate the shared blue link before tools mount so a reload
      // restores the user's last workstation symbol (and ratio legs) rather
      // than defaulting every linked surface back to SPY.
      const savedSymbol = workspace.value.tabs
        .flatMap(tab => tab.windows)
        .find(window => window.link_group === 'blue' && typeof window.configuration?.symbol === 'string')
        ?.configuration.symbol
      if (typeof savedSymbol === 'string' && savedSymbol.trim()) {
        const normalizedSymbol = savedSymbol.trim().toUpperCase()
        const configuredInstrumentId = workspace.value.tabs
          .flatMap(tab => tab.windows)
          .find(window => window.link_group === 'blue' && typeof window.configuration?.symbol === 'string' && window.configuration.symbol.trim().toUpperCase() === normalizedSymbol)
          ?.configuration?.instrument_id
        const event: LinkEvent = {
          symbol: normalizedSymbol,
          ...(typeof configuredInstrumentId === 'number' ? { instrumentId: configuredInstrumentId } : {}),
          group: 'blue',
          sourceWindowKey: 'workstation',
        }
        linkedSymbol.value = normalizedSymbol
        linkedSymbols.value = { ...linkedSymbols.value, blue: event }
        locallyPublishedSymbols.value = { ...locallyPublishedSymbols.value, blue: normalizedSymbol }
        latestWorkstationSymbol.value = normalizedSymbol
        latestWorkstationInstrumentId.value = typeof configuredInstrumentId === 'number' ? configuredInstrumentId : null
        wildcardSymbol.value = event
      }
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

  async function refreshWorkspaces() {
    const rows = await api.get<WorkspaceState[]>('/workspaces')
    if (!Array.isArray(rows)) return workspaces.value
    workspaces.value = rows.map(({ id, name, is_default, position, revision }) => ({ id, name, is_default, position, revision }))
      .sort((a, b) => a.position - b.position || a.id - b.id)
    return workspaces.value
  }

  function invalidateQueuedSnapshot() {
    // Workspace CRUD mutations (create/clone/rename/delete) are control-plane
    // writes. A trailing Golden Layout snapshot captured before one of those
    // writes must never be allowed to overwrite the newer name or resurrect a
    // deleted workspace after the control request completes.
    snapshotGeneration += 1
    if (snapshotTimer) {
      clearTimeout(snapshotTimer)
      snapshotTimer = null
    }
  }

  async function settleSnapshotBeforeWorkspaceMutation() {
    invalidateQueuedSnapshot()
    const pending = snapshotSavePromise
    if (pending) await pending
  }

  async function switchWorkspace(workspaceId: number) {
    if (!Number.isInteger(workspaceId) || workspace.value?.id === workspaceId) return workspace.value
    loading.value = true
    try {
      const next = await api.get<WorkspaceState>(`/workspaces/${workspaceId}`)
      workspace.value = next
      persistedWorkspace = cloneSerializable(next)
      activeTabKey.value = next.tabs[0]?.stable_key ?? 'us-top-down'
      error.value = null
      await refreshWorkspaces()
      return next
    } catch (cause: any) {
      error.value = cause?.message ?? 'Unable to switch workspace'
      return null
    } finally { loading.value = false }
  }

  async function createWorkspace(name = 'New Workspace') {
    const normalized = name.trim().replace(/\s+/g, ' ').slice(0, 120) || 'New Workspace'
    try {
      await settleSnapshotBeforeWorkspaceMutation()
      const created = await api.post<WorkspaceState>('/workspaces', { name: normalized, is_default: false })
      workspace.value = created
      persistedWorkspace = cloneSerializable(created)
      activeTabKey.value = created.tabs[0]?.stable_key ?? 'us-top-down'
      error.value = null
      await refreshWorkspaces()
      return created
    } catch (cause: any) { error.value = cause?.message ?? 'Unable to create workspace'; return null }
  }

  async function cloneWorkspace() {
    if (!workspace.value) return null
    try {
      await settleSnapshotBeforeWorkspaceMutation()
      const clone = await api.post<WorkspaceState>(`/workspaces/${workspace.value.id}/clone`, {})
      workspace.value = clone
      persistedWorkspace = cloneSerializable(clone)
      activeTabKey.value = clone.tabs[0]?.stable_key ?? 'us-top-down'
      error.value = null
      await refreshWorkspaces()
      return clone
    } catch (cause: any) { error.value = cause?.message ?? 'Unable to clone workspace'; return null }
  }

  async function renameWorkspace(name: string) {
    if (!workspace.value) return null
    const normalized = name.trim().replace(/\s+/g, ' ').slice(0, 120)
    if (!normalized) return null
    try {
      await settleSnapshotBeforeWorkspaceMutation()
      const updated = await api.patch<WorkspaceState>(`/workspaces/${workspace.value.id}`, { name: normalized })
      workspace.value = updated
      persistedWorkspace = cloneSerializable(updated)
      error.value = null
      await refreshWorkspaces()
      return updated
    } catch (cause: any) { error.value = cause?.message ?? 'Unable to rename workspace'; return null }
  }

  async function deleteCurrentWorkspace() {
    if (!workspace.value || workspace.value.is_default) return false
    try {
      await settleSnapshotBeforeWorkspaceMutation()
      await api.delete(`/workspaces/${workspace.value.id}`)
      const rows = await refreshWorkspaces()
      const fallback = rows.find(item => item.is_default) ?? rows[0]
      if (fallback) await switchWorkspace(fallback.id)
      return true
    } catch (cause: any) { error.value = cause?.message ?? 'Unable to delete workspace'; return false }
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
   * Merge independently changed window records and deterministic local layout
   * edits. Golden Layout can emit several structurally equivalent snapshots while
   * a tool is mounting or a tab is becoming active. Treating every concurrent
   * layout/active-tab difference as unrecoverable would create a recovery copy for
   * a normal single-window interaction. In that narrow case the current window's
   * latest layout wins; identity, settings, and tab membership still require
   * recovery because they cannot be safely inferred. Same-window record
   * conflicts use the explicit current-window-wins tie-breaker below.
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
        || localTab.position !== baseTab.position || remoteTab.position !== baseTab.position) return null
      const localLayoutChanged = !sameJson(localTab.layout_config, baseTab.layout_config)
      const localActiveWindowChanged = localTab.active_window_key !== baseTab.active_window_key
      if (localLayoutChanged) mergedTab.layout_config = cloneSerializable(localTab.layout_config)
      if (localActiveWindowChanged) mergedTab.active_window_key = localTab.active_window_key
      for (const baseWindow of baseTab.windows) {
        const localWindow = localTab.windows.find(window => window.instance_key === baseWindow.instance_key)
        const remoteWindow = remoteTab.windows.find(window => window.instance_key === baseWindow.instance_key)
        const mergedWindow = mergedTab.windows.find(window => window.instance_key === baseWindow.instance_key)
        // A local tool-open and a remote layout snapshot can legitimately race.
        // Additive windows are safe to merge by stable instance key; destructive
        // removal remains a recovery-worthy conflict so an older snapshot cannot
        // silently resurrect a user's explicit close.
        if (!localWindow || !remoteWindow || !mergedWindow) return null
        const localChanged = !sameJson(localWindow, baseWindow)
        const remoteChanged = !sameJson(remoteWindow, baseWindow)
        // A single workstation window can publish several legitimate local
        // mutations in one debounce interval (symbol/link hydration, Study Lab
        // run metadata, and layout activation). If another snapshot advanced the
        // same record before this write, prefer the current user's latest record;
        // disjoint windows still merge with the remote state above. Structural
        // identity changes remain guarded by the checks before this loop.
        if (localChanged) Object.assign(mergedWindow, cloneSerializable(localWindow))
      }
      const baseKeys = new Set(baseTab.windows.map(window => window.instance_key))
      const localExtra = localTab.windows.filter(window => !baseKeys.has(window.instance_key))
      const remoteExtra = remoteTab.windows.filter(window => !baseKeys.has(window.instance_key))
      const mergedKeys = new Set(mergedTab.windows.map(window => window.instance_key))
      // Keep remote additions, then append local-only additions in their local
      // order. This is deterministic and preserves both users' newly opened
      // tools without treating normal Add tool activity as an unrecoverable
      // workspace identity conflict.
      for (const window of [...remoteExtra, ...localExtra]) {
        if (mergedKeys.has(window.instance_key)) continue
        mergedTab.windows.push(cloneSerializable(window))
        mergedKeys.add(window.instance_key)
      }
    }
    return merged
  }

  async function loadMarketGroup(stableKey: string) {
    const requestKey = `top-down:market-group:${stableKey}`
    const generation = beginAnalysisRequest(requestKey)
    if (!documentIsVisible()) return null
    marketGroupErrors.value = { ...marketGroupErrors.value, [stableKey]: null }
    try {
      const group = await api.get<MarketGroupState>(`/market-groups/${encodeURIComponent(stableKey)}`)
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      let hydratedGroup = group
      // Older persisted/backend fixtures may expose the benchmark root before
      // the family registry was added.  Recover the registry from the explicit
      // child endpoint instead of hard-coding family symbols or silently
      // changing the selected universe.
      if (stableKey === 'us-benchmarks' && group.provenance && !Array.isArray(group.provenance.benchmark_families)) {
        try {
          const children = await api.get<MarketGroupState[]>('/market-groups/us-benchmarks/children')
          const families = children
            .filter(child => child.group_type === 'benchmark_family')
            .map(child => ({ logical_key: child.stable_key, name: child.name }))
          if (families.length) {
            hydratedGroup = { ...group, provenance: { ...group.provenance, benchmark_families: families } }
          }
        } catch {
          // Keep the root response and its explicit provenance. A missing child
          // registry is surfaced by the UI as unavailable rather than inferred.
        }
      }
      marketGroups.value = { ...marketGroups.value, [stableKey]: hydratedGroup }
      return hydratedGroup
    } catch (cause: any) {
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      error.value = cause?.message ?? `Unable to load ${stableKey}`
      marketGroupErrors.value = { ...marketGroupErrors.value, [stableKey]: error.value }
      return null
    }
  }

  async function loadGroupSnapshot(stableKey: string, benchmark?: string, options: { timeframe?: string; adjusted?: boolean; as_of?: string; new_high_lookback?: number; near_threshold?: number } = {}) {
    const requestKey = `top-down:group-snapshot:${stableKey}`
    const generation = beginAnalysisRequest(requestKey)
    if (!documentIsVisible()) return null
    groupSnapshotErrors.value = { ...groupSnapshotErrors.value, [stableKey]: null }
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
      groupSnapshotErrors.value = { ...groupSnapshotErrors.value, [stableKey]: error.value }
      return null
    }
  }

  async function loadBenchmarkFamilyRatios(
    familyKey: string,
    role: BenchmarkFamilyRatioState['role'] = 'equal_weight',
    marketBenchmark = 'SPY',
    options: { timeframe?: string; adjusted?: boolean; as_of?: string; roles?: BenchmarkFamilyRatioState['role'][] } = {},
  ) {
    const normalizedFamily = familyKey.trim()
    const normalizedMarket = marketBenchmark.trim().toUpperCase()
    if (!normalizedFamily) return null
    const requestedRoles = [...new Set(options.roles?.length ? options.roles : [role])]
    const roleKey = requestedRoles.join(',')
    const cacheKey = `${normalizedFamily}:${roleKey}:${normalizedMarket}:${options.timeframe ?? 'D1'}:${options.adjusted !== false ? 'adj' : 'raw'}${options.as_of ? `:${options.as_of}` : ''}`
    const requestKey = `top-down:family-ratios:${cacheKey}`
    const generation = beginAnalysisRequest(requestKey)
    if (!documentIsVisible()) return null
    benchmarkFamilyRatioErrors.value = { ...benchmarkFamilyRatioErrors.value, [cacheKey]: null }
    try {
      const result = await api.get<BenchmarkFamilyRatiosState>(
        `/analysis/benchmark-families/${encodeURIComponent(normalizedFamily)}/ratios`,
        {
          role,
          ...(requestedRoles.length > 1 ? { roles: requestedRoles.join(',') } : {}),
          market_benchmark: normalizedMarket,
          ...(options.timeframe ? { timeframe: options.timeframe } : {}),
          ...(typeof options.adjusted === 'boolean' ? { adjusted: options.adjusted } : {}),
          ...(options.as_of ? { as_of: options.as_of } : {}),
        },
      )
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      benchmarkFamilyRatios.value = { ...benchmarkFamilyRatios.value, [cacheKey]: result }
      return result
    } catch (cause: any) {
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      const message = cause?.message ?? `Unable to calculate ${normalizedFamily} relative strength`
      benchmarkFamilyRatioErrors.value = { ...benchmarkFamilyRatioErrors.value, [cacheKey]: message }
      benchmarkFamilyRatios.value = { ...benchmarkFamilyRatios.value, [cacheKey]: null }
      return null
    }
  }

  async function loadBenchmarkFamilyTechnicals(
    familyKey: string,
    options: { timeframe?: string; adjusted?: boolean; as_of?: string } = {},
  ) {
    const normalizedFamily = familyKey.trim()
    if (!normalizedFamily) return null
    const cacheKey = `${normalizedFamily}:${options.timeframe ?? 'D1'}:${options.adjusted !== false ? 'adj' : 'raw'}:${options.as_of ?? 'latest'}`
    const requestKey = `top-down:family-technicals:${cacheKey}`
    const generation = beginAnalysisRequest(requestKey)
    if (!documentIsVisible()) return null
    benchmarkFamilyTechnicalErrors.value = { ...benchmarkFamilyTechnicalErrors.value, [cacheKey]: null }
    try {
      const result = await api.get<BenchmarkFamilyTechnicalsState>(
        `/analysis/benchmark-families/${encodeURIComponent(normalizedFamily)}/technicals`,
        {
          ...(options.timeframe ? { timeframe: options.timeframe } : {}),
          ...(typeof options.adjusted === 'boolean' ? { adjusted: options.adjusted } : {}),
          ...(options.as_of ? { as_of: options.as_of } : {}),
        },
      )
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      benchmarkFamilyTechnicals.value = { ...benchmarkFamilyTechnicals.value, [cacheKey]: result }
      return result
    } catch (cause: any) {
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      const message = cause?.message ?? `Unable to load ${normalizedFamily} family technicals`
      benchmarkFamilyTechnicalErrors.value = { ...benchmarkFamilyTechnicalErrors.value, [cacheKey]: message }
      benchmarkFamilyTechnicals.value = { ...benchmarkFamilyTechnicals.value, [cacheKey]: null }
      return null
    }
  }

  async function loadBenchmarkFamilyBreadth(
    familyKey: string,
    options: { timeframe?: string; adjusted?: boolean; as_of?: string; near_threshold?: number; new_high_lookback?: number } = {},
  ) {
    const normalizedFamily = familyKey.trim()
    if (!normalizedFamily) return null
    const cacheKey = `${normalizedFamily}:${options.timeframe ?? 'D1'}:${options.adjusted !== false ? 'adj' : 'raw'}:${options.as_of ?? 'latest'}:${options.near_threshold ?? 0.01}:${options.new_high_lookback ?? 20}`
    const requestKey = `top-down:family-breadth:${cacheKey}`
    const generation = beginAnalysisRequest(requestKey)
    if (!documentIsVisible()) return null
    benchmarkFamilyBreadthErrors.value = { ...benchmarkFamilyBreadthErrors.value, [cacheKey]: null }
    try {
      const result = await api.get<BenchmarkFamilyBreadthState>(
        `/analysis/benchmark-families/${encodeURIComponent(normalizedFamily)}/breadth`,
        {
          ...(options.timeframe ? { timeframe: options.timeframe } : {}),
          ...(typeof options.adjusted === 'boolean' ? { adjusted: options.adjusted } : {}),
          ...(options.as_of ? { as_of: options.as_of } : {}),
          ...(typeof options.near_threshold === 'number' ? { near_threshold: options.near_threshold } : {}),
          ...(typeof options.new_high_lookback === 'number' ? { new_high_lookback: options.new_high_lookback } : {}),
        },
      )
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      benchmarkFamilyBreadths.value = { ...benchmarkFamilyBreadths.value, [cacheKey]: result }
      return result
    } catch (cause: any) {
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      const message = cause?.message ?? `Unable to load ${normalizedFamily} family breadth`
      benchmarkFamilyBreadthErrors.value = { ...benchmarkFamilyBreadthErrors.value, [cacheKey]: message }
      benchmarkFamilyBreadths.value = { ...benchmarkFamilyBreadths.value, [cacheKey]: null }
      return null
    }
  }

  async function loadBenchmarkFamilyBreadthHistory(
    familyKey: string,
    options: { timeframe?: string; adjusted?: boolean; as_of?: string; limit?: number } = {},
  ) {
    const normalizedFamily = familyKey.trim()
    if (!normalizedFamily) return null
    const cacheKey = `${normalizedFamily}:${options.timeframe ?? 'D1'}:${options.adjusted !== false ? 'adj' : 'raw'}:${options.as_of ?? 'latest'}:${options.limit ?? 500}`
    const requestKey = `top-down:family-breadth-history:${cacheKey}`
    const generation = beginAnalysisRequest(requestKey)
    if (!documentIsVisible()) return null
    benchmarkFamilyBreadthHistoryErrors.value = { ...benchmarkFamilyBreadthHistoryErrors.value, [cacheKey]: null }
    try {
      const result = await api.get<BenchmarkFamilyBreadthHistoryState>(
        `/analysis/benchmark-families/${encodeURIComponent(normalizedFamily)}/breadth/history`,
        {
          limit: options.limit ?? 500,
          ...(options.timeframe ? { timeframe: options.timeframe } : {}),
          ...(typeof options.adjusted === 'boolean' ? { adjusted: options.adjusted } : {}),
          ...(options.as_of ? { as_of: options.as_of } : {}),
        },
      )
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      benchmarkFamilyBreadthHistories.value = { ...benchmarkFamilyBreadthHistories.value, [cacheKey]: result }
      return result
    } catch (cause: any) {
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      const message = cause?.message ?? `Unable to load ${normalizedFamily} family breadth history`
      benchmarkFamilyBreadthHistoryErrors.value = { ...benchmarkFamilyBreadthHistoryErrors.value, [cacheKey]: message }
      benchmarkFamilyBreadthHistories.value = { ...benchmarkFamilyBreadthHistories.value, [cacheKey]: null }
      return null
    }
  }

  async function loadBenchmarkFamilyRanking(
    familyKey: string,
    options: { timeframe?: string; adjusted?: boolean; as_of?: string; rank_period?: string } = {},
  ) {
    const normalizedFamily = familyKey.trim()
    if (!normalizedFamily) return null
    const rankPeriod = options.rank_period ?? '1M'
    const cacheKey = `${normalizedFamily}:${options.timeframe ?? 'D1'}:${options.adjusted !== false ? 'adj' : 'raw'}:${options.as_of ?? 'latest'}:${rankPeriod}`
    const requestKey = `top-down:family-ranking:${cacheKey}`
    const generation = beginAnalysisRequest(requestKey)
    if (!documentIsVisible()) return null
    benchmarkFamilyRankingErrors.value = { ...benchmarkFamilyRankingErrors.value, [cacheKey]: null }
    try {
      const result = await api.get<BenchmarkFamilyRankingState>(
        `/analysis/benchmark-families/${encodeURIComponent(normalizedFamily)}/ranking`,
        {
          rank_period: rankPeriod,
          ...(options.timeframe ? { timeframe: options.timeframe } : {}),
          ...(typeof options.adjusted === 'boolean' ? { adjusted: options.adjusted } : {}),
          ...(options.as_of ? { as_of: options.as_of } : {}),
        },
      )
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      benchmarkFamilyRankings.value = { ...benchmarkFamilyRankings.value, [cacheKey]: result }
      return result
    } catch (cause: any) {
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      const message = cause?.message ?? `Unable to rank ${normalizedFamily} family roles`
      benchmarkFamilyRankingErrors.value = { ...benchmarkFamilyRankingErrors.value, [cacheKey]: message }
      benchmarkFamilyRankings.value = { ...benchmarkFamilyRankings.value, [cacheKey]: null }
      return null
    }
  }

  async function loadBenchmarkFamilyConcentration(
    familyKey: string,
    options: { timeframe?: string; adjusted?: boolean; as_of?: string; rank_period?: string; top_n?: number } = {},
  ) {
    const normalizedFamily = familyKey.trim()
    if (!normalizedFamily) return null
    const rankPeriod = options.rank_period ?? '1M'
    const topN = options.top_n ?? 10
    const cacheKey = `${normalizedFamily}:${options.timeframe ?? 'D1'}:${options.adjusted !== false ? 'adj' : 'raw'}:${options.as_of ?? 'latest'}:${rankPeriod}:${topN}`
    const requestKey = `top-down:family-concentration:${cacheKey}`
    const generation = beginAnalysisRequest(requestKey)
    if (!documentIsVisible()) return null
    benchmarkFamilyConcentrationErrors.value = { ...benchmarkFamilyConcentrationErrors.value, [cacheKey]: null }
    try {
      const result = await api.get<BenchmarkFamilyConcentrationState>(
        `/analysis/benchmark-families/${encodeURIComponent(normalizedFamily)}/concentration`,
        {
          rank_period: rankPeriod,
          top_n: topN,
          ...(options.timeframe ? { timeframe: options.timeframe } : {}),
          ...(typeof options.adjusted === 'boolean' ? { adjusted: options.adjusted } : {}),
          ...(options.as_of ? { as_of: options.as_of } : {}),
        },
      )
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      benchmarkFamilyConcentrations.value = { ...benchmarkFamilyConcentrations.value, [cacheKey]: result }
      return result
    } catch (cause: any) {
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      const message = cause?.message ?? `Unable to load ${normalizedFamily} concentration`
      benchmarkFamilyConcentrationErrors.value = { ...benchmarkFamilyConcentrationErrors.value, [cacheKey]: message }
      benchmarkFamilyConcentrations.value = { ...benchmarkFamilyConcentrations.value, [cacheKey]: null }
      return null
    }
  }

  async function loadCrossFamilyRanking(
    options: { timeframe?: string; adjusted?: boolean; as_of?: string; rank_period?: string; families?: string[]; benchmark?: string } = {},
  ) {
    const rankPeriod = options.rank_period ?? '1M'
    const familyFilter = [...(options.families ?? [])].sort().join(',')
    const benchmark = options.benchmark?.trim().toUpperCase()
    const cacheKey = `${options.timeframe ?? 'D1'}:${options.adjusted !== false ? 'adj' : 'raw'}:${options.as_of ?? 'latest'}:${rankPeriod}:${familyFilter}:${benchmark ?? ''}`
    const requestKey = `top-down:cross-family-ranking:${cacheKey}`
    const generation = beginAnalysisRequest(requestKey)
    if (!documentIsVisible()) return null
    crossFamilyRankingErrors.value = { ...crossFamilyRankingErrors.value, [cacheKey]: null }
    try {
      const result = await api.get<CrossFamilyRankingState>('/analysis/benchmark-families/ranking', {
        rank_period: rankPeriod,
        ...(familyFilter ? { families: familyFilter } : {}),
        ...(benchmark ? { benchmark } : {}),
        ...(options.timeframe ? { timeframe: options.timeframe } : {}),
        ...(typeof options.adjusted === 'boolean' ? { adjusted: options.adjusted } : {}),
        ...(options.as_of ? { as_of: options.as_of } : {}),
      })
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      crossFamilyRankings.value = { ...crossFamilyRankings.value, [cacheKey]: result }
      return result
    } catch (cause: any) {
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      const message = cause?.message ?? 'Unable to rank benchmark families'
      crossFamilyRankingErrors.value = { ...crossFamilyRankingErrors.value, [cacheKey]: message }
      crossFamilyRankings.value = { ...crossFamilyRankings.value, [cacheKey]: null }
      return null
    }
  }

  async function loadCrossFamilyRankingHistory(
    options: { timeframe?: string; adjusted?: boolean; as_of?: string; rank_period?: string; families?: string[]; benchmark?: string; limit?: number } = {},
  ) {
    const rankPeriod = options.rank_period ?? '1M'
    const familyFilter = [...(options.families ?? [])].sort().join(',')
    const benchmark = options.benchmark?.trim().toUpperCase()
    const limit = options.limit ?? 500
    const cacheKey = `${options.timeframe ?? 'D1'}:${options.adjusted !== false ? 'adj' : 'raw'}:${options.as_of ?? 'latest'}:${rankPeriod}:${familyFilter}:${benchmark ?? ''}:${limit}`
    const requestKey = `top-down:cross-family-ranking-history:${cacheKey}`
    const generation = beginAnalysisRequest(requestKey)
    if (!documentIsVisible()) return null
    crossFamilyRankingHistoryErrors.value = { ...crossFamilyRankingHistoryErrors.value, [cacheKey]: null }
    try {
      const result = await api.get<CrossFamilyRankingHistoryState>('/analysis/benchmark-families/ranking/history', {
        rank_period: rankPeriod,
        limit,
        ...(familyFilter ? { families: familyFilter } : {}),
        ...(benchmark ? { benchmark } : {}),
        ...(options.timeframe ? { timeframe: options.timeframe } : {}),
        ...(typeof options.adjusted === 'boolean' ? { adjusted: options.adjusted } : {}),
        ...(options.as_of ? { as_of: options.as_of } : {}),
      })
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      crossFamilyRankingHistories.value = { ...crossFamilyRankingHistories.value, [cacheKey]: result }
      return result
    } catch (cause: any) {
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      const message = cause?.message ?? 'Unable to load historical benchmark-family ranking'
      crossFamilyRankingHistoryErrors.value = { ...crossFamilyRankingHistoryErrors.value, [cacheKey]: message }
      crossFamilyRankingHistories.value = { ...crossFamilyRankingHistories.value, [cacheKey]: null }
      return null
    }
  }

  async function loadBenchmarkFamilyOverview(
    familyKey: string,
    options: { timeframe?: string; adjusted?: boolean; as_of?: string } = {},
  ) {
    const normalizedFamily = familyKey.trim()
    if (!normalizedFamily) return null
    const cacheKey = `${normalizedFamily}:${options.timeframe ?? 'D1'}:${options.adjusted !== false ? 'adj' : 'raw'}:${options.as_of ?? 'latest'}`
    const requestKey = `top-down:family-overview:${cacheKey}`
    const generation = beginAnalysisRequest(requestKey)
    if (!documentIsVisible()) return null
    benchmarkFamilyOverviewErrors.value = { ...benchmarkFamilyOverviewErrors.value, [cacheKey]: null }
    try {
      const result = await api.get<BenchmarkFamilyOverviewState>(
        `/analysis/benchmark-families/${encodeURIComponent(normalizedFamily)}/overview`,
        {
          ...(options.timeframe ? { timeframe: options.timeframe } : {}),
          ...(typeof options.adjusted === 'boolean' ? { adjusted: options.adjusted } : {}),
          ...(options.as_of ? { as_of: options.as_of } : {}),
        },
      )
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      benchmarkFamilyOverviews.value = { ...benchmarkFamilyOverviews.value, [cacheKey]: result }
      return result
    } catch (cause: any) {
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      const message = cause?.message ?? `Unable to load ${normalizedFamily} family overview`
      benchmarkFamilyOverviewErrors.value = { ...benchmarkFamilyOverviewErrors.value, [cacheKey]: message }
      benchmarkFamilyOverviews.value = { ...benchmarkFamilyOverviews.value, [cacheKey]: null }
      return null
    }
  }

  async function loadBenchmarkFamilyCoverage(
    familyKey: string,
    options: { as_of?: string; limit?: number } = {},
  ) {
    const normalizedFamily = familyKey.trim()
    if (!normalizedFamily) return null
    const cacheKey = `${normalizedFamily}:${options.as_of ?? 'latest'}:${options.limit ?? 256}`
    const requestKey = `top-down:family-coverage:${cacheKey}`
    const generation = beginAnalysisRequest(requestKey)
    if (!documentIsVisible()) return null
    benchmarkFamilyCoverageErrors.value = { ...benchmarkFamilyCoverageErrors.value, [cacheKey]: null }
    try {
      const result = await api.get<BenchmarkFamilyCoverageState>(
        `/analysis/benchmark-families/${encodeURIComponent(normalizedFamily)}/coverage`,
        {
          ...(options.as_of ? { as_of: options.as_of } : {}),
          ...(options.limit ? { limit: options.limit } : {}),
        },
      )
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      benchmarkFamilyCoverages.value = { ...benchmarkFamilyCoverages.value, [cacheKey]: result }
      return result
    } catch (cause: any) {
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      const message = cause?.message ?? `Unable to load ${normalizedFamily} family coverage`
      benchmarkFamilyCoverageErrors.value = { ...benchmarkFamilyCoverageErrors.value, [cacheKey]: message }
      benchmarkFamilyCoverages.value = { ...benchmarkFamilyCoverages.value, [cacheKey]: null }
      return null
    }
  }

  async function loadBenchmarkFamilyConstituents(
    familyKey: string,
    role: BenchmarkFamilyMappingState['role'] = 'cap_weight',
    options: { timeframe?: string; adjusted?: boolean; as_of?: string; market_benchmark?: string } = {},
  ) {
    const normalizedFamily = familyKey.trim()
    const normalizedMarket = options.market_benchmark?.trim().toUpperCase()
    if (!normalizedFamily) return null
    const cacheKey = `${normalizedFamily}:${role}:${options.timeframe ?? 'D1'}:${options.adjusted !== false ? 'adj' : 'raw'}:${options.as_of ?? 'latest'}:${normalizedMarket ?? ''}`
    const requestKey = `top-down:family-constituents:${cacheKey}`
    const generation = beginAnalysisRequest(requestKey)
    if (!documentIsVisible()) return null
    benchmarkFamilyConstituentErrors.value = { ...benchmarkFamilyConstituentErrors.value, [cacheKey]: null }
    try {
      const result = await api.get<BenchmarkFamilyConstituentsState>(
        `/analysis/benchmark-families/${encodeURIComponent(normalizedFamily)}/constituents`,
        {
          role,
          ...(normalizedMarket ? { market_benchmark: normalizedMarket } : {}),
          ...(options.timeframe ? { timeframe: options.timeframe } : {}),
          ...(typeof options.adjusted === 'boolean' ? { adjusted: options.adjusted } : {}),
          ...(options.as_of ? { as_of: options.as_of } : {}),
        },
      )
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      benchmarkFamilyConstituents.value = { ...benchmarkFamilyConstituents.value, [cacheKey]: result }
      return result
    } catch (cause: any) {
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      const message = cause?.message ?? `Unable to load ${normalizedFamily} ${role} constituents`
      benchmarkFamilyConstituentErrors.value = { ...benchmarkFamilyConstituentErrors.value, [cacheKey]: message }
      benchmarkFamilyConstituents.value = { ...benchmarkFamilyConstituents.value, [cacheKey]: null }
      return null
    }
  }

  async function loadBreadth(stableKey: string, options: { timeframe?: string; adjusted?: boolean; as_of?: string; new_high_lookback?: number; near_threshold?: number } = {}) {
    const requestKey = `top-down:breadth:${stableKey}`
    const generation = beginAnalysisRequest(requestKey)
    if (!documentIsVisible()) return null
    breadthLoading.value = { ...breadthLoading.value, [stableKey]: true }
    breadthErrors.value = { ...breadthErrors.value, [stableKey]: null }
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
      const message = cause?.message ?? `Unable to calculate breadth for ${stableKey}`
      error.value = message
      breadthErrors.value = { ...breadthErrors.value, [stableKey]: message }
      return null
    } finally {
      if (isCurrentAnalysisRequest(requestKey, generation)) breadthLoading.value = { ...breadthLoading.value, [stableKey]: false }
    }
  }

  async function loadBreadthHistory(stableKey: string, options: { timeframe?: string; adjusted?: boolean; as_of?: string; new_high_lookback?: number; near_threshold?: number } = {}) {
    const requestKey = `top-down:breadth-history:${stableKey}`
    const generation = beginAnalysisRequest(requestKey)
    if (!documentIsVisible()) return null
    breadthHistoryLoading.value = { ...breadthHistoryLoading.value, [stableKey]: true }
    breadthHistoryErrors.value = { ...breadthHistoryErrors.value, [stableKey]: null }
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
      const message = cause?.message ?? `Unable to calculate historical breadth for ${stableKey}`
      error.value = message
      breadthHistoryErrors.value = { ...breadthHistoryErrors.value, [stableKey]: message }
      return null
    } finally {
      if (isCurrentAnalysisRequest(requestKey, generation)) breadthHistoryLoading.value = { ...breadthHistoryLoading.value, [stableKey]: false }
    }
  }

  async function loadGenericBreadth(
    definition: Record<string, unknown>,
    cacheKey: string,
  ) {
    const requestKey = `top-down:generic-breadth:${cacheKey}`
    const generation = beginAnalysisRequest(requestKey)
    if (!documentIsVisible()) return null
    genericBreadthLoading.value = { ...genericBreadthLoading.value, [cacheKey]: true }
    genericBreadthErrors.value = { ...genericBreadthErrors.value, [cacheKey]: null }
    try {
      const result = await api.post<GenericBreadthState>('/analysis/breadth', definition)
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      genericBreadth.value = { ...genericBreadth.value, [cacheKey]: result }
      return result
    } catch (cause: any) {
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      const message = cause?.message ?? 'Unable to evaluate the breadth condition'
      error.value = message
      genericBreadthErrors.value = { ...genericBreadthErrors.value, [cacheKey]: message }
      return null
    } finally {
      if (isCurrentAnalysisRequest(requestKey, generation)) genericBreadthLoading.value = { ...genericBreadthLoading.value, [cacheKey]: false }
    }
  }

  async function loadGenericBreadthHistory(
    definition: Record<string, unknown>,
    cacheKey: string,
  ) {
    const requestKey = `top-down:generic-breadth-history:${cacheKey}`
    const generation = beginAnalysisRequest(requestKey)
    if (!documentIsVisible()) return null
    genericBreadthHistoryLoading.value = { ...genericBreadthHistoryLoading.value, [cacheKey]: true }
    genericBreadthHistoryErrors.value = { ...genericBreadthHistoryErrors.value, [cacheKey]: null }
    try {
      const result = await api.post<GenericBreadthHistoryState>('/analysis/breadth/history', { ...definition, limit: 500 })
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      genericBreadthHistory.value = { ...genericBreadthHistory.value, [cacheKey]: result }
      return result
    } catch (cause: any) {
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      const message = cause?.message ?? 'Unable to evaluate historical breadth'
      error.value = message
      genericBreadthHistoryErrors.value = { ...genericBreadthHistoryErrors.value, [cacheKey]: message }
      return null
    } finally {
      if (isCurrentAnalysisRequest(requestKey, generation)) genericBreadthHistoryLoading.value = { ...genericBreadthHistoryLoading.value, [cacheKey]: false }
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
        if (isPersistenceLeader.value) announceMarketAnalysisRefresh(marketAnalysisRefreshedAt.value)
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
    if (!documentIsVisible()) return null
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
      // An older request for another ETF may finish after the user has already
      // selected an industry. It must not erase that visible drill-down state;
      // a new sector selection clears it synchronously at the symbol boundary.
      if (!sameETF && !selectedIndustry.value) {
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
    if (!documentIsVisible()) return null
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
    if (!documentIsVisible()) return null
    try {
      const composition = await api.get<ETFIndustryCompositionState>(`/market-groups/etf/${encodeURIComponent(normalized)}/industries`)
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      etfIndustries.value = { ...etfIndustries.value, [normalized]: composition }
      void loadIndustrySnapshot(normalized)
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

  async function loadIndustrySnapshot(symbol: string) {
    const normalized = symbol.trim().toUpperCase()
    if (!normalized) return null
    const requestKey = 'top-down:industry-snapshot'
    const generation = beginAnalysisRequest(requestKey)
    if (!documentIsVisible()) return null
    industrySnapshotErrors.value = { ...industrySnapshotErrors.value, [normalized]: null }
    try {
      const snapshot = await api.get<IndustrySnapshotState>(`/analysis/etf/${encodeURIComponent(normalized)}/industries/snapshot`, { market_benchmark: 'SPY' })
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      industrySnapshots.value = { ...industrySnapshots.value, [normalized]: snapshot }
      return snapshot
    } catch (cause: any) {
      if (!isCurrentAnalysisRequest(requestKey, generation)) return null
      const message = cause?.message ?? `Unable to rank industries for ${normalized}`
      industrySnapshots.value = { ...industrySnapshots.value, [normalized]: null }
      industrySnapshotErrors.value = { ...industrySnapshotErrors.value, [normalized]: message }
      return null
    }
  }

  async function selectIndustry(symbol: string, industry: string | null) {
    const normalized = symbol.trim().toUpperCase()
    selectedIndustry.value = industry
    if (!normalized || !industry) return null
    // Establish the selected ETF synchronously at the click boundary.  ETF
    // holdings hydration can still be in flight; leaving the previous ETF here
    // lets that late response clear the freshly selected industry before its
    // proxy request finishes.
    constituentETF.value = normalized
    const key = `${normalized}:${industry}`
    const requestKey = 'top-down:industry'
    const generation = beginAnalysisRequest(requestKey)
    selectedIndustryProxy.value = null
    if (!documentIsVisible()) return null
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
    if (!documentIsVisible()) return null
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
    if (!documentIsVisible()) return null
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

  function clearIndustrySelection() {
    selectedIndustry.value = null
    selectedIndustryProxy.value = null
  }

  function setConstituentETF(symbol: string) {
    const normalized = symbol.trim().toUpperCase()
    if (!normalized) return
    constituentETF.value = normalized
    clearIndustrySelection()
  }

  async function loadTechnical(symbol: string) {
    const normalized = symbol.trim().toUpperCase()
    if (!normalized) return null
    const requestKey = 'top-down:technical'
    const generation = beginAnalysisRequest(requestKey)
    if (!documentIsVisible()) return null
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
          // Always reconcile a revision conflict against the latest remote
          // snapshot. Layout engines and tool edits can legitimately queue a
          // newer local generation while the first PUT is in flight; abandoning
          // the conflict in that case silently loses the edit and leaves the
          // workspace permanently stale.
          if (generation !== snapshotGeneration) {
            scheduleSnapshot()
            return
          }
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
    lastLocalWorkspaceMutationAt = Date.now()
    snapshotGeneration += 1
    // Layout engines can report a burst of observational state changes while a
    // tool is mounting or resizing. Keep one bounded trailing save instead of
    // continually postponing persistence until the burst happens to stop.
    if (snapshotTimer) return
    snapshotTimer = setTimeout(() => {
      snapshotTimer = null
      void saveSnapshot()
    }, 350)
  }

  function applyActiveLayout(layout: Record<string, unknown>, visibleToolKeys: string[]) {
    const tab = activeTab.value
    if (!tab) return
    tab.layout_config = normaliseGoldenLayoutConfig(layout)
    // Golden Layout can emit a transient/incomplete component list while a
    // virtual tool is being installed, resized, or mirrored in a browser
    // pop-out. Never interpret that observational list as a destructive close:
    // explicit close actions already call closeTool(), which is the sole owner
    // of removing a persisted window. This preserves tools for pop-out
    // recovery and prevents layout churn from deleting serialized state.
    void visibleToolKeys
    scheduleSnapshot()
  }

  function componentMatches(node: Record<string, unknown>, windowKey: string | null) {
    if (!windowKey || node.type !== 'component') return false
    const state = node.componentState
    return Boolean(state && typeof state === 'object' && (state as Record<string, unknown>).instance_key === windowKey)
  }

  function findStack(node: Record<string, unknown>, windowKey: string | null): Record<string, unknown> | null {
    if (node.type === 'stack' && (windowKey == null || containsComponent(node, windowKey))) return node
    const content = node.content
    if (!Array.isArray(content)) return null
    for (const child of content) {
      if (!child || typeof child !== 'object') continue
      const found = findStack(child as Record<string, unknown>, windowKey)
      if (found) return found
    }
    return null
  }

  function containsComponent(node: Record<string, unknown>, windowKey: string): boolean {
    if (componentMatches(node, windowKey)) return true
    const content = node.content
    return Array.isArray(content) && content.some(child => Boolean(child && typeof child === 'object' && containsComponent(child as Record<string, unknown>, windowKey)))
  }

  function wrapComponentInStack(node: Record<string, unknown>, preferredWindowKey: string | null): Record<string, unknown> | null {
    const content = node.content
    if (!Array.isArray(content)) return null
    for (let index = 0; index < content.length; index += 1) {
      const child = content[index]
      if (!child || typeof child !== 'object') continue
      const childRecord = child as Record<string, unknown>
      if (componentMatches(childRecord, preferredWindowKey) || (preferredWindowKey == null && childRecord.type === 'component')) {
        const stack = { type: 'stack', content: [childRecord] }
        content[index] = stack
        return stack
      }
      const nested = wrapComponentInStack(childRecord, preferredWindowKey)
      if (nested) return nested
    }
    return null
  }

  function ensureToolStack(layout: Record<string, unknown>, activeWindowKey: string | null) {
    const root = layout.root as Record<string, unknown> | undefined
    if (!root) {
      layout.root = { type: 'stack', content: [] }
      return layout.root as Record<string, unknown>
    }
    if (root.type === 'stack') return root
    const activeStack = findStack(root, activeWindowKey)
    if (activeStack) return activeStack
    const existingStack = findStack(root, null)
    if (existingStack) return existingStack
    const wrappedActive = wrapComponentInStack(root, activeWindowKey)
    if (wrappedActive) return wrappedActive
    const wrappedFirst = wrapComponentInStack(root, null)
    if (wrappedFirst) return wrappedFirst
    if (Array.isArray(root.content)) {
      const stack = { type: 'stack', content: [] as Record<string, unknown>[] }
      root.content.push(stack)
      return stack
    }
    layout.root = { type: 'stack', content: [root] }
    return layout.root as Record<string, unknown>
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
    const stack = ensureToolStack(layout, tab.active_window_key)
    const content = Array.isArray(stack.content) ? stack.content : []
    stack.content = [...content, component]
    tab.windows = [...tab.windows, window]
    tab.layout_config = layout
    tab.active_window_key = instanceKey
    recentActiveWindowOverrides.set(tab.stable_key, { windowKey: instanceKey, at: Date.now() })
    scheduleSnapshot()
    return window
  }

  function setActiveWindow(windowKey: string) {
    const tab = activeTab.value
    if (!tab || !tab.windows.some(window => window.instance_key === windowKey) || tab.active_window_key === windowKey) return false
    tab.active_window_key = windowKey
    recentActiveWindowOverrides.set(tab.stable_key, { windowKey, at: Date.now() })
    scheduleSnapshot()
    return true
  }

  /**
   * Link membership is workspace state, not transient component state. This keeps a
   * docked tool and any browser pop-out on the same persisted link contract after a
   * reload or recovery.
   */
  function updateToolLinkGroup(windowKey: string, group: LinkGroup, displayedSymbol?: string) {
    const tab = activeTab.value
    const tool = tab?.windows.find(window => window.instance_key === windowKey)
    if (!tool || tool.link_group === group) return false
    // Grey is a true isolation boundary. Capture the tool's currently displayed
    // symbol before detaching it from a shared group so a later linked selection
    // cannot overwrite the isolated view through the global active-symbol state.
    if (group === 'grey') {
      const configuredSymbol = typeof tool.configuration.symbol === 'string' ? tool.configuration.symbol : null
      const configuredInstrumentId = typeof tool.configuration.instrument_id === 'number'
        ? tool.configuration.instrument_id
        : tool.link_group === 'blue'
          ? latestWorkstationInstrumentId.value
          : linkedSymbols.value[tool.link_group]?.instrumentId
      const isolatedSymbol = displayedSymbol
        ? (tool.link_group === 'blue' ? latestWorkstationSymbol.value : displayedSymbol.trim().toUpperCase())
        : locallyPublishedSymbols.value[tool.link_group]
          || symbolForLinkGroup(tool.link_group, configuredSymbol)
      tool.configuration = {
        ...tool.configuration,
        symbol: isolatedSymbol,
        ...(typeof configuredInstrumentId === 'number' ? { instrument_id: configuredInstrumentId } : {}),
      }
      recentLinkGroupOverrides.set(windowKey, { group, symbol: isolatedSymbol, at: Date.now() })
    } else {
      const configuredSymbol = typeof tool.configuration.symbol === 'string' ? tool.configuration.symbol : 'SPY'
      recentLinkGroupOverrides.set(windowKey, { group, symbol: configuredSymbol, at: Date.now() })
    }
    tool.link_group = group
    scheduleSnapshot()
    return true
  }

  function updateToolStyle(windowKey: string, style: Record<string, unknown>) {
    const tool = workspace.value?.tabs.flatMap(tab => tab.windows).find(window => window.instance_key === windowKey)
    if (!tool) return false
    if (Object.entries(style).every(([key, value]) => JSON.stringify(tool.style?.[key]) === JSON.stringify(value))) return false
    tool.style = { ...tool.style, ...style }
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
    const configuration: Record<string, unknown> & { symbol: string } = {
      ...tool.configuration,
      symbol: normalized,
    }
    if (typeof instrumentId === 'number') configuration.instrument_id = instrumentId
    else delete configuration.instrument_id
    tool.configuration = configuration
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
    if (snapshotTimer) {
      clearTimeout(snapshotTimer)
      snapshotTimer = null
    }
    // Invalidate a pending save generated by the pre-reset layout. Await its
    // cleanup before asking the server for the factory snapshot so an old
    // Golden Layout state cannot race the reset endpoint or announce a stale
    // revision to other browser windows.
    snapshotGeneration += 1
    if (snapshotSavePromise) await snapshotSavePromise
    try {
      const reset = await api.post<WorkspaceState>(`/workspaces/${workspace.value.id}/reset-factory`, {})
      workspace.value = reset
      persistedWorkspace = cloneSerializable(reset)
      recentLinkGroupOverrides.clear()
      recentActiveWindowOverrides.clear()
      lastLocalWorkspaceMutationAt = Date.now()
      activeTabKey.value = reset.tabs[0]?.stable_key ?? 'us-top-down'
      announceWorkspaceSnapshot(reset)
      error.value = null
      return true
    } catch (cause: any) {
      error.value = cause?.message ?? 'Unable to reset factory workspace'
      return false
    }
  }

  return {
    workspace,
    workspaces,
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
    benchmarkFamilyRatios,
    benchmarkFamilyRatioErrors,
    benchmarkFamilyTechnicals,
    benchmarkFamilyTechnicalErrors,
    benchmarkFamilyBreadths,
    benchmarkFamilyBreadthErrors,
    benchmarkFamilyBreadthHistories,
    benchmarkFamilyBreadthHistoryErrors,
    benchmarkFamilyRankings,
    benchmarkFamilyRankingErrors,
    benchmarkFamilyConcentrations,
    benchmarkFamilyConcentrationErrors,
    crossFamilyRankings,
    crossFamilyRankingErrors,
    crossFamilyRankingHistories,
    crossFamilyRankingHistoryErrors,
    benchmarkFamilyOverviews,
    benchmarkFamilyOverviewErrors,
    benchmarkFamilyCoverages,
    benchmarkFamilyCoverageErrors,
    benchmarkFamilyConstituents,
    benchmarkFamilyConstituentErrors,
    marketGroupErrors,
    groupSnapshotErrors,
    marketAnalysisRefreshing,
    marketAnalysisRefreshedAt,
    breadth,
    breadthHistory,
    breadthLoading,
    breadthHistoryLoading,
    breadthErrors,
    breadthHistoryErrors,
    genericBreadth,
    genericBreadthLoading,
    genericBreadthErrors,
    genericBreadthHistory,
    genericBreadthHistoryLoading,
    genericBreadthHistoryErrors,
    etfHoldings,
    etfConstituentSnapshots,
    etfIndustries,
    industryConstituents,
    industryProxies,
    industryProxySnapshots,
    industrySnapshots,
    industrySnapshotErrors,
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
    refreshWorkspaces,
    switchWorkspace,
    createWorkspace,
    cloneWorkspace,
    renameWorkspace,
    deleteCurrentWorkspace,
    loadMarketGroup,
    loadGroupSnapshot,
    loadBenchmarkFamilyRatios,
    loadBenchmarkFamilyTechnicals,
    loadBenchmarkFamilyBreadth,
    loadBenchmarkFamilyBreadthHistory,
    loadBenchmarkFamilyRanking,
    loadBenchmarkFamilyConcentration,
    loadCrossFamilyRanking,
    loadCrossFamilyRankingHistory,
    loadBenchmarkFamilyOverview,
    loadBenchmarkFamilyCoverage,
    loadBenchmarkFamilyConstituents,
    loadBreadth,
    loadBreadthHistory,
    loadGenericBreadth,
    loadGenericBreadthHistory,
    refreshMarketAnalysis,
    loadETFHoldings,
    loadETFConstituentSnapshot,
    loadETFIndustries,
    loadIndustrySnapshot,
    selectIndustry,
    loadIndustryProxies,
    loadIndustryProxySnapshot,
    selectIndustryProxy,
    clearIndustrySelection,
    setConstituentETF,
    loadTechnical,
    saveSnapshot,
    scheduleSnapshot,
    applyActiveLayout,
    openTool,
    setActiveWindow,
    updateToolLinkGroup,
    updateToolStyle,
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
