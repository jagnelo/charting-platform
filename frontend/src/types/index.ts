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
  | 'triangle'
  | 'text_box'
  | 'arrow'

// ── Domain models ─────────────────────────────────────────────────────────────

export interface Instrument {
  id: number
  symbol: string
  name: string
  description?: string
  currency?: string
  is_active: boolean
  equity_detail?: EquityDetail
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

export interface ChartDrawing {
  id: number
  instrument_id: number
  timeframe?: Timeframe
  pin_to_all: boolean
  drawing_type: DrawingType
  label?: string
  notes?: string
  data: Record<string, unknown>
  style: DrawingStyle
  is_visible: boolean
  is_locked: boolean
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
}

export type IndicatorType = 'sma' | 'ema' | 'vwap' | 'avwap' | 'rsi' | 'macd' | 'bb' | 'volume'

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
}

export interface Watchlist {
  id: number
  name: string
  is_default: boolean
  items: WatchlistItem[]
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
  type: 'alert_triggered' | 'pong'
  alert_id?: number
  symbol?: string
  condition?: string
  threshold?: number
  current_price?: number
  triggered_at?: string
}
