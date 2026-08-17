// ── Enums matching backend ────────────────────────────────────────────────────

export type Timeframe = 'M1'|'M5'|'M15'|'M30'|'H1'|'H2'|'H4'|'H12'|'D1'|'W1'|'MN'

export type AlertCondition =
  | 'crosses_above'
  | 'crosses_below'
  | 'touches'
  | 'percent_change_up'
  | 'percent_change_down'
  | 'within_percent'

export type AlertStatus = 'active' | 'triggered' | 'paused' | 'expired'

export type DrawingType =
  | 'trendline'
  | 'ray'
  | 'horizontal_line'
  | 'vertical_line'
  | 'fibonacci_retracement'
  | 'fibonacci_extension'
  | 'rectangle'
  | 'circle'
  | 'half_circle'
  | 'triangle'
  | 'text_box'
  | 'arrow'
  | 'freehand'

// ── Domain models ─────────────────────────────────────────────────────────────

export interface InstrumentStats {
  week52_high?: number
  week52_low?: number
  avg_volume_30d?: number
  pe_ratio?: number
  market_cap?: number
  beta?: number
  dividend_yield?: number
  computed_at?: string
  field_provenance?: Record<string, FieldProvenance>
}

export interface SyntheticConstituent {
  ticker_alias: string
  constituent_instrument_id: number
}

export interface FieldProvenance {
  source: string
  fetched_at?: string | null
  observed_at?: string | null
  selection_reason?: string | null
  quality_score?: number | null
  note?: string | null
}

export interface InstrumentIdentifier {
  identifier_type: string
  identifier_value: string
  is_primary: boolean
  is_active: boolean
  extra_data?: Record<string, unknown> | null
}

export interface Exchange {
  id: number
  mic: string
  name: string
  country_code?: string | null
  timezone?: string | null
  market_open?: string | null
  market_close?: string | null
  currency?: string | null
}

export interface InstrumentListing {
  ticker: string
  currency?: string | null
  is_primary: boolean
  is_active: boolean
  effective_at?: string | null
  known_at?: string | null
  delisted_at?: string | null
  exchange?: Exchange | null
}

export interface OptionDetail {
  underlying_instrument_id: number
  right: string
  style: string
  contract_key?: string | null
  venue_code?: string | null
  strike: number
  expiry_date: string
  contract_size?: number | null
  delta?: number | null
  gamma?: number | null
  theta?: number | null
  vega?: number | null
  rho?: number | null
  implied_vol?: number | null
  field_provenance?: Record<string, FieldProvenance>
}

export interface Instrument {
  id: number
  symbol: string
  name: string
  description?: string
  currency?: string
  is_active: boolean
  is_synthetic?: boolean
  expression?: string
  primary_identifier_type?: string | null
  primary_identifier_value?: string | null
  field_provenance?: Record<string, FieldProvenance>
  equity_detail?: EquityDetail
  option_detail?: OptionDetail
  stats?: InstrumentStats
  identifiers?: InstrumentIdentifier[]
  listings?: InstrumentListing[]
  synthetic_constituents?: SyntheticConstituent[]
}

export interface ETFHolding {
  id: number
  snapshot_id: number
  constituent_instrument_id?: number | null
  constituent_symbol?: string | null
  constituent_name?: string | null
  position: number
  reported_symbol?: string | null
  reported_name?: string | null
  cusip?: string | null
  isin?: string | null
  sedol?: string | null
  weight?: number | string | null
  shares?: number | string | null
  market_value?: number | string | null
  currency?: string | null
  country?: string | null
  exchange?: string | null
  holding_type: string
  row_type: string
  source_row_id?: string | null
  is_resolved: boolean
  resolution_confidence?: number | string | null
  resolution_note?: string | null
  extra_data?: Record<string, unknown> | null
}

export interface ETFHoldingsSnapshot {
  id: number
  etf_profile_id: number
  etf_instrument_id: number
  etf_symbol: string
  etf_name: string
  composition_date: string
  as_of_date?: string | null
  known_at?: string | null
  published_at?: string | null
  provenance: string
  source_provider: string
  source_url?: string | null
  source_identifier?: string | null
  source_quality: string
  completeness_status: string
  row_count: number
  resolved_count: number
  unresolved_count: number
  total_weight?: number | string | null
  parser_version: string
  notes?: string | null
  extra_data?: Record<string, unknown> | null
  holdings: ETFHolding[]
}

export interface ETFHoldingsPage {
  snapshot: ETFHoldingsSnapshot
  holdings: ETFHolding[]
  total: number
  limit: number
  offset: number
  has_next: boolean
}

export interface ETFHoldingsDiffRow {
  key: string
  symbol: string
  name: string
  status: 'added' | 'removed' | 'changed' | 'unchanged'
  weight_before?: number | string | null
  weight_after?: number | string | null
  weight_delta?: number | string | null
  market_value_before?: number | string | null
  market_value_after?: number | string | null
  shares_before?: number | string | null
  shares_after?: number | string | null
  holding_type_before?: string | null
  holding_type_after?: string | null
  row_type_before?: string | null
  row_type_after?: string | null
  resolved_before?: boolean | null
  resolved_after?: boolean | null
}

