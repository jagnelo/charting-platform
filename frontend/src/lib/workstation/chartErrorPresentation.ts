/** Convert a known local-history ApiError message into useful chart copy. */
export function chartErrorPresentation(message: string | null | undefined): string {
  if (!message) return ''
  const apiError = /^API GET (\/ohlcv\/local\/[^\s→]+|\/baskets\/\d+\/ohlcv\/[^\s→]+) → (\d{3}):/i.exec(message)
  if (!apiError) return message

  const [, path, statusText] = apiError
  const basket = /^\/baskets\/\d+\/ohlcv\/([^/?]+)/i.exec(path)
  if (basket) {
    const timeframe = decodeURIComponent(basket[1]).toUpperCase()
    const status = Number(statusText)
    if (status === 404) return `No local ${timeframe} price history is available for this saved basket.`
    if (status === 401 || status === 403) return `Access to this saved basket's ${timeframe} price history is unavailable.`
    if (status >= 500) return `This saved basket's ${timeframe} price history is temporarily unavailable.`
    return `This saved basket's ${timeframe} price history could not be loaded (HTTP ${status}).`
  }
  const identity = /^\/ohlcv\/local\/([^/?]+)\/([^/?]+)/i.exec(path)
  if (!identity) return message
  const [, rawSymbol, rawTimeframe] = identity
  const symbol = decodeURIComponent(rawSymbol).toUpperCase()
  const timeframe = decodeURIComponent(rawTimeframe).toUpperCase()
  const status = Number(statusText)

  if (status === 404) return `No local ${timeframe} price history is available for ${symbol}.`
  if (status === 401 || status === 403) return `Access to local ${timeframe} price history for ${symbol} is unavailable.`
  if (status >= 500) return `Local ${timeframe} price history for ${symbol} is temporarily unavailable.`
  return `Local ${timeframe} price history for ${symbol} could not be loaded (HTTP ${status}).`
}
