import type { IndicatorConfig, IndicatorType } from '@/types'

export interface IndicatorParamDef {
  key: string
  label: string
  input?: 'number' | 'datetime' | 'select'
  options?: Array<{ value: string; label: string }>
}

export interface IndicatorCatalogItem {
  type: IndicatorType
  label: string
  pickerLabel: string
  defaultConfig: IndicatorConfig
  params: IndicatorParamDef[]
}

const nowMinus30d = () => Math.floor(Date.now() / 1000) - 86400 * 30

export const INDICATOR_CATALOG: IndicatorCatalogItem[] = [
  {
    type: 'sma',
    label: 'SMA',
    pickerLabel: 'SMA - Simple Moving Average',
    defaultConfig: { type: 'sma', params: { period: 20 }, style: { color: '#ffb74d', lineWidth: 1.5 }, pane: 'main' },
    params: [{ key: 'period', label: 'Period' }],
  },
  {
    type: 'ema',
    label: 'EMA',
    pickerLabel: 'EMA - Exponential Moving Average',
    defaultConfig: { type: 'ema', params: { period: 50 }, style: { color: '#64b5f6', lineWidth: 1.5 }, pane: 'main' },
    params: [{ key: 'period', label: 'Period' }],
  },
  {
    type: 'wma',
    label: 'WMA',
    pickerLabel: 'WMA - Weighted Moving Average',
    defaultConfig: { type: 'wma', params: { period: 20 }, style: { color: '#a5d6a7', lineWidth: 1.5 }, pane: 'main' },
    params: [{ key: 'period', label: 'Period' }],
  },
  {
    type: 'hma',
    label: 'HMA',
    pickerLabel: 'HMA - Hull Moving Average',
    defaultConfig: { type: 'hma', params: { period: 20 }, style: { color: '#a5d6a7', lineWidth: 1.5 }, pane: 'main' },
    params: [{ key: 'period', label: 'Period' }],
  },
  {
    type: 'dema',
    label: 'DEMA',
    pickerLabel: 'DEMA - Double EMA',
    defaultConfig: { type: 'dema', params: { period: 20 }, style: { color: '#ffb74d', lineWidth: 1.5 }, pane: 'main' },
    params: [{ key: 'period', label: 'Period' }],
  },
  {
    type: 'tema',
    label: 'TEMA',
    pickerLabel: 'TEMA - Triple EMA',
    defaultConfig: { type: 'tema', params: { period: 20 }, style: { color: '#f48fb1', lineWidth: 1.5 }, pane: 'main' },
    params: [{ key: 'period', label: 'Period' }],
  },
  {
    type: 'vwap',
    label: 'VWAP',
    pickerLabel: 'VWAP - Volume Weighted Avg Price',
    defaultConfig: { type: 'vwap', params: {}, style: { color: '#ce93d8', lineWidth: 2 }, pane: 'main' },
    params: [],
  },
  {
    type: 'avwap',
    label: 'AVWAP',
    pickerLabel: 'AVWAP - Anchored VWAP',
    defaultConfig: { type: 'avwap', params: { anchor_timestamp: nowMinus30d() }, style: { color: '#80cbc4', lineWidth: 2 }, pane: 'main' },
    params: [{ key: 'anchor_timestamp', label: 'Anchor date', input: 'datetime' }],
  },
  {
    type: 'bb',
    label: 'BB',
    pickerLabel: 'BB - Bollinger Bands',
    defaultConfig: { type: 'bb', params: { period: 20, std_dev: 2 }, style: { color: '#80cbc4', lineWidth: 1 }, pane: 'main' },
    params: [{ key: 'period', label: 'Period' }, { key: 'std_dev', label: 'Std dev' }],
  },
  {
    type: 'keltner',
    label: 'Keltner',
    pickerLabel: 'Keltner Channels',
    defaultConfig: { type: 'keltner', params: { period: 20, atr_period: 10, multiplier: 2 }, style: { color: '#ce93d8', lineWidth: 1 }, pane: 'main' },
    params: [{ key: 'period', label: 'EMA period' }, { key: 'atr_period', label: 'ATR period' }, { key: 'multiplier', label: 'Multiplier' }],
  },
  {
    type: 'donchian',
    label: 'Donchian',
    pickerLabel: 'Donchian Channels',
    defaultConfig: { type: 'donchian', params: { period: 20 }, style: { color: '#80deea', lineWidth: 1 }, pane: 'main' },
    params: [{ key: 'period', label: 'Period' }],
  },
  {
    type: 'ichimoku',
    label: 'Ichimoku',
    pickerLabel: 'Ichimoku Cloud',
    defaultConfig: { type: 'ichimoku', params: { tenkan: 9, kijun: 26, senkou_b: 52, displacement: 26 }, style: { color: '#80cbc4', lineWidth: 1.5 }, pane: 'main' },
    params: [
      { key: 'tenkan', label: 'Tenkan' },
      { key: 'kijun', label: 'Kijun' },
      { key: 'senkou_b', label: 'Senkou B' },
      { key: 'displacement', label: 'Displacement' },
    ],
  },
  {
    type: 'psar',
    label: 'PSAR',
    pickerLabel: 'Parabolic SAR',
    defaultConfig: { type: 'psar', params: { af_start: 0.02, af_step: 0.02, af_max: 0.2 }, style: { color: '#ef9a9a', lineWidth: 1 }, pane: 'main' },
    params: [{ key: 'af_start', label: 'AF start' }, { key: 'af_step', label: 'AF step' }, { key: 'af_max', label: 'AF max' }],
  },
  {
    type: 'pivot_points',
    label: 'Pivots',
    pickerLabel: 'Pivot Points',
    defaultConfig: { type: 'pivot_points', params: { method: 'classic' }, style: { color: '#80cbc4', lineWidth: 1 }, pane: 'main' },
    params: [{ key: 'method', label: 'Method', input: 'select', options: [
      { value: 'classic', label: 'Classic' },
      { value: 'fibonacci', label: 'Fibonacci' },
      { value: 'camarilla', label: 'Camarilla' },
    ] }],
  },
  {
    type: 'rsi',
    label: 'RSI',
    pickerLabel: 'RSI - Relative Strength Index',
    defaultConfig: { type: 'rsi', params: { period: 14 }, style: { color: '#ef9a9a', lineWidth: 1.5 }, pane: 'separate' },
    params: [{ key: 'period', label: 'Period' }],
  },
  {
    type: 'macd',
    label: 'MACD',
    pickerLabel: 'MACD - Moving Avg Convergence Div',
    defaultConfig: { type: 'macd', params: { fast: 12, slow: 26, signal: 9 }, style: { color: '#ef5350', lineWidth: 1.5 }, pane: 'separate' },
    params: [{ key: 'fast', label: 'Fast' }, { key: 'slow', label: 'Slow' }, { key: 'signal', label: 'Signal' }],
  },
  {
    type: 'stoch',
    label: 'Stoch',
    pickerLabel: 'Stochastic Oscillator',
    defaultConfig: { type: 'stoch', params: { k_period: 14, d_period: 3, smooth_k: 3 }, style: { color: '#a5d6a7', lineWidth: 1.5 }, pane: 'separate' },
    params: [{ key: 'k_period', label: '%K period' }, { key: 'smooth_k', label: '%K smooth' }, { key: 'd_period', label: '%D period' }],
  },
  {
    type: 'adx',
    label: 'ADX',
    pickerLabel: 'ADX / DMI',
    defaultConfig: { type: 'adx', params: { period: 14 }, style: { color: '#fff59d', lineWidth: 1.5 }, pane: 'separate' },
    params: [{ key: 'period', label: 'Period' }],
  },
  {
    type: 'aroon',
    label: 'Aroon',
    pickerLabel: 'Aroon Up / Down',
    defaultConfig: { type: 'aroon', params: { period: 25 }, style: { color: '#81d4fa', lineWidth: 1.5 }, pane: 'separate' },
    params: [{ key: 'period', label: 'Period' }],
  },
  {
    type: 'cci',
    label: 'CCI',
    pickerLabel: 'CCI - Commodity Channel Index',
    defaultConfig: { type: 'cci', params: { period: 20 }, style: { color: '#f48fb1', lineWidth: 1.5 }, pane: 'separate' },
    params: [{ key: 'period', label: 'Period' }],
  },
  {
    type: 'williams_r',
    label: 'Williams %R',
    pickerLabel: 'Williams %R',
    defaultConfig: { type: 'williams_r', params: { period: 14 }, style: { color: '#ffcc80', lineWidth: 1.5 }, pane: 'separate' },
    params: [{ key: 'period', label: 'Period' }],
  },
  {
    type: 'mfi',
    label: 'MFI',
    pickerLabel: 'MFI - Money Flow Index',
    defaultConfig: { type: 'mfi', params: { period: 14 }, style: { color: '#f48fb1', lineWidth: 1.5 }, pane: 'separate' },
    params: [{ key: 'period', label: 'Period' }],
  },
  {
    type: 'roc',
    label: 'ROC',
    pickerLabel: 'ROC - Rate of Change',
    defaultConfig: { type: 'roc', params: { period: 10 }, style: { color: '#ffb74d', lineWidth: 1.5 }, pane: 'separate' },
    params: [{ key: 'period', label: 'Period' }],
  },
  {
    type: 'momentum',
    label: 'Momentum',
    pickerLabel: 'Momentum',
    defaultConfig: { type: 'momentum', params: { period: 10 }, style: { color: '#b39ddb', lineWidth: 1.5 }, pane: 'separate' },
    params: [{ key: 'period', label: 'Period' }],
  },
  {
    type: 'stddev',
    label: 'StdDev',
    pickerLabel: 'Standard Deviation',
    defaultConfig: { type: 'stddev', params: { period: 20 }, style: { color: '#fff59d', lineWidth: 1.5 }, pane: 'separate' },
    params: [{ key: 'period', label: 'Period' }],
  },
  {
    type: 'cmf',
    label: 'CMF',
    pickerLabel: 'CMF - Chaikin Money Flow',
    defaultConfig: { type: 'cmf', params: { period: 20 }, style: { color: '#80deea', lineWidth: 1.5 }, pane: 'separate' },
    params: [{ key: 'period', label: 'Period' }],
  },
  {
    type: 'obv',
    label: 'OBV',
    pickerLabel: 'OBV - On Balance Volume',
    defaultConfig: { type: 'obv', params: {}, style: { color: '#81d4fa', lineWidth: 1.5 }, pane: 'separate' },
    params: [],
  },
  {
    type: 'atr',
    label: 'ATR',
    pickerLabel: 'ATR - Average True Range',
    defaultConfig: { type: 'atr', params: { period: 14 }, style: { color: '#ffcc80', lineWidth: 1.5 }, pane: 'separate' },
    params: [{ key: 'period', label: 'Period' }],
  },
  {
    type: 'trix',
    label: 'TRIX',
    pickerLabel: 'TRIX',
    defaultConfig: { type: 'trix', params: { period: 15 }, style: { color: '#a5d6a7', lineWidth: 1.5 }, pane: 'separate' },
    params: [{ key: 'period', label: 'Period' }],
  },
  {
    type: 'ppo',
    label: 'PPO',
    pickerLabel: 'PPO - Percentage Price Oscillator',
    defaultConfig: { type: 'ppo', params: { fast: 12, slow: 26 }, style: { color: '#ce93d8', lineWidth: 1.5 }, pane: 'separate' },
    params: [{ key: 'fast', label: 'Fast' }, { key: 'slow', label: 'Slow' }],
  },
  {
    type: 'volume',
    label: 'Volume',
    pickerLabel: 'Volume bars',
    defaultConfig: { type: 'volume', params: {}, style: { color: '#4db6ac', lineWidth: 1 }, pane: 'main' },
    params: [],
  },
  {
    type: 'volume_ratio',
    label: 'Vol Ratio',
    pickerLabel: 'Volume Spike Ratio',
    defaultConfig: { type: 'volume_ratio', params: { period: 20 }, style: { color: '#4db6ac', lineWidth: 1.5 }, pane: 'separate' },
    params: [{ key: 'period', label: 'Avg volume period' }],
  },
]

