export function autoRatioExpression(
  symbol: string,
  sectorSymbols: readonly string[],
  constituentETF?: string | null,
): string {
  const numerator = symbol.trim().toUpperCase()
  if (!numerator) return '=SPY/RSP'
  if (numerator === 'SPY') return '=SPY/RSP'
  if (numerator === 'RSP') return '=RSP/SPY'
  if (sectorSymbols.some(value => value.trim().toUpperCase() === numerator)) return `=${numerator}/SPY`
  const denominator = constituentETF?.trim().toUpperCase() || 'SPY'
  return `=${numerator}/${denominator}`
}

/**
 * Return the benchmark legs needed to render the automatic relative-strength
 * comparison for the active symbol.  The ratio chart accepts a numerator and
 * one or more benchmark symbols, so this keeps the product-level defaults in
 * one place and avoids self-referential ratios such as SPY/SPY.
 */
export function autoRatioBenchmarks(
  symbol: string,
  sectorSymbols: readonly string[],
  constituentETF?: string | null,
): string[] {
  const numerator = symbol.trim().toUpperCase()
  const expression = autoRatioExpression(numerator, sectorSymbols, constituentETF)
  const match = expression.match(/^=([^/]+)\/([^/]+)$/)
  const parsedDenominator = match?.[2]?.trim().toUpperCase() || 'SPY'
  const denominator = parsedDenominator === numerator ? 'SPY' : parsedDenominator
  const benchmarks = [denominator]

  // Constituents need both their sector-relative and market-relative legs;
  // benchmark/sector symbols only need the primary denominator.  Never emit a
  // leg equal to the numerator because it produces a meaningless flat ratio.
  if (denominator !== 'SPY' && numerator !== 'SPY') benchmarks.push('SPY')
  return [...new Set(benchmarks.filter(benchmark => benchmark !== numerator))]
}
