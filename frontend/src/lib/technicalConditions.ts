import { cloneDefaultIndicator, INDICATOR_BY_TYPE, INDICATOR_CATALOG, normalizeIndicatorParams as normalizeCatalogIndicatorParams } from '@/lib/indicators/catalog'
import type { IndicatorType, PriceChangePeriod } from '@/types'

export type SupportedIndicatorType = IndicatorType
export type TechnicalIndicatorParamValue = string | number | boolean
export type TechnicalIndicatorParams = Record<string, TechnicalIndicatorParamValue>

export type TechnicalConditionType =
  | 'indicator_threshold'
  | 'indicator_cross'
  | 'price_indicator'
  | 'price_threshold'
  | 'price_change'
  | 'price_change_period'
  | 'week52_new_high'
  | 'week52_new_low'
  | 'pct_from_52w_high'
  | 'pct_from_52w_low'
  | 'performance'
  | 'stats_filter'
  | 'fundamental_filter'

export interface TechnicalIndicatorRef {
  type: SupportedIndicatorType
  params: TechnicalIndicatorParams
  output?: string
}

export interface TechnicalConditionDraft {
  type: TechnicalConditionType
  indicator?: SupportedIndicatorType
  params?: TechnicalIndicatorParams
  output?: string
  indicator_a?: TechnicalIndicatorRef
  indicator_b?: TechnicalIndicatorRef
  op?: string
  value?: number | string
  field?: string
  period?: PriceChangePeriod
  lookback_bars?: number
}

export const SUPPORTED_INDICATOR_TYPES: SupportedIndicatorType[] = INDICATOR_CATALOG.map(item => item.type)
export const TECHNICAL_INDICATOR_OPTIONS = INDICATOR_CATALOG.map(item => ({
  value: item.type,
  label: item.pickerLabel,
}))
export const PERIOD_OPTIONS: PriceChangePeriod[] = ['1D', '1W', '1M', '3M', '6M', 'MTD', 'QTD', 'YTD', '1Y']
export const STATS_FIELDS = [
  { value: 'market_cap', label: 'Market Cap' },
  { value: 'pe_ratio', label: 'P/E Ratio' },
  { value: 'beta', label: 'Beta' },
  { value: 'avg_volume_30d', label: 'Avg Volume (30d)' },
  { value: 'dividend_yield', label: 'Dividend Yield' },
] as const

export const FUNDAMENTAL_FIELDS = [
  { value: 'sector', label: 'Sector', kind: 'string' },
  { value: 'industry', label: 'Industry', kind: 'string' },
  { value: 'country', label: 'Country', kind: 'string' },
  { value: 'exchange_mic', label: 'Exchange', kind: 'string' },
  { value: 'market_cap_tier', label: 'Market Cap Tier', kind: 'string' },
  { value: 'currency', label: 'Currency', kind: 'string' },
  { value: 'employees', label: 'Employees', kind: 'number' },
] as const

export const ALL_CONDITION_TYPE_OPTIONS: Array<{ value: TechnicalConditionType; label: string }> = [
  { value: 'indicator_threshold', label: 'Indicator vs Value' },
  { value: 'indicator_cross', label: 'Indicator vs Indicator' },
  { value: 'price_indicator', label: 'Price vs Indicator' },
  { value: 'price_threshold', label: 'Price vs Value' },
  { value: 'price_change_period', label: 'Price % Change (period)' },
  { value: 'price_change', label: 'Price % Change (bars)' },
  { value: 'performance', label: 'Performance (calendar)' },
  { value: 'week52_new_high', label: '52-Week New High' },
  { value: 'week52_new_low', label: '52-Week New Low' },
  { value: 'pct_from_52w_high', label: '% from 52W High' },
  { value: 'pct_from_52w_low', label: '% from 52W Low' },
  { value: 'stats_filter', label: 'Stats Filter' },
]

export const STRATEGY_LAB_CONDITION_TYPE_OPTIONS: Array<{ value: TechnicalConditionType; label: string }> = [
  ...ALL_CONDITION_TYPE_OPTIONS,
  { value: 'fundamental_filter', label: 'Fundamental Filter' },
]

