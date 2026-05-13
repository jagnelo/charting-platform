import type { PriceChangePeriod } from '@/types'

export type SupportedIndicatorType = 'rsi' | 'sma' | 'ema'

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
  params: {
    period: number
  }
}

export interface TechnicalConditionDraft {
  type: TechnicalConditionType
  indicator?: SupportedIndicatorType
  params?: {
    period: number
  }
  indicator_a?: TechnicalIndicatorRef
  indicator_b?: TechnicalIndicatorRef
  op?: string
  value?: number | string
  field?: string
  period?: PriceChangePeriod
  lookback_bars?: number
}

export const SUPPORTED_INDICATOR_TYPES: SupportedIndicatorType[] = ['rsi', 'sma', 'ema']
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

export function createDefaultTechnicalCondition(
  type: TechnicalConditionType = 'indicator_threshold',
): TechnicalConditionDraft {
  const condition: TechnicalConditionDraft = {
    type: 'indicator_threshold',
    indicator: 'rsi',
    params: { period: 14 },
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
    target.params = { period: 14 }
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
    target.indicator_a = { type: 'sma', params: { period: 20 } }
    target.indicator_b = { type: 'sma', params: { period: 50 } }
    target.op = 'crosses_above'
    delete target.indicator
    delete target.params
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
    target.params = { period: 20 }
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
    delete target.indicator_a
    delete target.indicator_b
    delete target.period
    delete target.lookback_bars
    return target
  }
  delete target.indicator
  delete target.params
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
    condition.params = { period: clampPeriod((raw.params as any).period, condition.params?.period ?? 14) }
  }
  if ('indicator_a' in raw && raw.indicator_a && typeof raw.indicator_a === 'object') {
    condition.indicator_a = {
      type: normalizeIndicatorType((raw.indicator_a as any).type),
      params: { period: clampPeriod((raw.indicator_a as any).params?.period, 20) },
    }
  }
  if ('indicator_b' in raw && raw.indicator_b && typeof raw.indicator_b === 'object') {
    condition.indicator_b = {
      type: normalizeIndicatorType((raw.indicator_b as any).type),
      params: { period: clampPeriod((raw.indicator_b as any).params?.period, 50) },
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
    return `${formatIndicator(condition.indicator, condition.params?.period)} ${operatorText} ${condition.value ?? 0}`
  }
  if (condition.type === 'indicator_cross') {
    return `${formatIndicator(condition.indicator_a?.type, condition.indicator_a?.params?.period)} ${describeCrossOperator(op)} ${formatIndicator(condition.indicator_b?.type, condition.indicator_b?.params?.period)}`
  }
  if (condition.type === 'price_indicator') {
    return `${humanizeField(condition.field ?? 'close')} ${describeOperator(op)} ${formatIndicator(condition.indicator, condition.params?.period)}`
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

function formatIndicator(indicator: unknown, period: unknown): string {
  return `${String(indicator ?? 'indicator').toUpperCase()}(${clampPeriod(period, 14)})`
}

function normalizeIndicatorType(value: unknown): SupportedIndicatorType {
  const token = String(value ?? '').toLowerCase()
  return SUPPORTED_INDICATOR_TYPES.includes(token as SupportedIndicatorType)
    ? token as SupportedIndicatorType
    : 'rsi'
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
        params: { period: clampPeriod(raw.left_period, 20) },
      },
      indicator_b: {
        type: normalizeIndicatorType(raw.right_indicator),
        params: { period: clampPeriod(raw.right_period, 50) },
      },
      op: operator,
    }
  }

  if (leftSource === 'indicator' && rightSource === 'value') {
    return {
      type: 'indicator_threshold',
      indicator: normalizeIndicatorType(raw.left_indicator),
      params: { period: clampPeriod(raw.left_period, 14) },
      op: operator,
      value: Number(raw.right_value ?? 0),
    }
  }

  if (leftSource === 'value' && rightSource === 'indicator') {
    return {
      type: 'indicator_threshold',
      indicator: normalizeIndicatorType(raw.right_indicator),
      params: { period: clampPeriod(raw.right_period, 14) },
      op: flipOperator(operator),
      value: Number(raw.left_value ?? 0),
    }
  }

  if (leftSource === 'price' && rightSource === 'indicator') {
    return {
      type: 'price_indicator',
      field: 'close',
      indicator: normalizeIndicatorType(raw.right_indicator),
      params: { period: clampPeriod(raw.right_period, 20) },
      op: operator,
    }
  }

  if (leftSource === 'indicator' && rightSource === 'price') {
    return {
      type: 'price_indicator',
      field: 'close',
      indicator: normalizeIndicatorType(raw.left_indicator),
      params: { period: clampPeriod(raw.left_period, 20) },
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
