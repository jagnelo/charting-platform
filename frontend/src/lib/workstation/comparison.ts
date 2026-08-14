import type { ChartComparisonSeries, OHLCVBar } from '@/types'

export interface ComparisonTarget {
  symbol: string
  label: string
  color: string
  bars: OHLCVBar[]
}

function timestampKey(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value > 10_000_000_000 ? value / 1000 : value
  if (typeof value !== 'string' || !value.trim()) return null
  const numeric = Number(value)
  if (Number.isFinite(numeric)) return numeric > 10_000_000_000 ? numeric / 1000 : numeric
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed / 1000 : null
}

/** Build normalized, timestamp-aligned comparison series for a uPlot chart. */
export function buildNormalizedComparisonSeries(mainBars: OHLCVBar[], targets: ComparisonTarget[]): ChartComparisonSeries[] {
  const mainAnchor = mainBars.find(bar => Number.isFinite(bar.close) && bar.close > 0)?.close ?? null
  if (!mainBars.length || mainAnchor == null) return []
  return targets.map(target => {
    const byTimestamp = new Map<number, number>()
    target.bars.forEach(bar => {
      const key = timestampKey(bar.ts)
      if (key != null && Number.isFinite(bar.close)) byTimestamp.set(key, bar.close)
    })
    const aligned = mainBars.map(bar => {
      const key = timestampKey(bar.ts)
      return key == null ? null : byTimestamp.get(key) ?? null
    })
    const compareAnchor = aligned.find(value => value != null && Number.isFinite(value) && value > 0) ?? null
    const values = compareAnchor == null
      ? mainBars.map(() => null)
      : aligned.map(value => value != null && Number.isFinite(value) ? mainAnchor * (value / compareAnchor) : null)
    const last = [...aligned].reverse().find(value => value != null && Number.isFinite(value) && value > 0) ?? null
    return {
      symbol: target.symbol,
      label: target.label,
      color: target.color,
      values,
      percentChange: compareAnchor != null && last != null ? ((last - compareAnchor) / compareAnchor) * 100 : null,
    }
  })
}