const INDICATOR_OUTPUT_OPTIONS: Partial<Record<SupportedIndicatorType, Array<{ value: string; label: string }>>> = {
  macd: [
    { value: 'macd', label: 'MACD line' },
    { value: 'signal', label: 'Signal line' },
    { value: 'histogram', label: 'Histogram' },
  ],
  bb: [
    { value: 'bb_upper', label: 'Upper band' },
    { value: 'bb_mid', label: 'Middle band' },
    { value: 'bb_lower', label: 'Lower band' },
  ],
  stoch: [
    { value: 'stoch_k', label: '%K' },
    { value: 'stoch_d', label: '%D' },
  ],
  adx: [
    { value: 'adx', label: 'ADX' },
    { value: 'plus_di', label: '+DI' },
    { value: 'minus_di', label: '-DI' },
  ],
  ichimoku: [
    { value: 'ichimoku_tenkan', label: 'Tenkan' },
    { value: 'ichimoku_kijun', label: 'Kijun' },
    { value: 'ichimoku_senkou_a', label: 'Senkou A' },
    { value: 'ichimoku_senkou_b', label: 'Senkou B' },
    { value: 'ichimoku_chikou', label: 'Chikou' },
  ],
  donchian: [
    { value: 'donchian_upper', label: 'Upper channel' },
    { value: 'donchian_mid', label: 'Middle channel' },
    { value: 'donchian_lower', label: 'Lower channel' },
  ],
  keltner: [
    { value: 'keltner_upper', label: 'Upper channel' },
    { value: 'keltner_mid', label: 'Middle channel' },
    { value: 'keltner_lower', label: 'Lower channel' },
  ],
  aroon: [
    { value: 'aroon_up', label: 'Aroon up' },
    { value: 'aroon_down', label: 'Aroon down' },
    { value: 'aroon_osc', label: 'Aroon oscillator' },
  ],
  pivot_points: [
    { value: 'pp', label: 'Pivot point' },
    { value: 'r1', label: 'Resistance 1' },
    { value: 'r2', label: 'Resistance 2' },
    { value: 'r3', label: 'Resistance 3' },
    { value: 's1', label: 'Support 1' },
    { value: 's2', label: 'Support 2' },
    { value: 's3', label: 'Support 3' },
  ],
}

export function getTechnicalIndicatorParamDefs(type: SupportedIndicatorType) {
  return INDICATOR_BY_TYPE[type]?.params ?? []
}

export function getTechnicalIndicatorOutputOptions(type: SupportedIndicatorType) {
  return INDICATOR_OUTPUT_OPTIONS[type] ?? []
}

function defaultIndicatorParams(type: SupportedIndicatorType): TechnicalIndicatorParams {
  return normalizeCatalogIndicatorParams(type, cloneDefaultIndicator(type).params) as TechnicalIndicatorParams
}

function defaultIndicatorOutput(type: SupportedIndicatorType): string | undefined {
  return getTechnicalIndicatorOutputOptions(type)[0]?.value
}

export function createDefaultTechnicalIndicatorRef(
  type: SupportedIndicatorType = 'rsi',
): TechnicalIndicatorRef {
  return {
    type,
    params: defaultIndicatorParams(type),
    output: defaultIndicatorOutput(type),
  }
}

export function createDefaultTechnicalCondition(
  type: TechnicalConditionType = 'indicator_threshold',
): TechnicalConditionDraft {
  const condition: TechnicalConditionDraft = {
    type: 'indicator_threshold',
    indicator: 'rsi',
    params: defaultIndicatorParams('rsi'),
    output: defaultIndicatorOutput('rsi'),
    op: 'lt',
    value: 30,
  }
  return resetTechnicalConditionForType(condition, type)
}