export interface ETFHoldingsDiffSummary {
  gross_weight_churn?: number | string | null
  total_added_weight?: number | string | null
  total_removed_weight?: number | string | null
  total_increased_weight?: number | string | null
  total_decreased_weight?: number | string | null
  largest_additions: ETFHoldingsDiffRow[]
  largest_removals: ETFHoldingsDiffRow[]
  largest_reweights: ETFHoldingsDiffRow[]
}

export interface ETFHoldingsDiff {
  left_snapshot: ETFHoldingsSnapshot
  right_snapshot: ETFHoldingsSnapshot
  total_rows: number
  added: number
  removed: number
  changed: number
  unchanged: number
  summary: ETFHoldingsDiffSummary
  rows: ETFHoldingsDiffRow[]
}

export interface ETFHoldingsTransition {
  left_snapshot: ETFHoldingsSnapshot
  right_snapshot: ETFHoldingsSnapshot
  added: number
  removed: number
  changed: number
  unchanged: number
  gross_weight_churn?: number | string | null
  total_added_weight?: number | string | null
  total_removed_weight?: number | string | null
  total_increased_weight?: number | string | null
  total_decreased_weight?: number | string | null
  largest_additions: ETFHoldingsDiffRow[]
  largest_removals: ETFHoldingsDiffRow[]
  largest_reweights: ETFHoldingsDiffRow[]
}

export interface ETFHoldingsTransitionTimeline {
  etf_symbol: string
  etf_name: string
  snapshot_count: number
  transition_count: number
  from_date?: string | null
  to_date?: string | null
  transitions: ETFHoldingsTransition[]
}

export interface ETFHoldingsOverlapConstituent {
  key: string
  symbol: string
  name: string
  weight_left?: number | string | null
  weight_right?: number | string | null
  min_weight?: number | string | null
}

export interface ETFHoldingsOverlapPair {
  left_symbol: string
  right_symbol: string
  left_snapshot: ETFHoldingsSnapshot
  right_snapshot: ETFHoldingsSnapshot
  left_count: number
  right_count: number
  shared_count: number
  left_unique_count: number
  right_unique_count: number
  jaccard_overlap: number | string
  shared_weight_left?: number | string | null
  shared_weight_right?: number | string | null
  overlap_weight_min?: number | string | null
  top_shared: ETFHoldingsOverlapConstituent[]
}

export interface ETFHoldingsOverlapSummary {
  requested_symbols: string[]
  snapshot_date?: string | null
  point_in_time: boolean
  etf_count: number
  pair_count: number
  pairs: ETFHoldingsOverlapPair[]
  missing: string[]
}

export interface ETFHoldingsOverlapMatrixCell {
  row_symbol: string
  column_symbol: string
  value: number | string
  shared_count: number
  jaccard_overlap: number | string
  overlap_weight_min?: number | string | null
}

export interface ETFHoldingsOverlapMatrixRow {
  symbol: string
  name: string
  snapshot: ETFHoldingsSnapshot
  average_overlap: number | string
  max_overlap: number | string
  min_overlap: number | string
  closest_peer?: string | null
  most_distinct_peer?: string | null
  cells: ETFHoldingsOverlapMatrixCell[]
}

export interface ETFHoldingsOverlapMatrix {
  requested_symbols: string[]
  snapshot_date?: string | null
  point_in_time: boolean
  metric: 'jaccard' | 'shared_count' | 'overlap_weight_min'
  etf_count: number
  symbols: string[]
  rows: ETFHoldingsOverlapMatrixRow[]
  highest_overlap_pairs: ETFHoldingsOverlapPair[]
  lowest_overlap_pairs: ETFHoldingsOverlapPair[]
  missing: string[]
}

export interface ETFHoldingsDate {
  snapshot_id: number
  composition_date: string
  as_of_date?: string | null
  known_at?: string | null
  provenance: string
  source_provider: string
  row_count: number
  resolved_count: number
  unresolved_count: number
  source_quality: string
}

export interface ETFHoldingsWeightEvolutionPoint {
  snapshot_id: number
  composition_date: string
  weight?: number | string | null
  shares?: number | string | null
  market_value?: number | string | null
}

export interface ETFHoldingsWeightEvolutionSeries {
  key: string
  symbol: string
  name: string
  first_weight?: number | string | null
  last_weight?: number | string | null
  weight_delta?: number | string | null
  min_weight?: number | string | null
  max_weight?: number | string | null
  observation_count: number
  points: ETFHoldingsWeightEvolutionPoint[]
}

export interface ETFHoldingsWeightEvolution {
  etf_symbol: string
  etf_name: string
  snapshot_count: number
  from_date?: string | null
  to_date?: string | null
  series: ETFHoldingsWeightEvolutionSeries[]
}

