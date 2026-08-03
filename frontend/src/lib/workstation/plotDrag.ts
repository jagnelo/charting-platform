import { INDICATOR_BY_TYPE, indicatorDisplayName } from '@/lib/indicators/catalog'
import type { TechnicalConditionDraft, TechnicalIndicatorParams } from '@/lib/technicalConditions'
import type { IndicatorConfig, IndicatorType, Timeframe } from '@/types'

export const CHART_PLOT_DRAG_MIME = 'application/x-charting-platform-plot'
const PLOT_DRAG_VERSION = 1
const MAX_PLOT_DRAG_BYTES = 16_384
const TIMEFRAMES: Timeframe[] = ['M1', 'M5', 'M15', 'M30', 'H1', 'H2', 'H4', 'H12', 'D1', 'W1', 'MN']

export interface ChartPlotDragPayload {
  version: 1
  kind: 'chart-plot'
  indicator: {
    type: IndicatorType
    params: Record<string, unknown>
    output?: string
    timeframe: Timeframe
    label: string
    sourceWindowKey: string
  }
}

export interface TechnicalConditionDragPayload {
  version: 1
  kind: 'technical-condition'
  condition: Record<string, unknown>
  timeframe: Timeframe
  label: string
  sourceWindowKey: string
}

export type ChartAnalysisDragPayload = ChartPlotDragPayload | TechnicalConditionDragPayload

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}

function isIndicatorType(value: unknown): value is IndicatorType {
  return typeof value === 'string' && Object.prototype.hasOwnProperty.call(INDICATOR_BY_TYPE, value)
}

function isTimeframe(value: unknown): value is Timeframe {
  return typeof value === 'string' && TIMEFRAMES.includes(value as Timeframe)
}

export function createChartPlotDragPayload(indicator: IndicatorConfig, timeframe: Timeframe, sourceWindowKey: string): ChartPlotDragPayload {
  const payload: ChartPlotDragPayload = {
    version: PLOT_DRAG_VERSION,
    kind: 'chart-plot',
    indicator: {
      type: indicator.type,
      params: JSON.parse(JSON.stringify(indicator.params ?? {})) as Record<string, unknown>,
      timeframe,
      label: indicatorDisplayName(indicator),
      sourceWindowKey: sourceWindowKey.slice(0, 128),
    },
  }
  return payload
}

export function writeChartPlotDrag(dataTransfer: DataTransfer, payload: ChartPlotDragPayload) {
  return writeAnalysisDrag(dataTransfer, payload)
}

export function createTechnicalConditionDragPayload(condition: Record<string, unknown>, timeframe: Timeframe, sourceWindowKey: string, label: string): TechnicalConditionDragPayload {
  return {
    version: 1,
    kind: 'technical-condition',
    condition: JSON.parse(JSON.stringify(condition)) as Record<string, unknown>,
    timeframe,
    label: label.slice(0, 160) || 'Technical condition',
    sourceWindowKey: sourceWindowKey.slice(0, 128),
  }
}

export function writeTechnicalConditionDrag(dataTransfer: DataTransfer, payload: TechnicalConditionDragPayload) {
  return writeAnalysisDrag(dataTransfer, payload)
}

function writeAnalysisDrag(dataTransfer: DataTransfer, payload: ChartAnalysisDragPayload) {
  const serialized = JSON.stringify(payload)
  if (serialized.length > MAX_PLOT_DRAG_BYTES) return false
  dataTransfer.setData(CHART_PLOT_DRAG_MIME, serialized)
  dataTransfer.setData('text/plain', payload.kind === 'chart-plot' ? payload.indicator.label : payload.label)
  dataTransfer.effectAllowed = 'copy'
  return true
}

export function readChartPlotDrag(dataTransfer: DataTransfer | null | undefined): ChartPlotDragPayload | null {
  const payload = readAnalysisDrag(dataTransfer)
  return payload?.kind === 'chart-plot' ? payload : null
}

export function readAnalysisDrag(dataTransfer: DataTransfer | null | undefined): ChartAnalysisDragPayload | null {
  if (!dataTransfer) return null
  let serialized = ''
  try { serialized = dataTransfer.getData(CHART_PLOT_DRAG_MIME) } catch { return null }
  if (!serialized || serialized.length > MAX_PLOT_DRAG_BYTES) return null
  try {
    const candidate = JSON.parse(serialized) as unknown
    if (!isRecord(candidate) || candidate.version !== PLOT_DRAG_VERSION) return null
    if (candidate.kind === 'technical-condition') {
      if (!isRecord(candidate.condition) || !isTimeframe(candidate.timeframe) || typeof candidate.label !== 'string' || typeof candidate.sourceWindowKey !== 'string') return null
      if (candidate.label.length > 160 || candidate.sourceWindowKey.length > 128) return null
      return {
        version: 1,
        kind: 'technical-condition',
        condition: JSON.parse(JSON.stringify(candidate.condition)) as Record<string, unknown>,
        timeframe: candidate.timeframe,
        label: candidate.label,
        sourceWindowKey: candidate.sourceWindowKey,
      }
    }
    if (candidate.kind !== 'chart-plot' || !isRecord(candidate.indicator)) return null
    const indicator = candidate.indicator
    if (!isIndicatorType(indicator.type) || !isRecord(indicator.params) || !isTimeframe(indicator.timeframe) || typeof indicator.label !== 'string' || typeof indicator.sourceWindowKey !== 'string') return null
    if (indicator.label.length > 160 || indicator.sourceWindowKey.length > 128) return null
    const output = indicator.output
    return {
      version: 1,
      kind: 'chart-plot',
      indicator: {
        type: indicator.type,
        params: JSON.parse(JSON.stringify(indicator.params)) as Record<string, unknown>,
        ...(typeof output === 'string' && output.length <= 64 ? { output } : {}),
        timeframe: indicator.timeframe as Timeframe,
        label: indicator.label,
        sourceWindowKey: indicator.sourceWindowKey,
      },
    }
  } catch { return null }
}

export function indicatorColumnFromPlot(payload: ChartPlotDragPayload) {
  const { indicator } = payload
  const key = `indicator:${indicator.type}:${JSON.stringify(indicator.params)}:${indicator.timeframe}`
  return {
    key,
    name: indicator.label,
    indicator: indicator.type,
    params: { ...indicator.params },
    timeframe: indicator.timeframe,
    ...(indicator.output ? { output: indicator.output } : { output: 'value' }),
  }
}

export function technicalConditionFromPlot(payload: ChartPlotDragPayload) {
  const { indicator } = payload
  const params = Object.fromEntries(Object.entries(indicator.params).filter(([, value]) => typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean')) as TechnicalIndicatorParams
  return {
    type: 'indicator_threshold' as const,
    indicator: indicator.type,
    params,
    ...(indicator.output ? { output: indicator.output } : {}),
    op: 'gt' as const,
    value: 0,
  } satisfies TechnicalConditionDraft
}