export function resetTechnicalConditionForType(
  target: TechnicalConditionDraft,
  type: TechnicalConditionType,
): TechnicalConditionDraft {
  target.type = type
  if (type === 'indicator_threshold') {
    target.indicator = 'rsi'
    target.params = defaultIndicatorParams('rsi')
    target.output = defaultIndicatorOutput('rsi')
    target.op = 'lt'
    target.value = 30
    delete target.indicator_a
    delete target.indicator_b
    delete target.field
    delete target.period
    delete target.lookback_bars
    return target
  }
  if (type === 'indicator_cross') {
    target.indicator_a = createDefaultTechnicalIndicatorRef('sma')
    target.indicator_b = createDefaultTechnicalIndicatorRef('sma')
    target.indicator_b.params = { ...target.indicator_b.params, period: 50 }
    target.op = 'crosses_above'
    delete target.indicator
    delete target.params
    delete target.output
    delete target.field
    delete target.period
    delete target.lookback_bars
    delete target.value
    return target
  }
  if (type === 'price_indicator') {
    target.field = 'close'
    target.op = 'gt'
    target.indicator = 'sma'
    target.params = defaultIndicatorParams('sma')
    target.output = defaultIndicatorOutput('sma')
    delete target.indicator_a
    delete target.indicator_b
    delete target.period
    delete target.lookback_bars
    delete target.value
    return target
  }
  if (type === 'price_threshold') {
    target.field = 'close'
    target.op = 'gt'
    target.value = 0
    delete target.indicator
    delete target.params
    delete target.output
    delete target.indicator_a
    delete target.indicator_b
    delete target.period
    delete target.lookback_bars
    return target
  }
  if (type === 'price_change_period' || type === 'performance') {
    target.period = '1D'
    target.op = 'gt'
    target.value = 0
    delete target.indicator
    delete target.params
    delete target.output
    delete target.indicator_a
    delete target.indicator_b
    delete target.field
    delete target.lookback_bars
    return target
  }
  if (type === 'price_change') {
    target.lookback_bars = 5
    target.op = 'gt'
    target.value = 0
    delete target.indicator
    delete target.params
    delete target.output
    delete target.indicator_a
    delete target.indicator_b
    delete target.field
    delete target.period
    return target
  }
  if (type === 'pct_from_52w_high' || type === 'pct_from_52w_low') {
    target.op = 'lt'
    target.value = 0.05
    delete target.indicator
    delete target.params
    delete target.output
    delete target.indicator_a
    delete target.indicator_b
    delete target.field
    delete target.period
    delete target.lookback_bars
    return target
  }
  if (type === 'stats_filter') {
    target.field = 'market_cap'
    target.op = 'gt'
    target.value = 0
    delete target.indicator
    delete target.params
    delete target.output
    delete target.indicator_a
    delete target.indicator_b
    delete target.period
    delete target.lookback_bars
    return target
  }
  if (type === 'fundamental_filter') {
    target.field = 'sector'
    target.op = 'eq'
    target.value = ''
    delete target.indicator
    delete target.params
    delete target.output
    delete target.indicator_a
    delete target.indicator_b
    delete target.period
    delete target.lookback_bars
    return target
  }
  delete target.indicator
  delete target.params
  delete target.output
  delete target.indicator_a
  delete target.indicator_b
  delete target.field
  delete target.period
  delete target.lookback_bars
  delete target.op
  delete target.value
  return target
}

export function normalizeTechnicalCondition(raw: Record<string, unknown>): TechnicalConditionDraft {
  const legacy = normalizeLegacyCondition(raw)
  if (legacy) return legacy
  const type = String(raw.type ?? 'indicator_threshold') as TechnicalConditionType
  const condition = createDefaultTechnicalCondition(type)
  if ('indicator' in raw && typeof raw.indicator === 'string') {
    condition.indicator = normalizeIndicatorType(raw.indicator)
  }
  if ('params' in raw && raw.params && typeof raw.params === 'object') {
    condition.params = normalizeIndicatorParamsForType(condition.indicator ?? 'rsi', raw.params as Record<string, unknown>)
  }
  if ('output' in raw && raw.output != null) condition.output = normalizeIndicatorOutput(condition.indicator ?? 'rsi', raw.output)
  if ('indicator_a' in raw && raw.indicator_a && typeof raw.indicator_a === 'object') {
    const indicatorType = normalizeIndicatorType((raw.indicator_a as any).type)
    condition.indicator_a = {
      type: indicatorType,
      params: normalizeIndicatorParamsForType(indicatorType, (raw.indicator_a as any).params),
      output: normalizeIndicatorOutput(indicatorType, (raw.indicator_a as any).output),
    }
  }
  if ('indicator_b' in raw && raw.indicator_b && typeof raw.indicator_b === 'object') {
    const indicatorType = normalizeIndicatorType((raw.indicator_b as any).type)
    condition.indicator_b = {
      type: indicatorType,
      params: normalizeIndicatorParamsForType(indicatorType, (raw.indicator_b as any).params),
      output: normalizeIndicatorOutput(indicatorType, (raw.indicator_b as any).output),
    }
  }
  if ('op' in raw && raw.op != null) condition.op = String(raw.op)
  if ('operator' in raw && raw.operator != null && !('op' in raw)) condition.op = String(raw.operator)
  if ('value' in raw && raw.value != null) condition.value = Number(raw.value)
  if ('value' in raw && typeof raw.value === 'string') (condition as any).value = raw.value
  if ('field' in raw && raw.field != null) condition.field = String(raw.field)
  if ('period' in raw && raw.period != null) condition.period = String(raw.period) as PriceChangePeriod
  if ('lookback_bars' in raw && raw.lookback_bars != null) condition.lookback_bars = Math.max(1, Math.round(Number(raw.lookback_bars) || 1))
  return condition
}