export interface ETFProfile {
  id: number
  instrument_id: number
  symbol: string
  name: string
  issuer?: string | null
  sponsor?: string | null
  fund_family?: string | null
  index_name?: string | null
  product_url?: string | null
  sec_cik?: string | null
  sec_series_id?: string | null
  sec_class_id?: string | null
  adapter_key?: string | null
  adapter_confidence?: number | string | null
  adapter_status: string
  provider_aliases?: Record<string, unknown> | null
  legal_metadata?: Record<string, unknown> | null
  latest_composition_date?: string | null
  latest_snapshot_id?: number | null
  resolved_count: number
  unresolved_count: number
}

export interface EquityDetail {
  sector?: string
  industry?: string
  country?: string
  ipo_date?: string
  market_cap_tier?: string
  employees?: number
  website?: string
  logo_url?: string
  field_provenance?: Record<string, FieldProvenance>
}

export interface OHLCVBar {
  ts: string
  open: number
  high: number
  low: number
  close: number
  volume?: number
  vwap?: number
  is_adjusted: boolean
}

export interface ChartComparisonSeries {
  symbol: string
  label: string
  color: string
  values: Array<number | null>
  percentChange?: number | null
}

/** A typed, uPlot-renderable series produced by a validated Python plot asset. */
export interface ChartPythonSeries {
  codeVersionId: number
  label: string
  color: string
  timestamps: string[]
  values: Array<number | null>
  /** Numeric series can also originate from retained EasyScan history. */
  source?: 'python' | 'scan'
}

export type RadarSetupType =
  | 'approaching_support'
  | 'approaching_resistance'
  | 'breakout'
  | 'breakout_retest'
  | 'breakdown'
  | 'breakdown_retest'
  | 'fakeout'
  | 'fakedown'
  | 'failed_reclaim'
  | 'failed_breakdown_recovery'
  | 'compression_support'
  | 'compression_resistance'
  | 'reclaim'
  | 'rejection'

export type RadarState =
  | 'developing'
  | 'confirmed'
  | 'resolved'
  | 'invalidated'
  | 'stale'

export type RadarOutcomeStatus =
  | 'open'
  | 'target_hit'
  | 'invalidated'
  | 'stale'

export interface RadarIndicatorVisual {
  type: IndicatorType
  params: Record<string, unknown>
  style: { color: string; lineWidth: number }
  pane?: 'main' | 'separate'
  role?: string | null
  label?: string | null
  source_tag?: string | null
}

export interface RadarDrawingVisual {
  drawing_type: DrawingType
  indicator_key?: string | null
  label?: string | null
  notes?: string | null
  data: Record<string, unknown>
  style: DrawingStyle
  is_visible: boolean
  is_locked: boolean
  source_role?: string | null
  source_tag?: string | null
}

export interface RadarEvidence {
  overlays: Array<Record<string, unknown>>
  indicator_visuals: RadarIndicatorVisual[]
  drawing_visuals: RadarDrawingVisual[]
  metrics: Record<string, unknown>
  structures: Array<Record<string, unknown>>
}

export interface RadarRun {
  id: number
  timeframe: Timeframe
  universe_type: string
  universe_filter?: Record<string, unknown> | null
  status: 'running' | 'completed' | 'failed'
  started_at: string
  completed_at?: string | null
  evaluated_count: number
  detection_count: number
  error_summary?: string | null
  created_at: string
  updated_at: string
}