export const INDICATOR_BY_TYPE = Object.fromEntries(
  INDICATOR_CATALOG.map(item => [item.type, item]),
) as Record<IndicatorType, IndicatorCatalogItem>

const PARAM_ALIASES: Record<string, string> = {
  anchorTime: 'anchor_timestamp',
  stdDev: 'std_dev',
  atrPeriod: 'atr_period',
  senkouB: 'senkou_b',
  afStart: 'af_start',
  afStep: 'af_step',
  afMax: 'af_max',
  smoothK: 'smooth_k',
  smoothD: 'd_period',
}

export function normalizeIndicatorParams(type: string, params: Record<string, unknown> = {}) {
  const out: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(params)) {
    out[PARAM_ALIASES[key] ?? key] = value
  }
  if (type === 'stoch' && out.period != null && out.k_period == null) out.k_period = out.period
  return out
}

export function getParamNumber(params: Record<string, unknown>, key: string, fallback: number): number {
  const normalized = normalizeIndicatorParams('', params)
  const raw = normalized[key]
  const num = typeof raw === 'number' ? raw : Number(raw)
  return Number.isFinite(num) ? num : fallback
}

export function getParamString(params: Record<string, unknown>, key: string, fallback: string): string {
  const normalized = normalizeIndicatorParams('', params)
  const raw = normalized[key]
  return raw == null || raw === '' ? fallback : String(raw)
}

