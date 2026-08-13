import { INDICATOR_BY_TYPE, indicatorDisplayName } from '@/lib/indicators/catalog'
import type { TechnicalConditionDraft, TechnicalIndicatorParams } from '@/lib/technicalConditions'
import type { IndicatorConfig, IndicatorType, Timeframe } from '@/types'

export const CHART_PLOT_DRAG_MIME = 'application/x-charting-platform-plot'
const PLOT_DRAG_VERSION = 1
const MAX_PLOT_DRAG_BYTES = 16_384
const TIMEFRAMES: Timeframe[] = ['M1', 'M5', 'M15', 'M30', 'H1', 'H2', 'H4', 'H12', 'D1', 'W1', 'MN']
// Some browser drag implementations expose custom MIME types during
// dragover but return an empty value during drop. Keep the current serialized
// payload in the page while the drag is active as a same-document fallback.
let activeAnalysisDragPayload: ChartAnalysisDragPayload | null = null
let analysisDragCleanupTimer: ReturnType<typeof setTimeout> | null = null

export function hasActiveAnalysisDrag() {
  return activeAnalysisDragPayload != null
}

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

export interface ChartPythonPlotDragPayload {
  version: 1
  kind: 'python-plot'
  python: {
    codeVersionId: number
    name: string
    timeframe: Timeframe
    color?: string
    sourceWindowKey: string
  }
}

export type ChartAnalysisDragPayload = ChartPlotDragPayload | TechnicalConditionDragPayload | ChartPythonPlotDragPayload

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

export function createPythonPlotDragPayload(
  plot: { code_version_id: number; name: string; color?: string; timeframe?: string },
  fallbackTimeframe: Timeframe,
  sourceWindowKey: string,
): ChartPythonPlotDragPayload | null {
  if (!Number.isInteger(plot.code_version_id) || plot.code_version_id <= 0 || !plot.name.trim()) return null
  const timeframe = isTimeframe(plot.timeframe) ? plot.timeframe : fallbackTimeframe
  return {
    version: 1,
    kind: 'python-plot',
    python: {
      codeVersionId: plot.code_version_id,
      name: plot.name.trim().slice(0, 160),
      timeframe,
      ...(typeof plot.color === 'string' && plot.color.trim() ? { color: plot.color.trim().slice(0, 32) } : {}),
      sourceWindowKey: sourceWindowKey.slice(0, 128),
    },
  }
}

export function writePythonPlotDrag(dataTransfer: DataTransfer, payload: ChartPythonPlotDragPayload) {
  return writeAnalysisDrag(dataTransfer, payload)
}

function writeAnalysisDrag(dataTransfer: DataTransfer, payload: ChartAnalysisDragPayload) {
  const serialized = JSON.stringify(payload)
  if (analysisDragCleanupTimer !== null) {
    clearTimeout(analysisDragCleanupTimer)
    analysisDragCleanupTimer = null
  }
  activeAnalysisDragPayload = null
  if (serialized.length > MAX_PLOT_DRAG_BYTES) return false
  dataTransfer.setData(CHART_PLOT_DRAG_MIME, serialized)
  const textLabel = payload.kind === 'chart-plot'
    ? payload.indicator.label
    : payload.kind === 'technical-condition'
      ? payload.label
      : payload.python.name
  dataTransfer.setData('text/plain', textLabel)
  dataTransfer.effectAllowed = 'copy'
  activeAnalysisDragPayload = payload
  return true
}

export function clearAnalysisDrag() {
  if (analysisDragCleanupTimer !== null) {
    clearTimeout(analysisDragCleanupTimer)
    analysisDragCleanupTimer = null
  }
  activeAnalysisDragPayload = null
}

/**
 * Chromium may dispatch dragend on a teleported source before the destination
 * receives drop. Keep the same-document fallback alive for one event turn plus
 * a short bounded grace period; an actual drop still calls clearAnalysisDrag()
 * immediately after reading the payload.
 */
export function scheduleAnalysisDragCleanup(delayMs = 10_000) {
  if (analysisDragCleanupTimer !== null) clearTimeout(analysisDragCleanupTimer)
  analysisDragCleanupTimer = setTimeout(() => {
    analysisDragCleanupTimer = null
    activeAnalysisDragPayload = null
  }, Math.max(0, Math.min(15_000, delayMs)))
}

export function readChartPlotDrag(dataTransfer: DataTransfer | null | undefined): ChartPlotDragPayload | null {
  const payload = readAnalysisDrag(dataTransfer)
  return payload?.kind === 'chart-plot' ? payload : null
}

export function readAnalysisDrag(dataTransfer: DataTransfer | null | undefined): ChartAnalysisDragPayload | null {
  if (!dataTransfer) return null
  let serialized = ''
  try { serialized = dataTransfer.getData(CHART_PLOT_DRAG_MIME) } catch { serialized = '' }
  if (!serialized) return activeAnalysisDragPayload
  if (serialized.length > MAX_PLOT_DRAG_BYTES) return null
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
    if (candidate.kind === 'python-plot') {
      if (!isRecord(candidate.python)) return null
      const python = candidate.python
      if (!Number.isInteger(python.codeVersionId) || Number(python.codeVersionId) <= 0 || typeof python.name !== 'string' || python.name.length > 160 || !isTimeframe(python.timeframe) || typeof python.sourceWindowKey !== 'string' || python.sourceWindowKey.length > 128) return null
      if (python.color !== undefined && (typeof python.color !== 'string' || python.color.length > 32)) return null
      return {
        version: 1,
        kind: 'python-plot',
        python: {
          codeVersionId: Number(python.codeVersionId),
          name: python.name,
          timeframe: python.timeframe,
          ...(typeof python.color === 'string' ? { color: python.color } : {}),
          sourceWindowKey: python.sourceWindowKey,
        },
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

export function pythonColumnFromPlot(payload: ChartPythonPlotDragPayload) {
  return {
    code_version_id: payload.python.codeVersionId,
    name: payload.python.name,
    timeframe: payload.python.timeframe,
  }
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
