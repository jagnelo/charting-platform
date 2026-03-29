const FALLBACK_SYMBOLS: Record<string, string> = {
  USD: '$',
  EUR: '€',
  GBP: '£',
  JPY: '¥',
  CHF: 'CHF',
  CAD: 'CA$',
  AUD: 'A$',
  NZD: 'NZ$',
}

export function formatMoney(
  value: number | null | undefined,
  currency?: string | null,
  fractionDigits = 4,
): string {
  if (value == null || Number.isNaN(value)) return '—'
  const code = currency?.trim().toUpperCase()
  if (!code) return value.toFixed(fractionDigits)

  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: code,
      currencyDisplay: 'narrowSymbol',
      minimumFractionDigits: fractionDigits,
      maximumFractionDigits: fractionDigits,
    }).format(value)
  } catch {
    const symbol = FALLBACK_SYMBOLS[code] ?? code
    return `${symbol} ${value.toFixed(fractionDigits)}`
  }
}