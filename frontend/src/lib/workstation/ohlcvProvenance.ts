import type { OHLCVBar } from '@/types'

function adjustmentLabel(bar: OHLCVBar): string {
  if (bar.is_adjusted === false) return 'raw'
  if (bar.is_adjusted === true) return 'adjusted'
  return 'adjustment unspecified'
}

/** Describe the lineage of one chartable OHLCV observation without inventing a provider. */
export function describeOhlcvBarProvenance(bar: OHLCVBar | null | undefined): string {
  if (!bar) return 'Bar provenance unavailable.'
  const adjustment = adjustmentLabel(bar)
  if (bar.is_derived === true) {
    const source = bar.source_timeframe ? ` from ${bar.source_timeframe}` : ''
    const method = bar.derivation_method ? ` via ${bar.derivation_method}` : ''
    const count = bar.source_bar_count != null ? ` using ${bar.source_bar_count} source bars` : ''
    return `Derived ${adjustment} data${source}${method}${count}.`
  }
  if (bar.is_derived === false) return `Provider-observed ${adjustment} data.`
  return `Chart data with ${adjustment} adjustment; source lineage unavailable.`
}

/** Summarize the loaded chart range for screen-reader users without changing pixels. */
export function summarizeOhlcvProvenance(
  bars: readonly OHLCVBar[],
  timeframe: string,
  chartType?: string,
): string {
  const typeLabel = chartType && chartType !== 'candles' ? ` ${chartType.replace(/_/g, ' ')}` : ''
  if (!bars.length) return `${timeframe}${typeLabel} chart; no OHLCV bars loaded.`

  const derived = bars.filter(bar => bar.is_derived === true).length
  const provider = bars.filter(bar => bar.is_derived === false).length
  const unknown = bars.length - derived - provider
  const lineage = derived > 0 && provider > 0
    ? 'mixed provider-observed and derived lineage'
    : derived > 0
      ? 'derived lineage'
      : provider > 0
        ? 'provider-observed lineage'
        : 'lineage unavailable'
  const adjustment = bars.every(bar => bar.is_adjusted === true)
    ? 'adjusted'
    : bars.every(bar => bar.is_adjusted === false)
      ? 'raw'
      : 'mixed adjustment'
  const unknownNote = unknown > 0 ? `, ${unknown} with unknown lineage` : ''
  return `${timeframe}${typeLabel} chart; ${bars.length} bars; ${adjustment}; ${lineage}${unknownNote}.`
}