export function displayParams(type: string, params: Record<string, unknown> = {}): unknown[] {
  const normalized = normalizeIndicatorParams(type, params)
  const defs = INDICATOR_BY_TYPE[type as IndicatorType]?.params ?? []
  if (defs.length) return defs.map(def => normalized[def.key]).filter(v => v !== undefined && v !== null && v !== '')
  return Object.values(normalized)
}

export function indicatorDisplayName(ind: Pick<IndicatorConfig, 'type' | 'params'>): string {
  const type = ind.type
  const normalized = normalizeIndicatorParams(type, ind.params)
  const label = INDICATOR_BY_TYPE[type]?.label ?? type.toUpperCase()
  if (type === 'avwap' && normalized.anchor_timestamp) {
    const d = new Date(Number(normalized.anchor_timestamp) * 1000)
    const stamp = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    return `AVWAP(${stamp})`
  }
  const params = displayParams(type, normalized).join(',')
  return params ? `${label.toUpperCase()}(${params})` : label.toUpperCase()
}

export function indicatorDefaultPane(type: IndicatorType): 'main' | 'separate' {
  return INDICATOR_BY_TYPE[type]?.defaultConfig.pane ?? 'main'
}

export function cloneDefaultIndicator(type: IndicatorType): IndicatorConfig {
  const cfg = INDICATOR_BY_TYPE[type].defaultConfig
  const params = { ...cfg.params }
  if (type === 'avwap') params.anchor_timestamp = nowMinus30d()
  return {
    ...cfg,
    params,
    style: { ...cfg.style },
  }
}