export function describeTechnicalCondition(condition: TechnicalConditionDraft): string {
  const op = condition.op ?? 'gt'
  const operatorText = describeOperator(op)
  if (condition.type === 'indicator_threshold') {
    return `${formatIndicator(condition.indicator, condition.params, condition.output)} ${operatorText} ${condition.value ?? 0}`
  }
  if (condition.type === 'indicator_cross') {
    return `${formatIndicator(condition.indicator_a?.type, condition.indicator_a?.params, condition.indicator_a?.output)} ${describeCrossOperator(op)} ${formatIndicator(condition.indicator_b?.type, condition.indicator_b?.params, condition.indicator_b?.output)}`
  }
  if (condition.type === 'price_indicator') {
    return `${humanizeField(condition.field ?? 'close')} ${describeOperator(op)} ${formatIndicator(condition.indicator, condition.params, condition.output)}`
  }
  if (condition.type === 'price_threshold') {
    return `${humanizeField(condition.field ?? 'close')} ${operatorText} ${condition.value ?? 0}`
  }
  if (condition.type === 'price_change_period') {
    return `price change over ${condition.period ?? '1D'} ${operatorText} ${condition.value ?? 0}`
  }
  if (condition.type === 'price_change') {
    return `price change over ${condition.lookback_bars ?? 1} bars ${operatorText} ${condition.value ?? 0}`
  }
  if (condition.type === 'week52_new_high') return 'instrument is making a new 52-week high'
  if (condition.type === 'week52_new_low') return 'instrument is making a new 52-week low'
  if (condition.type === 'pct_from_52w_high') return `distance from 52-week high ${operatorText} ${condition.value ?? 0}`
  if (condition.type === 'pct_from_52w_low') return `distance from 52-week low ${operatorText} ${condition.value ?? 0}`
  if (condition.type === 'performance') return `calendar performance over ${condition.period ?? '1D'} ${operatorText} ${condition.value ?? 0}`
  if (condition.type === 'stats_filter') return `${humanizeField(condition.field ?? 'value')} ${operatorText} ${condition.value ?? 0}`
  if (condition.type === 'fundamental_filter') return `${humanizeField(condition.field ?? 'field')} ${describeTextOperator(op)} ${condition.value ?? ''}`
  return 'custom condition'
}

function formatIndicator(
  indicator: unknown,
  params: TechnicalIndicatorParams | undefined,
  output?: string,
): string {
  const type = normalizeIndicatorType(indicator)
  const label = INDICATOR_BY_TYPE[type]?.label?.toUpperCase() ?? String(indicator ?? 'indicator').toUpperCase()
  const defs = getTechnicalIndicatorParamDefs(type)
  const normalized = normalizeIndicatorParamsForType(type, params)
  const paramValues = defs
    .map(def => normalized[def.key])
    .filter(value => value !== undefined && value !== null && value !== '')
    .map(value => typeof value === 'boolean' ? (value ? 'on' : 'off') : String(value))
  const outputLabel = getTechnicalIndicatorOutputOptions(type).find(item => item.value === output)?.label
  const base = paramValues.length ? `${label}(${paramValues.join(',')})` : label
  return outputLabel ? `${base} · ${outputLabel}` : base
}

function normalizeIndicatorType(value: unknown): SupportedIndicatorType {
  const token = String(value ?? '').toLowerCase()
  return SUPPORTED_INDICATOR_TYPES.includes(token as SupportedIndicatorType)
    ? token as SupportedIndicatorType
    : 'rsi'
}

function normalizeIndicatorParamsForType(
  type: SupportedIndicatorType,
  params: Record<string, unknown> | undefined,
): TechnicalIndicatorParams {
  return {
    ...defaultIndicatorParams(type),
    ...(normalizeCatalogIndicatorParams(type, params ?? {}) as TechnicalIndicatorParams),
  }
}

function normalizeIndicatorOutput(
  type: SupportedIndicatorType,
  value: unknown,
): string | undefined {
  const options = getTechnicalIndicatorOutputOptions(type)
  if (!options.length) return undefined
  const token = String(value ?? '')
  return options.some(option => option.value === token) ? token : options[0].value
}

