import type {
  ChartDrawing,
  DrawingStyle,
  IndicatorConfig,
  RadarDetection,
  RadarDrawingVisual,
  RadarIndicatorVisual,
  Timeframe,
} from '@/types'
import { normalizeIndicatorParams } from '@/lib/indicators/catalog'

const DRAWING_FLOAT_PRECISION = 4

export interface ResolvedRadarIndicator extends IndicatorConfig {
  __radarSource?: 'overlay' | 'reuse'
  __radarHighlightOpacity?: number
  __radarRoles?: string[]
  __radarLabel?: string | null
}

export type ResolvedRadarDrawing = ChartDrawing & {
  __radarSource?: 'overlay' | 'reuse'
  __radarHighlightOpacity?: number
  __radarRoles?: string[]
  __radarSourceTag?: string | null
  sourceTag?: string | null
  radarLinked?: boolean
  radarHighlightOpacity?: number
  radarRoles?: string[]
}

function roundDrawingNumber(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return 'null'
  return value.toFixed(DRAWING_FLOAT_PRECISION)
}

function stableObject(value: Record<string, unknown>) {
  return Object.fromEntries(
    Object.entries(value)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, inner]) => [
        key,
        typeof inner === 'number' && Number.isFinite(inner) ? Number(inner.toFixed(6)) : inner,
      ]),
  )
}

export function radarIndicatorSignature(
  indicator: Pick<RadarIndicatorVisual, 'type' | 'params' | 'pane'> | Pick<IndicatorConfig, 'type' | 'params' | 'pane'>,
) {
  return JSON.stringify({
    type: indicator.type,
    pane: indicator.pane ?? 'main',
    params: stableObject(normalizeIndicatorParams(indicator.type, indicator.params)),
  })
}

function pointsSignature(points: unknown): string {
  if (!Array.isArray(points)) return '[]'
  return JSON.stringify(
    points.map(point => {
      if (!point || typeof point !== 'object') return point
      const value = point as Record<string, unknown>
      return {
        time: value.time,
        price: typeof value.price === 'number' ? roundDrawingNumber(value.price) : value.price,
      }
    }),
  )
}

export function radarDrawingSignature(
  drawing: Pick<RadarDrawingVisual, 'drawing_type' | 'indicator_key' | 'data'> | Pick<ChartDrawing, 'drawing_type' | 'indicator_key' | 'data'>,
) {
  const data = drawing.data as Record<string, unknown>
  return JSON.stringify({
    type: drawing.drawing_type,
    indicator_key: drawing.indicator_key ?? null,
    filled: data.filled ?? null,
    extendRight: data.extendRight ?? null,
    extendLeft: data.extendLeft ?? null,
    points: pointsSignature(data.points),
  })
}

function applyOpacityToHex(color: string | undefined, opacity: number) {
  if (!color) return color
  const normalized = color.trim()
  if (!normalized.startsWith('#')) return normalized
  const hex = normalized.slice(1)
  const expanded = hex.length === 3
    ? hex.split('').map(ch => ch + ch).join('')
    : hex.length === 6
      ? hex
      : hex.length === 8
        ? hex.slice(0, 6)
        : null
  if (!expanded) return normalized
  const alpha = Math.max(0, Math.min(255, Math.round(opacity * 255)))
  return `#${expanded}${alpha.toString(16).padStart(2, '0')}`
}

function mergeRoles(left: string[] | undefined, role: string | null | undefined) {
  const next = new Set(left ?? [])
  if (role) next.add(role)
  return [...next]
}

export function buildRadarIndicatorOverlays(
  detections: RadarDetection[],
  focusedId: number | null,
): RadarIndicatorVisual[] {
  const merged = new Map<string, RadarIndicatorVisual & { __opacity: number; __roles: string[] }>()
  const hasFocused = focusedId != null && detections.some(detection => detection.id === focusedId)

  for (const detection of detections) {
    const opacity = !hasFocused || detection.id === focusedId ? 1 : 0.24
    for (const visual of detection.evidence?.indicator_visuals ?? []) {
      const signature = radarIndicatorSignature(visual)
      const existing = merged.get(signature)
      if (existing) {
        existing.__opacity = Math.max(existing.__opacity, opacity)
        existing.__roles = mergeRoles(existing.__roles, visual.role)
        if (!existing.label && visual.label) existing.label = visual.label
        continue
      }
      merged.set(signature, {
        ...visual,
        style: {
          ...visual.style,
          color: applyOpacityToHex(visual.style?.color, opacity) ?? visual.style?.color,
        },
        __opacity: opacity,
        __roles: mergeRoles([], visual.role),
      })
    }
  }

  return [...merged.values()].map(({ __opacity: _opacity, __roles: _roles, ...visual }) => visual)
}

