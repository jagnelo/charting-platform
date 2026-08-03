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
