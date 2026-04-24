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
  provider_symbol?: string | null
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

export interface InstrumentListing {
  ticker: string
  currency?: string | null
  is_primary: boolean
  is_active: boolean
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

// ── Screener ──────────────────────────────────────────────────────────────────

export type PriceChangePeriod = '1D' | '1W' | '1M' | 'MTD' | 'YTD' | '1Y'

export type ScreenerConditionType =
  | 'indicator_threshold'
  | 'indicator_cross'
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

// ── WebSocket messages ────────────────────────────────────────────────────────

export interface WsMessage {
  type: 'alert_triggered' | 'screener_alert_triggered' | 'pong'
  alert_id?: number
  screener_alert_id?: number
  screener_id?: number
  screener_name?: string
  entered?: string[]
  left?: string[]
  symbol?: string
  condition?: string
  threshold?: number
  current_price?: number
  triggered_at?: string
}