export function buildRadarDrawingOverlays(
  detections: RadarDetection[],
  focusedId: number | null,
): RadarDrawingVisual[] {
  const merged = new Map<string, RadarDrawingVisual & { __opacity: number; __roles: string[] }>()
  const hasFocused = focusedId != null && detections.some(detection => detection.id === focusedId)

  for (const detection of detections) {
    const opacity = !hasFocused || detection.id === focusedId ? 1 : 0.24
    for (const visual of detection.evidence?.drawing_visuals ?? []) {
      const signature = radarDrawingSignature(visual)
      const existing = merged.get(signature)
      if (existing) {
        existing.__opacity = Math.max(existing.__opacity, opacity)
        existing.__roles = mergeRoles(existing.__roles, visual.source_role)
        if (!existing.label && visual.label) existing.label = visual.label
        continue
      }
      merged.set(signature, {
        ...visual,
        style: {
          ...visual.style,
          color: applyOpacityToHex(visual.style?.color, opacity) ?? visual.style?.color,
          opacity: visual.style?.opacity != null ? Math.max(visual.style.opacity, opacity) : opacity,
        } as DrawingStyle,
        __opacity: opacity,
        __roles: mergeRoles([], visual.source_role),
      })
    }
  }

  return [...merged.values()].map(({ __opacity: _opacity, __roles: _roles, ...visual }) => visual)
}

export function mergeChartIndicatorsWithRadar(
  userIndicators: IndicatorConfig[],
  radarIndicators: RadarIndicatorVisual[],
): ResolvedRadarIndicator[] {
  const merged = userIndicators.map(indicator => ({ ...indicator })) as ResolvedRadarIndicator[]
  const bySignature = new Map<string, ResolvedRadarIndicator>()
  for (const indicator of merged) {
    bySignature.set(radarIndicatorSignature(indicator), indicator)
  }

  for (const visual of radarIndicators) {
    const signature = radarIndicatorSignature(visual)
    const existing = bySignature.get(signature)
    if (existing) {
      existing.__radarSource = 'reuse'
      existing.__radarHighlightOpacity = Math.max(existing.__radarHighlightOpacity ?? 0, 1)
      existing.__radarRoles = mergeRoles(existing.__radarRoles, visual.role)
      existing.__radarLabel = visual.label ?? existing.__radarLabel ?? null
      continue
    }
    const overlay: ResolvedRadarIndicator = {
      type: visual.type,
      params: visual.params,
      style: visual.style,
      pane: visual.pane ?? 'main',
      __radarSource: 'overlay',
      __radarHighlightOpacity: 1,
      __radarRoles: mergeRoles([], visual.role),
      __radarLabel: visual.label ?? null,
    }
    merged.push(overlay)
    bySignature.set(signature, overlay)
  }

  return merged
}

export function mergeChartDrawingsWithRadar(
  userDrawings: ChartDrawing[],
  radarDrawings: RadarDrawingVisual[],
  options: {
    instrumentId: number | null
    timeframe: Timeframe | null
  },
): ResolvedRadarDrawing[] {
  const { instrumentId, timeframe } = options
  const merged = userDrawings.map(drawing => ({ ...drawing })) as ResolvedRadarDrawing[]
  const bySignature = new Map<string, ResolvedRadarDrawing>()
  for (const drawing of merged) {
    bySignature.set(radarDrawingSignature(drawing), drawing)
  }

  let syntheticId = -1
  for (const visual of radarDrawings) {
    const signature = radarDrawingSignature(visual)
    const existing = bySignature.get(signature)
    if (existing) {
      existing.__radarSource = 'reuse'
      existing.__radarHighlightOpacity = Math.max(existing.__radarHighlightOpacity ?? 0, 1)
      existing.__radarRoles = mergeRoles(existing.__radarRoles, visual.source_role)
      existing.__radarSourceTag = visual.source_tag ?? existing.__radarSourceTag ?? 'radar'
      existing.sourceTag = existing.__radarSourceTag
      existing.radarLinked = true
      existing.radarHighlightOpacity = existing.__radarHighlightOpacity
      existing.radarRoles = existing.__radarRoles
      continue
    }
    const overlay: ResolvedRadarDrawing = {
      id: syntheticId--,
      instrument_id: instrumentId ?? 0,
      timeframe: timeframe ?? undefined,
      pin_to_all: false,
      indicator_key: visual.indicator_key ?? null,
      drawing_type: visual.drawing_type,
      label: visual.label ?? undefined,
      notes: visual.notes ?? undefined,
      data: visual.data,
      style: visual.style,
      is_visible: visual.is_visible,
      is_locked: true,
      position: 0,
      created_at: '',
      updated_at: '',
      __radarSource: 'overlay',
      __radarHighlightOpacity: 1,
      __radarRoles: mergeRoles([], visual.source_role),
      __radarSourceTag: visual.source_tag ?? 'radar',
      sourceTag: visual.source_tag ?? 'radar',
      radarLinked: true,
      radarHighlightOpacity: 1,
      radarRoles: mergeRoles([], visual.source_role),
    }
    merged.push(overlay)
    bySignature.set(signature, overlay)
  }

  return merged
}