export interface BasketMember {
  id: number
  instrument_id: number
  symbol?: string | null
  name?: string | null
  source_holding_id?: number | null
  position: number
  weight?: string | number | null
  label?: string | null
  notes?: string | null
  metadata?: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export interface Basket {
  id: number
  user_id?: number | null
  name: string
  description?: string | null
  source_type: string
  weighting_scheme: string
  rebalance_frequency?: string | null
  classification_mode?: string | null
  sector?: string | null
  industry?: string | null
  source_etf_profile_id?: number | null
  source_snapshot_id?: number | null
  composition_date?: string | null
  snapshot_count?: number
  latest_snapshot_date?: string | null
  is_system_managed: boolean
  is_read_only: boolean
  metadata?: Record<string, unknown> | null
  members: BasketMember[]
  created_at: string
  updated_at: string
}

export interface RadarSetupThread {
  id: number
  instrument_id: number
  timeframe: Timeframe
  context_role?: string | null
  reference_price: number
  current_setup_type: RadarSetupType
  current_state: RadarState
  state_changed_at: string
  started_at: string
  last_seen_at: string
  detection_count: number
}

export interface RadarThreadEvent {
  id: number
  setup_type: RadarSetupType
  score: number
  observed_at: string
  signal_at: string
  context_at?: string | null
  state: RadarState
  state_reason?: string | null
  thread_event_index?: number | null
  key_level_price?: number | null
  entry_price?: number | null
  invalidation_price?: number | null
  target_price?: number | null
  outcome_status: RadarOutcomeStatus
  outcome_last_evaluated_at?: string | null
  bars_since_signal: number
  max_favorable_excursion_pct?: number | null
  max_adverse_excursion_pct?: number | null
  target_hit_at?: string | null
  invalidated_at?: string | null
  summary: string
  invalidation_hint?: string | null
  created_at: string
  updated_at: string
}

export interface RadarOutcomeSummary {
  timeframe: Timeframe
  setup_type: RadarSetupType
  total: number
  open_count: number
  target_hit_count: number
  invalidated_count: number
  stale_count: number
  target_hit_rate: number
  invalidated_rate: number
  stale_rate: number
  avg_mfe_pct?: number | null
  avg_mae_pct?: number | null
}

export interface RadarDetection {
  id: number
  run_id: number
  instrument_id: number
  instrument_symbol: string
  instrument_name: string
  timeframe: Timeframe
  setup_type: RadarSetupType
  score: number
  observed_at: string
  signal_at?: string
  context_at?: string | null
  state: RadarState
  state_reason?: string | null
  fresh_until: string
  thread_id?: number | null
  thread_event_index?: number | null
  key_level_price?: number | null
  entry_price?: number | null
  invalidation_price?: number | null
  target_price?: number | null
  outcome_status: RadarOutcomeStatus
  outcome_last_evaluated_at?: string | null
  bars_since_signal: number
  max_favorable_excursion_pct?: number | null
  max_adverse_excursion_pct?: number | null
  target_hit_at?: string | null
  invalidated_at?: string | null
  summary: string
  invalidation_hint?: string | null
  score_factors: Record<string, number>
  created_at: string
  updated_at: string
  thread?: RadarSetupThread | null
  thread_history?: RadarThreadEvent[]
  evidence?: RadarEvidence
}

export interface RadarWatchlistAction {
  watchlist_id: number
  watchlist_name: string
  item_id: number
}

export interface ChartDrawing {
  id: number
  instrument_id: number
  timeframe?: Timeframe
  pin_to_all: boolean
  indicator_key?: string | null
  drawing_type: DrawingType
  label?: string
  notes?: string
  data: Record<string, unknown>
  style: DrawingStyle
  is_visible: boolean
  is_locked: boolean
  position: number
  created_at: string
  updated_at: string
}

export interface DrawingStyle {
  color?: string
  lineWidth?: number
  opacity?: number
  filled?: boolean
  fontSize?: number
  fontFamily?: string
  dashPattern?: number[]
}

export interface PriceAlert {
  id: number
  instrument_id: number
  instrument_currency?: string | null
  instrument_symbol: string
  condition: AlertCondition
  threshold_price: number
  reference_price?: number
  status: AlertStatus
  repeat: boolean
  show_projection: boolean
  notes?: string
  triggered_at?: string
  trigger_count: number
  last_known_price?: number
  created_at: string
  updated_at: string
}

export interface IndicatorAlert {
  id: number
  instrument_id: number
  instrument_currency?: string | null
  instrument_symbol: string
  timeframe: string
  indicator_a_type: string
  indicator_a_params: Record<string, unknown>
  condition: string
  threshold_value: number | null
  indicator_b_type: string | null
  indicator_b_params: Record<string, unknown> | null
  status: AlertStatus
  repeat: boolean
  notes: string | null
  triggered_at: string | null
  trigger_count: number
  last_value_a: number | null
  last_value_b: number | null
  created_at: string
  updated_at: string
}

export interface IndicatorConfig {
  type: IndicatorType
  params: Record<string, unknown>
  style: { color: string; lineWidth: number }
  pane?: 'main' | 'separate'
  /** Hidden plots remain configured and template-serializable but are not rendered. */
  hidden?: boolean
  /** Timeframes this indicator is active on. null/undefined = all timeframes. */
  lockedTimeframes?: Timeframe[] | null
  /** Show a dashed horizontal projection line to the Y axis. */
  showYProjection?: boolean
}

export type IndicatorType =
  // Moving averages
  | 'sma' | 'ema' | 'wma' | 'hma' | 'dema' | 'tema'
  // Bands / channels
  | 'bb' | 'keltner' | 'donchian'
  // Volume / price-weighted
  | 'vwap' | 'avwap' | 'volume' | 'volume_ratio' | 'obv' | 'mfi' | 'cmf'
  // Oscillators / momentum
  | 'rsi' | 'macd' | 'stoch' | 'cci' | 'williams_r' | 'roc' | 'momentum' | 'trix' | 'ppo'
  // Trend / direction
  | 'adx' | 'aroon' | 'psar' | 'ichimoku'
  // Volatility
  | 'atr' | 'stddev'
  // Price levels
  | 'pivot_points'

export type ChartBarType =
  | 'candles'
  | 'line'
  | 'ohlc'
  | 'heikin_ashi'
  | 'area'
  | 'baseline'
  | 'renko'
  | 'kagi'
  | 'point_figure'

export const CHART_BAR_TYPES: { value: ChartBarType; label: string }[] = [
  { value: 'candles',      label: 'Candles' },
  { value: 'line',         label: 'Line' },
  { value: 'ohlc',         label: 'OHLC Bars' },
  { value: 'heikin_ashi',  label: 'Heikin-Ashi' },
  { value: 'area',         label: 'Area' },
  { value: 'baseline',     label: 'Baseline' },
  { value: 'renko',        label: 'Renko' },
  { value: 'kagi',         label: 'Kagi' },
  { value: 'point_figure', label: 'Point & Figure' },
]

export interface IndicatorPreset {
  id: number
  name: string
  description?: string
  indicators: IndicatorConfig[]
  is_default: boolean
  created_at: string
  updated_at: string
}

export interface WatchlistItem {
  id: number
  instrument_id: number
  symbol?: string
  name?: string
  position: number
  flagged?: boolean
  left_screener_at?: string | null
}

export interface Watchlist {
  id: number
  name: string
  is_default: boolean
  is_managed: boolean
  is_locked: boolean
  screener_id?: number | null
  screener_name?: string | null
  last_screener_run_at?: string | null
  position: number
  items: WatchlistItem[]
}

export type WatchlistSourceKind =
  | 'personal'
  | 'screener_managed'
  | 'index_membership'
  | 'market_group'
  | 'etf_holdings'
  | 'combo'
  | 'explicit'

export interface WatchlistSource {
  source_id: string
  source_kind: WatchlistSourceKind
  name: string
  description?: string | null
  locked: boolean
  can_follow: boolean
  can_clone: boolean
  can_edit_membership: boolean
  watchlist_id?: number | null
  stable_key?: string | null
  instrument_id?: number | null
  symbol?: string | null
  membership_version?: string | null
  member_count?: number | null
  source?: string | null
  provenance: Record<string, unknown>
  effective_at?: string | null
  known_at?: string | null
  composition_date?: string | null
}

export interface WatchlistSourceMember {
  instrument_id: number
  position: number
  weight?: number | null
  relationship_type: string
  source?: string | null
  effective_at?: string | null
  known_at?: string | null
}

export interface WatchlistSourceResolved {
  source: WatchlistSource
  members: WatchlistSourceMember[]
  exclusions: Array<Record<string, unknown>>
}

export type MarketMapGroupBy = 'none' | 'sector' | 'industry' | 'sector_industry'
export type MarketMapAreaMetric = 'equal' | 'market_cap' | 'weight' | 'volume'
export type MarketMapColorMetric = 'return' | 'relative_return' | 'rsi_14' | 'relative_volume' | 'distance_52w_high' | 'distance_52w_low'

export interface MarketMapRequest {
  source_id: string
  group_by?: MarketMapGroupBy
  period?: string
  start?: string | null
  end?: string | null
  timeframe?: Timeframe
  adjusted?: boolean
  area_metric?: MarketMapAreaMetric
  color_metric?: MarketMapColorMetric
  reference_symbol?: string | null
  as_of?: string | null
  limit?: number
}

export interface MarketMapWarning {
  code: string
  message: string
  instrument_id?: number | null
  node_id?: string | null
}

export interface MarketMapCell {
  instrument_id: number
  symbol: string
  name: string
  sector?: string | null
  industry?: string | null
  group_path: string[]
  area_value?: number | null
  color_value?: number | null
  return_value?: number | null
  observation_time?: string | null
  coverage: number
  warnings: MarketMapWarning[]
}

export interface MarketMapNode {
  node_id: string
  parent_id?: string | null
  level: string
  label: string
  group_path: string[]
  member_count: number
  covered_count: number
  area_total?: number | null
  color_value?: number | null
  coverage: number
  aggregation_method: string
  warnings: MarketMapWarning[]
}

export interface MarketMap {
  source: WatchlistSource
  group_by: MarketMapGroupBy
  period: string
  period_start?: string | null
  period_end?: string | null
  timeframe: Timeframe
  adjustment: string
  area_metric: MarketMapAreaMetric
  color_metric: MarketMapColorMetric
  reference_symbol?: string | null
  membership_version?: string | null
  calculation_version: string
  cache_key: string
  cache_hit?: boolean
  cached_at?: string | null
  freshness: string
  freshness_detail: Record<string, number>
  requested_count: number
  evaluated_count: number
  coverage: number
  nodes: MarketMapNode[]
  cells: MarketMapCell[]
  exclusions: MarketMapWarning[]
  warnings: MarketMapWarning[]
}

export interface MarketMapSnapshotSummary {
  id: number
  name: string
  source_id: string
  membership_version?: string | null
  cache_key: string
  snapshot_hash: string
  created_at: string
  updated_at: string
}

export interface MarketMapSnapshot extends MarketMapSnapshotSummary {
  map: MarketMap
}

export type ScreenerAlertTriggerType = 'entered' | 'left' | 'both'
export type ScreenerAlertStatus = 'active' | 'triggered' | 'paused' | 'disabled'

export interface ScreenerAlert {
  id: number
  screener_id: number
  screener_name: string
  trigger_type: ScreenerAlertTriggerType
  status: ScreenerAlertStatus
  repeat: boolean
  notes?: string | null
  triggered_at?: string | null
  last_checked_run_id?: number | null
  created_at: string
  updated_at: string
}

export interface InstrumentMembershipWatchlist {
  id: number
  name: string
  is_managed: boolean
}

export interface InstrumentMembershipScreener {
  id: number
  name: string
  last_run_at: string | null
  in_current_results: boolean
}

export interface InstrumentMembership {
  watchlists: InstrumentMembershipWatchlist[]
  screeners: InstrumentMembershipScreener[]
}

export interface ProviderPolicyStatus {
  provider: string
  capability: string
  supported_capabilities: string[]
  is_enabled: boolean
  is_pinned: boolean
  auto_weight_enabled: boolean
  base_priority: number
  effective_score: number
  learned_weight: number
  max_concurrency: number
  tokens_per_minute: number
  burst_capacity: number
  cooldown_seconds: number
  freshness_seconds: number
  failure_streak: number
  last_success_at?: string | null
  last_failure_at?: string | null
  circuit_open_until?: string | null
  ewma_latency_ms: number
  ewma_success_rate: number
  ewma_completeness: number
  ewma_freshness: number
  ewma_consistency: number
  last_error_type?: string | null
  last_error_message?: string | null
}

export interface ProviderHealth {
  provider: string
  capability: string
  failure_streak: number
  last_success_at?: string | null
  last_failure_at?: string | null
  circuit_open_until?: string | null
  ewma_latency_ms: number
  ewma_success_rate: number
  ewma_completeness: number
  ewma_freshness: number
  ewma_consistency: number
  last_error_type?: string | null
  last_error_message?: string | null
}

export interface ProviderUsageBucket {
  bucket_start: string
  requests: number
  units: number
  failures: number
}

export interface ProviderUsageOperation {
  operation_family: string
  requests: number
  units: number
  failures: number
  successes: number
}

export interface ProviderUsageCapabilityRow {
  capability: string
  requests: number
  units: number
  failures: number
}

export interface ProviderUsageErrorRow {
  error_type: string
  count: number
}

export interface ProviderUsageSummary {
  provider: string
  base_url?: string | null
  description?: string | null
  usage_mode: string
  usage_unit_label: string
  limit_kind: string
  quota_limit?: number | null
  estimated_quota_limit?: number | null
  quota_window_seconds?: number | null
  current_window_started_at?: string | null
  current_window_ends_at?: string | null
  current_window_requests?: number | null
  current_window_units?: number | null
  current_window_utilization_pct?: number | null
  retained_requests: number
  retained_units: number
  requests_24h: number
  units_24h: number
  requests_7d: number
  units_7d: number
  success_rate_24h: number
  failure_rate_24h: number
  timeout_rate_24h: number
  avg_latency_ms_24h?: number | null
  p95_latency_ms_24h?: number | null
  last_request_at?: string | null
  last_success_at?: string | null
  last_failure_at?: string | null
  top_operations: ProviderUsageOperation[]
  capability_breakdown: ProviderUsageCapabilityRow[]
  error_breakdown: ProviderUsageErrorRow[]
  hourly_buckets: ProviderUsageBucket[]
  daily_buckets: ProviderUsageBucket[]
}

export interface OptionExpirationResponse {
  symbol: string
  expirations: string[]
}

export interface OptionChainRow {
  instrument_id: number
  symbol: string
  name: string
  currency?: string | null
  right: string
  style: string
  strike: number
  expiry_date: string
  contract_size?: number | null
  contract_key?: string | null
  bid?: number | null
  ask?: number | null
  mark?: number | null
  last?: number | null
  volume?: number | null
  open_interest?: number | null
  implied_vol?: number | null
  delta?: number | null
  gamma?: number | null
  theta?: number | null
  vega?: number | null
  rho?: number | null
  observed_at?: string | null
  provider_symbol?: string | null
  provenance?: Record<string, FieldProvenance>
}

export interface OptionChainSnapshotSummary {
  id: number
  observed_at: string
  fetched_at: string
  provider?: string | null
  contract_count: number
}

export interface OptionChainResponse {
  symbol: string
  expiration?: string | null
  available_expirations: string[]
  snapshot?: OptionChainSnapshotSummary | null
  rows: OptionChainRow[]
}

export interface OptionContractSummary {
  id: number
  symbol: string
  name: string
  currency?: string | null
  contract_key?: string | null
  right: string
  style: string
  strike: number
  expiry_date: string
  contract_size?: number | null
  underlying_instrument_id: number
  provenance?: Record<string, FieldProvenance>
}

export interface OptionQuotePoint {
  observed_at: string
  bid?: number | null
  ask?: number | null
  mark?: number | null
  last?: number | null
  volume?: number | null
  open_interest?: number | null
  implied_vol?: number | null
  delta?: number | null
  gamma?: number | null
  theta?: number | null
  vega?: number | null
  rho?: number | null
  provider_symbol?: string | null
}

// ── Options Exposure ─────────────────────────────────────────────────────────

export interface ExpiryBreakdown {
  call_gex: number
  put_gex: number
  net_gex: number
  call_dex: number
  put_dex: number
  net_dex: number
  call_oi: number
  put_oi: number
}

export interface ExposureLadderRow {
  strike: number
  call_gex: number
  put_gex: number
  net_gex: number
  call_dex: number
  put_dex: number
  net_dex: number
  call_oi: number
  put_oi: number
  call_iv: number | null
  put_iv: number | null
  call_mark: number | null
  put_mark: number | null
  by_expiry: Record<string, ExpiryBreakdown>
}

export interface ExposureKeyLevels {
  call_wall: number | null
  put_wall: number | null
  gamma_flip: number | null
  max_pain: number | null
}

export interface OptionsExposureResponse {
  symbol: string
  spot: number | null
  expirations: string[]
  active_expirations: string[]
  computed_at: string
  ladder: ExposureLadderRow[]
  key_levels: ExposureKeyLevels
  pcr_oi: number | null
  pcr_volume: number | null
  implied_move_pct: number | null
  total_gex: number
  total_net_dex: number
  greeks_estimated?: boolean
}

export interface ExpirationSummary {
  expiration: string
  dte: number
  total_call_oi: number
  total_put_oi: number
  pcr_oi: number | null
  total_gex: number
}

// ── Dashboards ───────────────────────────────────────────────────────────────

export type DashboardWidgetType =
  | 'notes'
  | 'checklist'
  | 'quote'
  | 'simple_chart'
  | 'watchlist'
  | 'alerts'
  | 'screener'
  | 'radar'
  | 'instrument_details'
  | 'advanced_chart'
  | 'comparison_chart'
  | 'ratio_chart'
  | 'economic_calendar'
  | 'options_chain'
  | 'gex_ladder'
  | 'heat_map'
  | 'seasonality'

export interface DashboardWidgetLayout {
  x: number
  y: number
  w: number
  h: number
}

export interface DashboardWidget {
  id: number
  tab_id: number
  widget_type: DashboardWidgetType | string
  title?: string | null
  layout: DashboardWidgetLayout
  config: Record<string, any>
  style: Record<string, any>
  position: number
  created_at: string
  updated_at: string
}

export interface DashboardTab {
  id: number
  dashboard_id: number
  name: string
  position: number
  layout_settings: Record<string, any>
  widgets: DashboardWidget[]
  created_at: string
  updated_at: string
}

export interface Dashboard {
  id: number
  user_id: number
  name: string
  is_default: boolean
  position: number
  settings: Record<string, any>
  tabs: DashboardTab[]
  created_at: string
  updated_at: string
}

// ── Strategy Lab ──────────────────────────────────────────────────────────────

export type StrategySourceType = 'custom' | 'radar'
export type StrategyDefinitionType = 'rules' | 'dsl' | 'python' | 'signal_source'
export type StrategyTestMode = 'backtest' | 'walk_forward' | 'paper_forward'
export type StrategyRunStatus = 'queued' | 'running' | 'completed' | 'failed' | 'canceled'

export interface StrategyCoverageInstrument {
  instrument_id: number
  symbol: string
  available_from?: string | null
  available_to?: string | null
  requested_first_bar_at?: string | null
  requested_last_bar_at?: string | null
  total_bars: number
  requested_bars: number
  requested_status: string
  note?: string | null
  ipo_date?: string | null
}

export interface StrategyCoverageUniverse {
  preview_mode: string
  preview_note?: string | null
  instrument_count: number
  instruments_with_data: number
  instruments_with_requested_data: number
  instruments_with_full_requested_coverage: number
  instruments_with_partial_requested_coverage: number
  instruments_without_requested_coverage: number
  total_bars: number
  requested_first_bar_at?: string | null
  requested_last_bar_at?: string | null
  any_coverage_from?: string | null
  any_coverage_to?: string | null
  collective_coverage_from?: string | null
  collective_coverage_to?: string | null
  requested_fits_collective_range?: boolean | null
  resolved_symbols: string[]
  limiting_instruments: StrategyCoverageInstrument[]
  instruments: StrategyCoverageInstrument[]
  simulatable_instrument_count?: number
  simulatable_symbols?: string[]
}

export interface StrategyCoverageBenchmark {
  symbol?: string | null
  preview_note?: string | null
  requested_status: string
  available_from?: string | null
  available_to?: string | null
  requested_first_bar_at?: string | null
  requested_last_bar_at?: string | null
  total_bars: number
  requested_bars: number
  requested_fits_range?: boolean | null
}

export interface StrategyCoveragePreview {
  timeframe: string
  requested_date_from?: string | null
  requested_date_to?: string | null
  universe: StrategyCoverageUniverse
  benchmark: StrategyCoverageBenchmark
  warnings: string[]
}

export interface StrategyVersion {
  id: number
  strategy_id: number
  version_number: number
  definition_snapshot: Record<string, any>
  parameter_schema: Record<string, any>
  default_parameters: Record<string, any>
  universe_config: Record<string, any>
  benchmark_config: Record<string, any>
  execution_model: Record<string, any>
  notes?: string | null
  is_current: boolean
  created_at: string
  updated_at: string
}

export interface StrategyRun {
  id: number
  strategy_id: number
  strategy_version_id: number
  requested_by_user_id: number
  run_batch_id?: number | null
  test_mode: StrategyTestMode | string
  status: StrategyRunStatus | string
  timeframe?: string | null
  started_at?: string | null
  completed_at?: string | null
  date_from?: string | null
  date_to?: string | null
  parameter_values: Record<string, any>
  parameter_diff?: Record<string, any>
  universe_config: Record<string, any>
  benchmark_config: Record<string, any>
  execution_assumptions: Record<string, any>
  engine_run_ref?: string | null
  result_summary: Record<string, any>
  artifact_manifest: Record<string, any>
  warning_log: any[]
  error_log?: string | null
  created_at: string
  updated_at: string
}

export interface StrategyRunBatch {
  id: number
  strategy_id: number
  strategy_version_id: number
  requested_by_user_id: number
  label?: string | null
  test_mode: StrategyTestMode | string
  status: StrategyRunStatus | string
  parameter_dimensions: any[]
  parameter_grid: Array<Record<string, any>>
  summary: Record<string, any>
  created_at: string
  updated_at: string
}

export interface StrategyDefinition {
  id: number
  user_id: number
  name: string
  description?: string | null
  source_type: StrategySourceType | string
  definition_type: StrategyDefinitionType | string
  is_active: boolean
  tags: string[]
  metadata: Record<string, any>
  versions: StrategyVersion[]
  run_batches?: StrategyRunBatch[]
  runs: StrategyRun[]
  created_at: string
  updated_at: string
}

// ── Screener ──────────────────────────────────────────────────────────────────

export type PriceChangePeriod = '1D' | '1W' | '1M' | '3M' | '6M' | 'MTD' | 'QTD' | 'YTD' | '1Y'

export type ScreenerConditionType =
  | 'indicator_threshold'
  | 'indicator_cross'
  | 'price_indicator'
  | 'price_threshold'
  | 'price_change'
  | 'price_change_period'
  | 'fundamental_filter'
  | 'and'
  | 'or'
  | 'not'

export interface ScreenerConditionLeaf {
  type: Exclude<ScreenerConditionType, 'and' | 'or' | 'not'>
  indicator?: string
  indicator_b?: string
  params?: Record<string, unknown>
  params_b?: Record<string, unknown>
  timeframe?: string
  operator?: string
  value?: number
  field?: string
  period?: PriceChangePeriod
}

export interface ScreenerConditionGroup {
  type: 'and' | 'or' | 'not'
  conditions?: ScreenerConditionNode[]
  condition?: ScreenerConditionNode
}

export type ScreenerConditionNode = ScreenerConditionLeaf | ScreenerConditionGroup

export interface ScreenerFilter {
  id?: number
  name: string
  universe: 'all' | 'watchlist'
  watchlist_id?: number
  conditions: ScreenerConditionGroup
}

/** One row returned by POST /screener/run */
export interface ScreenerResultRow {
  instrument_id: number
  symbol: string
  result_data: Record<string, unknown>
}

/** Item shape from GET /instruments/browse */
export interface BrowseResult {
  id: number
  symbol: string
  name: string
  instrument_type?: string
  exchange?: string
  currency?: string
  sector?: string
  industry?: string
  country?: string
  market_cap_tier?: string
}

// ── Chart state ───────────────────────────────────────────────────────────────

export interface ChartState {
  symbol: string
  timeframe: Timeframe
  bars: OHLCVBar[]
  drawings: ChartDrawing[]
  indicators: IndicatorConfig[]
  activeDrawingTool: DrawingType | null
  selectedDrawingId: number | null
}

// ── Alert firing history ──────────────────────────────────────────────────────

export interface AlertFiringEvent {
  id: number
  instrument_id: number | null
  instrument_symbol: string | null
  alert_type: 'price' | 'indicator' | 'screener'
  alert_id: number
  fired_at: string
  trigger_value: number | null
  condition_snapshot: Record<string, unknown>
  is_viewed: boolean
  created_at: string
}

// ── WebSocket messages ────────────────────────────────────────────────────────

export interface WsMessage {
  type: 'alert_triggered' | 'screener_alert_triggered' | 'pong'
  alert_id?: number
  alert_kind?: 'price' | 'indicator'
  firing_event_id?: number
  screener_alert_id?: number
  screener_id?: number
  screener_name?: string
  entered?: string[]
  left?: string[]
  symbol?: string
  condition?: string
  threshold?: number
  current_price?: number
  value_a?: number
  value_b?: number
  triggered_at?: string
}
