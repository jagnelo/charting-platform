import type { ChartComparisonSeries, OHLCVBar } from '@/types'

export interface ComparisonTarget {
  symbol: string
  label: string
  color: string
  bars: OHLCVBar[]
}

/** Build normalized, timestamp-aligned comparison series for a uPlot chart. */
export function buildNormalizedComparisonSeries(mainBars: OHLCVBar[], targets: ComparisonTarget[]): ChartComparisonSeries[] {
  const mainAnchor = mainBars.find(bar => Number.isFinite(bar.close) && bar.close > 0)?.close ?? null
  if (!mainBars.length || mainAnchor == null) return []
  return targets.map(target => {
    const byTimestamp = new Map(target.bars.map(bar => [bar.ts, bar.close]))
    const aligned = mainBars.map(bar => byTimestamp.get(bar.ts) ?? null)
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
