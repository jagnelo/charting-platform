export type MarketMapAccessibilityInput = {
  sourceName: string
  period: string
  timeframe: string
  adjustment: string
  areaMetric: string
  colorMetric: string
  freshness: string
  requestedCount: number
  evaluatedCount: number
  coverage: number
  colorCoverage?: number | null
  areaCoverage?: number | null
  visibleCount: number
  groupCount: number
  selectedCount: number
  warningCount: number
  exclusionCount: number
}

function percent(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? 'unknown' : `${Math.round(value * 100)}%`
}

/** Describe a canvas map without duplicating every tile in the accessibility tree. */
export function describeMarketMap(input: MarketMapAccessibilityInput): string {
  const coverage = `coverage ${percent(input.coverage)} (${input.evaluatedCount} of ${input.requestedCount} evaluated)`
  const metrics = `${input.colorMetric.replace(/_/g, ' ')} colour by ${input.areaMetric.replace(/_/g, ' ')} area`
  const scope = `${input.visibleCount} visible member${input.visibleCount === 1 ? '' : 's'} in ${input.groupCount} group${input.groupCount === 1 ? '' : 's'}`
  const disclosures = [
    `colour coverage ${percent(input.colorCoverage)}`,
    `area coverage ${percent(input.areaCoverage)}`,
    `${input.warningCount} warning${input.warningCount === 1 ? '' : 's'}`,
    `${input.exclusionCount} exclusion${input.exclusionCount === 1 ? '' : 's'}`,
  ].join(', ')
  return `${input.sourceName} market map for ${input.period} ${input.timeframe}, ${input.adjustment.replace(/_/g, ' ')}; ${metrics}; ${scope}; ${coverage}; freshness ${input.freshness}; ${disclosures}; ${input.selectedCount} selected.`
}
