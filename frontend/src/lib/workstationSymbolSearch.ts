export interface LocalInstrumentSearchOption {
  symbol: string
}

export const TICKER_DISCOVERY_DEBOUNCE_MS = 300

/** Keep ordinary search local unless a ticker-shaped query has no exact hit. */
export function shouldDiscoverTicker(
  query: string,
  localResults: readonly LocalInstrumentSearchOption[],
): boolean {
  const normalized = query.trim().toUpperCase()
  if (!/^[A-Z0-9][A-Z0-9.-]{0,14}$/.test(normalized)) return false
  return !localResults.some(result => result.symbol.trim().toUpperCase() === normalized)
}

export function scheduleTickerDiscovery(callback: () => void, delay = TICKER_DISCOVERY_DEBOUNCE_MS) {
  return setTimeout(callback, delay)
}

export function tickerDiscoveryMessage(status: 'complete' | 'partial' | 'held' | 'unavailable' | 'no_match', candidateCount: number) {
  if (candidateCount > 0) return `${candidateCount} matching ticker listing${candidateCount === 1 ? '' : 's'} found. Select one to verify its identity.`
  if (status === 'held') return 'Ticker availability check is currently held.'
  if (status === 'unavailable') return 'Ticker availability could not be checked right now.'
  if (status === 'no_match') return 'No matching ticker listing was found.'
  return 'No matching ticker listings were returned.'
}
