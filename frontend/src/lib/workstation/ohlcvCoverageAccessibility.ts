export type OhlcvCoverageAccessibilityInput = {
  timeframe: string
  status: string
  barCount: number
  sourceLineage: string
  providerBarCount: number
  derivedBarCount: number
  unknownBarCount: number
  sourceTimeframes?: readonly string[]
  adjustmentMode: string
  factorStatus: string
  factorVersion?: string | null
}

/** Describe local OHLCV range evidence without claiming an unreported provider. */
export function describeOhlcvCoverage(input: OhlcvCoverageAccessibilityInput): string {
  const source = input.sourceLineage.replace(/_/g, ' ')
  const sourceTimeframes = input.sourceTimeframes?.length
    ? `; source timeframes ${input.sourceTimeframes.join(', ')}`
    : ''
  const factorVersion = input.factorVersion ? `; factor version ${input.factorVersion}` : ''
  return `${input.timeframe} ${input.status} local coverage: ${input.barCount} bars; ${source} (${input.providerBarCount} provider, ${input.derivedBarCount} derived, ${input.unknownBarCount} unknown); adjustment ${input.adjustmentMode.replace(/_/g, ' ')}; factor status ${input.factorStatus.replace(/_/g, ' ')}${factorVersion}${sourceTimeframes}.`
}