function normalizeLegacyCondition(raw: Record<string, unknown>): TechnicalConditionDraft | null {
  const leftSource = String(raw.left_source ?? '')
  const rightSource = String(raw.right_source ?? '')
  if (!leftSource && !rightSource) return null

  const operator = String(raw.operator ?? raw.op ?? 'gt')
  if (leftSource === 'indicator' && rightSource === 'indicator') {
    return {
      type: 'indicator_cross',
      indicator_a: {
        type: normalizeIndicatorType(raw.left_indicator),
        params: normalizeIndicatorParamsForType(normalizeIndicatorType(raw.left_indicator), { period: clampPeriod(raw.left_period, 20) }),
        output: defaultIndicatorOutput(normalizeIndicatorType(raw.left_indicator)),
      },
      indicator_b: {
        type: normalizeIndicatorType(raw.right_indicator),
        params: normalizeIndicatorParamsForType(normalizeIndicatorType(raw.right_indicator), { period: clampPeriod(raw.right_period, 50) }),
        output: defaultIndicatorOutput(normalizeIndicatorType(raw.right_indicator)),
      },
      op: operator,
    }
  }

  if (leftSource === 'indicator' && rightSource === 'value') {
    return {
      type: 'indicator_threshold',
      indicator: normalizeIndicatorType(raw.left_indicator),
      params: normalizeIndicatorParamsForType(normalizeIndicatorType(raw.left_indicator), { period: clampPeriod(raw.left_period, 14) }),
      output: defaultIndicatorOutput(normalizeIndicatorType(raw.left_indicator)),
      op: operator,
      value: Number(raw.right_value ?? 0),
    }
  }

  if (leftSource === 'value' && rightSource === 'indicator') {
    return {
      type: 'indicator_threshold',
      indicator: normalizeIndicatorType(raw.right_indicator),
      params: normalizeIndicatorParamsForType(normalizeIndicatorType(raw.right_indicator), { period: clampPeriod(raw.right_period, 14) }),
      output: defaultIndicatorOutput(normalizeIndicatorType(raw.right_indicator)),
      op: flipOperator(operator),
      value: Number(raw.left_value ?? 0),
    }
  }

  if (leftSource === 'price' && rightSource === 'indicator') {
    return {
      type: 'price_indicator',
      field: 'close',
      indicator: normalizeIndicatorType(raw.right_indicator),
      params: normalizeIndicatorParamsForType(normalizeIndicatorType(raw.right_indicator), { period: clampPeriod(raw.right_period, 20) }),
      output: defaultIndicatorOutput(normalizeIndicatorType(raw.right_indicator)),
      op: operator,
    }
  }

  if (leftSource === 'indicator' && rightSource === 'price') {
    return {
      type: 'price_indicator',
      field: 'close',
      indicator: normalizeIndicatorType(raw.left_indicator),
      params: normalizeIndicatorParamsForType(normalizeIndicatorType(raw.left_indicator), { period: clampPeriod(raw.left_period, 20) }),
      output: defaultIndicatorOutput(normalizeIndicatorType(raw.left_indicator)),
      op: flipOperator(operator),
    }
  }

  if (leftSource === 'price' && rightSource === 'value') {
    return {
      type: 'price_threshold',
      field: 'close',
      op: operator,
      value: Number(raw.right_value ?? 0),
    }
  }

  if (leftSource === 'value' && rightSource === 'price') {
    return {
      type: 'price_threshold',
      field: 'close',
      op: flipOperator(operator),
      value: Number(raw.left_value ?? 0),
    }
  }

  return null
}

function flipOperator(operator: string): string {
  if (operator === 'gt') return 'lt'
  if (operator === 'gte') return 'lte'
  if (operator === 'lt') return 'gt'
  if (operator === 'lte') return 'gte'
  return operator
}

function clampPeriod(value: unknown, fallback: number): number {
  const numeric = Math.round(Number(value) || fallback)
  return Math.max(1, numeric)
}

function describeOperator(operator: string): string {
  if (operator === 'gt') return 'is above'
  if (operator === 'gte') return 'is at or above'
  if (operator === 'eq') return 'equals'
  if (operator === 'lt') return 'is below'
  if (operator === 'lte') return 'is at or below'
  if (operator === 'crosses_above') return 'crosses above'
  if (operator === 'crosses_below') return 'crosses below'
  return operator
}

function describeTextOperator(operator: string): string {
  if (operator === 'eq') return 'matches'
  if (operator === 'contains') return 'contains'
  return describeOperator(operator)
}

function describeCrossOperator(operator: string): string {
  if (operator === 'crosses_above') return 'crosses above'
  if (operator === 'crosses_below') return 'crosses below'
  if (operator === 'gt') return 'is above'
  if (operator === 'lt') return 'is below'
  return operator
}

function humanizeField(value: string): string {
  return value.replace(/_/g, ' ')
}
